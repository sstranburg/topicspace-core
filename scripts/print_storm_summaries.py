#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
from datetime import datetime

print("="*80)
print("STORM DETECTION SYSTEM - DETAILED STORM SUMMARIES")
print("="*80)

# Load storms
with open("data/derived/actor_storms.jsonl", 'r') as f:
    storms = [json.loads(line) for line in f]

print(f"\nTotal storms detected: {len(storms)}\n")

# Group by actor
from collections import defaultdict
storms_by_actor = defaultdict(list)
for storm in storms:
    storms_by_actor[storm['actor']].append(storm)

# Print each storm
for actor in sorted(storms_by_actor.keys()):
    actor_storms = storms_by_actor[actor]
    
    print("="*80)
    print(f"ACTOR: {actor}")
    print("="*80)
    print(f"Total storms: {len(actor_storms)}\n")
    
    for i, storm in enumerate(actor_storms, 1):
        # Parse dates
        created = storm['created_at'][:10]
        updated = storm['updated_at'][:10]
        
        # Calculate duration
        created_dt = datetime.fromisoformat(storm['created_at'].rstrip('Z'))
        updated_dt = datetime.fromisoformat(storm['updated_at'].rstrip('Z'))
        duration_days = (updated_dt - created_dt).days
        
        print(f"STORM #{i}: {storm['storm_id']}")
        print("-" * 80)
        print(f"Time Period:     {created} to {updated} ({duration_days} days)")
        print(f"Event Count:     {storm['event_count']} events")
        print(f"")
        print(f"Representative Events (Top 5):")
        
        for j, rep in enumerate(storm['representative_events'][:5], 1):
            print(f"  {j}. {rep['title']}")
        
        print(f"")
        print(f"Event IDs: {len(storm['event_ids'])} total")
        print(f"  First 3: {', '.join(storm['event_ids'][:3])}")
        print("")

print("="*80)
print("END OF STORM SUMMARIES")
print("="*80)
