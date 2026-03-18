#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

from datetime import datetime, timedelta
from src.ingest_finnhub import fetch_finnhub_company_news
from src.ingest_newsapi import fetch_newsapi_query
from src.ingest_sec import fetch_sec_submissions
from src.anchors import make_anchor_event
from src.merge_events import dedupe_events, write_jsonl

# Company info: (symbol, cik)
COMPANIES = [
    ("NVDA", "1045810"),
    ("AMD", "0000002488"),
    ("TSM", "1046179"),
    ("MSFT", "789019"),
    ("AMZN", "1018724"),
    ("GOOGL", "1652044"),
    ("AVGO", "1649338"),
]

# Date range
end_date = datetime.now().date()
start_date = end_date - timedelta(days=60)

print("Fetching events from all sources...\n")
all_events = []

# Fetch Finnhub events
print("1. Fetching Finnhub company news...")
for symbol, _ in COMPANIES:
    try:
        events = fetch_finnhub_company_news(symbol, str(start_date), str(end_date))
        all_events.extend(events)
        print(f"   {symbol}: {len(events)} events")
    except Exception as e:
        print(f"   {symbol}: Error - {e}")

# Fetch NewsAPI events
print("\n2. Fetching NewsAPI articles...")
queries = [
    "NVIDIA",
    "AMD semiconductor",
    "TSMC",
    "Broadcom AVGO",
]

for query in queries:
    try:
        events = fetch_newsapi_query(query, str(start_date), page_size=50)
        all_events.extend(events)
        print(f"   '{query[:40]}...': {len(events)} events")
    except Exception as e:
        print(f"   '{query[:40]}...': Error - {e}")

# Fetch SEC submissions
print("\n3. Fetching SEC filings...")
for symbol, cik in COMPANIES:
    try:
        events = fetch_sec_submissions(cik, symbol)
        # Filter to recent events only
        recent_events = [e for e in events if e.timestamp >= str(start_date)]
        all_events.extend(recent_events)
        print(f"   {symbol}: {len(recent_events)} events")
    except Exception as e:
        print(f"   {symbol}: Error - {e}")

# Create anchor events
print("\n4. Creating anchor events...")
anchors = [
    make_anchor_event("2024-01-01T00:00:00Z", "NVIDIA Q4 Earnings", "NVDA", "earnings"),
    make_anchor_event("2024-02-01T00:00:00Z", "AMD Product Launch", "AMD", "product_launch"),
    make_anchor_event("2024-01-15T00:00:00Z", "TSMC Capacity Expansion", "TSM", "capacity"),
]
all_events.extend(anchors)
print(f"   Created {len(anchors)} anchor events")

# Deduplicate
print("\n5. Deduplicating events...")
print(f"   Before: {len(all_events)} events")
unique_events = dedupe_events(all_events)
print(f"   After: {len(unique_events)} events")

# Sort by timestamp
unique_events.sort(key=lambda e: e.timestamp)

# Write to file
output_path = "data/normalized/tech_ecosystem.jsonl"
print(f"\n6. Writing to {output_path}...")
write_jsonl(unique_events, output_path)

print(f"\n✅ Done! Wrote {len(unique_events)} events to {output_path}")

# Summary stats
print("\n=== Summary ===")
sources = {}
actors_count = {}
tags_count = {}

for event in unique_events:
    sources[event.source] = sources.get(event.source, 0) + 1
    for actor in event.actors:
        actors_count[actor] = actors_count.get(actor, 0) + 1
    for tag in event.tags:
        tags_count[tag] = tags_count.get(tag, 0) + 1

print(f"\nEvents by source:")
for source, count in sorted(sources.items()):
    print(f"  {source}: {count}")

print(f"\nEvents by actor:")
for actor, count in sorted(actors_count.items(), key=lambda x: -x[1])[:10]:
    print(f"  {actor}: {count}")

print(f"\nEvents by tag:")
for tag, count in sorted(tags_count.items(), key=lambda x: -x[1])[:10]:
    print(f"  {tag}: {count}")
