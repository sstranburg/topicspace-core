#!/usr/bin/env python3
"""Generate side-by-side comparison report for clustered vs baseline summaries."""

import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
from src.storm_summaries import generate_storm_summary
from src.storm_topic_clustering import load_embeddings

print("="*70)
print("CLUSTERING COMPARISON REPORT GENERATOR")
print("="*70)

# Load embeddings
print("\nLoading embeddings...")
title_embeddings_map = load_embeddings()
print(f"Loaded {len(title_embeddings_map)} titles")

# Load storms
print("Loading storms...")
storms = []
with open("data/derived/actor_storms.jsonl", 'r') as f:
    for line in f:
        storm = json.loads(line)
        storms.append(storm)

print(f"Loaded {len(storms)} storms")

# Load trajectories
print("Loading trajectories...")
trajectories = []
trajectory_by_actor = {}
with open("data/derived/storm_trajectories.jsonl", 'r') as f:
    for line in f:
        traj = json.loads(line)
        trajectories.append(traj)
        trajectory_by_actor[traj['actor']] = traj

print(f"Loaded {len(trajectories)} trajectories")

# Generate comparison report
print("\n" + "="*70)
print("GENERATING COMPARISON REPORT")
print("="*70)

report_lines = []
report_lines.append("# Storm Clustering Comparison Report")
report_lines.append("")
report_lines.append("Side-by-side comparison of baseline vs clustered summaries for clustering-eligible storms.")
report_lines.append("")
report_lines.append("---")
report_lines.append("")

clustered_count = 0
improved_count = 0

for storm in storms:
    actor = storm.get('actor')
    trajectory = trajectory_by_actor.get(actor)
    
    # Convert to expected format
    storm_formatted = {
        'storm_id': storm['storm_id'],
        'actors': [actor],
        'event_count': storm['event_count'],
        'representative_titles': [e['title'] for e in storm.get('representative_events', [])],
        'cluster_titles_topN': storm.get('cluster_titles_topN', []),
        'tags': storm.get('tags', [])
    }
    
    # Generate baseline summary (no clustering)
    baseline = generate_storm_summary(storm_formatted, trajectory, title_embeddings_map, use_clustering=False)
    
    # Generate clustered summary
    clustered = generate_storm_summary(storm_formatted, trajectory, title_embeddings_map, use_clustering=True)
    
    # Only include if clustering was actually used
    if not clustered.get('used_topic_clustering'):
        continue
    
    clustered_count += 1
    
    # Check if improved (different headline)
    improved = baseline['headline'] != clustered['headline']
    if improved:
        improved_count += 1
    
    # Add to report
    report_lines.append(f"## Storm {clustered_count}: {storm['storm_id']}")
    report_lines.append("")
    report_lines.append(f"**Actor**: {actor}")
    report_lines.append(f"**Event Count**: {storm['event_count']}")
    report_lines.append(f"**State**: {clustered['state']}")
    report_lines.append("")
    
    # Display titles
    report_lines.append("### Top 3 Display Titles")
    report_lines.append("")
    for i, title in enumerate(storm_formatted['representative_titles'][:3], 1):
        report_lines.append(f"{i}. {title}")
    report_lines.append("")
    
    # Cluster title pool
    report_lines.append(f"### Cluster Title Pool ({len(storm_formatted['cluster_titles_topN'])} titles)")
    report_lines.append("")
    for i, title in enumerate(storm_formatted['cluster_titles_topN'][:5], 1):
        report_lines.append(f"{i}. {title}")
    if len(storm_formatted['cluster_titles_topN']) > 5:
        report_lines.append(f"... and {len(storm_formatted['cluster_titles_topN']) - 5} more")
    report_lines.append("")
    
    # Clustering info
    report_lines.append("### Clustering Analysis")
    report_lines.append("")
    report_lines.append(f"- **Clusters**: {clustered['num_title_clusters']}")
    report_lines.append(f"- **Dominant Cluster Size**: {clustered['dominant_cluster_size']}")
    report_lines.append(f"- **Dominance Ratio**: {clustered['cluster_dominance_ratio']:.2f}")
    if clustered.get('dominant_cluster_terms'):
        report_lines.append(f"- **Dominant Terms**: {', '.join(clustered['dominant_cluster_terms'])}")
    if clustered.get('dominant_cluster_bigrams'):
        report_lines.append(f"- **Dominant Bigrams**: {', '.join(clustered['dominant_cluster_bigrams'])}")
    report_lines.append("")
    
    # Baseline summary
    report_lines.append("### Baseline Summary (No Clustering)")
    report_lines.append("")
    report_lines.append(f"**Headline**: {baseline['headline']}")
    report_lines.append(f"**One-liner**: {baseline['one_liner']}")
    report_lines.append(f"**Confidence**: {baseline['summary_confidence']}")
    if baseline.get('themes'):
        report_lines.append(f"**Themes**: {', '.join(baseline['themes'])}")
    if baseline.get('domain_phrases'):
        report_lines.append(f"**Domain Phrases**: {', '.join(baseline['domain_phrases'])}")
    report_lines.append("")
    
    # Clustered summary
    report_lines.append("### Clustered Summary")
    report_lines.append("")
    report_lines.append(f"**Headline**: {clustered['headline']}")
    report_lines.append(f"**One-liner**: {clustered['one_liner']}")
    report_lines.append(f"**Confidence**: {clustered['summary_confidence']}")
    if clustered.get('themes'):
        report_lines.append(f"**Themes**: {', '.join(clustered['themes'])}")
    if clustered.get('domain_phrases'):
        report_lines.append(f"**Domain Phrases**: {', '.join(clustered['domain_phrases'])}")
    report_lines.append("")
    
    # Improvement assessment
    if improved:
        report_lines.append("**✅ Improved**: Headline changed with clustering")
    else:
        report_lines.append("**➖ No Change**: Headline identical")
    report_lines.append("")
    
    # Dominance assessment
    dominance = clustered['cluster_dominance_ratio']
    if dominance >= 0.6:
        report_lines.append("**Coherence**: Strong (high dominance)")
    elif dominance >= 0.4:
        report_lines.append("**Coherence**: Moderate (mixed topics)")
    else:
        report_lines.append("**Coherence**: Weak (fragmented)")
    report_lines.append("")
    
    report_lines.append("---")
    report_lines.append("")

# Summary
report_lines.append("## Summary")
report_lines.append("")
report_lines.append(f"- **Total storms analyzed**: {len(storms)}")
report_lines.append(f"- **Clustering-eligible storms**: {clustered_count}")
report_lines.append(f"- **Improved headlines**: {improved_count} ({improved_count/clustered_count*100:.1f}%)")
report_lines.append(f"- **No change**: {clustered_count - improved_count} ({(clustered_count-improved_count)/clustered_count*100:.1f}%)")
report_lines.append("")

# Write report
report_text = '\n'.join(report_lines)
with open("CLUSTERING_COMPARISON_REPORT.md", 'w') as f:
    f.write(report_text)

print(f"\n✅ Report generated: CLUSTERING_COMPARISON_REPORT.md")
print(f"\nClustering-eligible storms: {clustered_count}")
print(f"Improved headlines: {improved_count} ({improved_count/clustered_count*100:.1f}%)")
print(f"No change: {clustered_count - improved_count}")

print("\n" + "="*70)
print("COMPARISON REPORT COMPLETE")
print("="*70)
