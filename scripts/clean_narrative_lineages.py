#!/usr/bin/env python3
"""
Clean and consolidate narrative lineages using an LLM.

Pipeline step: after generate_storm_summaries.py, before generate_master_report.py
Output: data/derived/cleaned_lineages.json

Only processes lineages with >= MIN_STORMS_TO_CLEAN storms.
Results are cached — re-run is a no-op unless --force is passed.
"""
import json
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from narrative_lineage import group_into_lineages
from storm_identity import (
    StormWindow, build_storms_from_windows,
    make_storm_display_name, canonicalize_phase_key,
)

# ── Config ────────────────────────────────────────────────────────────────────
MIN_STORMS_TO_CLEAN = 5
MODEL    = os.getenv('LLM_NAMING_MODEL', 'gpt-4o')
API_URL  = 'https://api.openai.com/v1/chat/completions'
API_KEY  = os.getenv('OPENAI_API_KEY')
OUTPUT_PATH = Path(__file__).parent.parent / 'data' / 'derived' / 'cleaned_lineages.json'

SYSTEM_PROMPT = """\
You are a narrative intelligence analyst.

Your task is to transform fragmented event clusters into coherent, high-signal
narrative structures suitable for a professional research note.

A narrative is NOT a list of events.
A narrative is a persistent idea that evolves over time.

You must:
1. Identify the underlying narrative (what is the story really about?)
2. Remove surface-level language (e.g. "developments", "announcements", "investments")
3. Replace generic phrasing with specific thematic meaning
4. Collapse redundant phases into meaningful narrative shifts
5. Ensure each phase reflects a CHANGE IN INTERPRETATION, not just activity

STRICT RULES:
- Do NOT use: "developments", "updates", "announcements", "activity", "changes", "news"
- Each phase must represent a DIFFERENT STATE of the narrative
  (e.g. emergence → expansion → consolidation → saturation)
- Narrative names must be conceptual, not descriptive:
    BAD:  "AI Chip Developments"
    GOOD: "AI Compute Supply Expansion"
- Prefer noun-based industry themes:
    compute, capacity, infrastructure, monetization,
    deployment, bottleneck, scaling, coupling, constraint
- Eliminate duplication aggressively — max 5 phases total
- Do NOT invent data or introduce actors not present in the input

Your output should read like a sharp research note, not a system log.\
"""

USER_PROMPT_TEMPLATE = """\
INPUT LINEAGE:
  Label:      {label}
  Actors:     {actors}
  Date range: {start} → {end}
  Storms:     {storm_count}

Storms (sorted by date):
{storm_list}

TASK:
1. Identify the TRUE narrative (not surface events)
2. Rename it using a conceptual label — specific, noun-based, no generic words
3. Collapse all redundant or similar phases
4. Produce ONLY 3–5 phases total
5. Each phase must represent a clear shift in narrative meaning

Respond with JSON only — no commentary outside the JSON. Schema:
{{
  "canonical_name": "Conceptual name (≤8 words, no generic words)",
  "actors": ["list of actors, most prominent first"],
  "summary": "2-3 sentence analyst explanation of what this narrative really represents",
  "narrative_type": "event_driven | structural | cyclical | persistent",
  "phases": [
    {{
      "phase_number": 1,
      "name": "Conceptual phase name (≤5 words, noun-based)",
      "date_range": "human-readable range e.g. 'late Jan – early Feb'",
      "description": "One sentence on what changed in narrative meaning",
      "key_actors": ["list"],
      "signal": "emergence | expansion | consolidation | saturation | contraction | inflection"
    }}
  ],
  "notes": "analyst interpretation note e.g. 'structural, not event-driven'"
}}\
"""


# ── Helpers ───────────────────────────────────────────────────────────────────
def _format_storm_list(storms):
    lines = []
    for s in sorted(storms, key=lambda x: x.get('created_at', '')):
        actor    = s.get('actor', '?')
        headline = s.get('display_headline') or s.get('headline') or '—'
        themes   = ', '.join((s.get('themes') or [])[:3])
        date     = (s.get('created_at') or '')[:10]
        state    = s.get('state', '?')
        events   = s.get('event_count', 0)
        lines.append(
            f"  [{date}] {actor:6s} | {headline[:70]:<70} | {themes:<30} | {state} | {events}ev"
        )
    return '\n'.join(lines)


def _call_llm(lineage_label, actor_set, storms):
    dates = [s.get('created_at', '') for s in storms if s.get('created_at')]
    start = min(dates)[:10] if dates else '?'
    end   = max(dates)[:10] if dates else '?'

    user_prompt = USER_PROMPT_TEMPLATE.format(
        label=lineage_label,
        actors=', '.join(sorted(actor_set)),
        start=start,
        end=end,
        storm_count=len(storms),
        storm_list=_format_storm_list(storms),
    )

    response = requests.post(
        API_URL,
        headers={
            'Authorization': f'Bearer {API_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'model': MODEL,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user',   'content': user_prompt},
            ],
            'response_format': {'type': 'json_object'},
            'temperature': 0.2,
        },
        timeout=120,
    )

    if response.status_code != 200:
        raise RuntimeError(f"API error {response.status_code}: {response.text[:200]}")

    content = response.json()['choices'][0]['message']['content']
    return json.loads(content)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    force = '--force' in sys.argv

    if not API_KEY:
        print('ERROR: OPENAI_API_KEY not set in environment or .env')
        sys.exit(1)

    # Load actor storms + summaries
    base = Path(__file__).parent.parent
    storms_raw = [json.loads(l) for l in open(base / 'data/derived/actor_storms.jsonl') if l.strip()]
    summaries  = {
        json.loads(l)['storm_id']: json.loads(l)
        for l in open(base / 'data/derived/actor_storm_summaries.jsonl') if l.strip()
    }
    for s in storms_raw:
        if s['storm_id'] in summaries:
            s.update(summaries[s['storm_id']])

    # Load ecosystem storms + summaries (needed so eco lineages are formed)
    eco_path = base / 'data/derived/ecosystem_storms.jsonl'
    eco_summaries_path = base / 'data/derived/ecosystem_storm_summaries.jsonl'
    eco_storms_raw = []
    if eco_path.exists():
        eco_raw = [json.loads(l) for l in open(eco_path) if l.strip()]
        eco_summaries = {}
        if eco_summaries_path.exists():
            eco_summaries = {
                json.loads(l)['storm_id']: json.loads(l)
                for l in open(eco_summaries_path) if l.strip()
            }
        for s in eco_raw:
            if s['storm_id'] in eco_summaries:
                s.update(eco_summaries[s['storm_id']])
            # Ensure `actor` field exists for downstream formatting
            if not s.get('actor'):
                dominant = s.get('dominant_actors') or s.get('actors') or []
                s['actor'] = dominant[0] if dominant else '?'
        eco_storms_raw = eco_raw

    all_storms = storms_raw + eco_storms_raw
    storms_with_ids, lineage_objs = group_into_lineages(all_storms)

    lineage_storms: dict[str, list] = {}
    for s in storms_with_ids:
        lid = s.get('lineage_id')
        if lid:
            lineage_storms.setdefault(lid, []).append(s)

    lineage_meta = {lin['lineage_id']: lin for lin in lineage_objs}

    existing: dict = {}
    if OUTPUT_PATH.exists() and not force:
        try:
            existing = json.loads(OUTPUT_PATH.read_text())
        except Exception:
            pass

    to_clean = sorted(
        [(lid, storms) for lid, storms in lineage_storms.items() if len(storms) >= MIN_STORMS_TO_CLEAN],
        key=lambda x: -len(x[1])
    )

    new_count = sum(1 for lid, _ in to_clean if lid not in existing or 'error' in existing[lid])
    print(f"Lineages to clean: {len(to_clean)} total, {new_count} new  (model: {MODEL})")

    results = dict(existing)

    for lid, storms in to_clean:
        cached = existing.get(lid, {})
        if cached and 'canonical_name' in cached and not force:
            print(f"  [{lid}] cached → {cached['canonical_name']}")
            continue

        meta      = lineage_meta.get(lid, {})
        label     = meta.get('lineage_label', lid)
        actor_set = set(meta.get('lineage_actor_set') or []) or {s.get('actor', '') for s in storms}

        print(f"  [{lid}] {label} ({len(storms)} storms, actors={sorted(actor_set)}) ...", flush=True)

        try:
            cleaned = _call_llm(label, actor_set, storms)
            results[lid] = {
                'lineage_id':           lid,
                'original_storm_count': len(storms),
                'original_label':       label,
                **cleaned,
            }
            print(f"    → {cleaned['canonical_name']} ({len(cleaned.get('phases', []))} phases, {cleaned.get('narrative_type', '?')})")
        except Exception as e:
            print(f"    ✗ Error: {e}")
            results[lid] = {'lineage_id': lid, 'error': str(e)}

        OUTPUT_PATH.write_text(json.dumps(results, indent=2))

    print(f"\nSaved → {OUTPUT_PATH}")
    print(f"Total cleaned lineages: {sum(1 for r in results.values() if 'canonical_name' in r)}")

    # Build and write per-storm canonical display names + cluster merge map
    display_names, storm_merges = _build_storm_display_names(lineage_storms, results)
    display_names_path = Path(__file__).parent.parent / 'data' / 'derived' / 'storm_display_names.json'
    display_names_path.write_text(json.dumps(display_names, indent=2))
    print(f"Storm display names → {display_names_path}  ({len(display_names)} storms mapped)")
    storm_merges_path = Path(__file__).parent.parent / 'data' / 'derived' / 'storm_merges.json'
    storm_merges_path.write_text(json.dumps(storm_merges, indent=2))
    clusters = len({v['storm_identity_key'] for v in storm_merges.values()})
    print(f"Storm merges        → {storm_merges_path}  ({len(storm_merges)} windows → {clusters} clusters)")


def _build_storm_display_names(lineage_storms: dict, results: dict) -> tuple[dict, dict]:
    """
    Map each storm_id → canonical display label using storm_identity.py.

    Converts raw storm dicts to StormWindow objects, runs build_storms_from_windows()
    (greedy chronological merge with time-gap + actor-overlap + cosine-similarity
    thresholds), then emits display_names and storm_merges from the resulting Storm
    entities.

    Returns:
        display_names  — storm_id → display label string  ("ACTOR — Phase")
        storm_merges   — storm_id → cluster metadata dict
    """
    display_names: dict[str, str]  = {}
    storm_merges:  dict[str, dict] = {}

    for lid, storms in lineage_storms.items():
        cl = results.get(lid, {})
        if 'canonical_name' not in cl or not cl.get('phases'):
            continue

        phases        = cl['phases']
        n_phases      = len(phases)
        sorted_storms = sorted(storms, key=lambda s: s.get('created_at', ''))
        n_storms      = len(sorted_storms)

        # Proportional chronological phase assignment (LLM phases → canonical keys)
        phase_assignments: dict[str, str] = {}
        for i, s in enumerate(sorted_storms):
            phase_idx = min(int(i * n_phases / n_storms), n_phases - 1)
            phase_assignments[s['storm_id']] = canonicalize_phase_key(phases[phase_idx]['name'])

        # Convert to StormWindow objects for the identity model
        windows: list[StormWindow] = []
        for s in sorted_storms:
            actor_ids = s.get('actor_ids') or s.get('actors') or [s.get('actor', '?')]
            if not isinstance(actor_ids, list):
                actor_ids = list(actor_ids)
            top_terms = (s.get('themes') or []) + (s.get('domain_phrases') or [])
            date_str  = (s.get('created_at') or '')[:10]
            windows.append(StormWindow(
                window_id   = s['storm_id'],
                lineage_id  = lid,
                phase_key   = phase_assignments[s['storm_id']],
                actor       = s.get('actor', '?'),
                actor_ids   = actor_ids,
                start_date  = date_str,
                end_date    = date_str,
                centroid    = s.get('centroid'),
                top_terms   = top_terms[:10],
                event_count = s.get('event_count', 0),
                coherence   = s.get('coherence'),
                gravity     = s.get('gravity_score'),
            ))

        # Merge windows into Storm entities using time-gap + cosine-similarity
        merged_storms = build_storms_from_windows(windows)

        for storm in merged_storms:
            label              = make_storm_display_name(storm)
            storm_identity_key = f"{storm.lineage_id}::{storm.actor}::{storm.phase_key}"
            rep_id             = storm.representative_id or storm.window_ids[0]
            for wid in storm.window_ids:
                display_names[wid] = label
                storm_merges[wid]  = {
                    'storm_identity_key': storm_identity_key,
                    'lineage_id':         storm.lineage_id,
                    'actor':              storm.actor,
                    'canonical_phase':    storm.phase_key,
                    'representative_id':  rep_id,
                    'window_ids':         storm.window_ids,
                    'window_count':       len(storm.window_ids),
                    'agg_event_count':    storm.event_count,
                    'start_date':         storm.start_date,
                    'end_date':           storm.end_date,
                }

    return display_names, storm_merges


if __name__ == '__main__':
    main()
