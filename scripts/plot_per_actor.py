#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

from src.visualize_field import (
    load_actor_storms, load_storm_trajectories, load_events, load_embeddings,
    compute_storm_centroids, project_to_2d, assign_time_positions,
    assign_events_to_storms, plot_storm_field
)
from datetime import datetime as dt

print("="*70)
print("GENERATING PER-ACTOR STORM VISUALIZATIONS")
print("="*70)

# Load data
print("\nLoading data...")
storms = load_actor_storms()
trajectories = load_storm_trajectories()
events = load_events()
embedding_lookup, embeddings = load_embeddings()

# Filter to Feb 1 - March 11, 2026
cutoff_date = dt(2026, 2, 1)
events = [e for e in events if dt.fromisoformat(e['timestamp'].rstrip('Z')) >= cutoff_date]
storms = [s for s in storms if dt.fromisoformat(s['start_ts'].rstrip('Z')).replace(tzinfo=None) >= cutoff_date]

print(f"  Filtered to {len(events)} events, {len(storms)} storms (Feb 1 - March 11)")

# Compute centroids and project
storms = compute_storm_centroids(storms, events, embedding_lookup)
storms, events = project_to_2d(storms, events, embedding_lookup)
storms, events = assign_time_positions(storms, events)
storms = assign_events_to_storms(storms, events)

# Get all actors with storms in this period
actors = sorted(set(s['actor'] for s in storms))
print(f"\nActors with storms: {', '.join(actors)}")

# Generate visualization for each actor
print("\nGenerating visualizations...")
for actor in actors:
    output_path = f"data/derived/storm_field_{actor}_feb_mar.png"
    result = plot_storm_field(
        storms, trajectories, output_path, 
        filter_actors=[actor], use_2d_semantic=True, show_density=True
    )
    event_count, storm_count, traj_count = result[:3]
    print(f"  {actor}: {event_count} events, {storm_count} storms → {output_path}")

print("\n" + "="*70)
print("COMPLETE")
print("="*70)
print(f"\nGenerated {len(actors)} visualizations in data/derived/")
print("Files: storm_field_<ACTOR>_feb_mar.png")
