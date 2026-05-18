#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, '/Users/sue/Documents/git/storm')

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from datetime import datetime, timedelta
from src.ingest_finnhub import fetch_finnhub_company_news
from src.ingest_newsapi import fetch_newsapi_query
from src.ingest_reddit_ai import fetch_all_subreddits as fetch_reddit_ai
from src.ingest_x import fetch_x_posts, fetch_x_keyword_queries
from src.x_search_config import AI_KEYWORD_QUERIES
from src.ingest_amplification import fetch_amplification_for_actors
from src.merge_events import dedupe_events, dedupe_by_title_tiered, write_jsonl, load_jsonl

print("Fetching today's data...")

today = datetime.now().date()
yesterday = today - timedelta(days=1)

print(f"Date range: {yesterday} to {today}")

# Fetch from Finnhub
actors = ['NVDA', 'AMD', 'TSM', 'MSFT', 'AMZN', 'GOOGL', 'ASML', 'AVGO',
          'META', 'ORCL', 'ADBE', 'CRM', 'SNOW', 'TSLA',
          'ARM', 'SMCI', 'DELL', 'INTC', 'MU', 'CRWV', 'NBIS',
          'PLTR', 'VRT', 'ANET', 'CEG', 'VST', 'DDOG', 'ZETA', 'ODC', 'NFLX', 'TTD',
          'SNDK', 'MELI',
          'COHR', 'ALAB', 'CLS', 'WDC']
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
    # SNOW and TSLA each get their own query (previously sharing
    # 'Snowflake OR Tesla OR TSLA' was diluting both — flagged in the
    # 2026-05-18 gap audit).
    ('Snowflake OR SNOW OR "data cloud" OR "Snowpark" OR "Cortex AI"', ['SNOW']),
    ('Tesla OR TSLA OR "FSD" OR "robotaxi" OR "Cybertruck" OR "Optimus" OR "Elon Musk"', ['TSLA']),
    # AAPL had no daily NewsAPI query (Finnhub only — explains 45% gap rate).
    ('Apple OR AAPL OR "Apple Intelligence" OR "Apple silicon" OR "Tim Cook" OR iPhone', ['AAPL']),
    ('ARM Holdings OR "ARM architecture" OR "ARM chips"',         ['ARM']),
    ('"Super Micro" OR SMCI OR "Supermicro server"',              ['SMCI']),
    ('Dell AI OR "Dell server" OR "Dell infrastructure"',         ['DELL']),
    ('Intel OR INTC OR "Intel foundry" OR "Intel AI"',            ['INTC']),
    ('Micron OR MU OR "HBM memory" OR "DRAM AI" OR "memory chip" OR "NAND flash"', ['MU']),
    ('SanDisk OR SNDK OR "enterprise SSD" OR "NAND flash AI"',    ['SNDK']),
    ('MercadoLibre OR MELI OR "Mercado Pago" OR "Mercado Crédito"', ['MELI']),
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
    ('Vertiv power cooling "data center" thermal AI',                       ['VRT']),
    ('Arista Networks AI ethernet switching datacenter',                    ['ANET']),
    ('"Constellation Energy" OR CEG nuclear "data center" OR AI power',     ['CEG']),
    ('Vistra energy nuclear "data center" OR "AI power" OR VST',            ['VST']),
    ('Datadog OR DDOG OR "datadog observability" OR "datadog AI"',           ['DDOG']),
    ('"Zeta Global" OR ZETA OR "Zeta CDP" OR "Zeta marketing AI"',          ['ZETA']),
    ('"Oil-Dri" OR ODC OR "Oil-Dri Corporation"',                            ['ODC']),
    ('Netflix OR NFLX OR "Netflix ads" OR "Netflix advertising" OR "Netflix live"', ['NFLX']),
    ('"The Trade Desk" OR TTD OR "programmatic advertising" OR "connected TV" OR "CTV advertising"', ['TTD']),
    ('"Coherent Corp" OR COHR OR "optical transceiver" OR "photonics AI" OR "II-VI"', ['COHR']),
    ('"Astera Labs" OR ALAB OR "PCIe retimer" OR "AI fabric switch" OR "CXL"',         ['ALAB']),
    ('Celestica OR CLS OR "AI server manufacturing" OR "hyperscaler contract manufacturer"', ['CLS']),
    ('"Western Digital" OR WDC OR "enterprise HDD" OR "AI storage HDD" OR "HDD pricing"', ['WDC']),
]
newsapi_events = []
for query, source_actors in queries:
    events = fetch_newsapi_query(query, str(yesterday), page_size=50, source_actors=source_actors)
    newsapi_events.extend(events)
print(f"  NewsAPI: {len(newsapi_events)} events")

# Fetch from Reddit (AI overlay — formation/attention signal, low reliability)
print("\nFetching Reddit AI overlay...")
reddit_ai_events = fetch_reddit_ai(str(yesterday), str(today))
print(f"  Reddit AI total: {len(reddit_ai_events)} events")

# Fetch from X — account-based (curated accounts) + keyword-based (public feed)
print("\nFetching X (Twitter) AI overlay...")
x_start = f"{yesterday}T00:00:00Z"
x_end   = f"{today}T00:00:00Z"
x_ai_events = fetch_x_posts("ai", x_start, x_end)
print(f"  X accounts total: {len(x_ai_events)} events")

print("\nFetching X keyword queries (actor/theme public feed)...")
x_keyword_events = fetch_x_keyword_queries(AI_KEYWORD_QUERIES, x_start, x_end)
x_ai_events = x_ai_events + x_keyword_events

# Fetch from amplification sources (Yahoo Finance, MarketWatch — breadth signal only)
from src.ingest_amplification import fetch_amplification_news
print("\nFetching amplification sources (Yahoo Finance, MarketWatch)...")
amplification_events = fetch_amplification_news("ai", str(yesterday))
print(f"  Amplification total: {len(amplification_events)} events")

# Combine new events — order matters for tiered title dedup (primary first)
print(f"  X AI total: {len(x_ai_events)} events")
new_events = finnhub_events + newsapi_events + reddit_ai_events + x_ai_events + amplification_events
print(f"\nTotal new events (before dedup): {len(new_events)}")

# Title-based tiered dedup: primary/validation beats amplification on same headline
new_events, title_dupes = dedupe_by_title_tiered(new_events)
if title_dupes:
    print(f"  Title dedup: dropped {title_dupes} amplification/lower-tier duplicates")

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

# ── Daily fetch-health check ───────────────────────────────────────────────
# Flags days where today's ingest is materially below the 7-day rolling
# median, where actor coverage falls below 25/32, or where a normally-
# productive source delivers zero events. Writes one row per day to
# data/derived/fetch_health.jsonl.
print()
try:
    import subprocess, sys as _sys
    _r = subprocess.run(
        [_sys.executable, str(Path(__file__).parent / "fetch_health_check.py")],
        capture_output=True, text=True, timeout=120,
    )
    for line in _r.stdout.splitlines():
        if line.strip():
            print(line)
    if _r.returncode == 2:
        print("  ! fetch health: FAIL — see flags above")
    elif _r.returncode != 0:
        print(f"  ! fetch_health_check exit {_r.returncode}: {_r.stderr[:200]}")
except Exception as _e:
    print(f"  ! fetch_health_check failed: {_e}")
