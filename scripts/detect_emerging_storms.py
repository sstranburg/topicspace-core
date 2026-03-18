#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

from src.emerging_storms import detect_emerging_storms, save_emerging_storms
from src.emerging_storms import MIN_MOMENTUM, MIN_DENSITY, MIN_WINDOWS, TOP_K

print("="*70)
print("DETECTING EMERGING STORMS")
print("="*70)

# Load trajectories and compute scores
trajectories_path = 'data/derived/storm_trajectories.jsonl'
storms_path = 'data/derived/actor_storms.jsonl'

# Count total trajectories
import json
total_trajectories = 0
with open(trajectories_path, 'r') as f:
    for line in f:
        total_trajectories += 1

print(f"\nEvaluating {total_trajectories} trajectories...")
print(f"\nFilters:")
print(f"  MIN_MOMENTUM: {MIN_MOMENTUM}")
print(f"  MIN_DENSITY: {MIN_DENSITY}")
print(f"  MIN_WINDOWS: {MIN_WINDOWS}")
print(f"  TOP_K: {TOP_K}")

emerging_storms = detect_emerging_storms(trajectories_path, storms_path)

print(f"\nFound {len(emerging_storms)} emerging storms")
print("\n" + "="*70)
print("TOP EMERGING STORMS")
print("="*70 + "\n")

for i, storm in enumerate(emerging_storms, 1):
    print(f"{i}. {storm['trajectory_id']}")
    print(f"   actor: {storm['actor']}")
    print(f"   score: {storm['emerging_score']:.2f}")
    print(f"   momentum: {storm['current_momentum']:.1f}")
    print(f"   density: {storm['current_density']:.0f}")
    print(f"   drift: {storm['drift']:.3f}")
    print(f"   age: {storm['age_days']} days ({storm['num_windows']} windows)")
    if storm['latest_titles']:
        print(f"   latest titles:")
        for title in storm['latest_titles'][:2]:
            print(f"     - {title[:70]}")
    print()

# Save output
output_path = 'data/derived/emerging_storms.jsonl'
save_emerging_storms(emerging_storms, output_path)

print("="*70)
print(f"✓ Saved to {output_path}")
print("="*70)
