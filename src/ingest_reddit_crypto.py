#!/usr/bin/env python3
"""
Ingest posts from crypto-focused subreddits using Reddit's public JSON API.

No OAuth required — uses the public .json endpoint with a user-agent header.
Treated as "formation signal": lower reliability than news, but early.

Subreddits covered:
  r/CryptoCurrency  — general, highest volume
  r/Bitcoin         — BTC signal
  r/ethereum        — ETH / L2 signal
  r/solana          — SOL signal
  r/defi            — UNI, AAVE, MKR, PENDLE, ETHFI
  r/CryptoMarkets   — momentum / sentiment
  r/altcoin         — long-tail actors (TAO, RNDR, AKT, FET, etc.)
"""

import time
import hashlib
import requests
from datetime import datetime, timezone
from src.event import Event
from src.ingest_cryptopanic import detect_crypto_actors

USER_AGENT = "storm-narrative-system/1.0 (research; contact@topicspace.com)"

SUBREDDITS = [
    "CryptoCurrency",
    "Bitcoin",
    "ethereum",
    "solana",
    "defi",
    "CryptoMarkets",
    "altcoin",
    "bittensor_",      # TAO
    "RenderToken",     # RNDR
    "akashnetwork",    # AKT
    "fetchai",         # FET
    "nearprotocol",    # NEAR
    "FilecoinProject", # FIL
]

# Minimum thresholds — both must be met
MIN_SCORE    = 5    # catches real discussion without requiring viral traction
MIN_COMMENTS = 2    # ensures some engagement, not just upvoted noise

# Title patterns that are structural subreddit noise, not narratives
_NOISE_PATTERNS = [
    # Thread templates
    "daily discussion", "daily general discussion", "mentor monday",
    "weekly thread", "daily thread", "megathread", "ama ", " ama:",
    "monthly discussion", "weekly discussion",
    # Generic questions
    "what are you", "what's everyone", "what is everyone",
    "simple questions", "noob questions", "beginner questions",
    "what should i", "should i buy", "should i sell",
    "good investment", "portfolio advice", "advice needed",
    "help me understand", "newbie here", "just started",
    # Price chatter without substance
    "buy/sell/trade", "buy sell trade",
    "price prediction", "price target", "to the moon",
    "when lambo", "when moon", "wen moon",
    # Personal transaction noise
    "i just bought", "i just sold", "i just transferred",
]

# Reliability score — below news (0.75), above raw social (keeps it useful)
REDDIT_RELIABILITY = 0.55


def _make_event_id(post_id: str) -> str:
    raw = f"reddit|{post_id}"
    return "reddit_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _title_hash(title: str) -> str:
    """Normalised hash of first 10 words — used to dedup cross-sub reposts."""
    import re
    norm = re.sub(r"[^a-z0-9\s]", "", title.lower())
    tokens = norm.split()[:10]
    return hashlib.md5(" ".join(tokens).encode()).hexdigest()


def _post_to_event(post: dict, subreddit: str) -> Event | None:
    title = (post.get("title") or "").strip()
    if not title:
        return None

    score       = post.get("score", 0)
    num_comments = post.get("num_comments", 0)
    if score < MIN_SCORE or num_comments < MIN_COMMENTS:
        return None

    title_lower = title.lower()
    if any(pat in title_lower for pat in _NOISE_PATTERNS):
        return None

    created_utc = post.get("created_utc")
    if not created_utc:
        return None
    timestamp = datetime.fromtimestamp(float(created_utc), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    body = (post.get("selftext") or "")[:400].replace("\n", " ")
    combined = f"{title} {body}"
    actors = detect_crypto_actors(combined)

    # Skip posts with no recognised actors (broad market noise)
    if not actors:
        return None

    permalink = post.get("permalink", "")
    url = f"https://www.reddit.com{permalink}" if permalink else None

    return Event(
        event_id=_make_event_id(post["id"]),
        timestamp=timestamp,
        source="reddit",
        title=title,
        text=body,
        url=url,
        actors=actors,
        tags=[],
        narrative_lane="default",
        reliability=REDDIT_RELIABILITY,
        metadata={
            "subreddit": subreddit,
            "score": score,
            "num_comments": num_comments,
            "reddit_id": post["id"],
        },
    )


def fetch_reddit_posts(
    subreddit: str,
    start_date: str,
    end_date: str,
    limit: int = 100,
    sleep_between: float = 1.0,
) -> list[Event]:
    """
    Fetch recent posts from a subreddit and filter by date range.

    Reddit's public API returns the most recent posts (no historical backfill).
    Run daily to accumulate; deduplication in merge_events handles overlap.
    """
    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end_date).replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )

    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    params = {"limit": min(limit, 100), "raw_json": 1}
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Reddit r/{subreddit}: fetch failed — {e}")
        return []

    children = (data.get("data") or {}).get("children") or []
    events: list[Event] = []
    for child in children:
        post = child.get("data") or {}
        created = post.get("created_utc")
        if not created:
            continue
        post_dt = datetime.fromtimestamp(float(created), tz=timezone.utc)
        if post_dt < start_dt or post_dt > end_dt:
            continue
        event = _post_to_event(post, subreddit)
        if event:
            events.append(event)

    time.sleep(sleep_between)
    return events


def fetch_all_subreddits(
    start_date: str,
    end_date: str,
    subreddits: list[str] | None = None,
) -> list[Event]:
    """
    Fetch posts from all configured crypto subreddits.
    Applies cross-subreddit near-deduplication so the same story
    posted to r/CryptoCurrency and r/Bitcoin only counts once.
    """
    targets = subreddits or SUBREDDITS
    raw_events: list[Event] = []
    for sub in targets:
        events = fetch_reddit_posts(sub, start_date, end_date)
        print(f"  Reddit r/{sub}: {len(events)} events with known actors")
        raw_events.extend(events)

    # Cross-sub dedup: drop near-identical titles from different subreddits
    seen_hashes: set[str] = set()
    deduped: list[Event] = []
    dupes = 0
    for event in raw_events:
        h = _title_hash(event.title)
        if h not in seen_hashes:
            seen_hashes.add(h)
            deduped.append(event)
        else:
            dupes += 1

    if dupes:
        print(f"  Reddit cross-sub dedup: dropped {dupes} near-duplicate posts")

    return deduped
