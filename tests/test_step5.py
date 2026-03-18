#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sstranburg001/Documents/storm')

from datetime import datetime, timedelta
from src.ingest_finnhub import fetch_finnhub_company_news
from src.ingest_newsapi import fetch_newsapi_query
from src.ingest_sec import fetch_sec_submissions
from src.anchors import make_anchor_event


def test_step5():
    print("Testing Step 5: Ingestion Scripts\n")
    
    # Test dates
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    
    # Test 1: Finnhub
    print("✓ Test 1: Finnhub ingestion")
    try:
        events = fetch_finnhub_company_news("NVDA", str(start_date), str(end_date))
        print(f"  Fetched {len(events)} events for NVDA")
        if events:
            print(f"  Sample: {events[0].title[:60]}...")
            print(f"  Actors: {events[0].actors}")
            print(f"  Tags: {events[0].tags}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test 2: NewsAPI
    print("\n✓ Test 2: NewsAPI ingestion")
    try:
        events = fetch_newsapi_query("NVIDIA AI", str(start_date), page_size=10)
        print(f"  Fetched {len(events)} events for 'NVIDIA AI'")
        if events:
            print(f"  Sample: {events[0].title[:60]}...")
            print(f"  Actors: {events[0].actors}")
            print(f"  Tags: {events[0].tags}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test 3: SEC
    print("\n✓ Test 3: SEC ingestion")
    try:
        # NVIDIA CIK: 0001045810
        events = fetch_sec_submissions("1045810", "NVDA")
        print(f"  Fetched {len(events)} SEC filings for NVDA")
        if events:
            print(f"  Sample: {events[0].title}")
            print(f"  Form type: {events[0].metadata.get('form_type')}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test 4: Anchors
    print("\n✓ Test 4: Anchor events")
    anchor = make_anchor_event(
        ts="2024-01-01T00:00:00Z",
        title="NVIDIA Q4 Earnings",
        actor="NVDA",
        anchor_type="earnings"
    )
    print(f"  Created anchor: {anchor.title}")
    print(f"  Event ID: {anchor.event_id}")
    print(f"  Metadata: {anchor.metadata}")
    
    print("\n✅ All Step 5 tests completed!")
    print("\nNote: Check that:")
    print("  - API calls succeeded")
    print("  - Events were returned")
    print("  - Actor tagging looks sensible")


if __name__ == "__main__":
    test_step5()
