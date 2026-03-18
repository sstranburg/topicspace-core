#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sstranburg001/Documents/storm')

from src.normalize import normalize_text, make_event_id, build_event


def test_step4():
    print("Testing Step 4: Normalization Helpers\n")
    
    # Test 1: normalize_text
    print("✓ Test 1: Text normalization")
    result = normalize_text("  NVIDIA  ", "announces", "  new   GPU  ")
    assert result == "NVIDIA announces new GPU"
    print(f"  Normalized: '{result}'")
    
    result = normalize_text("Title", None, "", "Body")
    assert result == "Title Body"
    print(f"  Handles empty/None: '{result}'")
    
    # Test 2: make_event_id deterministic
    print("\n✓ Test 2: Event ID generation is deterministic")
    id1 = make_event_id("test", "same input")
    id2 = make_event_id("test", "same input")
    id3 = make_event_id("test", "different input")
    
    assert id1 == id2, "Same input should produce same ID"
    assert id1 != id3, "Different input should produce different ID"
    print(f"  Same input: {id1} == {id2}")
    print(f"  Different input: {id1} != {id3}")
    
    # Test 3: build_event
    print("\n✓ Test 3: build_event creates complete Event")
    event = build_event(
        timestamp="2024-01-15T10:00:00Z",
        source="finnhub",
        title="NVIDIA announces new AI chip with CoWoS packaging",
        text="The new GPU will improve inference efficiency",
        url="https://example.com/news",
        reliability=0.9
    )
    
    print(f"  Event ID: {event.event_id}")
    print(f"  Actors detected: {event.actors}")
    print(f"  Tags detected: {event.tags}")
    
    assert "NVDA" in event.actors, "Should detect NVIDIA"
    assert "ai_infra" in event.tags, "Should detect ai_infra"
    assert "advanced_packaging" in event.tags, "Should detect advanced_packaging"
    assert "inference_efficiency" in event.tags, "Should detect inference_efficiency"
    assert event.reliability == 0.9
    
    # Test 4: Event ID is deterministic
    print("\n✓ Test 4: Event ID is deterministic for same inputs")
    event2 = build_event(
        timestamp="2024-01-15T10:00:00Z",
        source="finnhub",
        title="NVIDIA announces new AI chip with CoWoS packaging",
        text="The new GPU will improve inference efficiency",
        url="https://example.com/news"
    )
    
    assert event.event_id == event2.event_id
    print(f"  Same inputs produce same ID: {event.event_id}")
    
    # Test 5: Handle empty/missing fields
    print("\n✓ Test 5: Handles empty/missing fields safely")
    event3 = build_event(
        timestamp="2024-01-16T10:00:00Z",
        source="test",
        title="Simple title"
    )
    
    assert event3.text == ""
    assert event3.url is None
    assert event3.actors == []
    assert event3.tags == []
    assert event3.metadata == {}
    print(f"  Empty fields handled: actors={event3.actors}, tags={event3.tags}")
    
    print("\n✅ All Step 4 tests passed!")


if __name__ == "__main__":
    test_step4()
