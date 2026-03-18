#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import numpy as np
import json
from collections import defaultdict
from src.merge_events import load_jsonl
from src.actor_grouping import detect_actor_storms

print("=== Step 8: Actor-Level Storm Detection ===\n")

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

print(f"Found {len(actor_events)} actors")

# Parameters
TAU_DAYS = 7.0
AFFINITY_THRESHOLD = 0.45
MIN_EVENTS_PER_STORM = 3

print(f"\nParameters:")
print(f"  tau_days: {TAU_DAYS}")
print(f"  affinity_threshold: {AFFINITY_THRESHOLD}")
print(f"  min_events_per_storm: {MIN_EVENTS_PER_STORM}")

# Detect storms for each actor
print("\n" + "="*60)
all_storms = {}

for actor in sorted(actor_events.keys()):
    events_for_actor = actor_events[actor]
    
    print(f"\n{actor}: {len(events_for_actor)} events")
    
    storms = detect_actor_storms(
        events_for_actor,
        embeddings,
        tau_days=TAU_DAYS,
        affinity_threshold=AFFINITY_THRESHOLD,
        min_events_per_storm=MIN_EVENTS_PER_STORM
    )
    
    all_storms[actor] = storms
    
    print(f"  Found {len(storms)} storms")
    
    for i, storm in enumerate(storms, 1):
        print(f"\n  Storm {i}: {storm['event_count']} events")
        print(f"    Time range: {storm['created_at'][:10]} to {storm['updated_at'][:10]}")
        print(f"    Top 3 representative events:")
        for j, rep in enumerate(storm['representative_events'], 1):
            print(f"      {j}. {rep['title'][:70]}")

print("\n" + "="*60)
print("\n=== Summary ===")
total_storms = sum(len(storms) for storms in all_storms.values())
total_events_in_storms = sum(
    sum(s['event_count'] for s in storms)
    for storms in all_storms.values()
)

print(f"Total storms detected: {total_storms}")
print(f"Total events in storms: {total_events_in_storms}")
print(f"\nStorms by actor:")
for actor in sorted(all_storms.keys()):
    storms = all_storms[actor]
    if storms:
        events_count = sum(s['event_count'] for s in storms)
        print(f"  {actor}: {len(storms)} storms ({events_count} events)")

# Save storms to file
print("\nSaving storms to data/derived/actor_storms.jsonl...")
with open("data/derived/actor_storms.jsonl", 'w') as f:
    for actor, storms in all_storms.items():
        for storm in storms:
            storm['actor'] = actor
            storm['storm_id'] = f"{actor}_{storm['created_at'][:10]}"
            f.write(json.dumps(storm) + '\n')

print(f"✅ Saved {total_storms} storms")

print("\n✅ Step 8 complete!")
