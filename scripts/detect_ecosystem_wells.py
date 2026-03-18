#!/usr/bin/env python3
"""Detect ecosystem storms using density-basin / gravity-well approach."""

import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
import numpy as np
from src.merge_events import load_jsonl
from src.ecosystem_grouping import is_ecosystem_relevant
from src.ecosystem_wells import (
    project_events_to_3d, compute_density_at_points,
    detect_density_peaks, assign_events_to_basins, form_ecosystem_wells
)
from src.ecosystem_summaries import generate_ecosystem_storm_summary
from src.storm_topic_clustering import load_embeddings

print("="*70)
print("ECOSYSTEM WELLS DETECTION (DENSITY-BASIN APPROACH)")
print("="*70)

# Load events
print("\nLoading events...")
events = load_jsonl("data/normalized/tech_ecosystem.jsonl")
print(f"Loaded {len(events)} events")

# Load embeddings
print("Loading embeddings...")
data = np.load("data/derived/tech_ecosystem_embeddings.npz")
embeddings = data['embeddings']
event_ids = data['event_ids']
print(f"Loaded {len(embeddings)} embeddings")

# Filter for ecosystem-relevant events
print("\nFiltering for ecosystem-relevant events...")
relevant_indices = []
relevant_events = []
relevant_embeddings = []

for i, event in enumerate(events):
    if is_ecosystem_relevant(event):
        relevant_indices.append(i)
        relevant_events.append(event)
        relevant_embeddings.append(embeddings[i])

relevant_embeddings = np.array(relevant_embeddings)
n = len(relevant_events)

print(f"Relevant events: {n} (excluded {len(events) - n} out-of-domain)")

# Project to 3D semantic-time space
print("\n" + "="*70)
print("PROJECTING TO SEMANTIC-TIME SPACE")
print("="*70)

coords, pca = project_events_to_3d(relevant_events, relevant_embeddings)
print(f"Projected {n} events to 3D coordinates")

# Compute density at each point
print("\n" + "="*70)
print("COMPUTING DENSITY FIELD")
print("="*70)

densities = compute_density_at_points(coords)
print(f"Computed densities (min={densities.min():.2f}, max={densities.max():.2f}, mean={densities.mean():.2f})")

# Detect density peaks
print("\n" + "="*70)
print("DETECTING DENSITY PEAKS")
print("="*70)

peak_indices = detect_density_peaks(coords, densities)
print(f"Detected {len(peak_indices)} density peaks")

if peak_indices:
    peak_densities = [densities[i] for i in peak_indices]
    print(f"Peak densities: min={min(peak_densities):.2f}, max={max(peak_densities):.2f}, mean={np.mean(peak_densities):.2f}")

# Assign events to basins
print("\n" + "="*70)
print("ASSIGNING EVENTS TO BASINS")
print("="*70)

assignments = assign_events_to_basins(coords, densities, peak_indices)
unassigned_count = np.sum(assignments == -1)
print(f"Assigned {n - unassigned_count} events to basins")
print(f"Unassigned events: {unassigned_count}")

# Form ecosystem wells
print("\n" + "="*70)
print("FORMING ECOSYSTEM WELLS")
print("="*70)

wells = form_ecosystem_wells(
    relevant_events,
    relevant_embeddings,
    coords,
    densities,
    peak_indices,
    assignments
)

print(f"\nFormed {len(wells)} ecosystem wells")

# Compute statistics
if wells:
    total_events_in_wells = sum(w['event_count'] for w in wells)
    avg_size = total_events_in_wells / len(wells)
    largest_size = max(w['event_count'] for w in wells)
    avg_actors = sum(w['num_unique_actors'] for w in wells) / len(wells)
    avg_entropy = sum(w['actor_entropy'] for w in wells) / len(wells)
    
    from collections import Counter
    scope_counts = Counter(w['well_scope'] for w in wells)
    
    print(f"\nEcosystem Wells Diagnostics:")
    print(f"  Relevant events: {n}")
    print(f"  Density peaks detected: {len(peak_indices)}")
    print(f"  Accepted wells: {len(wells)}")
    print(f"  Unassigned events: {unassigned_count}")
    print(f"  Average well size: {avg_size:.1f}")
    print(f"  Largest well size: {largest_size}")
    print(f"  Average actors per well: {avg_actors:.1f}")
    print(f"  Average actor entropy: {avg_entropy:.2f}")
    print(f"  Well scope distribution:")
    for scope, count in scope_counts.most_common():
        print(f"    {scope}: {count}")

# Show top 5 wells
print("\n" + "="*70)
print("TOP 5 ECOSYSTEM WELLS")
print("="*70)

for i, well in enumerate(wells[:5], 1):
    print(f"\n{i}. {well['well_id']}")
    print(f"   Peak density: {well['peak_density']:.2f}")
    print(f"   Events: {well['event_count']}")
    print(f"   Actors: {', '.join(well['dominant_actors'])} ({well['num_unique_actors']} total)")
    print(f"   Dominant actor ratio: {well['dominant_actor_ratio']:.2f}")
    print(f"   Actor entropy: {well['actor_entropy']:.2f}")
    print(f"   Basin radius: {well['basin_radius']:.3f}")
    print(f"   Mean distance to peak: {well['mean_event_distance_to_peak']:.3f}")
    print(f"   Duration: {well['duration_days']} days")
    print(f"   Representative: {well['representative_events'][0]['title']}")

# Save wells
print("\n" + "="*70)
print("SAVING ECOSYSTEM WELLS")
print("="*70)

output_path = "data/derived/ecosystem_wells.jsonl"
with open(output_path, 'w') as f:
    for well in wells:
        f.write(json.dumps(well) + '\n')

print(f"✅ Saved {len(wells)} ecosystem wells to {output_path}")

# Generate summaries
print("\n" + "="*70)
print("GENERATING WELL SUMMARIES")
print("="*70)

title_embeddings_map = load_embeddings()
summaries = []

for well in wells:
    summary = generate_ecosystem_storm_summary(
        well,
        trajectory=None,
        title_embeddings_map=title_embeddings_map,
        use_clustering=True,
        use_llm_naming=False  # Keep simple for comparison
    )
    summaries.append(summary)

# Save summaries
summary_path = "data/derived/ecosystem_well_summaries.jsonl"
with open(summary_path, 'w') as f:
    for summary in summaries:
        f.write(json.dumps(summary) + '\n')

print(f"✅ Saved {len(summaries)} well summaries to {summary_path}")

print("\n" + "="*70)
print("ECOSYSTEM WELLS DETECTION COMPLETE")
print("="*70)
