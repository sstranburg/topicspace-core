#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import numpy as np
import json
from collections import defaultdict
from src.merge_events import load_jsonl
from src.actor_grouping import detect_actor_storms
from src.storm_tracking import track_storms_over_time

print("=== Step 10: Diagnostics and Output Generation ===\n")

# Load events
print("Loading events...")
events = load_jsonl("data/normalized/tech_ecosystem.jsonl")
print(f"Loaded {len(events)} events")

# Load embeddings
print("Loading embeddings...")
data = np.load("data/derived/tech_ecosystem_embeddings.npz")
embeddings = data['embeddings']
event_ids = data['event_ids']

# Create event lookup
event_lookup = {e.event_id: e for e in events}

# Group events by actor
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

print("\n" + "="*70)
print("DIAGNOSTIC STATISTICS")
print("="*70)

# 1. Events per actor
print("\n1. Events per actor:")
for actor in sorted(actor_events.keys()):
    count = len(actor_events[actor])
    print(f"   {actor}: {count} events")

# 2. Events per source
print("\n2. Events per source:")
source_counts = defaultdict(int)
for event in events:
    source_counts[event.source] += 1
for source in sorted(source_counts.keys()):
    print(f"   {source}: {source_counts[source]} events")

# 3. Events per tag
print("\n3. Events per tag:")
tag_counts = defaultdict(int)
for event in events:
    for tag in event.tags:
        tag_counts[tag] += 1
for tag in sorted(tag_counts.keys(), key=lambda x: tag_counts[x], reverse=True):
    print(f"   {tag}: {tag_counts[tag]} events")

# 4. Detect storms for all actors
print("\n4. Actor-level storm detection:")
TAU_DAYS = 7.0
AFFINITY_THRESHOLD = 0.45
MIN_EVENTS_PER_STORM = 3

all_actor_storms = {}
total_events_in_storms = 0
total_singleton_events = 0

for actor in sorted(actor_events.keys()):
    events_for_actor = actor_events[actor]
    
    storms = detect_actor_storms(
        events_for_actor,
        embeddings,
        tau_days=TAU_DAYS,
        affinity_threshold=AFFINITY_THRESHOLD,
        min_events_per_storm=MIN_EVENTS_PER_STORM
    )
    
    all_actor_storms[actor] = storms
    
    events_in_storms = sum(s['event_count'] for s in storms)
    singleton = len(events_for_actor) - events_in_storms
    
    total_events_in_storms += events_in_storms
    total_singleton_events += singleton
    
    print(f"   {actor}: {len(storms)} storms, {events_in_storms} events in storms, {singleton} singletons")

print(f"\n   TOTAL: {sum(len(s) for s in all_actor_storms.values())} storms")
print(f"   Events in storms: {total_events_in_storms}")
print(f"   Singleton/dropped events: {total_singleton_events}")

# 5. Track storms over time
print("\n5. Storm trajectory tracking:")
WINDOW_DAYS = 30
STEP_DAYS = 7
MATCH_THRESHOLD = 0.75

all_trajectories = {}
for actor in sorted(actor_events.keys()):
    events_for_actor = actor_events[actor]
    
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
    
    if trajectories:
        avg_windows = sum(t['window_count'] for t in trajectories) / len(trajectories)
        print(f"   {actor}: {len(trajectories)} trajectories (avg {avg_windows:.1f} windows)")

# Save actor storms
print("\n" + "="*70)
print("SAVING OUTPUTS")
print("="*70)

print("\n6. Saving actor storms to data/derived/actor_storms.jsonl...")
with open("data/derived/actor_storms.jsonl", 'w') as f:
    for actor, storms in all_actor_storms.items():
        for storm in storms:
            output = {
                'actor': actor,
                'storm_id': f"{actor}_{storm['created_at'][:10]}",
                'created_at': storm['created_at'],
                'updated_at': storm['updated_at'],
                'event_count': storm['event_count'],
                'event_ids': storm['event_ids'],
                'representative_events': storm['representative_events']
            }
            f.write(json.dumps(output) + '\n')

storm_count = sum(len(storms) for storms in all_actor_storms.values())
print(f"   Saved {storm_count} storms")

# Save trajectories
print("\n7. Saving storm trajectories to data/derived/storm_trajectories.jsonl...")
with open("data/derived/storm_trajectories.jsonl", 'w') as f:
    for actor, trajectories in all_trajectories.items():
        for traj in trajectories:
            output = {
                'actor': actor,
                'trajectory_id': f"{actor}_traj_{traj['trajectory_id']}",
                'window_count': traj['window_count'],
                'total_events': traj['total_events'],
                'metrics': traj['metrics']
            }
            f.write(json.dumps(output) + '\n')

traj_count = sum(len(trajs) for trajs in all_trajectories.values())
print(f"   Saved {traj_count} trajectories")

# Final assessment
print("\n" + "="*70)
print("ASSESSMENT")
print("="*70)

print("\n✓ Which actors have enough signal?")
for actor in sorted(actor_events.keys()):
    event_count = len(actor_events[actor])
    storm_count = len(all_actor_storms[actor])
    traj_count = len(all_trajectories[actor])
    
    if event_count >= 50 and storm_count >= 1:
        signal = "STRONG"
    elif event_count >= 20:
        signal = "MODERATE"
    else:
        signal = "WEAK"
    
    print(f"   {actor}: {signal} ({event_count} events, {storm_count} storms, {traj_count} trajectories)")

print("\n✓ Are there too many tiny storms?")
tiny_storms = sum(1 for storms in all_actor_storms.values() for s in storms if s['event_count'] == 3)
total_storms = sum(len(storms) for storms in all_actor_storms.values())
print(f"   Storms with exactly 3 events: {tiny_storms}/{total_storms} ({100*tiny_storms/total_storms:.1f}%)")

print("\n✓ Are storms merging too aggressively?")
large_storms = sum(1 for storms in all_actor_storms.values() for s in storms if s['event_count'] > 50)
print(f"   Storms with >50 events: {large_storms}/{total_storms} ({100*large_storms/total_storms:.1f}%)")

print("\n✓ Parameter tuning suggestions:")
if tiny_storms / total_storms > 0.5:
    print("   - Consider lowering min_events_per_storm to 2")
if large_storms / total_storms > 0.3:
    print("   - Consider raising affinity_threshold to 0.50")
if total_singleton_events / len(events) > 0.6:
    print("   - Consider lowering affinity_threshold to 0.40")
if total_singleton_events / len(events) < 0.3:
    print("   - Parameters look well-tuned")

print("\n" + "="*70)
print("✅ Step 10 complete!")
print("="*70)

print("\nGenerated artifacts:")
print("  - data/normalized/tech_ecosystem.jsonl")
print("  - data/derived/tech_ecosystem_embeddings.npz")
print("  - data/derived/tech_ecosystem_embedded.jsonl")
print("  - data/derived/actor_storms.jsonl")
print("  - data/derived/storm_trajectories.jsonl")
