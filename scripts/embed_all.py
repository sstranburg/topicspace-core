#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import numpy as np
from src.embed_events import embed_events

# Paths
input_jsonl = "data/normalized/tech_ecosystem.jsonl"
output_npz = "data/derived/tech_ecosystem_embeddings.npz"
output_jsonl = "data/derived/tech_ecosystem_embedded.jsonl"

print("=== Step 7: Embedding Events ===\n")

# Generate embeddings
embeddings, event_ids = embed_events(input_jsonl, output_npz, output_jsonl)

# Verify
print("\n=== Verification ===")
print(f"Embedding file exists: {output_npz}")
print(f"Shape: {embeddings.shape}")
print(f"Contains NaNs: {np.isnan(embeddings).any()}")
print(f"Event IDs: {len(event_ids)}")

# Test lookup
print(f"\nSample event_id: {event_ids[0]}")
print(f"Sample embedding (first 5 dims): {embeddings[0][:5]}")

# Load and verify
print("\n=== Loading saved embeddings ===")
loaded = np.load(output_npz)
print(f"Keys in NPZ: {list(loaded.keys())}")
print(f"Loaded embeddings shape: {loaded['embeddings'].shape}")
print(f"Loaded event_ids count: {len(loaded['event_ids'])}")

print("\n✅ Step 7 complete!")
