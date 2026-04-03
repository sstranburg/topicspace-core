#!/usr/bin/env python3
"""
generate_crypto_report.py

Generate a full Crypto Narrative Intelligence Report from live event data.

Steps:
  1. Run the compass pipeline (load, cluster, label, classify)
  2. Build enriched cluster summaries with event samples
  3. Call GPT-4o to generate the full 12-section report as markdown
  4. Write to file or stdout

Usage:
  venv/bin/python scripts/generate_crypto_report.py
  venv/bin/python scripts/generate_crypto_report.py --out CRYPTO_NARRATIVE_REPORT.md
  venv/bin/python scripts/generate_crypto_report.py --clusters 15
  venv/bin/python scripts/generate_crypto_report.py --no-llm-labels  # skip cluster labeling
"""

import sys
import json
import argparse
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from generate_crypto_compass import (
    load_events,
    split_events,
    actor_density,
    actor_counts,
    cluster_titles,
    label_cluster,
    classify_with_llm,
    _momentum_label,
    _attention_level,
    SPLIT_DATE,
    N_CLUSTERS,
    ACTORS,
)
from src.llm_naming import _get_client

REPORT_MODEL = "gpt-4o"
REPORT_MAX_TOKENS = 8192
EVENTS_SAMPLE_PER_CLUSTER = 10


# ── Data packaging ─────────────────────────────────────────────────────────────

def _date_range(events) -> tuple[str, str]:
    dates = sorted(e.timestamp[:10] for e in events)
    return dates[0], dates[-1]


def _format_cluster_for_report(cluster: dict, momentum: str, attention: str) -> str:
    """Format a cluster dict into a text block for the LLM report prompt."""
    actors = ", ".join(cluster["actors"]) or "unknown"
    src_pct = cluster.get("source_pct", {})
    src_str = "  ".join(f"{s}={p}%" for s, p in sorted(src_pct.items(), key=lambda x: -x[1]))
    events = cluster.get("events", [])
    sample = events[:EVENTS_SAMPLE_PER_CLUSTER]
    event_lines = "\n".join(
        f"  [{e.timestamp[:10]}] [{','.join(e.actors) or '?'}] {e.title}"
        for e in sample
    )
    return (
        f"Cluster: \"{cluster['narrative']}\"\n"
        f"  family: {cluster.get('narrative_family', 'general')}\n"
        f"  actors: {actors}\n"
        f"  events: {cluster['size']}  attention: {attention}  momentum: {momentum}\n"
        f"  source_mix: {src_str or cluster.get('source_mix','unknown')}\n"
        f"  dominant_source: {cluster.get('dominant_source','unknown')}\n"
        f"  cross_source_count: {cluster.get('cross_source_count', 1)}\n"
        f"  representative_titles: {cluster.get('representative_titles', [])[:3]}\n"
        f"  Events (sample {len(sample)}/{cluster['size']}):\n{event_lines}"
    )


def _format_compass_for_report(sections: dict) -> str:
    """Format compass output sections into a compact text summary."""
    lines = []
    labels = [
        ("lean_in",    "LEAN IN"),
        ("step_back",  "STEP BACK"),
        ("be_careful", "BE CAREFUL"),
        ("ignore",     "IGNORE"),
    ]
    for key, header in labels:
        items = sections.get(key, [])
        lines.append(f"\n{header}:")
        if not items:
            lines.append("  (none)")
        else:
            for item in items:
                lines.append(f"  • {item['narrative']} [{item['confidence']}]")
                lines.append(f"    {item['summary']}")
                lines.append(f"    → {item['action']}")
    return "\n".join(lines)


def _format_actor_stats(events, early_events, late_events) -> str:
    """Top actors by event count, split early/late."""
    early_c = actor_counts(early_events)
    late_c  = actor_counts(late_events)
    all_actors = set(early_c) | set(late_c)
    rows = []
    for a in sorted(all_actors, key=lambda x: -(early_c.get(x,0) + late_c.get(x,0))):
        rows.append(f"  {a:8s}  early={early_c.get(a,0):3d}  late={late_c.get(a,0):3d}")
    return "\n".join(rows[:15])


# ── LLM report generation ─────────────────────────────────────────────────────

REPORT_SYSTEM_PROMPT = """\
You are a crypto narrative intelligence analyst producing a structured briefing report.

You will be given:
- A compass classification (LEAN IN / STEP BACK / BE CAREFUL / IGNORE) for each narrative
- Cluster details with event samples, actors, momentum, source mix
- Actor activity statistics

Your task: generate a complete Crypto Narrative Intelligence Report in markdown.

SECTION RULES:

1. EXECUTIVE OVERVIEW
   - SYSTEM STATE: One-line status headline (e.g. "No dominant narratives. Institutional signals forming.")
   - WHAT'S DRIVING THE SYSTEM: 3–5 bullets. Concrete facts, no opinions.
   - WHAT CHANGED SINCE LAST UPDATE: 3–5 bullets. Focus on shifts, not stable facts.
   - WHAT TO WATCH NEXT: 3–5 bullets framed as questions.
   - NARRATIVE MISALIGNMENT: 2–3 bullets. Where volume/signal are decoupled; where narratives conflict.

2. CRYPTO NARRATIVE MAP
   - Exactly mirrors the compass output provided.
   - LEAN IN: if empty, write "(none)" and a one-line explanation of why nothing qualifies.
   - BE CAREFUL: for each entry, write 2–3 sentences describing what the evidence shows.
   - STEP BACK: for each entry, explain why volume doesn't warrant action.
   - IGNORE: bullet list only.

3. NARRATIVE FORECAST
   - SURGING / FORMING: 1–3 narratives. State: what state, confirmation signals, invalidation signals, time horizon.
   - EMERGING / TRANSITIONING: 1–3 narratives. Same format.
   - AT RISK / REVERSING: 1–2 narratives. Reversal signal + time horizon.

4. NARRATIVE ACTIONS
   - One action card per top-3 BE_CAREFUL and LEAN_IN narrative.
   - Each card: Thesis, Action, Time horizon, Confidence, Who benefits, Who is at risk, Confirm signals, Invalidate signals.

5. STRATEGIC WATCHLIST
   Two tables:
   (a) Narrative Clusters: Narrative | Family | Assets | Momentum | Reinforcement | Market Read
   (b) Ecosystem Narratives: Narrative | Assets | Status | Why It Matters

6. NARRATIVE PHASE MAP
   - 5–6 items using gravity/velocity framing.
   - Each item: label (e.g. "High gravity, rising velocity"), narrative name, 1-sentence description.

7. NARRATIVE LINEAGES
   - One lineage per major narrative thread (3–5 total).
   - Each: Assets, Period, Phases (count), Events this window, Market Read.
   - 2–3 sentence narrative description + bulleted phase list.

8. ECOSYSTEM VIEW
   - 4–6 ecosystem-level narratives.
   - Each: Assets, Events, Status, What changed, Why it matters, What to watch.
   - End with a "Cross-ecosystem note" if patterns span multiple assets.

9. ASSET / PROTOCOL NARRATIVE SNAPSHOTS
   - One snapshot per major asset (BTC, ETH, SOL + any rising alt).
   - Each: Headline narrative, Status, 2–3 sentence narrative arc, Key events (bullet list).

10. CONVERGENCE & PROPAGATION
    - 2–4 propagation pathways observed.
    - Each: Title, 2–3 sentence narrative, Direction arrow.

11. METHODOLOGY & ANALYTICAL FRAMEWORK
    - Static description of pipeline (8 steps). Fill in actual stats from the data provided.
    - End with "What to be careful about" (5 caveats).

12. APPENDIX: STORM INDEX
    - Table: Cluster | Family | Actors | Events | Classification | Confidence

WRITING STYLE:
- Direct, professional, no hedging language
- No "this suggests" or "might possibly" — state what the data shows
- Max 12 words per summary line
- Concrete phrasing: "institutional flows", "retail panic", "conflicting narratives"
- Action statements are imperative: "Watch for confirmation", "Do not anchor on either thread"

OUTPUT: Complete markdown, starting with a title header.
"""


def generate_report_with_llm(
    sections: dict,
    clusters: list[dict],
    events,
    early_events,
    late_events,
    early_density: dict,
    late_density: dict,
    early_raw: dict,
    date_str: str,
) -> str:
    """Call GPT-4o to generate the full 12-section report."""
    date_from, date_to = _date_range(events)
    total = len(events)

    # Build enriched cluster summaries with momentum
    cluster_blocks = []
    for c in clusters:
        momentum = _momentum_label(c, early_density, late_density, early_raw)
        attention = _attention_level(c["size"])
        cluster_blocks.append(_format_cluster_for_report(c, momentum, attention))

    compass_text = _format_compass_for_report(sections)
    actor_stats  = _format_actor_stats(events, early_events, late_events)

    # Source list
    sources = sorted(set(e.source for e in events))

    user_message = f"""DATE: {date_str}
DATA WINDOW: {date_from} to {date_to}
TOTAL EVENTS: {total}
SOURCES: {', '.join(sources)}
EARLY WINDOW: {len(early_events)} events (before {SPLIT_DATE})
LATE WINDOW: {len(late_events)} events (from {SPLIT_DATE})

─────────────────────────────────────────
COMPASS CLASSIFICATION
─────────────────────────────────────────
{compass_text}

─────────────────────────────────────────
ACTOR ACTIVITY (early / late windows)
─────────────────────────────────────────
{actor_stats}

─────────────────────────────────────────
CLUSTER DETAILS ({len(clusters)} clusters)
─────────────────────────────────────────
{"".join(chr(10) + "═" * 60 + chr(10) + b for b in cluster_blocks)}

Generate the complete 12-section Crypto Narrative Intelligence Report as markdown.
"""

    client = _get_client()
    print(f"Generating report with {REPORT_MODEL} ({REPORT_MAX_TOKENS} max tokens)…")
    response = client.chat.completions.create(
        model=REPORT_MODEL,
        max_tokens=REPORT_MAX_TOKENS,
        messages=[
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
    )
    return response.choices[0].message.content.strip()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate Crypto Narrative Intelligence Report")
    parser.add_argument("--out",           help="Write report to this file (default: stdout)")
    parser.add_argument("--clusters",      type=int, default=N_CLUSTERS, help="Number of clusters")
    parser.add_argument("--no-llm-labels", action="store_true", help="Skip cluster LLM labeling")
    args = parser.parse_args()

    date_str = datetime.today().strftime("%Y-%m-%d")

    # 1. Load events
    events = load_events()

    # 2. Window
    early_events, late_events = split_events(events, SPLIT_DATE)
    early_density = actor_density(early_events)
    late_density  = actor_density(late_events)
    early_raw     = actor_counts(early_events)
    print(f"Early window: {len(early_events)} events | Late window: {len(late_events)} events")

    # 3. Cluster
    clusters = cluster_titles(events, n_clusters=args.clusters)
    print(f"Clusters found: {len(clusters)}")

    # 4. Label clusters
    print("Labeling clusters…")
    labeled = [label_cluster(c, use_llm=not args.no_llm_labels) for c in clusters]
    for c in labeled:
        src = "llm" if c.get("label_source") == "llm" else "terms"
        print(f"  [{src}] {c['narrative']}  (n={c['size']})")

    # 5. Classify
    print("Classifying narratives…")
    sections = classify_with_llm(labeled, early_density, late_density, early_raw)

    print("\nCompass summary:")
    for section, items in sections.items():
        names = [i["narrative"] for i in items]
        print(f"  {section:12s}: {names}")

    # 6. Generate report
    report_md = generate_report_with_llm(
        sections, labeled, events,
        early_events, late_events,
        early_density, late_density, early_raw,
        date_str,
    )

    # 7. Output
    if args.out:
        Path(args.out).write_text(report_md)
        print(f"\nReport written to {args.out}")
    else:
        print("\n" + report_md)


if __name__ == "__main__":
    main()
