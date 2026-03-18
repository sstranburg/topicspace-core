#!/usr/bin/env python3
"""
Compute narrative evolution for actor storms.
"""
import json
import sys
import numpy as np
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from narrative_evolution import analyze_storm_evolution


def load_jsonl(path):
    """Load JSONL file."""
    items = []
    with open(path) as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def main():
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data' / 'derived'
    
    # Load storms and embedded events
    storms_path = data_dir / 'actor_storms.jsonl'
    embedded_path = data_dir / 'tech_ecosystem_embedded.jsonl'
    output_path = data_dir / 'narrative_evolution.jsonl'
    
    print("Narrative Evolution Analysis")
    print("----------------------------")
    
    # Load storms
    print(f"Loading storms from {storms_path}...")
    storms = load_jsonl(storms_path)
    print(f"Loaded {len(storms)} storms")
    
    # Load embedded events
    print(f"Loading embedded events from {embedded_path}...")
    embedded_events = load_jsonl(embedded_path)
    event_map = {e['event_id']: e for e in embedded_events}
    print(f"Loaded {len(embedded_events)} embedded events")
    
    # Load embeddings from npz
    embeddings_path = data_dir / 'tech_ecosystem_embeddings.npz'
    print(f"Loading embeddings from {embeddings_path}...")
    embeddings_data = np.load(embeddings_path)
    embeddings_matrix = embeddings_data['embeddings']
    print(f"Loaded embeddings matrix: {embeddings_matrix.shape}")
    
    # Attach embeddings to events
    for event in embedded_events:
        if 'embedding_index' in event:
            idx = event['embedding_index']
            event['embedding'] = embeddings_matrix[idx].tolist()
    print(f"Attached embeddings to events")
    
    # Enrich storms with embeddings
    print("Enriching storms with embeddings...")
    enriched_storms = []
    for storm in storms:
        events_with_embeddings = []
        for event_id in storm.get('event_ids', []):
            if event_id in event_map:
                events_with_embeddings.append(event_map[event_id])
        
        if len(events_with_embeddings) >= 5:
            storm['events'] = events_with_embeddings
            enriched_storms.append(storm)
    
    print(f"Enriched {len(enriched_storms)} storms with embeddings")
    
    # Analyze evolution
    print("Computing narrative evolution...")
    evolutions = []
    for i, storm in enumerate(enriched_storms):
        evolution = analyze_storm_evolution(storm, window_days=7)
        evolutions.append(evolution)
            
        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(enriched_storms)} storms")
    
    # Count by reliability
    reliable_count = sum(1 for e in evolutions if e.get('has_evolution') and e.get('reliability') == 'high')
    moderate_count = sum(1 for e in evolutions if e.get('has_evolution') and e.get('reliability') == 'moderate')
    insufficient_count = sum(1 for e in evolutions if not e.get('has_evolution'))
    
    print(f"Computed evolution for {len(evolutions)} storms")
    print(f"  High reliability: {reliable_count}")
    print(f"  Moderate reliability: {moderate_count}")
    print(f"  Insufficient data: {insufficient_count}")
    
    # Save results
    with open(output_path, 'w') as f:
        for evolution in evolutions:
            f.write(json.dumps(evolution) + '\n')
    
    print(f"\nSaved to {output_path}")
    
    # Print sample
    if evolutions:
        print("\nSample evolution:")
        sample = evolutions[0]
        print(f"  Storm: {sample['storm_id']}")
        if sample.get('has_evolution'):
            print(f"  Drift: {sample.get('avg_drift', 0):.3f} ({sample.get('drift_classification', 'unknown')})")
            print(f"  Reliability: {sample.get('reliability', 'unknown')}")
            print(f"  Phases: {sample.get('window_count', 0)}")
        else:
            print(f"  Status: {sample.get('reliability', 'insufficient_data')}")


if __name__ == '__main__':
    main()
