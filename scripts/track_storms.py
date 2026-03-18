#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import numpy as np
from collections import defaultdict
from src.merge_events import load_jsonl
from src.storm_tracking import track_storms_over_time, MODERATE_DENSITY

print("=== Step 9: Storm Tracking Across Time ===\n")

# Load events
print("Loading events...")
events = load_jsonl("data/normalized/tech_ecosystem.jsonl")
print(f"Loaded {len(events)} events")

# Load embeddings
print("Loading embeddings...")
data = np.load("data/derived/tech_ecosystem_embeddings.npz")
embeddings = data['embeddings']
event_ids = data['event_ids']
print(f"Loaded {len(embeddings)} embeddings")

# Create event lookup
event_lookup = {e.event_id: e for e in events}

# Group events by actor
print("\nGrouping events by actor...")
actor_events = defaultdict(list)
for i, event_id in enumerate(event_ids):
    event = event_lookup[event_id]
    for actor in event.actors:
        actor_events[actor].append({
            'idx': i,
            'event_id': event.event_id,
            'timestamp': event.timestamp,
            'title': event.title,
            'actors': event.actors,
            'tags': event.tags
        })

# Parameters
WINDOW_DAYS = 30
STEP_DAYS = 7
TAU_DAYS = 7.0
AFFINITY_THRESHOLD = 0.45
MIN_EVENTS_PER_STORM = 3
MATCH_THRESHOLD = 0.75

print(f"\nParameters:")
print(f"  window_days: {WINDOW_DAYS}")
print(f"  step_days: {STEP_DAYS}")
print(f"  tau_days: {TAU_DAYS}")
print(f"  affinity_threshold: {AFFINITY_THRESHOLD}")
print(f"  min_events_per_storm: {MIN_EVENTS_PER_STORM}")
print(f"  match_threshold: {MATCH_THRESHOLD}")

# Track storms for each actor
print("\n" + "="*70)
all_trajectories = {}

for actor in sorted(actor_events.keys()):
    events_for_actor = actor_events[actor]
    
    print(f"\n{actor}: {len(events_for_actor)} events")
    
    trajectories = track_storms_over_time(
        events_for_actor,
        embeddings,
        window_days=WINDOW_DAYS,
        step_days=STEP_DAYS,
        tau_days=TAU_DAYS,
        affinity_threshold=AFFINITY_THRESHOLD,
        min_events_per_storm=MIN_EVENTS_PER_STORM,
        match_threshold=MATCH_THRESHOLD
    )
    
    all_trajectories[actor] = trajectories
    
    print(f"  Found {len(trajectories)} persistent storm trajectories")
    
    for traj in trajectories[:3]:  # Show top 3
        print(f"\n  Trajectory {traj['trajectory_id']}: {traj['window_count']} windows, {traj['total_events']} total events")
        print(f"    State: {traj['state']} ({traj['state_reason']})")
        print(f"    Latest: Density={traj['latest_density']}, Momentum={traj['latest_momentum']:+d}, Drift={traj['latest_drift']:.3f}")
        if traj['latest_acceleration'] is not None:
            print(f"    Acceleration: {traj['latest_acceleration']:+d}")
        print(f"    Peak ratio: {traj['peak_ratio']:.2f}, Max density: {traj['max_density_seen']}")
        print(f"    State history: {' → '.join(traj['state_history'][:5])}{'...' if len(traj['state_history']) > 5 else ''}")
        
        for i, metric in enumerate(traj['metrics'][:3]):  # Show first 3 windows
            print(f"    Window {i+1} ({metric['window_start'][:10]} to {metric['window_end'][:10]}):")
            print(f"      State: {metric['state']}, Density: {metric['density']}, Momentum: {metric['momentum']:+d}, Drift: {metric['drift']:.3f}")
            if metric['representative_events']:
                print(f"      Top event: {metric['representative_events'][0]['title'][:60]}...")

print("\n" + "="*70)
print("\n=== Summary ===")

total_trajectories = sum(len(trajs) for trajs in all_trajectories.values())
print(f"Total persistent trajectories: {total_trajectories}")

print(f"\nTrajectories by actor:")
for actor in sorted(all_trajectories.keys()):
    trajs = all_trajectories[actor]
    if trajs:
        avg_windows = sum(t['window_count'] for t in trajs) / len(trajs)
        total_events = sum(t['total_events'] for t in trajs)
        print(f"  {actor}: {len(trajs)} trajectories (avg {avg_windows:.1f} windows, {total_events} events)")

# Analyze trajectory stability
print(f"\n=== Trajectory Stability Analysis ===")
state_counts = {}

for actor in sorted(all_trajectories.keys()):
    trajs = all_trajectories[actor]
    if not trajs:
        continue
    
    print(f"\n{actor}:")
    for traj in trajs[:2]:  # Top 2 per actor
        metrics = traj['metrics']
        
        # Count state
        state = traj['state']
        state_counts[state] = state_counts.get(state, 0) + 1
        
        # Compute average drift
        drifts = [m['drift'] for m in metrics if m['drift'] > 0]
        avg_drift = sum(drifts) / len(drifts) if drifts else 0
        
        # Compute momentum trend
        momentums = [m['momentum'] for m in metrics]
        
        print(f"  Trajectory {traj['trajectory_id']}:")
        print(f"    State: {state}")
        print(f"    Windows: {traj['window_count']}, Events: {traj['total_events']}")
        print(f"    Avg drift: {avg_drift:.3f} (lower = more stable)")
        print(f"    Momentum pattern: {momentums}")

print(f"\n=== Storm States ===")
for state in sorted(state_counts.keys()):
    print(f"{state}: {state_counts[state]}")

print("\n✅ Step 9 complete!")

# Save trajectories with enhanced state information
print("\nSaving trajectories to data/derived/storm_trajectories.jsonl...")
import json

with open("data/derived/storm_trajectories.jsonl", 'w') as f:
    for actor in sorted(all_trajectories.keys()):
        for traj in all_trajectories[actor]:
            output = {
                'trajectory_id': f"{actor}_traj_{traj['trajectory_id']}",
                'actor': actor,
                'state': traj['state'],
                'state_reason': traj['state_reason'],
                'state_history': traj['state_history'],
                'window_count': traj['window_count'],
                'total_events': traj['total_events'],
                'latest_density': traj['latest_density'],
                'latest_momentum': traj['latest_momentum'],
                'latest_drift': traj['latest_drift'],
                'previous_momentum': traj['previous_momentum'],
                'previous_density': traj['previous_density'],
                'latest_acceleration': traj['latest_acceleration'],
                'peak_ratio': traj['peak_ratio'],
                'max_density_seen': traj['max_density_seen'],
                'num_windows_seen': traj['num_windows_seen'],
                'metrics': traj['metrics']
            }
            f.write(json.dumps(output) + '\n')

print("✅ Trajectories saved with enhanced state information!")

# Detect near-emerging storms
print("\nDetecting near-emerging storms...")
near_emerging = []

for actor in sorted(all_trajectories.keys()):
    for traj in all_trajectories[actor]:
        latest = traj['metrics'][-1]
        if (latest['momentum'] > 0 and 
            traj['num_windows_seen'] <= 4 and 
            latest['density'] >= 2 and 
            latest['density'] < MODERATE_DENSITY and
            traj['state'] != 'emerging'):
            near_emerging.append({
                'trajectory_id': f"{actor}_traj_{traj['trajectory_id']}",
                'actor': actor,
                'density': latest['density'],
                'momentum': latest['momentum'],
                'num_windows': traj['num_windows_seen'],
                'state': traj['state'],
                'representative_title': latest['representative_events'][0]['title'] if latest['representative_events'] else 'N/A'
            })

with open("data/derived/near_emerging_storms.jsonl", 'w') as f:
    for storm in near_emerging:
        f.write(json.dumps(storm) + '\n')

print(f"✅ Near-emerging storms detected: {len(near_emerging)}")
if near_emerging:
    print("\nNear-emerging storms:")
    for storm in near_emerging[:5]:
        print(f"  {storm['trajectory_id']}: density={storm['density']}, momentum={storm['momentum']:+d}")
        print(f"    {storm['representative_title'][:70]}...")
