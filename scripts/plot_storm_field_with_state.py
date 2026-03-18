#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

from src.visualize_field import (
    load_actor_storms, load_storm_trajectories, load_events, load_embeddings,
    compute_storm_centroids, project_to_2d, assign_time_positions,
    assign_events_to_storms, plot_storm_field
)

print("="*70)
print("STORM FIELD VISUALIZATION WITH STATE")
print("="*70)

print("\nStep 1: Loading data...")
storms = load_actor_storms()
trajectories = load_storm_trajectories()
events = load_events()
embedding_lookup, embeddings = load_embeddings()
print(f"  Loaded {len(storms)} storms")
print(f"  Loaded {len(trajectories)} trajectories")
print(f"  Loaded {len(events)} events")
print(f"  Loaded {len(embeddings)} embeddings")

print("\nStep 2: Computing storm centroids...")
storms = compute_storm_centroids(storms, events, embedding_lookup)
valid_centroids = sum(1 for s in storms if s['centroid'] is not None)
print(f"  Computed {valid_centroids}/{len(storms)} storm centroids")

print("\nStep 3: Projecting to 2-D semantic space...")
storms, events = project_to_2d(storms, events, embedding_lookup)

print("\nStep 4: Assigning time positions...")
storms, events = assign_time_positions(storms, events)

print("\nStep 5: Mapping events to storms...")
storms = assign_events_to_storms(storms, events)
mapped_events = sum(len(s.get('events', [])) for s in storms)
print(f"  Mapped {mapped_events} events to storms")

print("\nStep 6: Generating state-aware visualizations...")

# Full dataset with state
output_path = "data/derived/storm_field_real_data_2d_semantic_with_density_and_state.png"
result = plot_storm_field(
    storms, trajectories, output_path,
    use_2d_semantic=True, show_density=True, show_state=True
)
event_count, storm_count, traj_count, density_count, state_counts = result
print(f"\n  Full dataset:")
print(f"    {event_count} events, {storm_count} storms, {traj_count} trajectories")
print(f"    Density from {density_count} events")
print(f"    → {output_path}")

# Filtered dataset with state
output_path_filtered = "data/derived/storm_field_filtered_2d_semantic_with_density_and_state.png"
result_filtered = plot_storm_field(
    storms, trajectories, output_path_filtered,
    filter_actors=['NVDA', 'AMD', 'TSM', 'MSFT'],
    use_2d_semantic=True, show_density=True, show_state=True
)
event_count_f, storm_count_f, traj_count_f, density_count_f, state_counts_f = result_filtered
print(f"\n  Filtered (NVDA, AMD, TSM, MSFT):")
print(f"    {event_count_f} events, {storm_count_f} storms, {traj_count_f} trajectories")
print(f"    Density from {density_count_f} events")
print(f"    → {output_path_filtered}")

print("\n" + "="*70)
print("VISUALIZATION COMPLETE")
print("="*70)

print(f"\nPlotted {storm_count} storms total")
print(f"Labeled {min(7, sum(1 for s in state_counts.values() if s > 0))} storms with state")

print(f"\nState counts (full dataset):")
for state in sorted(state_counts.keys()):
    print(f"  {state}: {state_counts[state]}")

print(f"\nState counts (filtered):")
for state in sorted(state_counts_f.keys()):
    print(f"  {state}: {state_counts_f[state]}")

print(f"\nWrote:")
print(f"  {output_path}")
print(f"  {output_path_filtered}")

print("\n" + "="*70)
print("Parameter values used for state derivation:")
print("="*70)
from src.storm_tracking import (
    MIN_DENSITY_FOR_STATE, SMALL_MOMENTUM, GROWTH_THRESHOLD, FADE_THRESHOLD,
    LOW_DRIFT, HIGH_DRIFT, STABLE_MIN_WINDOWS, EMERGING_MAX_WINDOWS,
    HIGH_DENSITY, MODERATE_DENSITY
)
print(f"  MIN_DENSITY_FOR_STATE = {MIN_DENSITY_FOR_STATE}")
print(f"  SMALL_MOMENTUM = {SMALL_MOMENTUM}")
print(f"  GROWTH_THRESHOLD = {GROWTH_THRESHOLD}")
print(f"  FADE_THRESHOLD = {FADE_THRESHOLD}")
print(f"  LOW_DRIFT = {LOW_DRIFT}")
print(f"  HIGH_DRIFT = {HIGH_DRIFT}")
print(f"  STABLE_MIN_WINDOWS = {STABLE_MIN_WINDOWS}")
print(f"  EMERGING_MAX_WINDOWS = {EMERGING_MAX_WINDOWS}")
print(f"  HIGH_DENSITY = {HIGH_DENSITY}")
print(f"  MODERATE_DENSITY = {MODERATE_DENSITY}")

print("\n" + "="*70)
print("To regenerate:")
print("="*70)
print("  Trajectories: python3 scripts/track_storms.py")
print("  Plots: python3 scripts/plot_storm_field_with_state.py")
