#!/usr/bin/env python3
"""
fetch_backfill_historical.py

Backfills Finnhub company news for all backtest universe actors for the
sparse period May 2025 – Jan 2026 (before the daily pipeline ran regularly).

Writes to data/normalized/tech_ecosystem_backfill.jsonl.
Does NOT touch the production corpus (tech_ecosystem_filtered.jsonl).

Design:
  - Fetches per ticker per month to stay within Finnhub rate limits and give
    clean progress reporting
  - Sets actors=[symbol] directly — no NLP pipeline; each article is fetched
    for a specific ticker so the attribution is unambiguous
  - Adds backfill=True to metadata for provenance
  - Deduplicates against the production corpus AND the backfill file using the
    same event_id scheme as production (sha256 of timestamp|title|url)
  - Safe to rerun: any event_id already written is skipped

Actor universe: frozen to BACKFILL_TICKERS below — same as build_backtest_history.py.
Date range: 2025-05-01 → 2026-01-31 (stops before Feb 2026 where dense data begins).

Usage:
  source venv/bin/activate && python scripts/fetch_backfill_historical.py
  source venv/bin/activate && python scripts/fetch_backfill_historical.py --dry-run
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ingest_finnhub import FINNHUB_API_KEY

PRODUCTION_CORPUS = ROOT / "data" / "normalized" / "tech_ecosystem_filtered.jsonl"
BACKFILL_FILE     = ROOT / "data" / "normalized" / "tech_ecosystem_backfill.jsonl"

# Frozen actor universe — must match TICKERS in build_backtest_history.py exactly.
# Do not modify between the initial backfill and the v2 rerun.
BACKFILL_TICKERS = [
    "NVDA", "MRVL", "MSFT", "ARM",  "PLTR", "META", "ADBE", "MU",
    "ORCL", "SMCI", "INTC", "AMD",  "TSLA", "DELL", "GOOGL", "ANET",
    "NBIS", "AVGO", "AMZN", "TSM",  "VRT",  "CRM",  "CRWV",
    "AAPL", "ASML", "SNOW", "DDOG", "CEG",  "VST",  "NFLX", "TTD", "MP",
]

# Months to backfill: inclusive both ends, stops before the dense Feb 2026 period.
BACKFILL_START = date(2025, 5, 1)
BACKFILL_END   = date(2026, 1, 31)

# Finnhub rate: 60 calls/min on free tier.
# 1.1s between calls = ~54 calls/min — safely under the limit.
REQUEST_DELAY_S = 1.1
# On 429, wait this many seconds before one retry.
RATE_LIMIT_BACKOFF_S = 65


# ── ID generation (matches production normalize.make_event_id) ────────────────

def _make_event_id(source: str, timestamp: str, title: str, url: str) -> str:
    unique_str = f"{timestamp}|{title}|{url}"
    h = hashlib.sha256(unique_str.encode("utf-8")).hexdigest()[:16]
    return f"{source}_{h}"


# ── Existing event_id index ───────────────────────────────────────────────────

def load_existing_ids() -> set[str]:
    """Return all event_ids already in the production corpus and backfill file."""
    seen: set[str] = set()
    for path in [PRODUCTION_CORPUS, BACKFILL_FILE]:
        if not path.exists():
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    eid = obj.get("event_id", "")
                    if eid:
                        seen.add(eid)
                except json.JSONDecodeError:
                    continue
    return seen


# ── Finnhub fetch ─────────────────────────────────────────────────────────────

def fetch_finnhub_month(symbol: str, start: date, end: date) -> list[dict]:
    """
    Fetch Finnhub company news for symbol over [start, end].
    Retries once on 429 after a RATE_LIMIT_BACKOFF_S pause.
    Returns raw article dicts; caller handles Event construction.
    """
    url = "https://finnhub.io/api/v1/company-news"
    params = {
        "symbol": symbol,
        "from":   start.isoformat(),
        "to":     end.isoformat(),
        "token":  FINNHUB_API_KEY,
    }
    for attempt in range(2):
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                if attempt == 0:
                    print(f"    [rate-limit] {symbol} {start}–{end}: "
                          f"waiting {RATE_LIMIT_BACKOFF_S}s…")
                    time.sleep(RATE_LIMIT_BACKOFF_S)
                    continue
                else:
                    print(f"    [warn] {symbol} {start}–{end}: 429 after retry, skipping")
                    return []
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except requests.exceptions.HTTPError as e:
            print(f"    [warn] Finnhub {symbol} {start}–{end}: {e}")
            return []
        except Exception as e:
            print(f"    [warn] Finnhub {symbol} {start}–{end}: {e}")
            return []
    return []


# ── Month iterator ────────────────────────────────────────────────────────────

def month_ranges(start: date, end: date):
    """Yield (month_start, month_end) pairs covering [start, end]."""
    cur = start.replace(day=1)
    while cur <= end:
        # Last day of current month
        if cur.month == 12:
            last = cur.replace(year=cur.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last = cur.replace(month=cur.month + 1, day=1) - timedelta(days=1)
        yield cur, min(last, end)
        # Advance to next month
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1, day=1)
        else:
            cur = cur.replace(month=cur.month + 1, day=1)


# ── Event construction ────────────────────────────────────────────────────────

def article_to_jsonl_obj(article: dict, symbol: str) -> dict | None:
    """
    Convert a raw Finnhub article dict to a JSONL-serialisable event dict.
    Returns None if the article lacks a usable title or timestamp.
    Actors are set directly from the fetch symbol — no NLP pipeline.
    backfill=True in metadata marks provenance.
    """
    from datetime import datetime as dt
    title = (article.get("headline") or "").strip()
    if not title:
        return None

    raw_ts = article.get("datetime")
    if not raw_ts:
        return None
    try:
        timestamp = dt.fromtimestamp(int(raw_ts)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OSError):
        return None

    url       = article.get("url") or ""
    text      = (article.get("summary") or "")[:300]
    event_id  = _make_event_id("finnhub", timestamp, title, url)

    return {
        "event_id":       event_id,
        "timestamp":      timestamp,
        "source":         "finnhub",
        "title":          title,
        "text":           text,
        "url":            url or None,
        "actors":         [symbol],
        "tags":           [],
        "narrative_lane": "default",
        "reliability":    0.85,
        "metadata": {
            "symbol":       symbol,
            "source_actor": symbol,
            "category":     article.get("category", ""),
            "backfill":     True,
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical Finnhub events")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and count events but do not write anything")
    args = parser.parse_args()

    print("=" * 66)
    print("  HISTORICAL FINNHUB BACKFILL")
    print(f"  Range:   {BACKFILL_START} → {BACKFILL_END}")
    print(f"  Tickers: {len(BACKFILL_TICKERS)}")
    print(f"  Output:  {BACKFILL_FILE.relative_to(ROOT)}")
    if args.dry_run:
        print("  Mode:    DRY RUN — no writes")
    print("=" * 66)

    print("\nIndexing existing event IDs…")
    existing_ids = load_existing_ids()
    print(f"  {len(existing_ids):,} existing event IDs loaded")

    months = list(month_ranges(BACKFILL_START, BACKFILL_END))
    print(f"\n{len(months)} months × {len(BACKFILL_TICKERS)} tickers = "
          f"{len(months) * len(BACKFILL_TICKERS)} fetch calls\n")

    total_fetched  = 0
    total_new      = 0
    total_skipped  = 0
    new_ids: set[str] = set()

    for mo_start, mo_end in months:
        month_label = mo_start.strftime("%Y-%m")
        mo_new = 0
        mo_skip = 0

        for ticker in BACKFILL_TICKERS:
            articles = fetch_finnhub_month(ticker, mo_start, mo_end)
            total_fetched += len(articles)

            for article in articles:
                obj = article_to_jsonl_obj(article, ticker)
                if obj is None:
                    total_skipped += 1
                    continue

                eid = obj["event_id"]

                # Skip if already in production corpus, backfill file, or
                # already queued in this run (cross-ticker duplicate)
                if eid in existing_ids or eid in new_ids:
                    mo_skip += 1
                    total_skipped += 1
                    continue

                new_ids.add(eid)
                mo_new += 1
                total_new += 1

                if not args.dry_run:
                    with open(BACKFILL_FILE, "a") as fh:
                        fh.write(json.dumps(obj) + "\n")

                existing_ids.add(eid)

            time.sleep(REQUEST_DELAY_S)

        print(f"  {month_label}  fetched={total_fetched - mo_skip - total_new + mo_new + mo_skip:>5}  "
              f"new={mo_new:>4}  dup_skip={mo_skip:>4}")

    print(f"\n{'─' * 50}")
    print(f"  Total articles fetched : {total_fetched:,}")
    print(f"  New events written     : {total_new:,}")
    print(f"  Duplicates skipped     : {total_skipped:,}")
    if not args.dry_run:
        print(f"\n  → {BACKFILL_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
