#!/usr/bin/env python3
"""Generate strategic watchlist from pressure + leadership data."""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from strategic_watchlist import build_pressure_leadership_records, filter_watchlist, dedupe_watchlist


def load_jsonl(path):
    items = []
    if not path.exists():
        return items
    with open(path) as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def main():
    data_dir = Path(__file__).parent.parent / 'data' / 'derived'

    # Load inputs
    pressure_records = load_jsonl(data_dir / 'narrative_pressure.jsonl')
    leadership_list = json.loads((data_dir / 'narrative_leadership.json').read_text()) if (data_dir / 'narrative_leadership.json').exists() else []
    actor_summaries = load_jsonl(data_dir / 'actor_storm_summaries.jsonl')

    leadership_map = {r['actor']: r for r in leadership_list}

    # Enrich pressure records with summary fields
    summary_map = {s['storm_id']: s for s in actor_summaries}
    for pr in pressure_records:
        sm = summary_map.get(pr.get('storm_id', ''), {})
        pr.setdefault('shift_type', sm.get('shift_type', 'unclear'))
        pr.setdefault('domain_phrases', sm.get('domain_phrases', []))
        pr.setdefault('num_unique_actors', sm.get('num_unique_actors', 1))
        pr.setdefault('display_headline', sm.get('display_headline', pr.get('label', '')))

    # Build, filter, and dedupe
    records = build_pressure_leadership_records(pressure_records, leadership_map)
    filtered = filter_watchlist(records)
    filtered = dedupe_watchlist(filtered)
    filtered.sort(key=lambda r: -r['strategic_score'])

    # Save artifact
    out_path = data_dir / 'strategic_watchlist.jsonl'
    with open(out_path, 'w') as f:
        for r in filtered:
            f.write(json.dumps(r) + '\n')

    # Categorize
    priority = [r for r in filtered if r['watch_category'] == 'priority_watch']
    monitor = [r for r in filtered if r['watch_category'] == 'monitor_closely']
    lower = [r for r in filtered if r['watch_category'] == 'lower_priority']

    # Generate markdown report
    lines = [
        "# Strategic Watchlist Report",
        "",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
        "## 1. Priority Watch",
        "",
    ]
    for r in priority[:5]:
        lines.append(f"### {r['label']}")
        lines.append(f"- **Actor**: {r['actor']}  **Role**: {r['role'].title()}  **Pressure**: {r['pressure_level'].title()} ({r['pressure_score']:.2f})  **Strategic**: {r['strategic_score']:.2f}")
        lines.append(f"- {r['watch_interpretation']}")
        lines.append("")
    if not priority:
        lines.append("*No priority watch items*\n")

    lines += ["---", "", "## 2. Monitor Closely", ""]
    for r in monitor[:8]:
        lines.append(f"### {r['label']}")
        lines.append(f"- **Actor**: {r['actor']}  **Role**: {r['role'].title()}  **Pressure**: {r['pressure_level'].title()} ({r['pressure_score']:.2f})  **Strategic**: {r['strategic_score']:.2f}")
        lines.append(f"- {r['watch_interpretation']}")
        lines.append("")
    if not monitor:
        lines.append("*No monitor closely items*\n")

    lines += ["---", "", "## 3. Role-Based Breakdown", ""]
    role_counts = Counter(r['role'] for r in filtered)
    for role in ['leader', 'amplifier', 'bridge', 'receiver', 'unknown']:
        if role_counts[role]:
            lines.append(f"- **{role.title()}**: {role_counts[role]}")
    lines.append("")

    lines += ["## 4. Shift-Type Breakdown", ""]
    shift_counts = Counter(r['shift_type'] for r in filtered)
    for st in ['thematic_shift', 'mixed_shift', 'market_noise_shift', 'stable', 'unclear']:
        if shift_counts[st]:
            lines.append(f"- **{st}**: {shift_counts[st]}")
    lines.append("")

    lines += ["## 5. Key Interpretation", ""]
    if priority:
        lines.append(f"{len(priority)} narrative(s) require priority attention. ")
    if monitor:
        lines.append(f"{len(monitor)} additional narrative(s) are building and worth monitoring.")
    role_mix = [f"{role_counts[r]} {r}s" for r in ['leader', 'amplifier', 'bridge', 'receiver'] if role_counts[r]]
    if role_mix:
        lines.append(f"Role mix across watchlist: {', '.join(role_mix)}.")
    lines.append("")

    report_path = Path(__file__).parent.parent / 'STRATEGIC_WATCHLIST_REPORT.md'
    report_path.write_text('\n'.join(lines))

    # Diagnostics
    print("Strategic Watchlist Diagnostics")
    print("-------------------------------")
    print(f"Pressure records loaded: {len(pressure_records)}")
    print(f"Leadership records loaded: {len(leadership_list)}")
    print(f"Joined records (after filter): {len(filtered)}")
    print()
    print(f"Priority watch: {len(priority)}")
    print(f"Monitor closely: {len(monitor)}")
    print(f"Lower priority: {len(lower)}")
    print()
    print("Role breakdown:")
    for role in ['leader', 'amplifier', 'bridge', 'receiver', 'unknown']:
        if role_counts[role]:
            print(f"  {role}: {role_counts[role]}")
    print()
    print("Top watchlist items:")
    for i, r in enumerate(filtered[:10], 1):
        print(f"  {i}. {r['label'][:50]} | {r['actor']} | {r['role']} | {r['pressure_level']} ({r['pressure_score']:.2f}) | strategic={r['strategic_score']:.2f} | {r['watch_category']}")
    print()
    print(f"✓ Artifact: {out_path}")
    print(f"✓ Report: {report_path}")


if __name__ == '__main__':
    main()
