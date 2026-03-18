#!/usr/bin/env python3
"""
Backfill Feb–Mar 2026 event data for new AI demand-side actors.
Appends to existing tech_ecosystem.jsonl without touching original events.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingest_finnhub import fetch_finnhub_company_news
from src.ingest_newsapi import fetch_newsapi_query
from src.ingest_sec import fetch_sec_submissions
from src.merge_events import dedupe_events, load_jsonl, write_jsonl

START_DATE = '2026-02-01'
END_DATE   = '2026-03-31'

NEW_COMPANIES = [
    ('META', '0001326801'),
    ('ORCL', '0001341439'),
    ('ADBE', '0000796343'),
    ('CRM',  '0001108524'),
    ('TSLA', '0001318605'),
    ('ARM',  None),
    ('SMCI', None),
    ('DELL', None),
    ('INTC', None),
    ('MU',   None),
    ('CRWV', None),
    ('NBIS', None),
]

NEWSAPI_QUERIES = [
    ('META',  'Meta Platforms AI',                          ['META']),
    ('ORCL',  'Oracle cloud AI',                            ['ORCL']),
    ('ADBE',  'Adobe AI generative',                        ['ADBE']),
    ('CRM',   'Salesforce AI CRM',                          ['CRM']),
    ('TSLA',  'Tesla AI autonomous',                        ['TSLA']),
    ('ARM',   'ARM Holdings AI chips semiconductor',        ['ARM']),
    ('SMCI',  '"Super Micro" OR Supermicro AI server',      ['SMCI']),
    ('DELL',  'Dell AI server infrastructure',              ['DELL']),
    ('INTC',  'Intel AI chip foundry semiconductor',        ['INTC']),
    ('MU',    'Micron HBM memory AI chip',                  ['MU']),
    ('SKHX',  '"SK Hynix" HBM memory AI',                  ['SKHX']),
    ('CRWV',  'CoreWeave GPU cloud AI infrastructure',      ['CRWV']),
    ('NBIS',  'Nebius AI cloud infrastructure',             ['NBIS']),
]

output_path = Path('data/normalized/tech_ecosystem.jsonl')

print(f'=== Backfill: new actors {START_DATE} → {END_DATE} ===\n')

new_events = []

# Finnhub
print('1. Finnhub company news...')
for symbol, cik in NEW_COMPANIES:
    try:
        events = fetch_finnhub_company_news(symbol, START_DATE, END_DATE)
        new_events.extend(events)
        print(f'   {symbol}: {len(events)} events')
    except Exception as e:
        print(f'   {symbol}: error — {e}')

# NewsAPI
print('\n2. NewsAPI queries...')
for symbol, query, source_actors in NEWSAPI_QUERIES:
    try:
        events = fetch_newsapi_query(query, START_DATE, page_size=100, source_actors=source_actors)
        new_events.extend(events)
        print(f'   {symbol} "{query}": {len(events)} events')
    except Exception as e:
        print(f'   {symbol}: error — {e}')

# SEC filings (only for actors with a known CIK)
print('\n3. SEC filings...')
for symbol, cik in NEW_COMPANIES:
    if not cik:
        continue
    try:
        events = fetch_sec_submissions(cik, symbol)
        in_window = [e for e in events if START_DATE <= e.timestamp[:10] <= END_DATE]
        new_events.extend(in_window)
        print(f'   {symbol}: {len(in_window)} filings in window')
    except Exception as e:
        print(f'   {symbol}: error — {e}')

print(f'\nNew events fetched (pre-dedupe): {len(new_events)}')

# Load existing, merge, dedupe
existing = load_jsonl(output_path)
print(f'Existing events: {len(existing)}')

combined = existing + new_events
deduped  = dedupe_events(combined)
deduped.sort(key=lambda e: e.timestamp)

added = len(deduped) - len(existing)
print(f'After dedupe: {len(deduped)} total (+{added} net new)')

write_jsonl(deduped, output_path)
print(f'\n✅ Written to {output_path}')

# Per-actor summary
from collections import Counter
actor_counts = Counter(a for e in deduped for a in e.actors)
print('\nActor event counts after backfill:')
for actor in ['NVDA', 'AMD', 'TSM', 'MSFT', 'AMZN', 'GOOGL', 'ASML', 'AVGO',
              'META', 'ORCL', 'ADBE', 'CRM', 'SNOW', 'TSLA',
              'ARM', 'SMCI', 'DELL', 'INTC', 'MU', 'CRWV', 'NBIS', 'SKHX']:
    print(f'  {actor:<6} {actor_counts.get(actor, 0):>5}')
