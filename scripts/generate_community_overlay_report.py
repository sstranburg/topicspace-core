#!/usr/bin/env python3
"""Generate community overlay report from overlay and precursor artifacts."""

import json
from pathlib import Path
from datetime import datetime
from collections import Counter


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
    overlay = load_jsonl(data_dir / 'community_overlay.jsonl')
    precursors = load_jsonl(data_dir / 'community_precursors.jsonl')

    lines = [
        "# Community Overlay Report",
        "",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "Community signals mapped onto institutional storms without altering storm boundaries.",
        "",
        "---",
        "",
    ]

    # Section 1: Aligned storms
    aligned = [r for r in overlay if r['community_alignment_label'] == 'aligned']
    lines.append("## 1. Storms With Strong Community Reinforcement")
    lines.append("")
    if aligned:
        for r in sorted(aligned, key=lambda x: -x['community_post_count']):
            lines.append(f"### {r['label']} ({r['actor']})")
            lines.append(f"- Posts: {r['community_post_count']}  Subreddits: {', '.join(r['community_top_subreddits'])}")
            lines.append(f"- {r['community_interpretation']}")
            lines.append("")
    else:
        lines.append("*No strongly aligned storms in this window*")
        lines.append("")

    # Section 2: Divergent storms
    divergent = [r for r in overlay if r['community_alignment_label'] in ('divergent', 'mixed')]
    lines += ["---", "", "## 2. Storms With Community Divergence", ""]
    if divergent:
        for r in sorted(divergent, key=lambda x: -x['community_post_count']):
            lines.append(f"### {r['label']} ({r['actor']})")
            lines.append(f"- Posts: {r['community_post_count']}  Alignment: {r['community_alignment_label']}")
            if r['community_divergent_themes']:
                lines.append(f"- Divergent themes: {', '.join(r['community_divergent_themes'][:5])}")
            lines.append(f"- {r['community_interpretation']}")
            lines.append("")
    else:
        lines.append("*No divergent storms detected*")
        lines.append("")

    # Section 3: Precursors
    lines += ["---", "", "## 3. Community Precursors", ""]
    if precursors:
        lines.append("Emerging community topics not yet strongly represented in institutional storms:")
        lines.append("")
        for p in precursors:
            lines.append(f"### {p['label']}")
            lines.append(f"- Posts: {p['post_count']}  Avg score: {p['avg_score']}")
            lines.append(f"- Subreddits: {', '.join(p['top_subreddits'])}")
            if p.get('actors'):
                lines.append(f"- Actors: {', '.join(p['actors'])}")
            lines.append(f"- {p['interpretation']}")
            lines.append("")
    else:
        lines.append("*No precursor topics detected*")
        lines.append("")

    # Section 4: Top subreddits
    lines += ["---", "", "## 4. Top Subreddits by Attached Signal", ""]
    sub_counts = Counter()
    for r in overlay:
        for s in r['community_top_subreddits']:
            sub_counts[s] += r['community_post_count']
    if sub_counts:
        lines.append("| Subreddit | Attached Posts |")
        lines.append("|-----------|---------------|")
        for sub, ct in sub_counts.most_common(10):
            lines.append(f"| {sub} | {ct} |")
        lines.append("")
    else:
        lines.append("*No subreddit data available*")
        lines.append("")

    # Section 5: Caveats
    lines += [
        "---", "",
        "## 5. Caveats", "",
        "- Community overlay enriches institutional storms and does not define them.",
        "- Reddit signals are noisier and more interpretive than institutional sources.",
        "- Alignment scores use keyword overlap, not deep semantic comparison.",
        "- Precursors may represent noise rather than genuine emerging narratives.",
        "",
    ]

    report_path = Path(__file__).parent.parent / 'COMMUNITY_OVERLAY_REPORT.md'
    report_path.write_text('\n'.join(lines))
    print(f"Report: {report_path}")
    print(f"  Overlay storms: {len(overlay)} (aligned={len(aligned)}, divergent/mixed={len(divergent)})")
    print(f"  Precursors: {len(precursors)}")


if __name__ == '__main__':
    main()
