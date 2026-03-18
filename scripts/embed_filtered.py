#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

from src.embed_events import embed_events

# Paths
input_jsonl = "data/normalized/tech_ecosystem_filtered.jsonl"
output_npz = "data/derived/tech_ecosystem_embeddings.npz"
output_jsonl = "data/derived/tech_ecosystem_embedded.jsonl"

print("=== Embedding Filtered Events ===\n")

# Generate embeddings
embeddings, event_ids = embed_events(input_jsonl, output_npz, output_jsonl)

print(f"\n✅ Embedded {len(event_ids)} events")
print(f"Saved to {output_npz} and {output_jsonl}")
