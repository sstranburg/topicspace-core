#!/usr/bin/env python3
"""Generate Tech Ecosystem Storm Report - ecosystem-level narratives."""

import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
from datetime import datetime
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from strategic_watchlist import build_pressure_leadership_records, filter_watchlist

print("="*70)
print("TECH ECOSYSTEM STORM REPORT GENERATOR (ECOSYSTEM LEVEL)")
print("="*70)

# Load ecosystem summaries
print("\nLoading ecosystem storm summaries...")
summaries = []
with open("data/derived/ecosystem_storm_summaries.jsonl", 'r') as f:
    for line in f:
        summaries.append(json.loads(line))

print(f"Loaded {len(summaries)} ecosystem storm summaries")

# Load trajectories
print("Loading ecosystem trajectories...")
trajectories = []
with open("data/derived/ecosystem_trajectories.jsonl", 'r') as f:
    for line in f:
        trajectories.append(json.loads(line))

print(f"Loaded {len(trajectories)} ecosystem trajectories")

# Build trajectory lookup
traj_by_id = {t['trajectory_id']: t for t in trajectories}

# Match summaries to trajectories
for summary in summaries:
    storm_id = summary['storm_id']
    for traj in trajectories:
        if traj['trajectory_id'] == storm_id:
            summary['trajectory'] = traj
            break

# Generate report
print("\n" + "="*70)
print("GENERATING ECOSYSTEM REPORT")
print("="*70)

report_lines = []

# Header
report_lines.append("# TECH ECOSYSTEM STORM REPORT")
report_lines.append("")
report_lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
report_lines.append("")
report_lines.append("Ecosystem-level narrative intelligence across tech actors: NVDA, AMD, TSM, MSFT, AMZN, GOOGL, ASML, AVGO")
report_lines.append("")
report_lines.append("---")
report_lines.append("")

# Section 1: Top Active Ecosystem Narratives
report_lines.append("## 1. Top Active Ecosystem Narratives")
report_lines.append("")
report_lines.append("Cross-actor narratives with growing or peaking intensity:")
report_lines.append("")

active_summaries = [
    s for s in summaries 
    if s.get('state') in ['growing', 'peaking']
    and s.get('num_unique_actors', 0) > 1  # Exclude single-actor storms
]

# Sanity check: warn if any storm dominates
if summaries:
    total_events = sum(s['event_count'] for s in summaries)
    for summary in active_summaries:
        if summary['event_count'] / total_events > 0.40:
            print(f"⚠️  Warning: Storm {summary['storm_id']} contains {summary['event_count']/total_events:.1%} of all events")

if active_summaries:
    # Sort by event count
    active_summaries.sort(key=lambda x: x.get('event_count', 0), reverse=True)
    
    for i, summary in enumerate(active_summaries[:5], 1):
        traj = summary.get('trajectory', {})
        headline = summary.get('display_headline', summary['headline'])
        one_liner = summary.get('display_one_liner', summary['one_liner'])
        
        report_lines.append(f"### {i}. {headline}")
        report_lines.append("")
        report_lines.append(f"**State**: {summary['state'].title()}")
        report_lines.append(f"**Storm Scope**: {summary.get('storm_scope', 'unknown').replace('_', ' ').title()}")
        report_lines.append(f"**Actors**: {', '.join(summary['actors'])} ({summary['num_unique_actors']} total)")
        report_lines.append(f"**Event Count**: {summary['event_count']}")
        report_lines.append(f"**Dominant Actor Ratio**: {summary['dominant_actor_ratio']:.2f}")
        report_lines.append(f"**Actor Entropy**: {summary['actor_entropy']:.2f}")
        report_lines.append(f"**Cluster Quality**: radius={summary.get('cluster_radius', 0):.2f}, similarity={summary.get('mean_pairwise_similarity', 0):.2f}")
        
        if traj:
            report_lines.append(f"**Momentum**: {traj.get('latest_momentum', 0):+d}")
            report_lines.append(f"**Acceleration**: {traj.get('latest_acceleration', 0):+d}")
        
        report_lines.append("")
        report_lines.append(f"*{one_liner}*")
        report_lines.append("")
        
        if summary.get('domain_phrases'):
            report_lines.append(f"**Key Themes**: {', '.join(summary['domain_phrases'])}")
            report_lines.append("")
else:
    report_lines.append("*No active ecosystem narratives detected*")
    report_lines.append("")

report_lines.append("---")
report_lines.append("")

# Section 2: Emerging Ecosystem Narratives
report_lines.append("## 2. Emerging Ecosystem Narratives")
report_lines.append("")
report_lines.append("New cross-actor narratives forming:")
report_lines.append("")

emerging_summaries = [s for s in summaries if s.get('state') == 'emerging']

if emerging_summaries:
    for i, summary in enumerate(emerging_summaries, 1):
        headline = summary.get('display_headline', summary['headline'])
        one_liner = summary.get('display_one_liner', summary['one_liner'])
        
        report_lines.append(f"### {i}. {headline}")
        report_lines.append("")
        report_lines.append(f"**Actors**: {', '.join(summary['actors'])} ({summary['num_unique_actors']} total)")
        report_lines.append(f"**Event Count**: {summary['event_count']}")
        report_lines.append("")
        report_lines.append(f"*{one_liner}*")
        report_lines.append("")
else:
    report_lines.append("*No emerging ecosystem narratives detected*")
    report_lines.append("")

report_lines.append("---")
report_lines.append("")

# Section 3: Cross-Actor Convergence
report_lines.append("## 3. Cross-Actor Convergence")
report_lines.append("")
report_lines.append("Narratives involving multiple actors:")
report_lines.append("")

cross_actor_summaries = [s for s in summaries if s.get('num_unique_actors', 0) > 1]
cross_actor_summaries.sort(key=lambda x: x.get('num_unique_actors', 0), reverse=True)

if cross_actor_summaries:
    for i, summary in enumerate(cross_actor_summaries[:5], 1):
        headline = summary.get('display_headline', summary['headline'])
        
        report_lines.append(f"### {i}. {headline}")
        report_lines.append("")
        report_lines.append(f"**Actors**: {', '.join(summary.get('all_actors_involved', [])[:5])}")
        report_lines.append(f"**Total Actors**: {summary['num_unique_actors']}")
        report_lines.append(f"**Event Count**: {summary['event_count']}")
        report_lines.append(f"**Dominant Actor Ratio**: {summary['dominant_actor_ratio']:.2f}")
        report_lines.append(f"**Actor Entropy**: {summary['actor_entropy']:.2f}")
        report_lines.append("")
        
        # Interpretation
        if summary['dominant_actor_ratio'] > 0.6:
            report_lines.append("*Single actor dominates this narrative*")
        elif summary['actor_entropy'] > 2.0:
            report_lines.append("*High diversity - true ecosystem-wide narrative*")
        else:
            report_lines.append("*Moderate actor participation*")
        report_lines.append("")
else:
    report_lines.append("*No cross-actor narratives detected*")
    report_lines.append("")

report_lines.append("---")
report_lines.append("")

# Section 4: Actor Influence Map
report_lines.append("## 4. Actor Influence Map")
report_lines.append("")
report_lines.append("Actor participation across ecosystem narratives:")
report_lines.append("")

# Count actor appearances
actor_participation = Counter()
actor_event_counts = Counter()

for summary in summaries:
    for actor in summary.get('all_actors_involved', []):
        actor_participation[actor] += 1
        actor_event_counts[actor] += summary['event_count']

if actor_participation:
    report_lines.append("| Actor | Narratives | Total Events | Avg Events/Narrative |")
    report_lines.append("|-------|-----------|--------------|---------------------|")
    
    for actor, count in actor_participation.most_common():
        avg_events = actor_event_counts[actor] / count if count > 0 else 0
        report_lines.append(f"| {actor} | {count} | {actor_event_counts[actor]} | {avg_events:.0f} |")
    
    report_lines.append("")
else:
    report_lines.append("*No actor participation data available*")
    report_lines.append("")

report_lines.append("---")
report_lines.append("")

# Section 5: Ecosystem Dynamics
report_lines.append("## 5. Ecosystem Dynamics")
report_lines.append("")

# State distribution
state_counts = Counter(s['state'] for s in summaries)
report_lines.append("### Storm State Distribution")
report_lines.append("")
for state, count in state_counts.most_common():
    report_lines.append(f"- **{state.title()}**: {count}")
report_lines.append("")

# Ecosystem metrics
total_events = sum(s['event_count'] for s in summaries)
avg_actors_per_storm = sum(s['num_unique_actors'] for s in summaries) / len(summaries) if summaries else 0
cross_actor_count = sum(1 for s in summaries if s['num_unique_actors'] > 1)
single_actor_count = sum(1 for s in summaries if s['num_unique_actors'] == 1)

report_lines.append("### Ecosystem Metrics")
report_lines.append("")
report_lines.append(f"- **Total Ecosystem Storms**: {len(summaries)}")
report_lines.append(f"- **Total Events**: {total_events}")
report_lines.append(f"- **Average Actors per Storm**: {avg_actors_per_storm:.1f}")
report_lines.append(f"- **Cross-Actor Storms**: {cross_actor_count}")
report_lines.append(f"- **Single-Actor Storms**: {single_actor_count}")
report_lines.append("")

# Largest storm
if summaries:
    largest_storm = max(summaries, key=lambda x: x['event_count'])
    largest_headline = largest_storm.get('display_headline', largest_storm['headline'])
    report_lines.append(f"- **Largest Ecosystem Storm**: {largest_headline} ({largest_storm['event_count']} events)")
    report_lines.append("")

# Most diverse storm
if summaries:
    most_diverse = max(summaries, key=lambda x: x.get('actor_entropy', 0))
    diverse_headline = most_diverse.get('display_headline', most_diverse['headline'])
    report_lines.append(f"- **Most Diverse Storm**: {diverse_headline} (entropy: {most_diverse['actor_entropy']:.2f})")
    report_lines.append("")

report_lines.append("---")
report_lines.append("")

# Footer
report_lines.append("## System Architecture")
report_lines.append("")
report_lines.append("This report models **ecosystem-level narratives** that span multiple actors.")
report_lines.append("")
report_lines.append("**Key Differences from Actor-Level Reports:**")
report_lines.append("- Actor reports: Narratives around individual companies")
report_lines.append("- Ecosystem reports: Narratives across the entire industry")
report_lines.append("")
report_lines.append("**Metrics:**")
report_lines.append("- **Dominant Actor Ratio**: Measures if one actor dominates (1.0 = single actor, 0.0 = perfectly balanced)")
report_lines.append("- **Actor Entropy**: Measures diversity (0 = single actor, higher = more diverse)")
report_lines.append("")
report_lines.append("The system functions as **weather radar for industry dynamics** - tracking formation, growth, and convergence of narratives across the tech ecosystem.")
report_lines.append("")

# Section 6: Strategic Watchlist Context
report_lines.append("## 6. Strategic Watchlist Context")
report_lines.append("")

data_dir = Path(__file__).parent.parent / 'data' / 'derived'
watchlist_path = data_dir / 'strategic_watchlist.jsonl'
if watchlist_path.exists():
    wl_items = []
    with open(watchlist_path) as f:
        for line in f:
            if line.strip():
                wl_items.append(json.loads(line))
    wl_priority = [r for r in wl_items if r['watch_category'] == 'priority_watch']
    wl_monitor = [r for r in wl_items if r['watch_category'] == 'monitor_closely']
    report_lines.append(f"**Priority watch**: {len(wl_priority)} narratives")
    report_lines.append(f"**Monitor closely**: {len(wl_monitor)} narratives")
    report_lines.append("")
    for r in (wl_priority + wl_monitor)[:5]:
        report_lines.append(f"- **{r['label']}** ({r['actor']}, {r['role']}) — {r['pressure_level']} pressure, strategic={r['strategic_score']:.2f}")
    report_lines.append("")
else:
    report_lines.append("*Run generate_strategic_watchlist.py to populate this section*")
    report_lines.append("")

# Write report
report_text = '\n'.join(report_lines)

with open("TECH_ECOSYSTEM_STORM_REPORT_ECOSYSTEM.md", 'w') as f:
    f.write(report_text)

print("\n✅ Report generated: TECH_ECOSYSTEM_STORM_REPORT_ECOSYSTEM.md")

# Print summary
print("\n" + "="*70)
print("REPORT SUMMARY")
print("="*70)
print(f"\nTotal ecosystem storms: {len(summaries)}")
print(f"Active narratives (growing/peaking): {len(active_summaries)}")
print(f"Emerging narratives: {len(emerging_summaries)}")
print(f"Cross-actor storms: {cross_actor_count}")
print(f"Single-actor storms: {single_actor_count}")
print(f"\nState distribution:")
for state, count in state_counts.most_common():
    print(f"  {state}: {count}")
print(f"\nAverage actors per storm: {avg_actors_per_storm:.1f}")

print("\n" + "="*70)
print("ECOSYSTEM REPORT COMPLETE")
print("="*70)
