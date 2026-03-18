#!/usr/bin/env python3
"""Track ecosystem storms over time using sliding windows (mirrors actor storm logic)."""

import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import numpy as np
import json
from src.merge_events import load_jsonl
from src.storm_tracking import track_storms_over_time

print("=== Ecosystem Storm Tracking (Sliding Windows) ===\n")

# Load events
print("Loading events...")
events = load_jsonl("data/normalized/tech_ecosystem_filtered.jsonl")
print(f"Loaded {len(events)} events")

# Load embeddings
print("Loading embeddings...")
data = np.load("data/derived/tech_ecosystem_embeddings.npz")
embeddings = data['embeddings']
event_ids = data['event_ids']
print(f"Loaded {len(embeddings)} embeddings")

# Create event lookup
event_lookup = {e.event_id: e for e in events}

# Prepare ALL events for ecosystem tracking (not grouped by actor)
print("\nPreparing ecosystem event set...")
ecosystem_events = []
for i, event_id in enumerate(event_ids):
    event = event_lookup[event_id]
    ecosystem_events.append({
        'idx': i,
        'event_id': event.event_id,
        'timestamp': event.timestamp,
        'title': event.title,
        'actors': event.actors,
        'tags': event.tags
    })

print(f"Ecosystem events: {len(ecosystem_events)}")

# Parameters (stricter than actor-level)
WINDOW_DAYS = 30
STEP_DAYS = 7
TAU_DAYS = 7.0
AFFINITY_THRESHOLD = 0.75  # Stricter than actor-level (0.45)
MIN_EVENTS_PER_STORM = 8   # Higher than actor-level (3)
MATCH_THRESHOLD = 0.75

print(f"\nParameters:")
print(f"  window_days: {WINDOW_DAYS}")
print(f"  step_days: {STEP_DAYS}")
print(f"  tau_days: {TAU_DAYS}")
print(f"  affinity_threshold: {AFFINITY_THRESHOLD}")
print(f"  min_events_per_storm: {MIN_EVENTS_PER_STORM}")
print(f"  match_threshold: {MATCH_THRESHOLD}")

# Track ecosystem storms over time
print("\n" + "="*70)
print("TRACKING ECOSYSTEM STORMS")
print("="*70)

trajectories = track_storms_over_time(
    ecosystem_events,
    embeddings,
    window_days=WINDOW_DAYS,
    step_days=STEP_DAYS,
    tau_days=TAU_DAYS,
    affinity_threshold=AFFINITY_THRESHOLD,
    min_events_per_storm=MIN_EVENTS_PER_STORM,
    match_threshold=MATCH_THRESHOLD
)

print(f"\nFound {len(trajectories)} persistent ecosystem trajectories")

# Show trajectory details
for traj in trajectories[:5]:  # Show top 5
    print(f"\n  Trajectory {traj['trajectory_id']}: {traj['window_count']} windows, {traj['total_events']} total events")
    print(f"    State: {traj['state']} ({traj['state_reason']})")
    print(f"    Latest: Density={traj['latest_density']}, Momentum={traj['latest_momentum']:+d}, Drift={traj['latest_drift']:.3f}")
    if traj['latest_acceleration'] is not None:
        print(f"    Acceleration: {traj['latest_acceleration']:+d}")
    print(f"    Peak ratio: {traj['peak_ratio']:.2f}, Max density: {traj['max_density_seen']}")
    print(f"    State history: {' → '.join(traj['state_history'][:5])}{'...' if len(traj['state_history']) > 5 else ''}")
    
    # Show first window details
    if traj['metrics']:
        metric = traj['metrics'][0]
        print(f"    First window ({metric['window_start'][:10]} to {metric['window_end'][:10]}):")
        print(f"      State: {metric['state']}, Density: {metric['density']}, Momentum: {metric['momentum']:+d}")
        if metric['representative_events']:
            print(f"      Top event: {metric['representative_events'][0]['title'][:60]}...")

print("\n" + "="*70)
print("\n=== Summary ===")
print(f"Total ecosystem trajectories: {len(trajectories)}")

if trajectories:
    avg_windows = sum(t['window_count'] for t in trajectories) / len(trajectories)
    total_events = sum(t['total_events'] for t in trajectories)
    print(f"Average windows per trajectory: {avg_windows:.1f}")
    print(f"Total events in trajectories: {total_events}")

# State distribution
from collections import Counter
state_counts = Counter(t['state'] for t in trajectories)
print(f"\n=== State Distribution ===")
for state in sorted(state_counts.keys()):
    print(f"{state}: {state_counts[state]}")

# Save trajectories
print("\n" + "="*70)
print("SAVING TRAJECTORIES")
print("="*70)

output_path = "data/derived/ecosystem_trajectories.jsonl"
with open(output_path, 'w') as f:
    for traj in trajectories:
        output = {
            'trajectory_id': f"eco_traj_{traj['trajectory_id']}",
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

print(f"✅ Saved {len(trajectories)} trajectories to {output_path}")

# Extract storms from trajectories (each window is a storm snapshot)
print("\n" + "="*70)
print("EXTRACTING ECOSYSTEM STORMS FROM TRAJECTORIES")
print("="*70)

storms = []
storm_id_counter = 0

for traj in trajectories:
    for window_idx, metric in enumerate(traj['metrics']):
        # Get event details for this window
        event_ids = [e['event_id'] for e in metric['representative_events']]
        
        # Collect actors from representative events
        actors_involved = []
        actor_counts = {}
        for e in metric['representative_events']:
            event = event_lookup.get(e['event_id'])
            if event:
                for actor in event.actors:
                    if actor not in actors_involved:
                        actors_involved.append(actor)
                    actor_counts[actor] = actor_counts.get(actor, 0) + 1
        
        # Get dominant actors (top 3)
        sorted_actors = sorted(actor_counts.items(), key=lambda x: x[1], reverse=True)
        dominant_actors = [actor for actor, count in sorted_actors[:3]]
        num_unique_actors = len(actors_involved)
        
        # Compute dominant actor ratio
        total_actor_mentions = sum(actor_counts.values())
        dominant_actor_ratio = sorted_actors[0][1] / total_actor_mentions if sorted_actors and total_actor_mentions > 0 else 0
        
        # Compute actor entropy
        actor_entropy = 0.0
        if total_actor_mentions > 0:
            import math
            for count in actor_counts.values():
                p = count / total_actor_mentions
                if p > 0:
                    actor_entropy -= p * math.log2(p)
        
        # Classify ecosystem scope
        if num_unique_actors == 1:
            scope = "single_actor"
        elif num_unique_actors <= 3:
            scope = "cross_actor"
        else:
            scope = "ecosystem_wide"
        
        # Get unique titles for clustering
        unique_titles = []
        seen_titles = set()
        for e in metric['representative_events']:
            if e['title'] not in seen_titles:
                unique_titles.append(e['title'])
                seen_titles.add(e['title'])
        
        # Compute acceleration (change in momentum from previous window)
        current_momentum = metric['momentum']
        previous_momentum = metric.get('previous_momentum', 0)
        acceleration = current_momentum - previous_momentum if previous_momentum is not None else 0
        
        # Create storm from window
        storm = {
            'storm_id': f"eco_{metric['window_start'][:10]}_{storm_id_counter}",
            'trajectory_id': f"eco_traj_{traj['trajectory_id']}",
            'window_idx': window_idx,
            'created_at': metric['window_start'],
            'updated_at': metric['window_end'],
            'event_count': metric['density'],
            'event_ids': event_ids,
            'actors': actors_involved,
            'actors_involved': actors_involved,
            'dominant_actors': dominant_actors,
            'num_unique_actors': num_unique_actors,
            'dominant_actor_ratio': round(dominant_actor_ratio, 3),
            'actor_entropy': round(actor_entropy, 3),
            'scope': scope,
            'state': metric['state'],
            'momentum': metric['momentum'],
            'acceleration': acceleration,
            'drift': metric['drift'],
            'peak_ratio': metric['peak_ratio'],
            'representative_events': metric['representative_events'][:3],
            'cluster_titles_topN': unique_titles[:10],
            'centroid': None  # Would need to recompute if needed
        }
        storms.append(storm)
        storm_id_counter += 1

# Save storms
storms_output_path = "data/derived/ecosystem_storms.jsonl"

# Deduplicate storms before saving
print("\n" + "="*70)
print("DEDUPLICATING ECOSYSTEM STORMS")
print("="*70)

from datetime import datetime as _dt

def _parse_ts(ts):
    return _dt.fromisoformat(ts.rstrip('Z').replace('+00:00Z', '+00:00'))

def _time_lag_days(storm_a, storm_b):
    """Days between the end of the earlier storm and start of the later."""
    end_a = _parse_ts(storm_a['updated_at'])
    end_b = _parse_ts(storm_b['updated_at'])
    start_a = _parse_ts(storm_a['created_at'])
    start_b = _parse_ts(storm_b['created_at'])
    earlier_end = min(end_a, end_b)
    later_start = max(start_a, start_b)
    lag = (later_start - earlier_end).total_seconds() / 86400.0
    return max(0.0, lag)

def _cosine_sim(storm_a, storm_b, embeddings_map):
    """Mean cosine similarity between representative event embeddings."""
    ids_a = [e['event_id'] for e in storm_a['representative_events']]
    ids_b = [e['event_id'] for e in storm_b['representative_events']]
    embs_a = [embeddings_map[eid] for eid in ids_a if eid in embeddings_map]
    embs_b = [embeddings_map[eid] for eid in ids_b if eid in embeddings_map]
    if not embs_a or not embs_b:
        return 0.0
    centroid_a = np.mean(embs_a, axis=0)
    centroid_b = np.mean(embs_b, axis=0)
    norm_a = np.linalg.norm(centroid_a)
    norm_b = np.linalg.norm(centroid_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(centroid_a / norm_a, centroid_b / norm_b))

def _actor_overlap_score(storm_a, storm_b):
    """Shared actors / max actors in either storm."""
    actors_a = set(storm_a['actors'])
    actors_b = set(storm_b['actors'])
    if not actors_a and not actors_b:
        return 1.0
    if not actors_a or not actors_b:
        return 0.0
    shared = len(actors_a & actors_b)
    return shared / max(len(actors_a), len(actors_b))

def _theme_overlap_score(storm_a, storm_b):
    """Jaccard similarity between domain phrase sets (from cluster_titles_topN)."""
    def phrases(storm):
        words = set()
        for title in storm.get('cluster_titles_topN', []):
            words.update(title.lower().split())
        return words
    p_a = phrases(storm_a)
    p_b = phrases(storm_b)
    if not p_a and not p_b:
        return 1.0
    if not p_a or not p_b:
        return 0.0
    return len(p_a & p_b) / len(p_a | p_b)

def merge_score(storm_a, storm_b, embeddings_map):
    """Compute merge score between two ecosystem storms."""
    cos = _cosine_sim(storm_a, storm_b, embeddings_map)
    actor = _actor_overlap_score(storm_a, storm_b)
    theme = _theme_overlap_score(storm_a, storm_b)
    return 0.6 * cos + 0.25 * actor + 0.15 * theme

def merge_storms(storm_a, storm_b):
    """Merge two storms, combining actors, domain phrases, and representative events."""
    merged_actors = list(dict.fromkeys(storm_a['actors'] + storm_b['actors']))
    merged_titles = list(dict.fromkeys(
        storm_a.get('cluster_titles_topN', []) + storm_b.get('cluster_titles_topN', [])
    ))[:10]
    # Combine and dedupe representative events by event_id, keep top 3 by similarity
    seen = set()
    merged_rep = []
    for e in storm_a['representative_events'] + storm_b['representative_events']:
        if e['event_id'] not in seen:
            seen.add(e['event_id'])
            merged_rep.append(e)
    merged_rep = sorted(merged_rep, key=lambda e: e.get('similarity', 0), reverse=True)[:3]

    # Keep the storm with more events as base, update fields
    base = storm_a if storm_a['event_count'] >= storm_b['event_count'] else storm_b
    other = storm_b if base is storm_a else storm_a

    merged = dict(base)
    merged['actors'] = merged_actors
    merged['actors_involved'] = merged_actors
    merged['event_count'] = base['event_count'] + other['event_count']
    merged['event_ids'] = list(dict.fromkeys(base['event_ids'] + other['event_ids']))
    merged['cluster_titles_topN'] = merged_titles
    merged['representative_events'] = merged_rep
    merged['num_unique_actors'] = len(merged_actors)
    merged['created_at'] = min(base['created_at'], other['created_at'])
    merged['updated_at'] = max(base['updated_at'], other['updated_at'])
    return merged

# Build embeddings lookup by event_id
embeddings_map = {eid: embeddings[i] for i, eid in enumerate(event_ids)}

MERGE_SCORE_THRESHOLD = 0.72
MERGE_TIME_LAG_DAYS = 14

# Greedy merge: sort by event_count descending, merge eligible pairs
storms_sorted = sorted(storms, key=lambda s: s['event_count'], reverse=True)
merged_storms = []

for storm in storms_sorted:
    merged = False
    for i, kept in enumerate(merged_storms):
        lag = _time_lag_days(kept, storm)
        if lag > MERGE_TIME_LAG_DAYS:
            continue
        score = merge_score(kept, storm, embeddings_map)
        if score >= MERGE_SCORE_THRESHOLD:
            merged_storms[i] = merge_storms(kept, storm)
            merged = True
            break
    if not merged:
        merged_storms.append(storm)

kept_storms = merged_storms

print(f"Original storms: {len(storms)}")
print(f"After merging: {len(kept_storms)}")
print(f"Merged {len(storms) - len(kept_storms)} storms")

# Save deduplicated storms
with open(storms_output_path, 'w') as f:
    for storm in kept_storms:
        f.write(json.dumps(storm) + '\n')

print(f"✅ Saved {len(kept_storms)} merged ecosystem storms to {storms_output_path}")

print("\n" + "="*70)
print("ECOSYSTEM STORM TRACKING COMPLETE")
print("="*70)
