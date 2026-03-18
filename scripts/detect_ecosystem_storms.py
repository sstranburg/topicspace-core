#!/usr/bin/env python3
"""Detect ecosystem-level storms across all actors."""

import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
import numpy as np
from src.merge_events import load_jsonl
from src.ecosystem_grouping import detect_ecosystem_storms, summarize_ecosystem_component

print("="*70)
print("ECOSYSTEM STORM DETECTION")
print("="*70)

# Load events
print("\nLoading events...")
events = load_jsonl("data/normalized/tech_ecosystem_filtered.jsonl")
print(f"Loaded {len(events)} events")

# Load embeddings
print("Loading embeddings...")
data = np.load("data/derived/tech_ecosystem_embeddings.npz")
embeddings = data['embeddings']
event_ids = data['event_ids']
print(f"Loaded {len(embeddings)} embeddings")

# Verify alignment
assert len(events) == len(embeddings), "Event/embedding count mismatch"
assert all(e.event_id == eid for e, eid in zip(events, event_ids)), "Event ID mismatch"

# Detect ecosystem storms with stricter parameters
print("\n" + "="*70)
print("DETECTING ECOSYSTEM STORMS (STRICT CLUSTERING)")
print("="*70)

storms = detect_ecosystem_storms(
    events,
    embeddings
    # Uses ecosystem defaults: similarity=0.82, time_window=5 days, min_events=8
)

print(f"\nDetected {len(storms)} ecosystem storms")

# Compute statistics
total_events_in_storms = sum(s['event_count'] for s in storms)
avg_actors_per_storm = sum(s['num_unique_actors'] for s in storms) / len(storms) if storms else 0
cross_actor_storms = sum(1 for s in storms if s['num_unique_actors'] > 1)
single_actor_storms = sum(1 for s in storms if s['num_unique_actors'] == 1)

largest_storm = max(storms, key=lambda x: x['event_count']) if storms else None

print(f"\nStatistics:")
print(f"  Total events in storms: {total_events_in_storms}")
print(f"  Average actors per storm: {avg_actors_per_storm:.1f}")
print(f"  Cross-actor storms: {cross_actor_storms}")
print(f"  Single-actor storms: {single_actor_storms}")

if largest_storm:
    print(f"\nLargest ecosystem storm:")
    print(f"  ID: {largest_storm['storm_id']}")
    print(f"  Events: {largest_storm['event_count']}")
    print(f"  Actors: {', '.join(largest_storm['dominant_actors'])}")
    print(f"  Duration: {(np.datetime64(largest_storm['end_time']) - np.datetime64(largest_storm['start_time'])).astype('timedelta64[D]').astype(int)} days")

# Show top examples
print("\n" + "="*70)
print("TOP 5 ECOSYSTEM STORMS")
print("="*70)

sorted_storms = sorted(storms, key=lambda x: x['event_count'], reverse=True)
for i, storm in enumerate(sorted_storms[:5], 1):
    summary = summarize_ecosystem_component(storm)
    print(f"\n{i}. {storm['storm_id']}")
    print(f"   Events: {storm['event_count']}")
    print(f"   Actors: {', '.join(storm['dominant_actors'])} ({storm['num_unique_actors']} total)")
    print(f"   Dominant actor ratio: {storm['dominant_actor_ratio']:.2f}")
    print(f"   Actor entropy: {storm['actor_entropy']:.2f}")
    print(f"   Duration: {summary['duration_days']} days")
    print(f"   Representative: {summary['representative_titles'][0]}")

# Save storms
print("\n" + "="*70)
print("SAVING ECOSYSTEM STORMS")
print("="*70)

output_path = "data/derived/ecosystem_storms.jsonl"
with open(output_path, 'w') as f:
    for storm in storms:
        f.write(json.dumps(storm) + '\n')

print(f"✅ Saved {len(storms)} ecosystem storms to {output_path}")

print("\n" + "="*70)
print("ECOSYSTEM STORM DETECTION COMPLETE")
print("="*70)
