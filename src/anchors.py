from src.event import Event
from src.normalize import build_event


def make_anchor_event(ts: str, title: str, actor: str, anchor_type: str) -> Event:
    """Create a synthetic anchor event."""
    text = f"Anchor event for {actor}: {anchor_type}"
    
    event = build_event(
        timestamp=ts,
        source="anchor",
        title=title,
        text=text,
        reliability=1.0,
        metadata={"anchor_type": anchor_type, "actor": actor}
    )
    
    return event
