#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

from src.visualize_field import (
    load_actor_storms, load_storm_trajectories, load_events, load_embeddings,
    compute_storm_centroids, project_to_2d, assign_time_positions,
    assign_events_to_storms, plot_storm_field
)

print("="*70)
print("STORM FIELD VISUALIZATION")
print("="*70)

# Step 1: Load data
print("\nStep 1: Loading data...")
storms = load_actor_storms()
trajectories = load_storm_trajectories()
events = load_events()
embedding_lookup, embeddings = load_embeddings()

print(f"  Loaded {len(storms)} storms")
print(f"  Loaded {len(trajectories)} trajectories")
print(f"  Loaded {len(events)} events")
print(f"  Loaded {embeddings.shape[0]} embeddings")

# Step 2: Compute storm centroids
print("\nStep 2: Computing storm centroids...")
storms = compute_storm_centroids(storms, events, embedding_lookup)
valid_centroids = sum(1 for s in storms if s['centroid'] is not None)
print(f"  Computed {valid_centroids}/{len(storms)} storm centroids")

# Step 3: Project to 2-D
print("\nStep 3: Projecting to 2-D semantic space...")
storms, events = project_to_2d(storms, events, embedding_lookup)

# Step 4: Assign time positions
print("\nStep 4: Assigning time positions...")
storms, events = assign_time_positions(storms, events)

# Step 5: Assign events to storms
print("\nStep 5: Mapping events to storms...")
storms = assign_events_to_storms(storms, events)
total_mapped = sum(len(s.get('events', [])) for s in storms)
print(f"  Mapped {total_mapped} events to storms")

# Step 6-10: Generate visualizations (both 1D and 2D)
print("\nStep 6-10: Generating visualizations...")

# Generate 1D version (original)
output_path_1d = "data/derived/storm_field_real_data.png"
event_count, storm_count, traj_count, _ = plot_storm_field(storms, trajectories, output_path_1d, use_2d_semantic=False)

# Generate 2D semantic version
output_path_2d = "data/derived/storm_field_real_data_2d_semantic.png"
event_count_2d, storm_count_2d, traj_count_2d, _ = plot_storm_field(storms, trajectories, output_path_2d, use_2d_semantic=True)

# Generate 2D semantic version WITH DENSITY
output_path_2d_density = "data/derived/storm_field_real_data_2d_semantic_with_density.png"
event_count_2d_d, storm_count_2d_d, traj_count_2d_d, density_events, _ = plot_storm_field(
    storms, trajectories, output_path_2d_density, use_2d_semantic=True, show_density=True
)

print("\n" + "="*70)
print("VISUALIZATION COMPLETE")
print("="*70)
print(f"\nPlotted:")
print(f"  {event_count} events")
print(f"  {storm_count} storms")
print(f"  {traj_count} trajectories")
print(f"\nDensity field:")
print(f"  Built from {density_events} events")
print(f"  Grid shape: ({180}, {250})")
print(f"  Weighted density: no")
print(f"\nOutput files:")
print(f"  1D version: {output_path_1d}")
print(f"  2D semantic version: {output_path_2d}")
print(f"  2D semantic with density: {output_path_2d_density}")

print("\n" + "="*70)
print("To generate filtered view, modify the script to pass filter_actors parameter")
print("Example: plot_storm_field(storms, trajectories, output_path, filter_actors=['NVDA', 'AMD'])")
print("="*70)
