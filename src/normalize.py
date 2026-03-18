import hashlib
from typing import Optional
from src.event import Event
from src.actors import detect_actors, detect_tags
from src.narrative_lane import classify_narrative_lane


def normalize_text(*parts) -> str:
    """Combine and normalize text parts."""
    combined = " ".join(str(p) for p in parts if p)
    return " ".join(combined.split())


def make_event_id(prefix: str, unique_text: str) -> str:
    """Create deterministic event ID from prefix and unique text."""
    hash_input = unique_text.encode('utf-8')
    hash_hex = hashlib.sha256(hash_input).hexdigest()[:16]
    return f"{prefix}_{hash_hex}"


def build_event(
    timestamp: str,
    source: str,
    title: str,
    text: str = "",
    url: Optional[str] = None,
    reliability: float = 1.0,
    metadata: Optional[dict] = None
) -> Event:
    """Build a complete Event with automatic actor/tag detection and ID generation."""
    combined_text = normalize_text(title, text)
    actors = detect_actors(combined_text)
    tags = detect_tags(combined_text)
    lane = classify_narrative_lane(combined_text)
    
    unique_str = f"{timestamp}|{title}|{url or ''}"
    event_id = make_event_id(source, unique_str)
    
    return Event(
        event_id=event_id,
        timestamp=timestamp,
        source=source,
        title=title,
        text=text,
        url=url,
        actors=actors,
        tags=tags,
        narrative_lane=lane,
        reliability=reliability,
        metadata=metadata or {}
    )
