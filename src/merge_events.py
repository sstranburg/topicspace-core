from src.event import Event, events_to_jsonl_file, events_from_jsonl_file


def dedupe_events(events: list[Event]) -> list[Event]:
    """Deduplicate events by event_id."""
    seen = set()
    unique = []
    
    for event in events:
        if event.event_id not in seen:
            seen.add(event.event_id)
            unique.append(event)
    
    return unique


def write_jsonl(events: list[Event], path: str):
    """Write events to JSONL file."""
    events_to_jsonl_file(events, path)


def load_jsonl(path: str) -> list[Event]:
    """Load events from JSONL file."""
    return events_from_jsonl_file(path)
