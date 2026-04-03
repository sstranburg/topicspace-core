"""
Ingest amplification-tier news via RSS from Yahoo Finance and MarketWatch.

Design note:
  Amplification sources re-report stories that primary and validation sources
  broke first. They expand audience reach but do NOT add new information.

  Rules enforced here (also mirrored in classify_narrative.py):
  - reliability = 0.30 (vs primary 1.0, validation 0.75)
  - source_tier = "amplification" stored in metadata
  - source = "amplification" (distinct source key in the event store)
  - Cannot independently form new narrative clusters (enforced at classification)
  - Deduplicated against primary/validation by title hash before writing

Sources:
  Yahoo Finance  — per-ticker RSS: finance.yahoo.com/rss/2.0/headline?s={TICKER}
  MarketWatch    — top stories RSS: feeds.marketwatch.com/marketwatch/topstories/
                   market pulse RSS: feeds.marketwatch.com/marketwatch/marketpulse/

No API key required for RSS.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser

from src.event import Event
from src.normalize import build_event

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

AMPLIFICATION_RELIABILITY = 0.30

# Yahoo Finance per-ticker RSS — covers equities and crypto tickers
YAHOO_AI_TICKERS   = ["NVDA", "AMD", "AVGO", "MSFT", "AMZN", "GOOGL", "META", "ORCL", "TSLA"]
YAHOO_CRYPTO_TICKERS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"]

# MarketWatch RSS feeds — broader market coverage
MARKETWATCH_FEEDS = [
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://feeds.marketwatch.com/marketwatch/marketpulse/",
]

_MW_USER_AGENT = "storm-narrative-system/1.0 (research)"


# ── Event ID ──────────────────────────────────────────────────────────────────

def _make_event_id(source_name: str, title: str, pub_date: str) -> str:
    raw = f"amplification|{source_name}|{title[:80]}|{pub_date}"
    return "amp_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Date parsing ──────────────────────────────────────────────────────────────

def _parse_pub_date(entry: dict[str, Any]) -> datetime | None:
    """Parse publication date from a feedparser entry. Returns UTC datetime or None."""
    # Try feedparser's parsed struct first
    published_parsed = entry.get("published_parsed")
    if published_parsed:
        try:
            import calendar
            ts = calendar.timegm(published_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            pass

    # Fallback: parse raw string
    raw = entry.get("published") or entry.get("updated") or ""
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc)
        except Exception:
            pass

    return None


def _within_range(pub_dt: datetime | None, start_date: str, end_date: str | None) -> bool:
    """Return True if pub_dt falls within [start_date, end_date)."""
    if pub_dt is None:
        return True  # can't filter — include it
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = (
            datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if end_date
            else datetime.now(timezone.utc) + timedelta(days=1)
        )
        return start <= pub_dt < end
    except Exception:
        return True


# ── RSS fetchers ──────────────────────────────────────────────────────────────

def _fetch_yahoo_ticker(
    ticker: str,
    start_date: str,
    end_date: str | None = None,
) -> list[Event]:
    """Fetch Yahoo Finance RSS for a single ticker and return Events."""
    url  = f"https://finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    feed = feedparser.parse(url)

    # Map ticker to ecosystem actors
    # For crypto tickers like BTC-USD → BTC
    ticker_actor = ticker.split("-")[0]  # "BTC-USD" → "BTC"

    events: list[Event] = []
    for entry in feed.entries:
        pub_dt = _parse_pub_date(entry)
        if not _within_range(pub_dt, start_date, end_date):
            continue

        title = entry.get("title", "").strip()
        if not title:
            continue

        # Detect all actors in title; fall back to ticker actor
        ts = pub_dt.isoformat() if pub_dt else (start_date + "T00:00:00Z")

        ev = build_event(
            timestamp   = ts,
            source      = "amplification",
            title       = title,
            text        = entry.get("summary", "")[:300],
            url         = entry.get("link"),
            reliability = AMPLIFICATION_RELIABILITY,
            metadata    = {
                "source_tier": "amplification",
                "source_name": "Yahoo Finance",
                "source_uri":  "yahoo.com",
                "ticker":      ticker,
            },
        )
        # build_event auto-detects actors from ACTOR_ALIASES (AI/tech only).
        # For crypto tickers not in ACTOR_ALIASES, fall back to the ticker itself.
        if not ev.actors:
            ev.actors = [ticker_actor]

        events.append(ev)

    return events


def _fetch_marketwatch_feed(
    feed_url: str,
    start_date: str,
    end_date: str | None = None,
) -> list[Event]:
    """Fetch a MarketWatch RSS feed and return Events."""
    feed = feedparser.parse(feed_url, request_headers={"User-Agent": _MW_USER_AGENT})
    feed_label = feed_url.rstrip("/").split("/")[-1]

    events: list[Event] = []
    for entry in feed.entries:
        pub_dt = _parse_pub_date(entry)
        if not _within_range(pub_dt, start_date, end_date):
            continue

        title = entry.get("title", "").strip()
        if not title:
            continue

        ts = pub_dt.isoformat() if pub_dt else (start_date + "T00:00:00Z")

        ev = build_event(
            timestamp   = ts,
            source      = "amplification",
            title       = title,
            text        = entry.get("summary", "")[:300],
            url         = entry.get("link"),
            reliability = AMPLIFICATION_RELIABILITY,
            metadata    = {
                "source_tier": "amplification",
                "source_name": "MarketWatch",
                "source_uri":  "marketwatch.com",
                "feed":        feed_label,
            },
        )
        # Skip articles where no ecosystem actor was detected
        if not ev.actors:
            continue
        events.append(ev)

    return events


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_amplification_news(
    ecosystem: str,           # "ai" | "crypto"
    start_date: str,          # "YYYY-MM-DD"
    end_date: str | None = None,
) -> list[Event]:
    """
    Fetch amplification-tier news for the given ecosystem via RSS.

    AI ecosystem:   Yahoo Finance per-ticker (NVDA, AMD, MSFT, etc.) + MarketWatch
    Crypto ecosystem: Yahoo Finance crypto tickers (BTC-USD, ETH-USD, SOL-USD)

    Returns Events with reliability=0.30, source="amplification".
    """
    all_events: list[Event] = []

    if ecosystem == "ai":
        # Yahoo Finance per equity ticker
        for ticker in YAHOO_AI_TICKERS:
            events = _fetch_yahoo_ticker(ticker, start_date, end_date)
            log.info("Yahoo Finance %s: %d events", ticker, len(events))
            all_events.extend(events)

        # MarketWatch broad coverage
        for feed_url in MARKETWATCH_FEEDS:
            events = _fetch_marketwatch_feed(feed_url, start_date, end_date)
            feed_label = feed_url.rstrip("/").split("/")[-1]
            log.info("MarketWatch [%s]: %d events", feed_label, len(events))
            all_events.extend(events)

    elif ecosystem == "crypto":
        for ticker in YAHOO_CRYPTO_TICKERS:
            events = _fetch_yahoo_ticker(ticker, start_date, end_date)
            log.info("Yahoo Finance %s: %d events", ticker, len(events))
            all_events.extend(events)

    # Dedupe within this batch by event_id
    seen: set[str] = set()
    unique: list[Event] = []
    for ev in all_events:
        if ev.event_id not in seen:
            seen.add(ev.event_id)
            unique.append(ev)

    return unique


# ── Legacy compatibility (used by fetch scripts) ──────────────────────────────

def fetch_amplification_for_actors(
    actor_queries: list[tuple[str, list[str]]],
    start_date: str,
    page_size: int = 10,
) -> list[Event]:
    """
    Backwards-compatible wrapper used by fetch_today.py and fetch_crypto.py.
    actor_queries is ignored — we fetch all AI tickers from Yahoo/MarketWatch instead.
    Detects ecosystem from actor list: crypto actors → crypto, else → ai.
    """
    crypto_actors = {"BTC", "ETH", "SOL", "AVAX", "TAO", "RNDR", "FET", "ARB", "OP"}
    all_actors = {a for _, actors in actor_queries for a in actors}
    ecosystem = "crypto" if all_actors & crypto_actors else "ai"
    return fetch_amplification_news(ecosystem, start_date)
