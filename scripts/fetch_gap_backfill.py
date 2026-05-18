#!/usr/bin/env python3
"""
fetch_gap_backfill.py

Calendar-gap backfill for the existing tracked actor list. Targets the
post-holiday gap weeks (Dec 1–19 2025, Jan 2–15 2026, Feb 2–13 2026) and
any other windows the fetch-health check flagged as low-volume.

Different from fetch_backfill_new_actors.py:
  - That script is for adding NEW actors with their full history.
  - This script is for filling CALENDAR holes in the existing actors'
    coverage, e.g. weeks where fetch_today.py didn't run.

Reuses the same actor list + NewsAPI queries from fetch_backfill_new_actors
(imported, not duplicated, so they stay in sync).

Reads:
  data/normalized/tech_ecosystem.jsonl

Writes:
  data/normalized/tech_ecosystem.jsonl  (appended, deduped)

Usage:
  source venv/bin/activate && python scripts/fetch_gap_backfill.py \\
      --from 2025-12-01 --to 2025-12-19
  python scripts/fetch_gap_backfill.py --from 2026-01-02 --to 2026-01-15
  python scripts/fetch_gap_backfill.py --gap-windows   # run all flagged windows
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingest_finnhub import fetch_finnhub_company_news
from src.ingest_newsapi import fetch_newsapi_query
from src.ingest_sec import fetch_sec_submissions
from src.merge_events import dedupe_events, load_jsonl, write_jsonl

# Pull the actor list + queries from the existing script so they stay in sync.
sys.path.insert(0, str(Path(__file__).parent))
from fetch_backfill_new_actors import NEW_COMPANIES, NEWSAPI_QUERIES


CORPUS_PATH = Path("data/normalized/tech_ecosystem.jsonl")

# Defaults — match the gap windows surfaced by fetch_health_check.py on
# 2026-05-18. Update as needed; --from/--to overrides this list.
DEFAULT_GAP_WINDOWS = [
    ("2025-12-01", "2025-12-19"),
    ("2026-01-02", "2026-01-15"),
    ("2026-02-02", "2026-02-13"),
]


def backfill_window(start_date: str, end_date: str) -> int:
    """Fetch events from all sources for [start_date, end_date]. Returns net new events added."""
    print(f"\n═════════════════════════════════════════════════")
    print(f"  Gap backfill: {start_date} → {end_date}")
    print(f"═════════════════════════════════════════════════")

    new_events: list = []

    # ── 1. Finnhub ──────────────────────────────────────────────────────────
    print("\n1. Finnhub company news…")
    for symbol, _cik in NEW_COMPANIES:
        try:
            evs = fetch_finnhub_company_news(symbol, start_date, end_date)
            if evs:
                new_events.extend(evs)
                print(f"   {symbol}: {len(evs)} events")
        except Exception as e:
            print(f"   {symbol}: error — {e}")

    # ── 2. NewsAPI (Event Registry) ─────────────────────────────────────────
    # We pass both dateStart and dateEnd so the archive endpoint returns
    # only articles in our gap window, not "from start_date to today."
    print("\n2. NewsAPI queries (Event Registry archive)…")
    for symbol, query, source_actors in NEWSAPI_QUERIES:
        try:
            evs = fetch_newsapi_query(
                query, start_date, page_size=100,
                source_actors=source_actors, end_date=end_date,
            )
            # Belt-and-suspenders date filter in case the API returns drifts.
            evs = [e for e in evs if start_date <= e.timestamp[:10] <= end_date]
            if evs:
                new_events.extend(evs)
                print(f"   {symbol}: {len(evs)} events in window")
        except Exception as e:
            print(f"   {symbol}: error — {e}")

    # ── 3. SEC filings ──────────────────────────────────────────────────────
    print("\n3. SEC filings…")
    for symbol, cik in NEW_COMPANIES:
        if not cik:
            continue
        try:
            evs = fetch_sec_submissions(cik, symbol)
            in_window = [e for e in evs if start_date <= e.timestamp[:10] <= end_date]
            if in_window:
                new_events.extend(in_window)
                print(f"   {symbol}: {len(in_window)} filings in window")
        except Exception as e:
            print(f"   {symbol}: error — {e}")

    print(f"\nFetched {len(new_events)} events (pre-dedup).")

    if not new_events:
        return 0

    # ── Merge into the canonical corpus ─────────────────────────────────────
    existing = load_jsonl(CORPUS_PATH)
    print(f"  existing: {len(existing):,} events")
    combined = existing + new_events
    deduped  = dedupe_events(combined)
    deduped.sort(key=lambda e: e.timestamp)
    added = len(deduped) - len(existing)
    print(f"  after dedup: {len(deduped):,} (+{added} net new)")
    write_jsonl(deduped, CORPUS_PATH)
    return added


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", help="window start date YYYY-MM-DD")
    ap.add_argument("--to",   dest="end",   help="window end date YYYY-MM-DD")
    ap.add_argument("--gap-windows", action="store_true",
                    help="run all DEFAULT_GAP_WINDOWS")
    args = ap.parse_args()

    if args.gap_windows:
        windows = DEFAULT_GAP_WINDOWS
    elif args.start and args.end:
        windows = [(args.start, args.end)]
    else:
        ap.error("provide --from/--to or --gap-windows")

    # Sanity-check
    for s, e in windows:
        try:
            dt.date.fromisoformat(s)
            dt.date.fromisoformat(e)
        except Exception:
            ap.error(f"invalid date in window {s} → {e}")

    total_added = 0
    for s, e in windows:
        total_added += backfill_window(s, e)

    print(f"\n═════════════════════════════════════════════════")
    print(f"  TOTAL NET NEW EVENTS ADDED: {total_added}")
    print(f"═════════════════════════════════════════════════")
    print()
    print("  Next: re-run the pipeline so field instrumentation / cluster")
    print("  lineage / lifecycle / actor traces pick up the new events:")
    print("    source venv/bin/activate && python scripts/run_pipeline.py")
    print("    source venv/bin/activate && python scripts/build_backtest_history.py")


if __name__ == "__main__":
    main()
