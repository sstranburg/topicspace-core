#!/usr/bin/env python3
"""
generate_actor_detail.py

For each actor in actors.json, uses OpenAI to generate:
  - interpretation: 1-line sharp analyst read
  - drivers: 2-3 bullets on what's driving narrative
  - events: 3-5 dated recent events
  - market_read: 2-3 sentences on narrative vs price
  - watch: 2-3 forward signals to watch

Writes: ../topicspace-site/public/actors_detail.json

Usage:
  venv/bin/python scripts/generate_actor_detail.py
  venv/bin/python scripts/generate_actor_detail.py --ticker NVDA
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

ROOT = Path(__file__).parent.parent
ACTORS_JSON        = ROOT.parent / "topicspace-site" / "public" / "actors.json"
SIGNALS_FILE       = ROOT.parent / "topicspace-site" / "public" / "signals" / "ai" / "latest.json"
PRESSURE_FILE      = ROOT / "data" / "derived" / "narrative_pressure.jsonl"
LEADERSHIP_FILE    = ROOT / "data" / "derived" / "narrative_leadership.json"
STORM_SUMMARY_FILE = ROOT / "data" / "derived" / "actor_storm_summaries.jsonl"
LINEAGES_FILE      = ROOT / "data" / "derived" / "cleaned_lineages.json"
PROPAGATION_FILE   = ROOT / "data" / "derived" / "propagation_chains.json"
EVENTS_FILE        = ROOT / "data" / "normalized" / "tech_ecosystem_filtered.jsonl"
OUTPUT_FILE        = ROOT.parent / "topicspace-site" / "public" / "actors_detail.json"

# Canonical read → human-readable phrasing (single source of truth)
# Must stay in sync with morning.md phrasing map and generate_leaderboard.py vocabulary
READ_PHRASINGS: dict[str, str] = {
    "price ahead of story":              "market moved before narrative caught up",
    "price rejecting negative narrative": "market no longer pricing the bearish story",
    "selloff confirming narrative":       "price is validating the bearish story",
    "story not being paid":               "narrative is there but price isn't following",
    "price confirming negative story":    "price is aligning with a negative narrative framing",
    "price confirming narrative":         "narrative confirmed by price",
    "price starting to follow":           "early follow-through forming — not yet clean confirmation",
    "early confirmation forming":         "early confirmation forming — not yet clean confirmation",
}


def read_to_phrase(read: str) -> str:
    """Translate a canonical read value to its required human-readable phrasing."""
    return READ_PHRASINGS.get(read, read)


# ── data loaders ──────────────────────────────────────────────────────────────

def load_actors():
    data = json.loads(ACTORS_JSON.read_text())
    return data["date"], data["actors"]


def load_signals_by_ticker():
    """Return dict: ticker → list of relevant signal dicts."""
    if not SIGNALS_FILE.exists():
        return {}
    data = json.loads(SIGNALS_FILE.read_text())
    by_ticker = defaultdict(list)
    for sig in data.get("signals", []):
        for ent in sig.get("affected_entities", []):
            by_ticker[ent.upper()].append(sig)
    return by_ticker


def load_pressure_by_actor():
    """Return dict: actor → list of pressure records."""
    if not PRESSURE_FILE.exists():
        return {}
    by_actor = defaultdict(list)
    for line in PRESSURE_FILE.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            by_actor[r["actor"]].append(r)
    return by_actor


def load_leadership():
    """Return dict: ticker → {role, leader_score, ...}"""
    if not LEADERSHIP_FILE.exists():
        return {}
    items = json.loads(LEADERSHIP_FILE.read_text())
    return {x["actor"]: x for x in items}


def load_storm_phases_by_actor():
    """Return dict: ticker → list of storm states (phases)."""
    if not STORM_SUMMARY_FILE.exists():
        return {}
    by_actor = defaultdict(list)
    for line in STORM_SUMMARY_FILE.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            for a in r.get("actors", []):
                if r.get("state"):
                    by_actor[a].append(r["state"])
    return dict(by_actor)


def load_event_url_map() -> dict:
    """Return dict: title[:80] → url from normalized events."""
    if not EVENTS_FILE.exists():
        return {}
    url_map: dict[str, str] = {}
    for line in EVENTS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        url = r.get("url", "")
        title = r.get("title", "").strip()
        if url and title:
            url_map[title[:120]] = url
    return url_map


def load_recent_headlines_by_actor(cutoff_days: int = 60) -> dict:
    """Return dict: ticker → list of {date, title} sorted newest-first, from events file."""
    if not EVENTS_FILE.exists():
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=cutoff_days)).strftime("%Y-%m-%d")
    by_actor: dict[str, list] = defaultdict(list)
    for line in EVENTS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        ts = r.get("timestamp", "")
        date_str = ts[:10] if ts else ""
        if date_str < cutoff:
            continue
        title = (r.get("title") or "").strip()
        if not title:
            continue
        for actor in r.get("actors", []):
            by_actor[actor].append({"date": date_str, "title": title[:120]})
    # sort newest-first, dedupe by title
    result: dict[str, list] = {}
    for actor, items in by_actor.items():
        seen: set = set()
        deduped = []
        for item in sorted(items, key=lambda x: x["date"], reverse=True):
            if item["title"] not in seen:
                seen.add(item["title"])
                deduped.append(item)
        result[actor] = deduped
    return result


def load_storm_headlines_by_actor() -> dict:
    """Return dict: ticker → list of {title, source_type, timestamp, url} from storm summaries."""
    if not STORM_SUMMARY_FILE.exists():
        return {}
    by_actor: dict[str, list] = defaultdict(list)
    for line in STORM_SUMMARY_FILE.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        title = (r.get("representative_title") or "").strip()
        if not title:
            continue
        ts = r.get("updated_at") or r.get("created_at") or ""
        for actor in r.get("actors", []):
            by_actor[actor].append({
                "title": title[:120],
                "source_type": "news",
                "timestamp": ts,
                "url": "",
            })
    # sort each actor's list by timestamp desc, dedupe titles
    result = {}
    for actor, items in by_actor.items():
        seen: set = set()
        deduped = []
        for item in sorted(items, key=lambda x: x["timestamp"], reverse=True):
            if item["title"] not in seen:
                seen.add(item["title"])
                deduped.append(item)
        result[actor] = deduped
    return result


def load_threads_by_actor() -> dict:
    """Return dict: ticker → list of canonical narrative thread names."""
    if not LINEAGES_FILE.exists():
        return {}
    data = json.loads(LINEAGES_FILE.read_text())
    by_actor: dict[str, list[str]] = defaultdict(list)
    for lin in data.values():
        name = lin.get("canonical_name", "").strip()
        if not name:
            continue
        for actor in lin.get("actors", []):
            by_actor[actor].append(name)
    # deduplicate while preserving order
    return {k: list(dict.fromkeys(v)) for k, v in by_actor.items()}


def load_pressure_summary_by_actor() -> dict:
    """Return dict: ticker → {level, velocity, direction}."""
    if not PRESSURE_FILE.exists():
        return {}
    by_actor: dict[str, list] = defaultdict(list)
    for line in PRESSURE_FILE.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            by_actor[r["actor"]].append(r)
    summaries = {}
    _dir_map = {"accelerating": "↑", "stable": "→", "fading": "↓", "decelerating": "↓"}
    for actor, recs in by_actor.items():
        best = max(recs, key=lambda r: r.get("pressure_score", 0))
        vel = best.get("velocity_state", "stable")
        summaries[actor] = {
            "level": best.get("pressure_level", "stable"),
            "velocity": vel,
            "direction": _dir_map.get(vel, "→"),
        }
    return summaries


def load_propagation_by_actor() -> dict:
    """Return dict: ticker → list of frequently co-occurring tickers (top 3)."""
    if not PROPAGATION_FILE.exists():
        return {}
    chains = json.loads(PROPAGATION_FILE.read_text())
    co_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for chain in chains:
        actors = chain.get("actors", [])
        for a in actors:
            for b in actors:
                if a != b:
                    co_count[a][b] += 1
    result = {}
    for actor, counts in co_count.items():
        top = sorted(counts, key=lambda x: counts[x], reverse=True)[:3]
        result[actor] = top
    return result


# ── context builder ───────────────────────────────────────────────────────────

def build_context(ticker: str, actor: dict, signals: list, pressure_recs: list,
                  leadership: dict, phases: list, recent_headlines: list | None = None) -> str:
    lines = [
        f"TICKER: {ticker}",
        f"STATE: {actor['state']}",
        f"NARRATIVE SCORE: {actor['narr']}/100",
        f"5D REL RETURN vs QQQ: {actor['rel']:+.1f}%",
        f"NDS (narrative dislocation): {actor['nds']:+.1f}",
        f"NARRATIVE: {actor['narrative']}",
        f"SHORT READ: {actor['read']}",
        "",
    ]

    # leadership / role
    lead = leadership.get(ticker)
    if lead:
        role = lead.get("role", "unknown")
        lines.append(f"NARRATIVE ROLE: {role} (leader_score={lead.get('leader_score',0):.2f}, centrality={lead.get('centrality_score',0):.4f})")
        lines.append("")

    # phases
    if phases:
        from collections import Counter
        phase_counts = Counter(phases)
        dominant = phase_counts.most_common(3)
        phase_str = " → ".join(f"{p}" for p, _ in dominant)
        lines.append(f"NARRATIVE PHASES (recent): {phase_str}")
        lines.append("")

    # pressure labels
    if pressure_recs:
        labels = sorted({r["label"] for r in pressure_recs if r.get("label")})
        lines.append(f"ACTIVE NARRATIVE LABELS: {'; '.join(labels[:5])}")
        max_ps = max(r.get("pressure_score", 0) for r in pressure_recs)
        vel_states = [r.get("velocity_state") for r in pressure_recs if r.get("velocity_state")]
        lines.append(f"MAX PRESSURE SCORE: {max_ps:.2f}")
        if vel_states:
            lines.append(f"VELOCITY STATE: {vel_states[0]}")
        total_48h = sum(r.get("events_last_48h", 0) for r in pressure_recs)
        lines.append(f"EVENTS LAST 48H: {total_48h}")
        lines.append("")

    # signals
    if signals:
        lines.append("RELEVANT SIGNALS:")
        for sig in signals[:4]:
            lines.append(f"  [{sig.get('bucket', '?')}] {sig.get('title', '')}")
            lines.append(f"    {sig.get('summary', '')[:200]}")
        lines.append("")

    # recent sources
    sources = []
    for sig in signals[:4]:
        for src in sig.get("sources", [])[:3]:
            ts = src.get("timestamp", "")
            date = ts[:10] if ts else "?"
            sources.append((date, src.get("title", "")[:120]))
    sources.sort(key=lambda x: x[0], reverse=True)
    if sources:
        lines.append("RECENT NEWS SOURCES:")
        for date, title in sources[:8]:
            lines.append(f"  {date}: {title}")
        lines.append("")

    # dated headlines from event database — spread across the window for date diversity
    if recent_headlines:
        # group by date, pick 1-2 notable headlines per date, take up to 20 total
        by_date: dict[str, list] = defaultdict(list)
        for item in recent_headlines:
            by_date[item["date"]].append(item["title"])
        sampled: list[tuple[str, str]] = []
        for d in sorted(by_date.keys(), reverse=True):
            for title in by_date[d][:1]:
                sampled.append((d, title))
            if len(sampled) >= 40:
                break
        lines.append("DATED HEADLINES (use these to assign accurate dates to events[]):")
        for d, title in sampled:
            lines.append(f"  {d}: {title}")
        lines.append("")

    return "\n".join(lines)


SYSTEM_PROMPT = """You are a sharp, data-driven equity narrative analyst. You write terse, specific analyst notes — no filler, no hedging, no generic statements. Every line must add NEW information. No repetition between sections.

Rules:
- Plain prose only — return bullets as plain strings in JSON arrays, no markdown symbols
- Be specific: name catalysts, dates, percentages where available
- No "it's worth noting", "this suggests", "could potentially" — just state the read
- Every section must contain information not already in another section
- positioning_role: interpret what the role means for this actor RIGHT NOW (not just name the role)
- positioning_phase: name the current phase and whether it is early/mid/late in that phase
- phase_path: 3-4 stage progression ending in CURRENT PHASE in brackets, e.g. "Emergence → Expansion → [REPRICING]"
- drivers: what is actively moving the narrative today (not background or company description)
- events: exactly what happened, with dates
- market_read: what the divergence or confirmation means, tied to the state. Use the read field as the frame — do NOT reinterpret it. Required phrasings by read value:
  * "price ahead of story" → "market moved before narrative caught up"
  * "price rejecting negative narrative" → "market no longer pricing the bearish story"
  * "selloff confirming narrative" → "price is validating the bearish story"
  * "story not being paid" → "narrative is there but price isn't following"
  * "price confirming negative story" → "price is aligning with a negative narrative framing" (do NOT say "price rising against bearish narrative" or "price ahead of narrative")
- next: concrete forward signals — what confirms, what invalidates, what propagates
- confirm_signal: single observable price/event condition that would confirm the narrative thesis (≤12 words)
- break_signal: single observable condition that would invalidate the narrative (≤12 words)
"""

_cutoff_date = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")

USER_TEMPLATE = """Given this context for {ticker}:

{context}

Today is {today}. Only include events that occurred on or after {cutoff} — do not include anything older.
For events[], pick events spread across the full date range — do not cluster all events near today. Aim for at least one event from each of: early in the period, middle of the period, and recent. Use the DATED HEADLINES above to anchor exact dates.

Generate a JSON object with exactly these fields:
{{
  "interpretation": "one tight sentence — core tension or opportunity right now",
  "positioning_role": "role label + 1-phrase implication (e.g. 'receiver — downstream exposure to NVDA cycle')",
  "positioning_phase": "phase label + stage (e.g. 'expansion, mid-cycle' or 'breakdown, early')",
  "phase_path": "Stage → Stage → [CURRENT STAGE] (3-4 steps, current in brackets)",
  "drivers": ["driver 1 (≤10 words)", "driver 2 (≤10 words)", "driver 3 optional (≤10 words)"],
  "events": [
    {{"date": "YYYY-MM-DD", "event": "what happened (concise)"}},
    ...3-5 events spread across the date range...
  ],
  "market_read": "2-3 sentences: what price vs narrative means, tied to state, no repetition of drivers",
  "next": ["forward signal 1 — what confirms", "forward signal 2 — what invalidates", "propagation target or catalyst optional"],
  "confirm_signal": "observable condition that confirms the thesis (≤12 words)",
  "break_signal": "observable condition that breaks the narrative (≤12 words)"
}}

Return only valid JSON. No markdown fences."""


# ── generation ────────────────────────────────────────────────────────────────

def generate_detail(client: OpenAI, ticker: str, actor: dict,
                    signals: list, pressure_recs: list,
                    leadership: dict, phases: list,
                    recent_headlines: list | None = None) -> dict:
    context = build_context(ticker, actor, signals, pressure_recs, leadership, phases, recent_headlines)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = USER_TEMPLATE.format(ticker=ticker, context=context, today=today, cutoff=_cutoff_date)

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    text = response.choices[0].message.content or ""

    # strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]

    try:
        detail = json.loads(text)
        # strip events older than 60 days
        if "events" in detail:
            detail["events"] = [
                ev for ev in detail["events"]
                if ev.get("date", "") >= _cutoff_date
            ]
        return detail
    except json.JSONDecodeError as e:
        print(f"  WARNING: JSON parse failed for {ticker}: {e}", file=sys.stderr)
        print(f"  Raw response: {text[:300]}", file=sys.stderr)
        return {
            "interpretation": read_to_phrase(actor["read"]),
            "positioning_role": None,
            "positioning_phase": None,
            "drivers": [actor["narrative"]],
            "events": [],
            "market_read": read_to_phrase(actor["read"]),
            "next": [],
        }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Only generate for this ticker")
    args = parser.parse_args()

    print("Loading data…")
    date_str, actors    = load_actors()
    signals_by_ticker   = load_signals_by_ticker()
    pressure_by_actor   = load_pressure_by_actor()
    leadership          = load_leadership()
    phases_by_actor     = load_storm_phases_by_actor()
    threads_by_actor     = load_threads_by_actor()
    pressure_summary     = load_pressure_summary_by_actor()
    propagation_by_actor = load_propagation_by_actor()
    event_url_map        = load_event_url_map()
    storm_headlines      = load_storm_headlines_by_actor()
    recent_headlines_by_actor = load_recent_headlines_by_actor(cutoff_days=60)
    # backfill URLs into storm headlines from normalized events
    for actor_headlines in storm_headlines.values():
        for item in actor_headlines:
            if not item["url"]:
                item["url"] = event_url_map.get(item["title"], "")

    client = OpenAI()

    # Load existing output if present (for incremental updates)
    existing = {}
    if OUTPUT_FILE.exists():
        try:
            prev = json.loads(OUTPUT_FILE.read_text())
            existing = {item["t"]: item for item in prev.get("actors", [])}
        except Exception:
            pass

    to_process = actors
    if args.ticker:
        to_process = [a for a in actors if a["t"] == args.ticker.upper()]
        if not to_process:
            print(f"Ticker {args.ticker.upper()} not found in actors.json")
            sys.exit(1)

    results = dict(existing)  # start from existing, overwrite as we go

    for actor in to_process:
        t = actor["t"]
        signals  = signals_by_ticker.get(t, [])
        pressure = pressure_by_actor.get(t, [])
        phases   = phases_by_actor.get(t, [])
        recent_headlines = recent_headlines_by_actor.get(t, [])
        print(f"  {t}: {len(signals)} signals, {len(pressure)} pressure records, {len(phases)} phases, {len(recent_headlines)} dated headlines")

        try:
            detail = generate_detail(client, t, actor, signals, pressure, leadership, phases, recent_headlines)
            # merge in data-derived fields (no Claude call needed)
            detail["threads"]          = threads_by_actor.get(t, [])[:4]
            detail["pressure_summary"] = pressure_summary.get(t)
            detail["propagation"]      = propagation_by_actor.get(t, [])
            detail["signal_count"]     = len(signals)
            # top sources: collect from all signals, sort by timestamp, dedupe by title
            raw_sources = []
            for sig in signals:
                for src in sig.get("sources", []):
                    title = src.get("title", "").strip()
                    if title:
                        raw_sources.append({
                            "title": title[:120],
                            "source_type": src.get("source_type", ""),
                            "timestamp": src.get("timestamp", ""),
                            "url": src.get("url", ""),
                        })
            seen_titles: set = set()
            top_sources = []
            for src in sorted(raw_sources, key=lambda s: s["timestamp"], reverse=True):
                if src["title"] not in seen_titles:
                    seen_titles.add(src["title"])
                    top_sources.append(src)
                if len(top_sources) >= 5:
                    break
            # fill remaining slots from storm headlines
            if len(top_sources) < 5:
                for src in storm_headlines.get(t, []):
                    if src["title"] not in seen_titles:
                        seen_titles.add(src["title"])
                        top_sources.append(src)
                    if len(top_sources) >= 5:
                        break
            detail["top_sources"] = top_sources
            # total unique sources available (for "5 of N" display)
            # includes signals, storm headlines, and raw events database
            all_source_titles: set = set()
            for sig in signals:
                for src in sig.get("sources", []):
                    title = src.get("title", "").strip()
                    if title:
                        all_source_titles.add(title)
            for src in storm_headlines.get(t, []):
                all_source_titles.add(src["title"])
            for item in recent_headlines_by_actor.get(t, []):
                all_source_titles.add(item["title"])
            detail["source_count"] = len(all_source_titles)
            results[t] = {**actor, "detail": detail}
            print(f"    → {detail.get('interpretation', '')[:80]}")
        except Exception as e:
            print(f"  ERROR on {t}: {e}", file=sys.stderr)
            results[t] = {**actor, "detail": None}

    # Write output preserving actor order from actors.json
    ordered = []
    actor_order = {a["t"]: i for i, a in enumerate(actors)}
    for r in sorted(results.values(), key=lambda x: actor_order.get(x["t"], 999)):
        ordered.append(r)

    out = {"date": date_str, "actors": ordered}
    OUTPUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {OUTPUT_FILE} ({len(ordered)} actors)")


if __name__ == "__main__":
    main()
