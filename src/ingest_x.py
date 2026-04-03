"""
Ingest tweets from a curated list of high-signal X (Twitter) accounts.

Design note:
  X is treated as a high-velocity, low-confidence signal layer.
  It is NOT a primary source of structural truth.

  Reliability: 0.45 — lower than Reddit (0.50)
  Max bucket:  STEP_BACK ("Explore") unless reinforced by cross-source
  Cannot independently produce LEAN_IN ("Act") signals

API requirements:
  X API v2, Basic tier or higher (https://developer.twitter.com/en/portal)
  Set env var: X_BEARER_TOKEN

Rate limits (Basic tier):
  search/recent: 10 requests / 15 min
  With 50 accounts per batch query, 2 queries covers 100 accounts — well within limits.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from src.event import Event
from src.x_accounts import AI_ACCOUNTS, CRYPTO_ACCOUNTS

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

X_BEARER_TOKEN      = os.getenv("X_BEARER_TOKEN", "")
X_RELIABILITY       = 0.45   # Below Reddit (0.50) — high-velocity, low-confidence
X_MIN_LIKES         = 10     # Minimum likes to pass noise filter
X_MAX_RESULTS       = 100    # Tweets per API call (API max is 100)
X_ACCOUNTS_PER_QUERY = 50    # accounts per `from:` query (respects 1024-char URL limit)
X_BATCH_SLEEP       = 1.5    # Seconds between batch requests (rate-limit safety)
X_BASE_URL          = "https://api.twitter.com/2"

_HEADERS: dict[str, str] = {}  # populated lazily


def _get_headers() -> dict[str, str]:
    if not X_BEARER_TOKEN:
        raise RuntimeError(
            "X_BEARER_TOKEN env var not set. "
            "Get a Bearer Token from https://developer.twitter.com/en/portal"
        )
    return {"Authorization": f"Bearer {X_BEARER_TOKEN}"}


def _make_event_id(author: str, tweet_id: str) -> str:
    raw = f"x|{author}|{tweet_id}"
    return "x_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _batch(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


# ── API fetch ─────────────────────────────────────────────────────────────────

def _fetch_batch(
    accounts: list[str],
    start_time: str,
    end_time: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch recent tweets from a batch of accounts using search/recent.
    Excludes retweets. Returns raw tweet dicts with _username attached.
    """
    from_clause = " OR ".join(f"from:{a}" for a in accounts)
    query       = f"({from_clause}) -is:retweet lang:en"

    params: dict[str, Any] = {
        "query":        query,
        "max_results":  X_MAX_RESULTS,
        "start_time":   start_time,
        "tweet.fields": "text,created_at,public_metrics,author_id",
        "expansions":   "author_id",
        "user.fields":  "username",
    }
    if end_time:
        params["end_time"] = end_time

    resp = requests.get(
        f"{X_BASE_URL}/tweets/search/recent",
        headers=_get_headers(),
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    # Build author_id → username lookup from includes
    users: dict[str, str] = {
        u["id"]: u["username"]
        for u in data.get("includes", {}).get("users", [])
    }

    tweets = []
    for tw in data.get("data", []):
        tw["_username"] = users.get(tw.get("author_id", ""), "unknown")
        tweets.append(tw)
    return tweets


# ── Event conversion ──────────────────────────────────────────────────────────

def _tweet_to_event(
    tweet: dict[str, Any],
    detect_actors: Callable[[str], list[str]],
    route_lane: Callable[[str], str] | None,
) -> Event | None:
    """
    Convert a raw tweet dict to an Event, or None if filtered out.
    Filters: below MIN_LIKES, or no detectable ecosystem actors.
    """
    metrics    = tweet.get("public_metrics", {})
    likes      = metrics.get("like_count", 0)
    retweets   = metrics.get("retweet_count", 0)

    if likes < X_MIN_LIKES:
        return None

    text      = tweet.get("text", "").strip()
    author    = tweet.get("_username", "unknown")
    tweet_id  = tweet.get("id", "")
    created   = tweet.get("created_at", datetime.now(timezone.utc).isoformat())

    actors = detect_actors(text)
    if not actors:
        # Skip tweets with no recognisable ecosystem actors — avoids generic chatter
        return None

    lane = route_lane(text) if route_lane else "default"

    return Event(
        event_id       = _make_event_id(author, tweet_id),
        timestamp      = created,
        source         = "x",
        title          = text[:140],   # tweet-length title
        text           = text,
        url            = f"https://x.com/{author}/status/{tweet_id}",
        actors         = actors,
        tags           = [],
        narrative_lane = lane,
        reliability    = X_RELIABILITY,
        metadata       = {
            "source_type": "x",
            "author":      author,
            "tweet_id":    tweet_id,
            "likes":       likes,
            "retweets":    retweets,
            "engagement":  likes + retweets,
        },
    )


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_x_posts(
    ecosystem: str,                              # "ai" | "crypto"
    start_time: str,                             # ISO 8601 UTC, e.g. "2026-03-26T00:00:00Z"
    end_time: str | None = None,
    detect_actors: Callable[[str], list[str]] | None = None,
    route_lane: Callable[[str], str] | None = None,
) -> list[Event]:
    """
    Fetch tweets from the curated account list for the given ecosystem.

    Args:
        ecosystem:      "ai" or "crypto"
        start_time:     ISO 8601 UTC start boundary
        end_time:       ISO 8601 UTC end boundary (optional)
        detect_actors:  function(text) → list[str] of actor tickers
        route_lane:     function(text) → narrative_lane string (optional)

    Returns:
        list of Event objects, filtered by engagement and actor presence.
    """
    if not X_BEARER_TOKEN:
        log.warning("X_BEARER_TOKEN not set — skipping X ingestion")
        return []

    accounts = AI_ACCOUNTS if ecosystem == "ai" else CRYPTO_ACCOUNTS

    # Default actor detector uses ACTOR_ALIASES from config
    if detect_actors is None:
        from src.config import ACTOR_ALIASES
        def _default_detect(text: str) -> list[str]:
            text_lower = text.lower()
            found = []
            for ticker, aliases in ACTOR_ALIASES.items():
                if any(alias in text_lower for alias in aliases):
                    found.append(ticker)
            return found
        detect_actors = _default_detect

    batches    = _batch(accounts, X_ACCOUNTS_PER_QUERY)
    raw_tweets: list[dict[str, Any]] = []

    for i, batch in enumerate(batches):
        try:
            tweets = _fetch_batch(batch, start_time, end_time)
            raw_tweets.extend(tweets)
            log.info("X batch %d/%d: %d tweets", i + 1, len(batches), len(tweets))
        except requests.HTTPError as exc:
            log.warning("X batch %d/%d failed: %s", i + 1, len(batches), exc)
        except Exception as exc:
            log.warning("X batch %d/%d error: %s", i + 1, len(batches), exc)

        if i < len(batches) - 1:
            time.sleep(X_BATCH_SLEEP)

    # Deduplicate by tweet_id
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for tw in raw_tweets:
        tid = tw.get("id", "")
        if tid and tid not in seen:
            seen.add(tid)
            unique.append(tw)

    events: list[Event] = []
    for tw in unique:
        ev = _tweet_to_event(tw, detect_actors, route_lane)
        if ev:
            events.append(ev)

    log.info(
        "X ingestion (%s): %d events from %d accounts (%d raw tweets, %d after dedup)",
        ecosystem, len(events), len(accounts), len(raw_tweets), len(unique),
    )
    return events
