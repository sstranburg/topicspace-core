#!/usr/bin/env python3
"""Track ecosystem storm trajectories over time."""

import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
from src.ecosystem_tracking import track_ecosystem_trajectories

print("="*70)
print("ECOSYSTEM TRAJECTORY TRACKING")
print("="*70)

# Load ecosystem storms
print("\nLoading ecosystem storms...")
storms = []
with open("data/derived/ecosystem_storms.jsonl", 'r') as f:
    for line in f:
        storms.append(json.loads(line))

print(f"Loaded {len(storms)} ecosystem storms")

# Track trajectories
print("\n" + "="*70)
print("TRACKING TRAJECTORIES")
print("="*70)

trajectories = track_ecosystem_trajectories(
    storms,
    similarity_threshold=0.70,
    max_time_gap_days=14
)

print(f"\nTracked {len(trajectories)} ecosystem trajectories")

# Compute statistics
total_storms_in_trajs = sum(len(t['storm_ids']) for t in trajectories)
avg_storms_per_traj = total_storms_in_trajs / len(trajectories) if trajectories else 0
total_events = sum(t['total_events'] for t in trajectories)

print(f"\nStatistics:")
print(f"  Total storms in trajectories: {total_storms_in_trajs}")
print(f"  Average storms per trajectory: {avg_storms_per_traj:.1f}")
print(f"  Total events: {total_events}")

# State distribution
from collections import Counter
state_counts = Counter(t['state'] for t in trajectories)
print(f"\nState distribution:")
for state, count in state_counts.most_common():
    print(f"  {state}: {count}")

# Show examples
print("\n" + "="*70)
print("TOP 5 ECOSYSTEM TRAJECTORIES")
print("="*70)

sorted_trajs = sorted(trajectories, key=lambda x: x['total_events'], reverse=True)
for i, traj in enumerate(sorted_trajs[:5], 1):
    print(f"\n{i}. {traj['trajectory_id']}")
    print(f"   Actors: {', '.join(traj['actors_involved'][:3])}")
    print(f"   Storms: {traj['num_storms']}")
    print(f"   Events: {traj['total_events']}")
    print(f"   State: {traj['state']}")
    print(f"   Momentum: {traj['latest_momentum']:+d}")
    print(f"   Peak ratio: {traj['peak_ratio']:.2f}")

# Save trajectories
print("\n" + "="*70)
print("SAVING TRAJECTORIES")
print("="*70)

output_path = "data/derived/ecosystem_trajectories.jsonl"
with open(output_path, 'w') as f:
    for traj in trajectories:
        f.write(json.dumps(traj) + '\n')

print(f"✅ Saved {len(trajectories)} trajectories to {output_path}")

print("\n" + "="*70)
print("ECOSYSTEM TRAJECTORY TRACKING COMPLETE")
print("="*70)
