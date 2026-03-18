#!/usr/bin/env python3
"""Incrementally embed only new events that don't have embeddings yet."""
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
import numpy as np
from src.embed_events import get_embeddings_batch
from src.merge_events import load_jsonl

print("=== Incremental Embedding ===\n")

# Paths
input_jsonl = "data/normalized/tech_ecosystem_filtered.jsonl"
output_npz = "data/derived/tech_ecosystem_embeddings.npz"
output_jsonl = "data/derived/tech_ecosystem_embedded.jsonl"

# Load all filtered events
print("Loading filtered events...")
events = load_jsonl(input_jsonl)
print(f"Total filtered events: {len(events)}")

# Load existing embeddings
try:
    print("Loading existing embeddings...")
    data = np.load(output_npz)
    existing_embeddings = data['embeddings']
    existing_event_ids = list(data['event_ids'])
    existing_id_set = set(existing_event_ids)
    print(f"Existing embeddings: {len(existing_embeddings)}")
except FileNotFoundError:
    print("No existing embeddings found, will embed all events")
    existing_embeddings = np.array([]).reshape(0, 3072)
    existing_event_ids = []
    existing_id_set = set()

# Find new events that need embedding
new_events = [e for e in events if e.event_id not in existing_id_set]
print(f"New events to embed: {len(new_events)}")

if len(new_events) == 0:
    print("\n✅ No new events to embed, all events already have embeddings")
    sys.exit(0)

# Embed only new events
print("\nGenerating embeddings for new events...")
texts = [f"{e.title} {e.text}" for e in new_events]
new_embeddings = get_embeddings_batch(texts)

# Normalize new embeddings
norms = np.linalg.norm(new_embeddings, axis=1, keepdims=True)
new_embeddings = new_embeddings / norms

print(f"\nNew embedding shape: {new_embeddings.shape}")
print(f"Checking for NaNs: {np.isnan(new_embeddings).any()}")

# Combine with existing embeddings
all_event_ids = existing_event_ids + [e.event_id for e in new_events]
all_embeddings = np.vstack([existing_embeddings, new_embeddings]) if len(existing_embeddings) > 0 else new_embeddings

# Create event_id to index mapping for reordering
event_id_to_idx = {eid: i for i, eid in enumerate(all_event_ids)}

# Reorder to match filtered events order
ordered_embeddings = []
ordered_event_ids = []
for event in events:
    if event.event_id in event_id_to_idx:
        idx = event_id_to_idx[event.event_id]
        ordered_embeddings.append(all_embeddings[idx])
        ordered_event_ids.append(event.event_id)

ordered_embeddings = np.array(ordered_embeddings)

print(f"\nFinal embedding shape: {ordered_embeddings.shape}")
print(f"Final event count: {len(ordered_event_ids)}")

# Save combined embeddings
print(f"\nSaving embeddings to {output_npz}...")
np.savez(
    output_npz,
    embeddings=ordered_embeddings,
    event_ids=ordered_event_ids
)

# Save metadata
print(f"Saving metadata to {output_jsonl}...")
with open(output_jsonl, 'w') as f:
    for i, event in enumerate(events):
        if event.event_id in ordered_event_ids:
            data = {
                'event_id': event.event_id,
                'timestamp': event.timestamp,
                'actors': event.actors,
                'tags': event.tags,
                'title': event.title,
                'embedding_index': i
            }
            f.write(json.dumps(data) + '\n')

print(f"\n✅ Done! Embedded {len(new_events)} new events")
print(f"Total embeddings: {len(ordered_embeddings)}")
