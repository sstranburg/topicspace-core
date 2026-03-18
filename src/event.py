from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import json


class Event(BaseModel):
    event_id: str
    timestamp: str
    source: str
    title: str
    text: str
    url: Optional[str] = None
    actors: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    narrative_lane: str = "default"
    reliability: float = 1.0
    metadata: dict = Field(default_factory=dict)


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO format timestamp string to datetime."""
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))


def event_to_jsonl(event: Event) -> str:
    """Serialize Event to JSONL string."""
    return event.model_dump_json()


def event_from_jsonl(line: str) -> Event:
    """Deserialize Event from JSONL string."""
    return Event.model_validate_json(line)


def events_to_jsonl_file(events: list[Event], path: str):
    """Write events to JSONL file."""
    with open(path, 'w') as f:
        for event in events:
            f.write(event_to_jsonl(event) + '\n')


def events_from_jsonl_file(path: str) -> list[Event]:
    """Load events from JSONL file."""
    events = []
    with open(path, 'r') as f:
        for line in f:
            if line.strip():
                events.append(event_from_jsonl(line))
    return events
