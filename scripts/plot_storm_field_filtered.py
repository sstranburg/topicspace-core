#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

from src.visualize_field import (
    load_actor_storms, load_storm_trajectories, load_events, load_embeddings,
    compute_storm_centroids, project_to_2d, assign_time_positions,
    assign_events_to_storms, plot_storm_field
)

print("Generating filtered storm field visualizations (NVDA, AMD, TSM, MSFT)...\n")

# Load and process data
storms = load_actor_storms()
trajectories = load_storm_trajectories()
events = load_events()
embedding_lookup, embeddings = load_embeddings()

storms = compute_storm_centroids(storms, events, embedding_lookup)
storms, events = project_to_2d(storms, events, embedding_lookup)
storms, events = assign_time_positions(storms, events)
storms = assign_events_to_storms(storms, events)

# Generate filtered visualizations
filter_actors = ['NVDA', 'AMD', 'TSM', 'MSFT']

# 1D version
output_path_1d = "data/derived/storm_field_filtered.png"
event_count_1d, storm_count_1d, traj_count_1d = plot_storm_field(
    storms, trajectories, output_path_1d, filter_actors=filter_actors, use_2d_semantic=False
)

# 2D semantic version
output_path_2d = "data/derived/storm_field_filtered_2d_semantic.png"
event_count_2d, storm_count_2d, traj_count_2d = plot_storm_field(
    storms, trajectories, output_path_2d, filter_actors=filter_actors, use_2d_semantic=True
)

# 2D semantic version WITH DENSITY
output_path_2d_density = "data/derived/storm_field_filtered_2d_semantic_with_density.png"
event_count_2d_d, storm_count_2d_d, traj_count_2d_d, density_events = plot_storm_field(
    storms, trajectories, output_path_2d_density, filter_actors=filter_actors, 
    use_2d_semantic=True, show_density=True
)

print(f"\u2713 Filtered visualizations saved")
print(f"  Actors: {', '.join(filter_actors)}")
print(f"  1D version: {output_path_1d}")
print(f"    {event_count_1d} events, {storm_count_1d} storms, {traj_count_1d} trajectories")
print(f"  2D semantic version: {output_path_2d}")
print(f"    {event_count_2d} events, {storm_count_2d} storms, {traj_count_2d} trajectories")
print(f"  2D semantic with density: {output_path_2d_density}")
print(f"    {event_count_2d_d} events, {storm_count_2d_d} storms, {traj_count_2d_d} trajectories")
print(f"    Density built from {density_events} events")
