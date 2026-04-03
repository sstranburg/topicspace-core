#!/usr/bin/env python3
"""
Ingest news events from the CryptoPanic API (v2).

Maps CryptoPanic posts to the standard Event schema used by the Storm pipeline.

NOTE — Developer API limitations:
  - Returns ~20 most-recent posts per request (no historical date range)
  - No post ID or URL in response
  - No currency tags — actors are detected from title + description text
  - No pagination (next: null)

  To build a historical dataset, run fetch_crypto.py daily via cron.
  Each run appends new posts; deduplication handles overlap.
"""

import os
import hashlib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from src.event import Event

load_dotenv()

CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")
BASE_URL = "https://cryptopanic.com/api/developer/v2/posts/"

# Text-based actor detection for crypto — mirrors ACTOR_ALIASES in config.py
CRYPTO_ACTOR_ALIASES: dict[str, list[str]] = {
    "BTC":    ["bitcoin", " btc "],
    "ETH":    ["ethereum", " eth "],
    "SOL":    ["solana", " sol "],
    "AVAX":   ["avalanche", " avax "],
    "MATIC":  ["polygon", " matic "],
    "ARB":    ["arbitrum", " arb "],
    "OP":     ["optimism", " op token", "op mainnet"],
    "TIA":    ["celestia", " tia "],
    "UNI":    ["uniswap", " uni "],
    "AAVE":   ["aave"],
    "MKR":    ["maker dao", "makerdao", " mkr "],
    "RNDR":   ["render network", " rndr "],
    "TAO":    ["bittensor", " tao "],
    "AKT":    ["akash", " akt "],
    "FET":    ["fetch.ai", " fet "],
    "PENDLE": ["pendle"],
    "ETHFI":  ["ether.fi", "ethfi"],
    "WLD":    ["worldcoin", " wld "],
    "FIL":    ["filecoin", " fil "],
    "NEAR":   ["near protocol", "near network", "near blockchain", "$near"],
}


def detect_crypto_actors(text: str) -> list[str]:
    """Detect crypto actors from free-form text using alias matching."""
    text_lower = f" {text.lower()} "   # pad with spaces for whole-word matching
    detected = []
    for ticker, aliases in CRYPTO_ACTOR_ALIASES.items():
        for alias in aliases:
            if alias in text_lower:
                detected.append(ticker)
                break
    return sorted(set(detected))


def _make_event_id(title: str, published_at: str) -> str:
    raw = f"cryptopanic|{published_at}|{title}"
    return "cryptopanic_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _parse_published_at(s: str) -> str:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _post_to_event(post: dict) -> Event | None:
    title = (post.get("title") or "").strip()
    if not title:
        return None

    published_at = post.get("published_at") or post.get("created_at", "")
    if not published_at:
        return None

    timestamp = _parse_published_at(published_at)
    description = post.get("description") or ""
    combined = f"{title} {description}"
    actors = detect_crypto_actors(combined)

    return Event(
        event_id=_make_event_id(title, published_at),
        timestamp=timestamp,
        source="cryptopanic",
        title=title,
        text=description[:500],
        url=None,
        actors=actors,
        tags=[],
        narrative_lane="default",
        reliability=0.75,
        metadata={
            "kind": post.get("kind", "news"),
        },
    )


def fetch_cryptopanic_posts(
    currencies: list[str],
    start_date: str,
    end_date: str,
    **kwargs,
) -> list[Event]:
    """
    Fetch the most recent posts from CryptoPanic filtered by currencies.
    The developer API returns ~20 posts per call with no historical range support.
    Posts outside [start_date, end_date] are filtered client-side.

    Args:
        currencies:  List of tickers — used to build the currencies param.
        start_date:  "YYYY-MM-DD" — filter out older posts.
        end_date:    "YYYY-MM-DD" — filter out newer posts.
    """
    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end_date).replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )

    params = {
        "auth_token": CRYPTOPANIC_API_KEY,
        "currencies": ",".join(currencies),
        "public": "true",
        "kind": "news",
    }

    resp = requests.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []

    events: list[Event] = []
    for post in results:
        pub = post.get("published_at") or post.get("created_at", "")
        if not pub:
            continue
        post_dt = datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(timezone.utc)
        if post_dt < start_dt or post_dt > end_dt:
            continue
        event = _post_to_event(post)
        if event:
            events.append(event)

    print(f"  CryptoPanic [{','.join(currencies[:5])}{'…' if len(currencies) > 5 else ''}]: "
          f"{len(results)} fetched, {len(events)} in date range")
    return events
