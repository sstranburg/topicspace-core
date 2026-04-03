#!/usr/bin/env python3
"""
Earnings call transcript → narrative signals.

Segments a transcript, extracts themes/tone/pressure/forward signals via Claude,
saves structured JSON, and integrates events into the Storm pipeline.

Usage:
    python scripts/extract_transcript_signals.py \\
        --transcript earnings/NVDA_2026-02-26.txt \\
        --actor NVDA \\
        --date 2026-02-26

    # Extract only, skip JSONL integration:
    python scripts/extract_transcript_signals.py \\
        --transcript earnings/NVDA_2026-02-26.txt \\
        --actor NVDA \\
        --date 2026-02-26 \\
        --no-integrate

    # Use a faster/cheaper model:
    python scripts/extract_transcript_signals.py ... --model gpt-4o-mini

Output:
    data/derived/transcript_signals/{ACTOR}_{DATE}.json  — structured signals
    data/normalized/tech_ecosystem.jsonl                 — new events appended
"""

import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import argparse
import hashlib
import json
import os
import textwrap
from pathlib import Path

from openai import OpenAI

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

from src.actors import detect_actors, detect_tags
from src.narrative_lane import classify_narrative_lane

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).resolve().parent.parent
SIGNALS_DIR  = BASE_DIR / 'data' / 'derived' / 'transcript_signals'
EVENTS_FILE  = BASE_DIR / 'data' / 'normalized' / 'tech_ecosystem.jsonl'
EARNINGS_DIR = BASE_DIR / 'earnings'

SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
EARNINGS_DIR.mkdir(parents=True, exist_ok=True)

# ── Claude prompt ──────────────────────────────────────────────────────────────
_SYSTEM = (
    "You are a financial narrative analyst specializing in AI and semiconductor "
    "earnings calls. Extract structured narrative signals from transcripts. "
    "Return only valid JSON — no markdown, no explanation, no preamble."
)

_EXTRACT = """\
Analyze this earnings call transcript for {actor} ({date}).

TRANSCRIPT:
{transcript}

Return this exact JSON structure — fill every field:

{{
  "actor": "{actor}",
  "date": "{date}",
  "segments": {{
    "management_remarks_summary": "2–3 sentence summary of prepared remarks",
    "analyst_qa_summary": "2–3 sentence summary of Q&A dynamics and pressure points"
  }},
  "themes": [
    {{
      "label": "2–4 word theme label",
      "summary": "one sentence on what management said",
      "tone": "positive|neutral|negative"
    }}
  ],
  "management_tone": "confident|cautious|defensive|uncertain",
  "analyst_pressure": "high|medium|low",
  "pressure_topics": ["repeated or challenged topic 1", "topic 2"],
  "forward_signals": [
    {{
      "statement": "exact or close paraphrase of forward-looking statement",
      "direction": "raise|maintain|cut|uncertain"
    }}
  ],
  "confidence_score": 0.0
}}

Rules:
- themes: 3–5 items, ordered by narrative importance
- forward_signals: 2–5 items, prefer specific over vague
- confidence_score: 0.0–1.0 based on guidance specificity + management directness
- analyst_pressure: high = repeated follow-ups or explicit skepticism; low = soft questions
"""


# ── Extraction ─────────────────────────────────────────────────────────────────
def _clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'):
            raw = raw[4:]
    return raw.strip()


def extract_signals(transcript: str, actor: str, date: str, model: str) -> dict:
    """Send transcript to OpenAI, return parsed signal dict."""
    prompt = _EXTRACT.format(
        actor=actor,
        date=date,
        transcript=transcript[:50_000],
    )

    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    resp = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        messages=[
            {'role': 'system', 'content': _SYSTEM},
            {'role': 'user',   'content': prompt},
        ],
    )
    raw = resp.choices[0].message.content

    return json.loads(_clean_json(raw))


# ── Narrative strength scoring ───────────────────────────────────────────────────
_TONE_SCORE: dict[str, float] = {
    'confident': 1.00, 'optimistic': 0.85,
    'neutral':   0.50,
    'cautious':  0.30, 'defensive': 0.15, 'uncertain': 0.15,
}
_PRESSURE_SCORE: dict[str, float] = {'low': 1.0, 'medium': 0.5, 'high': 0.0}


def _compute_internal_strength(signals: dict) -> float:
    """Score company narrative strength 0–1 from transcript signals.

    Weights: tone 35% | guidance direction 30% | thematic confidence 20% | pressure (inv) 15%
    """
    tone    = (signals.get('management_tone') or 'neutral').lower()
    tone_s  = _TONE_SCORE.get(tone, 0.50)

    fwd      = signals.get('forward_signals', [])
    n_raises = sum(1 for f in fwd if f.get('direction') == 'raise')
    n_cuts   = sum(1 for f in fwd if f.get('direction') == 'cut')
    guidance_s = min(1.0, max(0.0, 0.5 + 0.15 * n_raises - 0.25 * n_cuts))

    themes  = signals.get('themes', [])
    n_pos   = sum(1 for t in themes if t.get('tone') == 'positive')
    n_neg   = sum(1 for t in themes if t.get('tone') in ('negative', 'cautious'))
    theme_s = min(1.0, max(0.0, (n_pos - 0.5 * n_neg) / max(len(themes), 1)))

    pressure   = (signals.get('analyst_pressure') or 'medium').lower()
    pressure_s = _PRESSURE_SCORE.get(pressure, 0.5)

    return round(
        0.35 * tone_s + 0.30 * guidance_s + 0.20 * theme_s + 0.15 * pressure_s,
        3,
    )


def _compute_external_strength(eco: dict) -> float:
    """Score ecosystem narrative strength 0–1 from trajectory snapshot.

    Weights: peak_ratio 35% | acceleration 30% | persistence 20% | density 15%
    """
    peak_ratio = float(eco.get('peak_ratio', 0) or 0)

    accel   = float(eco.get('acceleration', 0) or 0)
    accel_s = min(1.0, max(0.0, (accel + 200) / 400))   # maps [-200, +200] → [0, 1]

    consec    = int(eco.get('consec_decline', 0) or 0)
    persist_s = max(0.0, 1.0 - 0.25 * consec)

    density   = min(int(eco.get('density', 0) or 0), 50) / 50  # cap at 50

    return round(
        0.35 * peak_ratio + 0.30 * accel_s + 0.20 * persist_s + 0.15 * density,
        3,
    )


# ── Cross-signal comparison ─────────────────────────────────────────────────────
def _load_ecosystem_at_date(actor: str, date: str) -> dict | None:
    """Load the ecosystem window closest to (and not after) transcript date.

    Collects all metric windows across all trajectory records for actor,
    picks the window whose window_start is latest but ≤ date.  Falls back
    to the earliest available window when the transcript predates all data,
    marking the result with `extrapolated=True`.

    Returns a dict with fields matching what cross_signal_comparison expects:
        state, latest_acceleration, latest_density, peak_ratio,
        state_history, window_date, extrapolated
    """
    traj_file = BASE_DIR / 'data' / 'derived' / 'storm_trajectories.jsonl'
    if not traj_file.exists():
        return None

    # Gather every (window, parent_trajectory) pair for this actor
    all_windows: list[tuple[dict, dict]] = []
    with open(traj_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            if t.get('actor') != actor:
                continue
            for w in t.get('metrics', []):
                all_windows.append((w, t))

    if not all_windows:
        return None

    # Sort by window_start ascending
    all_windows.sort(key=lambda x: x[0]['window_start'])

    # Split: windows at-or-before date vs windows after
    target    = date  # YYYY-MM-DD, comparable as string (ISO format)
    before    = [(w, t) for w, t in all_windows if w['window_start'][:10] <= target]
    after     = [(w, t) for w, t in all_windows if w['window_start'][:10] >  target]

    if before:
        w, traj  = before[-1]          # latest window not after transcript date
        extrapolated = False
    else:
        # Transcript predates all available data — use highest-signal window
        # (highest |momentum|) as the best available proxy rather than the
        # arbitrary earliest window which may be an uninitialised "stable" state.
        w, traj  = max(all_windows, key=lambda x: abs(x[0].get('momentum', 0) or 0))
        extrapolated = True

    # Reconstruct acceleration: momentum delta within the window
    accel = int(w.get('momentum', 0) or 0) - int(w.get('previous_momentum') or 0)

    # Reconstruct state_history: states of all windows up to and including w
    matched_start = w['window_start']
    state_history = [
        x['state'] for x, _ in all_windows
        if x['window_start'] <= matched_start
    ]

    return {
        'state':              w.get('state', 'unknown'),
        'latest_acceleration': accel,
        'latest_density':     w.get('density', 0),
        'peak_ratio':         w.get('peak_ratio', 1.0),
        'state_history':      state_history,
        'window_date':        w['window_start'][:10],
        'extrapolated':       extrapolated,
    }


def _load_prior_classifications(actor: str, before_date: str) -> list[str]:
    """Return classifications from all prior transcript signal files for actor.

    Scans data/derived/transcript_signals/ for {ACTOR}_{DATE}.json files
    with DATE < before_date, returns classifications sorted oldest-first.
    """
    sig_dir = BASE_DIR / 'data' / 'derived' / 'transcript_signals'
    if not sig_dir.exists():
        return []
    prior = []
    for path in sorted(sig_dir.glob(f'{actor}_*.json')):
        date_str = path.stem[len(actor) + 1:]
        if date_str >= before_date:
            continue
        try:
            data = json.loads(path.read_text())
            cls = data.get('cross_signal', {}).get('classification')
            if cls:
                prior.append((date_str, cls))
        except Exception:
            continue
    prior.sort()
    return [cls for _, cls in prior]


def _persistence_suffix(classification: str, prior: list[str]) -> str:
    """Return persistence qualifier based on how many prior periods match."""
    matching = sum(1 for c in prior if c == classification)
    if matching >= 1:
        total = matching + 1  # prior + current
        return f'Sustained {classification.lower()} ({total}+ periods)'
    return f'Early {classification.lower()}'


def cross_signal_comparison(signals: dict, actor: str, date: str = '') -> dict:
    """Compare transcript signals against current ecosystem trajectory.

    Returns a dict with:
      classification — canonical 4-way label:
                       "Reinforced"  — company strong, ecosystem strong
                       "Diverging"   — company strong, ecosystem weakening
                       "Breakdown"   — company weak, ecosystem weak
                       "Formation"   — company neutral/weak, ecosystem strengthening
      persistence    — "Early <class>" or "Sustained <class> (N+ periods)"
      label         — one-line summary: "{ACTOR} — {Persistence} ({reason})"
      insight       — non-obvious observation drawn from the divergence or alignment
      ecosystem     — raw ecosystem snapshot for reference
    """
    eco = _load_ecosystem_at_date(actor, date)
    if eco is None:
        return {
            'classification': 'Unknown',
            'label':          f'{actor} — Unknown narrative (no ecosystem data)',
            'insight':        'No ecosystem data available for comparison.',
            'ecosystem':      None,
        }

    # ── Ecosystem signals ──
    eco_state     = eco.get('state', 'unknown')
    eco_accel     = eco.get('latest_acceleration', 0) or 0
    eco_density   = eco.get('latest_density', 0) or 0
    peak_ratio    = eco.get('peak_ratio', 1.0) or 1.0
    state_history = eco.get('state_history', [])

    _DECLINING = {'fading', 'cooling', 'collapse', 'volatile'}
    consec_decline = 0
    for s in reversed(state_history):
        if s in _DECLINING:
            consec_decline += 1
        else:
            break

    eco_strong = eco_state in {'growing', 'peaking', 'leading', 'emerging'}
    eco_weak   = eco_state in _DECLINING
    # "strengthening" = positive acceleration even if state not yet strong
    eco_strengthening = eco_accel > 0 and not eco_weak

    # ── Transcript signals ──
    tone         = signals.get('management_tone', 'uncertain')
    pressure     = signals.get('analyst_pressure', 'low')
    n_raises     = sum(1 for f in signals.get('forward_signals', []) if f.get('direction') == 'raise')
    n_cuts       = sum(1 for f in signals.get('forward_signals', []) if f.get('direction') == 'cut')
    n_pos_themes = sum(1 for t in signals.get('themes', []) if t.get('tone') == 'positive')

    tx_strong = tone == 'confident' and n_raises >= 1 and n_pos_themes >= 2
    tx_weak   = tone in ('cautious', 'defensive', 'uncertain') or n_cuts >= 1
    # neutral = neither clearly strong nor clearly weak

    # ── 4-way classification ──
    if tx_strong and (eco_strong or eco_strengthening):
        classification = 'Reinforced'
        reason  = 'company strong, ecosystem strong'
        insight = (
            f"{actor} management confidence aligns with positive ecosystem momentum "
            f"(state={eco_state}, accel={eco_accel:+d}). "
            f"Both internal and external signals reinforce the same narrative — "
            f"low divergence risk near-term."
        )

    elif tx_strong and eco_weak:
        classification = 'Diverging'
        reason  = 'company strong, ecosystem weakening'
        if peak_ratio < 0.15:
            insight = (
                f"{actor} management is raising guidance and projecting confidence, "
                f"but external narrative momentum is at {peak_ratio:.0%} of its all-time peak "
                f"with {consec_decline} consecutive declining window(s). "
                f"The company narrative has not yet absorbed the system-level deterioration."
            )
        else:
            insight = (
                f"{actor} tone is confident and guidance raised, "
                f"but ecosystem momentum has turned negative (accel={eco_accel:+d}). "
                f"The gap between management framing and external signal is widening — "
                f"watch for narrative correction in the next 1–2 windows."
            )

    elif tx_weak and eco_weak:
        classification = 'Breakdown'
        reason  = 'company weak, ecosystem weak'
        insight = (
            f"{actor} management tone ({tone}) is consistent with ecosystem weakening "
            f"(state={eco_state}, accel={eco_accel:+d}, {consec_decline} consecutive declines). "
            f"Both channels are signaling the same direction — this is acknowledged deterioration, "
            f"not a hidden crack."
        )

    elif (not tx_strong) and eco_strengthening:
        classification = 'Formation'
        reason  = 'company neutral/weak, ecosystem strengthening'
        insight = (
            f"{actor} management is {tone} while ecosystem momentum is turning positive "
            f"(state={eco_state}, accel={eco_accel:+d}). "
            f"External signals are ahead of company framing — "
            f"watch for management to catch up in the next 1–2 cycles."
        )

    elif tx_weak and eco_strong:
        # Internal caution ahead of still-strong external — early warning
        classification = 'Diverging'
        reason  = 'company cautious, ecosystem still strong'
        insight = (
            f"{actor} management is {tone} while ecosystem momentum remains positive "
            f"(state={eco_state}, accel={eco_accel:+d}). "
            f"Internal caution ahead of still-strong external signals is an early warning — "
            f"the ecosystem has not yet priced in what management is signaling."
        )

    else:
        classification = 'Diverging' if (pressure == 'high' or consec_decline >= 2) else 'Reinforced'
        reason  = f'mixed signals (tone={tone}, eco={eco_state})'
        insight = (
            f"{actor} transcript and ecosystem signals are mixed. "
            f"Management tone is {tone} while ecosystem is {eco_state} (accel={eco_accel:+d}). "
            f"No clear dominant signal — watch next window for resolution."
        )

    prior = _load_prior_classifications(actor, before_date=date)
    persistence = _persistence_suffix(classification, prior)

    eco_snapshot = {
        'state':          eco_state,
        'acceleration':   eco_accel,
        'density':        eco_density,
        'peak_ratio':     round(peak_ratio, 3),
        'consec_decline': consec_decline,
        'window_date':    eco.get('window_date'),
        'extrapolated':   eco.get('extrapolated', False),
    }
    internal_strength = _compute_internal_strength(signals)
    external_strength = _compute_external_strength(eco_snapshot)
    alignment_gap     = round(internal_strength - external_strength, 3)

    return {
        'classification':    classification,
        'persistence':       persistence,
        'label':             f'{actor} — {persistence} ({reason})',
        'internal_strength': internal_strength,
        'external_strength': external_strength,
        'alignment_gap':     alignment_gap,
        'insight':           insight,
        'ecosystem':         eco_snapshot,
    }


# ── Event conversion ────────────────────────────────────────────────────────────
def _make_id(*parts: str) -> str:
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:16]


def signals_to_events(signals: dict, actor: str, date: str) -> list[dict]:
    """Convert structured signals into Event dicts for Storm integration."""
    ts = f'{date}T13:30:00+00:00'   # earnings calls typically 9:30am ET = 13:30 UTC
    base_meta = {
        'transcript_date':  date,
        'management_tone':  signals.get('management_tone'),
        'analyst_pressure': signals.get('analyst_pressure'),
        'confidence_score': signals.get('confidence_score', 0.0),
    }
    events = []

    # Theme events — one per theme
    for theme in signals.get('themes', []):
        text = (
            f"{actor} earnings call: {theme['label']}. "
            f"{theme['summary']} "
            f"Management tone: {signals.get('management_tone', 'unknown')}."
        )
        actors = detect_actors(text)
        if actor not in actors:
            actors = sorted(set(actors + [actor]))
        events.append({
            'event_id':       _make_id(ts, actor, 'theme', theme['label']),
            'timestamp':      ts,
            'source':         'transcript',
            'title':          f"{actor} — {theme['label']} ({signals.get('management_tone', '?')})",
            'text':           text,
            'url':            None,
            'actors':         actors,
            'tags':           detect_tags(text),
            'narrative_lane': classify_narrative_lane(text),
            'reliability':    0.90,
            'metadata':       {**base_meta, 'signal_type': 'theme', 'theme_tone': theme['tone']},
        })

    # Forward signal events — one per signal
    for fwd in signals.get('forward_signals', []):
        text = f"{actor} forward guidance ({fwd['direction']}): {fwd['statement']}"
        actors = detect_actors(text)
        if actor not in actors:
            actors = sorted(set(actors + [actor]))
        events.append({
            'event_id':       _make_id(ts, actor, 'fwd', fwd['statement'][:60]),
            'timestamp':      ts,
            'source':         'transcript',
            'title':          f"{actor} guidance — {fwd['direction']}",
            'text':           text,
            'url':            None,
            'actors':         actors,
            'tags':           detect_tags(text),
            'narrative_lane': classify_narrative_lane(text),
            'reliability':    0.92,   # direct statement — slightly higher weight
            'metadata':       {**base_meta, 'signal_type': 'forward_signal', 'direction': fwd['direction']},
        })

    # Analyst pressure event — single summary event if pressure is high/medium
    pressure = signals.get('analyst_pressure', 'low')
    if pressure in ('high', 'medium'):
        topics = ', '.join(signals.get('pressure_topics', []))
        text = (
            f"{actor} earnings: analysts pushed back on {topics}. "
            f"Pressure level: {pressure}. "
            f"{signals['segments'].get('analyst_qa_summary', '')}"
        )
        actors = detect_actors(text)
        if actor not in actors:
            actors = sorted(set(actors + [actor]))
        events.append({
            'event_id':       _make_id(ts, actor, 'pressure', pressure),
            'timestamp':      ts,
            'source':         'transcript',
            'title':          f"{actor} — analyst pressure ({pressure}): {topics[:60]}",
            'text':           text,
            'url':            None,
            'actors':         actors,
            'tags':           detect_tags(text),
            'narrative_lane': 'market',
            'reliability':    0.88,
            'metadata':       {**base_meta, 'signal_type': 'analyst_pressure'},
        })

    return events


# ── JSONL integration ──────────────────────────────────────────────────────────
def append_events(events: list[dict]) -> int:
    """Append new events to tech_ecosystem.jsonl. Returns count of new events written."""
    existing_ids: set[str] = set()
    if EVENTS_FILE.exists():
        with open(EVENTS_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_ids.add(json.loads(line)['event_id'])
                    except Exception:
                        pass

    new_events = [e for e in events if e['event_id'] not in existing_ids]
    if new_events:
        with open(EVENTS_FILE, 'a') as f:
            for e in new_events:
                f.write(json.dumps(e) + '\n')
    return len(new_events)


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description='Extract narrative signals from earnings transcript')
    parser.add_argument('--transcript', required=True, help='Path to transcript .txt file')
    parser.add_argument('--actor',      required=True, help='Actor ticker (e.g. NVDA)')
    parser.add_argument('--date',       required=True, help='Call date YYYY-MM-DD')
    parser.add_argument('--model',      default='gpt-4o',
                        help='OpenAI model (default: gpt-4o)')
    parser.add_argument('--no-integrate', action='store_true',
                        help='Skip appending events to tech_ecosystem.jsonl')
    args = parser.parse_args()

    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        print(f"Error: transcript file not found: {transcript_path}")
        sys.exit(1)

    transcript = transcript_path.read_text(encoding='utf-8')
    actor = args.actor.upper()
    date  = args.date

    print(f"\nTranscript signal extraction: {actor} {date}")
    print(f"Model:  {args.model}")
    print(f"Length: {len(transcript):,} chars\n")

    # ── Extract ──
    signals = extract_signals(transcript, actor, date, args.model)

    # ── Cross-signal comparison ──
    comparison = cross_signal_comparison(signals, actor, date)
    signals['cross_signal'] = comparison

    # ── Save signals JSON ──
    out_path = SIGNALS_DIR / f'{actor}_{date}.json'
    out_path.write_text(json.dumps(signals, indent=2))
    print(f"Signals → {out_path}\n")

    # ── Print summary ──
    print(f"Management tone:   {signals.get('management_tone', '?').upper()}")
    print(f"Analyst pressure:  {signals.get('analyst_pressure', '?').upper()}")
    if signals.get('pressure_topics'):
        print(f"Pressure topics:   {', '.join(signals['pressure_topics'])}")
    print(f"Confidence score:  {signals.get('confidence_score', 0):.2f}")

    print(f"\nThemes ({len(signals.get('themes', []))}):")
    for t in signals.get('themes', []):
        print(f"  [{t['tone']:8}] {t['label']}")
        print(f"             {t['summary']}")

    print(f"\nForward signals ({len(signals.get('forward_signals', []))}):")
    for fwd in signals.get('forward_signals', []):
        print(f"  [{fwd['direction']:10}] {fwd['statement']}")

    # ── Cross-signal insight ──
    eco = comparison.get('ecosystem') or {}
    print(f"\n{'─'*60}")
    print(f"CROSS-SIGNAL COMPARISON")
    print(f"{'─'*60}")
    print(f"Classification:  {comparison['label']}")
    if eco:
        extrap = '  [extrapolated — transcript predates ecosystem data]' if eco.get('extrapolated') else ''
        print(f"Ecosystem:       state={eco['state']}  accel={eco['acceleration']:+d}  "
              f"density={eco['density']}  peak={eco['peak_ratio']:.0%}  "
              f"consec_decline={eco['consec_decline']}  "
              f"window={eco.get('window_date', '?')}{extrap}")
    print(f"\nInsight:")
    # Word-wrap the insight at 70 chars
    for line in textwrap.wrap(comparison['insight'], width=70):
        print(f"  {line}")

    # ── Integrate ──
    if not args.no_integrate:
        events = signals_to_events(signals, actor, date)
        n = append_events(events)
        print(f"\nIntegrated: {n}/{len(events)} new events → {EVENTS_FILE.name}")
        if n > 0:
            print("Next: python scripts/embed_incremental.py")
    else:
        print('\n(--no-integrate: skipped JSONL append)')


if __name__ == '__main__':
    main()
