#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

from datetime import datetime, timedelta
from src.ingest_finnhub import fetch_finnhub_company_news
from src.ingest_newsapi import fetch_newsapi_query
from src.merge_events import dedupe_events, write_jsonl, load_jsonl

print("Fetching today's data...")

today = datetime.now().date()
yesterday = today - timedelta(days=1)

print(f"Date range: {yesterday} to {today}")

# Fetch from Finnhub
actors = ['NVDA', 'AMD', 'TSM', 'MSFT', 'AMZN', 'GOOGL', 'ASML', 'AVGO',
          'META', 'ORCL', 'ADBE', 'CRM', 'SNOW', 'TSLA',
          'ARM', 'SMCI', 'DELL', 'INTC', 'MU', 'CRWV', 'NBIS',
          'PLTR']
finnhub_events = []
for actor in actors:
    events = fetch_finnhub_company_news(actor, str(yesterday), str(today))
    finnhub_events.extend(events)
    print(f"  Finnhub {actor}: {len(events)} events")

# Fetch from NewsAPI
# Each entry: (query, source_actors)
# source_actors lists the tracked actors this query targets
queries = [
    ('NVIDIA OR AMD OR TSMC OR "Taiwan Semiconductor"',          ['NVDA', 'AMD', 'TSM']),
    ('Microsoft OR Amazon OR Google OR Alphabet',                 ['MSFT', 'AMZN', 'GOOGL']),
    ('ASML OR "semiconductor equipment"',                         ['ASML']),
    ('Broadcom OR AVGO',                                          ['AVGO']),
    ('Meta OR Facebook OR "Meta AI" OR "Meta Llama"',             ['META']),
    ('Oracle cloud OR "Oracle AI" OR "Oracle infrastructure"',    ['ORCL']),
    ('Salesforce Agentforce OR "Salesforce AI" OR "CRM AI"',      ['CRM']),
    ('Adobe AI OR "Adobe Firefly" OR "Adobe generative"',         ['ADBE']),
    ('Snowflake OR Tesla OR TSLA',                                ['SNOW', 'TSLA']),
    ('ARM Holdings OR "ARM architecture" OR "ARM chips"',         ['ARM']),
    ('"Super Micro" OR SMCI OR "Supermicro server"',              ['SMCI']),
    ('Dell AI OR "Dell server" OR "Dell infrastructure"',         ['DELL']),
    ('Intel OR INTC OR "Intel foundry" OR "Intel AI"',            ['INTC']),
    ('Micron OR MU OR "HBM memory" OR "DRAM AI"',                 ['MU']),
    ('"SK Hynix" OR "SK hynix HBM" OR "SK hynix memory"',        ['SKHX']),
    ('CoreWeave OR "AI cloud" OR "GPU cloud"',                    ['CRWV']),
    ('Nebius OR "Nebius AI" OR "Nebius cloud"',                   ['NBIS']),
    ('Palantir OR PLTR OR "Palantir AIP" OR "Palantir AI"',       ['PLTR']),
    ('OpenAI OR "ChatGPT" OR "GPT-5" OR "OpenAI API"',            ['OPENAI']),
    ('Anthropic OR "Claude AI" OR "Anthropic Claude"',             ['ANTHROPIC']),
    # Cross-actor ecosystem queries — explicitly link supply and demand sides
    ('"AI infrastructure" AND (Meta OR Oracle OR Salesforce OR Adobe)',    ['META', 'ORCL', 'CRM', 'ADBE']),
    ('"AI chips" OR "GPU demand" AND (Meta OR Oracle OR Tesla OR Salesforce)', ['META', 'ORCL', 'TSLA', 'CRM']),
    ('enterprise AI spending OR enterprise AI investment 2026',            ['MSFT', 'AMZN', 'GOOGL', 'ORCL', 'CRM']),
    ('cloud AI platform OR AI agent platform 2026',                        ['MSFT', 'AMZN', 'GOOGL', 'META', 'ORCL']),
    # New actor cross-ecosystem queries
    ('"AI memory" OR "HBM" AND (NVIDIA OR AMD OR Intel OR Micron)',        ['NVDA', 'AMD', 'INTC', 'MU']),
    ('"AI server" OR "GPU server" AND (Dell OR Supermicro OR CoreWeave)',   ['DELL', 'SMCI', 'CRWV']),
    ('ARM OR "AI chip design" AND (NVIDIA OR Qualcomm OR Apple)',           ['ARM', 'NVDA']),
]
newsapi_events = []
for query, source_actors in queries:
    events = fetch_newsapi_query(query, str(yesterday), page_size=50, source_actors=source_actors)
    newsapi_events.extend(events)
print(f"  NewsAPI: {len(newsapi_events)} events")

# Combine new events
new_events = finnhub_events + newsapi_events
print(f"\nTotal new events: {len(new_events)}")

# Load existing events
existing_events = load_jsonl('data/normalized/tech_ecosystem.jsonl')
print(f"Existing events: {len(existing_events)}")

# Dedupe and merge
all_events = existing_events + new_events
deduped = dedupe_events(all_events)
print(f"After deduplication: {len(deduped)} events")

# Write back
write_jsonl(deduped, 'data/normalized/tech_ecosystem.jsonl')
print(f"\n✓ Updated data/normalized/tech_ecosystem.jsonl")
print(f"  Added {len(deduped) - len(existing_events)} new events")
