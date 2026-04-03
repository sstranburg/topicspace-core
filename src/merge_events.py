import hashlib
import re

from src.event import Event, events_to_jsonl_file, events_from_jsonl_file
from src.config import SOURCE_TYPE_TIER, SOURCE_TIER_WEIGHT


def dedupe_events(events: list[Event]) -> list[Event]:
    """Deduplicate events by event_id."""
    seen = set()
    unique = []

    for event in events:
        if event.event_id not in seen:
            seen.add(event.event_id)
            unique.append(event)

    return unique


def _title_hash(title: str) -> str:
    """Normalised first-10-word hash for cross-source near-dedup."""
    norm   = re.sub(r"[^a-z0-9\s]", "", title.lower())
    tokens = norm.split()[:10]
    return hashlib.md5(" ".join(tokens).encode()).hexdigest()


def _tier_rank(event: Event) -> int:
    """Lower number = higher priority tier (primary=0, validation=1, amplification=2, community=3)."""
    tier = event.metadata.get("source_tier") or SOURCE_TYPE_TIER.get(event.source, "validation")
    order = {"primary": 0, "validation": 1, "amplification": 2, "community": 3}
    return order.get(tier, 1)


def dedupe_by_title_tiered(events: list[Event]) -> tuple[list[Event], int]:
    """
    Deduplicate events by headline similarity across source tiers.

    When two events share the same normalised first-10-word title hash,
    keep the one from the higher-priority tier:
        primary > validation > amplification > community

    This collapses the pattern: Reuters publishes a story → Yahoo Finance
    and MarketWatch republish it → we keep Reuters, drop the amplification copies.

    Returns:
        (deduped_events, dropped_count)
    """
    # Sort by tier priority so the first occurrence is always the highest-tier version
    sorted_events = sorted(events, key=_tier_rank)

    seen_hashes: set[str] = set()
    unique: list[Event]   = []
    dropped = 0

    for ev in sorted_events:
        h = _title_hash(ev.title)
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append(ev)
        else:
            dropped += 1

    return unique, dropped


def write_jsonl(events: list[Event], path: str):
    """Write events to JSONL file."""
    events_to_jsonl_file(events, path)


def load_jsonl(path: str) -> list[Event]:
    """Load events from JSONL file."""
    return events_from_jsonl_file(path)
