#!/usr/bin/env python3
"""
Re-run actor detection over existing normalized events using current ACTOR_ALIASES.
Rewrites actors field in-place; does not re-fetch from APIs.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.actors import detect_actors

paths = [
    Path('data/normalized/tech_ecosystem.jsonl'),
    Path('data/normalized/tech_ecosystem_filtered.jsonl'),
]

for path in paths:
    if not path.exists():
        print(f'  skip (not found): {path}')
        continue

    events = []
    with open(path) as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))

    from collections import Counter
    before_counts = Counter(a for e in events for a in e.get('actors', []))

    for e in events:
        text = (e.get('title', '') + ' ' + e.get('text', '')).lower()
        e['actors'] = detect_actors(text)

    after_counts = Counter(a for e in events for a in e.get('actors', []))

    with open(path, 'w') as f:
        for e in events:
            f.write(json.dumps(e) + '\n')

    print(f'\n{path.name}: {len(events)} events reprocessed')
    all_actors = sorted(set(after_counts) | set(before_counts))
    print(f'  {"actor":<8} {"before":>8} {"after":>8} {"delta":>8}')
    for a in all_actors:
        b, af = before_counts.get(a, 0), after_counts.get(a, 0)
        delta = af - b
        marker = ' ← new' if b == 0 and af > 0 else (' ← gained' if delta > 0 else '')
        print(f'  {a:<8} {b:>8} {af:>8} {delta:>+8}{marker}')

print('\n✅ Actor re-detection complete')
