#!/usr/bin/env python3
"""
Filter tech_ecosystem.jsonl → tech_ecosystem_filtered.jsonl.
Rule: keep events where actor is known (not '?' and not empty).
Appends only events not already present in the filtered file.
"""
import json
from pathlib import Path

data_dir    = Path(__file__).parent.parent / 'data' / 'normalized'
src_path    = data_dir / 'tech_ecosystem.jsonl'
filt_path   = data_dir / 'tech_ecosystem_filtered.jsonl'

src_events  = [json.loads(l) for l in open(src_path) if l.strip()]
existing_ids = set()
if filt_path.exists():
    existing_ids = {json.loads(l)['event_id'] for l in open(filt_path) if l.strip()}

new_events = [
    e for e in src_events
    if e['event_id'] not in existing_ids
    and len(e.get('actors') or []) > 0
]

if new_events:
    with open(filt_path, 'a') as f:
        for e in new_events:
            f.write(json.dumps(e) + '\n')

total = len(existing_ids) + len(new_events)
print(f"filter_events: {len(new_events)} new events added → {total} total in filtered file")
print(f"  (skipped {len(src_events) - len(new_events) - len(existing_ids)} unresolved-actor events from source)")
