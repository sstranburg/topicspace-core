#!/usr/bin/env python3
"""Compare ecosystem clustering vs wells approaches."""

import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
import numpy as np

print("="*70)
print("ECOSYSTEM METHOD COMPARISON: CLUSTERING VS WELLS")
print("="*70)

# Load clustering-based storms
print("\nLoading clustering-based storms...")
clustering_storms = []
with open("data/derived/ecosystem_storms.jsonl", 'r') as f:
    for line in f:
        clustering_storms.append(json.loads(line))

print(f"Loaded {len(clustering_storms)} clustering-based storms")

# Load well-based storms
print("Loading well-based storms...")
well_storms = []
with open("data/derived/ecosystem_wells.jsonl", 'r') as f:
    for line in f:
        well_storms.append(json.loads(line))

print(f"Loaded {len(well_storms)} well-based storms")

# Load summaries
clustering_summaries = []
with open("data/derived/ecosystem_storm_summaries.jsonl", 'r') as f:
    for line in f:
        clustering_summaries.append(json.loads(line))

well_summaries = []
with open("data/derived/ecosystem_well_summaries.jsonl", 'r') as f:
    for line in f:
        well_summaries.append(json.loads(line))

# Compute statistics
print("\n" + "="*70)
print("SIZE DISTRIBUTION COMPARISON")
print("="*70)

clustering_sizes = [s['event_count'] for s in clustering_storms]
well_sizes = [w['event_count'] for w in well_storms]

print(f"\nClustering-based:")
print(f"  Number of storms: {len(clustering_storms)}")
print(f"  Total events: {sum(clustering_sizes)}")
print(f"  Largest storm: {max(clustering_sizes) if clustering_sizes else 0}")
print(f"  Average storm size: {np.mean(clustering_sizes) if clustering_sizes else 0:.1f}")
print(f"  Median storm size: {np.median(clustering_sizes) if clustering_sizes else 0:.1f}")

print(f"\nWell-based:")
print(f"  Number of wells: {len(well_storms)}")
print(f"  Total events: {sum(well_sizes)}")
print(f"  Largest well: {max(well_sizes) if well_sizes else 0}")
print(f"  Average well size: {np.mean(well_sizes) if well_sizes else 0:.1f}")
print(f"  Median well size: {np.median(well_sizes) if well_sizes else 0:.1f}")

# Actor diversity comparison
print("\n" + "="*70)
print("ACTOR DIVERSITY COMPARISON")
print("="*70)

clustering_actors = [s['num_unique_actors'] for s in clustering_storms]
clustering_entropy = [s['actor_entropy'] for s in clustering_storms]

well_actors = [w['num_unique_actors'] for w in well_storms]
well_entropy = [w['actor_entropy'] for w in well_storms]

print(f"\nClustering-based:")
print(f"  Average actors per storm: {np.mean(clustering_actors) if clustering_actors else 0:.1f}")
print(f"  Average actor entropy: {np.mean(clustering_entropy) if clustering_entropy else 0:.2f}")

print(f"\nWell-based:")
print(f"  Average actors per well: {np.mean(well_actors) if well_actors else 0:.1f}")
print(f"  Average actor entropy: {np.mean(well_entropy) if well_entropy else 0:.2f}")

# Coherence comparison
print("\n" + "="*70)
print("COHERENCE / CONCENTRATION COMPARISON")
print("="*70)

clustering_radius = [s.get('cluster_radius', 0) for s in clustering_storms]
clustering_similarity = [s.get('mean_pairwise_similarity', 0) for s in clustering_storms]

well_distance = [w.get('mean_event_distance_to_peak', 0) for w in well_storms]
well_radius = [w.get('basin_radius', 0) for w in well_storms]

print(f"\nClustering-based:")
print(f"  Average cluster radius: {np.mean(clustering_radius) if clustering_radius else 0:.3f}")
print(f"  Average pairwise similarity: {np.mean(clustering_similarity) if clustering_similarity else 0:.3f}")

print(f"\nWell-based:")
print(f"  Average distance to peak: {np.mean(well_distance) if well_distance else 0:.3f}")
print(f"  Average basin radius: {np.mean(well_radius) if well_radius else 0:.3f}")

# Narrative comparison
print("\n" + "="*70)
print("NARRATIVE COMPARISON (TOP 5)")
print("="*70)

print("\n### CLUSTERING-BASED NARRATIVES ###\n")
for i, summary in enumerate(clustering_summaries[:5], 1):
    print(f"{i}. {summary.get('display_headline', summary['headline'])}")
    print(f"   Events: {summary['event_count']}, Actors: {summary['num_unique_actors']}")
    print(f"   {summary.get('display_one_liner', summary['one_liner'])}")
    print()

print("\n### WELL-BASED NARRATIVES ###\n")
for i, summary in enumerate(well_summaries[:5], 1):
    print(f"{i}. {summary.get('display_headline', summary['headline'])}")
    print(f"   Events: {summary['event_count']}, Actors: {summary['num_unique_actors']}")
    print(f"   {summary.get('display_one_liner', summary['one_liner'])}")
    print()

# Evaluation
print("\n" + "="*70)
print("EVALUATION")
print("="*70)

mega_storm_clustering = max(clustering_sizes) if clustering_sizes else 0
mega_storm_wells = max(well_sizes) if well_sizes else 0

print(f"\n1. Does the well method produce fewer mega-storms?")
if mega_storm_wells < mega_storm_clustering:
    print(f"   ✅ YES - Wells largest: {mega_storm_wells}, Clustering largest: {mega_storm_clustering}")
else:
    print(f"   ❌ NO - Wells largest: {mega_storm_wells}, Clustering largest: {mega_storm_clustering}")

print(f"\n2. Are well boundaries more interpretable?")
if len(well_storms) > 0 and len(well_storms) < len(clustering_storms) * 2:
    print(f"   ⚠️  MIXED - Wells: {len(well_storms)}, Clustering: {len(clustering_storms)}")
    print(f"   Wells create larger but fewer groupings")
else:
    print(f"   ❌ NO - Wells: {len(well_storms)}, Clustering: {len(clustering_storms)}")

print(f"\n3. Do well summaries sound more coherent?")
print(f"   ⚠️  SUBJECTIVE - Review narratives above")

print(f"\n4. Do actor participation patterns look more realistic?")
clustering_avg_actors = np.mean(clustering_actors) if clustering_actors else 0
well_avg_actors = np.mean(well_actors) if well_actors else 0
if abs(well_avg_actors - clustering_avg_actors) < 1.0:
    print(f"   ✅ SIMILAR - Wells: {well_avg_actors:.1f}, Clustering: {clustering_avg_actors:.1f}")
else:
    print(f"   ⚠️  DIFFERENT - Wells: {well_avg_actors:.1f}, Clustering: {clustering_avg_actors:.1f}")

print(f"\n5. Coverage comparison:")
clustering_coverage = sum(clustering_sizes)
well_coverage = sum(well_sizes)
print(f"   Clustering: {clustering_coverage} events")
print(f"   Wells: {well_coverage} events")
print(f"   Difference: {abs(well_coverage - clustering_coverage)} events")

# Write report
print("\n" + "="*70)
print("GENERATING COMPARISON REPORT")
print("="*70)

report_lines = []
report_lines.append("# Ecosystem Method Comparison: Clustering vs Wells")
report_lines.append("")
report_lines.append("## Summary")
report_lines.append("")
report_lines.append(f"**Clustering-based**: {len(clustering_storms)} storms, largest {mega_storm_clustering} events")
report_lines.append(f"**Well-based**: {len(well_storms)} wells, largest {mega_storm_wells} events")
report_lines.append("")

report_lines.append("## Size Distribution")
report_lines.append("")
report_lines.append("| Metric | Clustering | Wells |")
report_lines.append("|--------|-----------|-------|")
report_lines.append(f"| Number of units | {len(clustering_storms)} | {len(well_storms)} |")
report_lines.append(f"| Total events | {sum(clustering_sizes)} | {sum(well_sizes)} |")
report_lines.append(f"| Largest unit | {max(clustering_sizes) if clustering_sizes else 0} | {max(well_sizes) if well_sizes else 0} |")
report_lines.append(f"| Average size | {np.mean(clustering_sizes) if clustering_sizes else 0:.1f} | {np.mean(well_sizes) if well_sizes else 0:.1f} |")
report_lines.append("")

report_lines.append("## Actor Diversity")
report_lines.append("")
report_lines.append("| Metric | Clustering | Wells |")
report_lines.append("|--------|-----------|-------|")
report_lines.append(f"| Avg actors/unit | {np.mean(clustering_actors) if clustering_actors else 0:.1f} | {np.mean(well_actors) if well_actors else 0:.1f} |")
report_lines.append(f"| Avg entropy | {np.mean(clustering_entropy) if clustering_entropy else 0:.2f} | {np.mean(well_entropy) if well_entropy else 0:.2f} |")
report_lines.append("")

report_lines.append("## Coherence Metrics")
report_lines.append("")
report_lines.append("| Metric | Clustering | Wells |")
report_lines.append("|--------|-----------|-------|")
report_lines.append(f"| Avg radius | {np.mean(clustering_radius) if clustering_radius else 0:.3f} | {np.mean(well_radius) if well_radius else 0:.3f} |")
report_lines.append(f"| Avg similarity/distance | {np.mean(clustering_similarity) if clustering_similarity else 0:.3f} | {np.mean(well_distance) if well_distance else 0:.3f} |")
report_lines.append("")

report_lines.append("## Conclusion")
report_lines.append("")
if mega_storm_wells < mega_storm_clustering:
    report_lines.append("✅ Wells method reduces mega-storm size")
else:
    report_lines.append("❌ Wells method does not reduce mega-storm size")

report_lines.append("")
report_lines.append(f"**Recommendation**: {'Continue exploring wells approach' if mega_storm_wells < mega_storm_clustering else 'Clustering approach is currently better'}")

with open("ECOSYSTEM_METHOD_COMPARISON_REPORT.md", 'w') as f:
    f.write('\n'.join(report_lines))

print("✅ Report saved to ECOSYSTEM_METHOD_COMPARISON_REPORT.md")

print("\n" + "="*70)
print("COMPARISON COMPLETE")
print("="*70)
