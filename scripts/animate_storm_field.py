#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
import numpy as np
import imageio
from src.animate_field import (
    generate_animation_windows, fit_global_pca, project_events_storms,
    get_window_data, compute_density_for_window, plot_frame
)

print("="*70)
print("ANIMATING STORM FIELD")
print("="*70)

# Load data
print("\nLoading data...")
events = []
with open('data/normalized/tech_ecosystem.jsonl', 'r') as f:
    for line in f:
        events.append(json.loads(line))

storms = []
with open('data/derived/actor_storms.jsonl', 'r') as f:
    for line in f:
        storms.append(json.loads(line))

data = np.load('data/derived/tech_ecosystem_embeddings.npz')
embeddings = data['embeddings']
event_ids = data['event_ids']
embedding_lookup = {str(eid): embeddings[i] for i, eid in enumerate(event_ids)}

print(f"  {len(events)} events")
print(f"  {len(storms)} storms")

# Filter to key actors for readability
FILTER_ACTORS = ['TSM']  # TSM has multiple moderate-sized storms with clear trajectories
events = [e for e in events if any(actor in e.get('actors', []) for actor in FILTER_ACTORS)]
storms = [s for s in storms if s['actor'] in FILTER_ACTORS]

# Filter to last 2 months only
from datetime import datetime as dt
cutoff_date = dt(2026, 2, 1)  # Start from Feb 1
events = [e for e in events if dt.fromisoformat(e['timestamp'].rstrip('Z')) >= cutoff_date]
storms = [s for s in storms if dt.fromisoformat(s['created_at'].rstrip('Z').replace('+00:00', '')) >= cutoff_date]

print(f"  Filtered to {len(events)} events, {len(storms)} storms (last 2 months)")

# Fit global PCA
print("\nFitting global PCA...")
pca = fit_global_pca(storms, events, embedding_lookup)
print(f"  Explained variance: PC1={pca.explained_variance_ratio_[0]:.3f}, PC2={pca.explained_variance_ratio_[1]:.3f}")

# Project all data
print("\nProjecting events and storms...")
project_events_storms(events, storms, embedding_lookup, pca)

# Generate windows
print("\nGenerating animation windows...")
windows = generate_animation_windows(events)  # Auto-detect from filtered events
print(f"  {len(windows)} windows")

# Compute global limits
all_x = [e['time_x'] for e in events if e.get('time_x') is not None]
all_y = [e['semantic_y'] for e in events if e.get('semantic_y') is not None]
all_c = [e['semantic_c'] for e in events if e.get('semantic_c') is not None]

x_min, x_max = min(all_x), max(all_x)
y_min, y_max = min(all_y), max(all_y)
vmin, vmax = min(all_c), max(all_c)

x_range = x_max - x_min
y_range = y_max - y_min
x_lim = (x_min - x_range * 0.05, x_max + x_range * 0.05)
y_lim = (y_min - y_range * 0.15, y_max + y_range * 0.30)  # Extra padding at top for labels

print(f"  Global limits: x={x_lim}, y={y_lim}")

# Render frames
print("\nRendering frames...")
frames = []
total_events_plotted = 0
total_storms_plotted = 0

# Track cumulative data
all_events_cumulative = []
all_storms_cumulative = []

for i, window in enumerate(windows):
    print(f"  Frame {i+1}/{len(windows)}: through {window['end'].strftime('%Y-%m-%d')}")
    
    # Get NEW events/storms in this window
    window_events, window_storms = get_window_data(window, events, storms)
    
    # Add to cumulative lists
    all_events_cumulative.extend(window_events)
    all_storms_cumulative.extend(window_storms)
    
    # Compute density from cumulative events
    density_data = compute_density_for_window(all_events_cumulative, x_lim[0], x_lim[1], y_lim[0], y_lim[1])
    
    # Plot frame with ALL accumulated data
    frame = plot_frame(window, all_events_cumulative, all_storms_cumulative, x_lim, y_lim, vmin, vmax,
                      density_data=density_data, frame_num=i+1, total_frames=len(windows))
    frames.append(frame)
    
    total_events_plotted = len(all_events_cumulative)
    total_storms_plotted = len(all_storms_cumulative)

# Save GIF with no loop
output_path = 'data/derived/storm_field_animation_filtered.gif'
print(f"\nSaving animation to {output_path}...")
print(f"  Total frames: {len(frames)}")
imageio.mimsave(output_path, frames, duration=5.0, loop=1)  # loop=1 means play once

print("\n" + "="*70)
print("ANIMATION COMPLETE")
print("="*70)
print(f"\nRendered {len(frames)} frames")
print(f"Plotted {total_events_plotted} events across windows")
print(f"Plotted {total_storms_plotted} storms across windows")
print(f"\nWrote:")
print(f"  {output_path}")
print("="*70)
