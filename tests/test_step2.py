#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sstranburg001/Documents/storm')

from src.event import Event, parse_timestamp, event_to_jsonl, event_from_jsonl
from datetime import datetime


def test_step2():
    print("Testing Step 2: Event Schema\n")
    
    # Create 3 sample events
    events = [
        Event(
            event_id="test_001",
            timestamp="2024-01-15T10:30:00Z",
            source="finnhub",
            title="NVIDIA announces new AI chip",
            text="NVIDIA unveiled its latest GPU architecture for AI workloads.",
            url="https://example.com/nvidia-chip",
            actors=["NVDA"],
            tags=["ai_infra"],
            reliability=0.95
        ),
        Event(
            event_id="test_002",
            timestamp="2024-01-16T14:20:00Z",
            source="newsapi",
            title="TSMC expands CoWoS capacity",
            text="Taiwan Semiconductor increases advanced packaging production.",
            actors=["TSM"],
            tags=["advanced_packaging", "supply_chain"]
        ),
        Event(
            event_id="test_003",
            timestamp="2024-01-17T09:00:00Z",
            source="sec",
            title="Amazon Q4 earnings report",
            text="Amazon reports strong cloud revenue growth.",
            url="https://sec.gov/example",
            actors=["AMZN"],
            tags=["capex"],
            metadata={"form_type": "10-K"}
        )
    ]
    
    # Test 1: Model validation
    print("✓ Test 1: Model validation works")
    for i, event in enumerate(events, 1):
        print(f"  Event {i}: {event.event_id} - {event.title[:40]}...")
    
    # Test 2: JSONL round-trip
    print("\n✓ Test 2: JSONL round-trip works")
    for event in events:
        jsonl_str = event_to_jsonl(event)
        restored = event_from_jsonl(jsonl_str)
        assert event == restored, f"Round-trip failed for {event.event_id}"
        print(f"  {event.event_id}: serialized and restored successfully")
    
    # Test 3: Timestamp parsing
    print("\n✓ Test 3: Timestamp parsing works")
    for event in events:
        dt = parse_timestamp(event.timestamp)
        assert isinstance(dt, datetime), f"Failed to parse {event.timestamp}"
        print(f"  {event.timestamp} → {dt}")
    
    print("\n✅ All Step 2 tests passed!")


if __name__ == "__main__":
    test_step2()
