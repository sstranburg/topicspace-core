#!/usr/bin/env python3
"""
Fetch crypto ecosystem events and append to crypto_ecosystem.jsonl.

Sources:
  1. CryptoPanic (news aggregation) — reliability 0.75
  2. Reddit crypto subreddits   — reliability 0.55, formation signal

Run daily (see cron_crypto_daily.sh) to accumulate history.

Usage:
  venv/bin/python scripts/fetch_crypto.py
  venv/bin/python scripts/fetch_crypto.py --start 2026-02-01 --end 2026-03-23
  venv/bin/python scripts/fetch_crypto.py --no-reddit
"""

import sys
import re
import hashlib
import argparse
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingest_cryptopanic import fetch_cryptopanic_posts
from src.ingest_reddit_crypto import fetch_all_subreddits
from src.ingest_newsapi import fetch_newsapi_query
from src.ingest_cryptopanic import detect_crypto_actors
from src.ingest_x import fetch_x_posts
from src.ingest_amplification import fetch_amplification_for_actors
from src.merge_events import dedupe_events, dedupe_by_title_tiered, write_jsonl, load_jsonl

# ── Config ────────────────────────────────────────────────────────────────────

ACTORS = [
    "BTC", "ETH",
    "SOL", "AVAX", "MATIC", "ARB", "OP", "TIA",
    "UNI", "AAVE", "MKR",
    "RNDR", "TAO", "AKT", "FET",
    "PENDLE", "ETHFI",
    "WLD", "FIL", "NEAR",
]

OUT_FILE = Path(__file__).parent.parent / "data" / "normalized" / "crypto_ecosystem.jsonl"

# NewsAPI queries for institutional / structural crypto signals.
# These are higher-trust than Reddit and CryptoPanic — they ground the narrative
# classification by providing non-social confirmation for key themes.
# Each entry: (query_string, actors_to_tag)
def _title_hash(title: str) -> str:
    """Normalised first-10-word hash for cross-source near-dedup."""
    norm = re.sub(r"[^a-z0-9\s]", "", title.lower())
    tokens = norm.split()[:10]
    return hashlib.md5(" ".join(tokens).encode()).hexdigest()


def _dedup_by_title(events: list) -> list:
    """
    Drop near-duplicate events across sources (same story from CryptoPanic + NewsAPI).
    Source priority is determined by order in events list — fetch order is:
    CryptoPanic → NewsAPI → Reddit (highest to lowest reliability).
    """
    seen: set[str] = set()
    out = []
    dupes = 0
    for e in events:
        h = _title_hash(e.title)
        if h not in seen:
            seen.add(h)
            out.append(e)
        else:
            dupes += 1
    if dupes:
        print(f"  Cross-source title dedup: dropped {dupes} near-duplicate events")
    return out


STRUCTURAL_NEWSAPI_QUERIES = [
    # BTC institutional accumulation
    ("MicroStrategy Bitcoin OR Saylor BTC acquisition OR \"strategy acquires\" bitcoin",   ["BTC"]),
    ("Bitcoin ETF flows OR BlackRock bitcoin OR Fidelity bitcoin OR \"bitcoin ETF\"",       ["BTC"]),
    ("\"bitcoin reserve\" OR \"BTC strategic reserve\" OR state bitcoin bill 2026",         ["BTC"]),
    # BTC macro
    ("bitcoin gold divergence OR bitcoin inflation hedge OR bitcoin macro 2026",            ["BTC"]),
    ("UK bond panic bitcoin OR federal reserve bitcoin OR bitcoin rate cut",                ["BTC"]),
    # ETH institutional
    ("Ethereum treasury OR \"ETH institutional\" OR Bitmine ethereum OR Tom Lee ETH",       ["ETH"]),
    ("Ethereum L2 OR Arbitrum ecosystem OR Optimism upgrade OR ETH bridge 2026",            ["ETH", "ARB", "OP"]),
    # Regulatory
    ("crypto regulation 2026 OR SEC cryptocurrency OR CFTC crypto enforcement",            ["BTC", "ETH"]),
    # AI-crypto crossover
    ("Bittensor TAO OR Render token RNDR OR \"AI crypto\" OR Fetch.ai FET 2026",           ["TAO", "RNDR", "FET"]),
    # SOL structural
    ("Solana institutional 2026 OR SOL ecosystem OR Solana real world assets",             ["SOL"]),
]


def main():
    yesterday = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.today().strftime("%Y-%m-%d")

    parser = argparse.ArgumentParser(description="Fetch crypto events")
    parser.add_argument("--start",     default=yesterday)
    parser.add_argument("--end",       default=today)
    parser.add_argument("--no-reddit",        action="store_true", help="Skip Reddit")
    parser.add_argument("--no-x",             action="store_true", help="Skip X (Twitter)")
    parser.add_argument("--no-amplification", action="store_true", help="Skip amplification sources")
    parser.add_argument("--no-append", action="store_true", help="Overwrite instead of append")
    args = parser.parse_args()

    print(f"Fetching crypto events: {args.start} → {args.end}")
    print()

    all_new: list = []

    # ── CryptoPanic ───────────────────────────────────────────────────────────
    print("[ CryptoPanic ]")
    cp_events = fetch_cryptopanic_posts(
        currencies=ACTORS,
        start_date=args.start,
        end_date=args.end,
        max_pages=25,
    )
    all_new.extend(cp_events)

    # ── NewsAPI (structural / institutional) ──────────────────────────────────
    print("\n[ NewsAPI — structural sources ]")
    newsapi_events = []
    for query, source_actors in STRUCTURAL_NEWSAPI_QUERIES:
        events = fetch_newsapi_query(query, args.start, page_size=30, source_actors=source_actors)
        # Ensure actors are also detected from title text (actor tagging is additive)
        for e in events:
            detected = detect_crypto_actors(e.title + " " + e.text)
            merged = sorted(set(e.actors) | set(detected))
            object.__setattr__(e, "actors", merged)
        events = [e for e in events if e.actors]   # drop events with no recognised actors
        newsapi_events.extend(events)
    print(f"  NewsAPI total: {len(newsapi_events)} events")
    all_new.extend(newsapi_events)

    # ── Reddit ────────────────────────────────────────────────────────────────
    if not args.no_reddit:
        print("\n[ Reddit ]")
        reddit_events = fetch_all_subreddits(args.start, args.end)
        all_new.extend(reddit_events)

    # ── X (Twitter) — high-velocity, low-confidence overlay ──────────────────
    if not args.no_x:
        print("\n[ X (Twitter) ]")
        x_start = f"{args.start}T00:00:00Z"
        x_end   = f"{args.end}T00:00:00Z"
        x_events = fetch_x_posts(
            "crypto", x_start, x_end,
            detect_actors=detect_crypto_actors,
        )
        all_new.extend(x_events)
        print(f"  X total: {len(x_events)} events")

    # ── Amplification (Yahoo Finance — breadth signal only) ──────────────────
    if not args.no_amplification:
        print("\n[ Amplification sources ]")
        from src.ingest_amplification import fetch_amplification_news
        amp_events = fetch_amplification_news("crypto", args.start)
        all_new.extend(amp_events)
        print(f"  Amplification total: {len(amp_events)} events")

    print(f"\nNew events this run (before title dedup): {len(all_new)}")

    # Tiered title dedup: primary/validation beats amplification on same headline.
    all_new, title_dupes = dedupe_by_title_tiered(all_new)
    if title_dupes:
        print(f"  Title dedup: dropped {title_dupes} lower-tier duplicates")
    print(f"New events this run (after title dedup):  {len(all_new)}")

    # ── Merge with existing ───────────────────────────────────────────────────
    existing = load_jsonl(str(OUT_FILE)) if OUT_FILE.exists() and not args.no_append else []
    if existing:
        print(f"Existing: {len(existing)} events")

    combined = dedupe_events(existing + all_new)
    print(f"Total after dedup: {len(combined)} events")

    # ── Write ─────────────────────────────────────────────────────────────────
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(combined, str(OUT_FILE))
    print(f"Written → {OUT_FILE}")

    # ── Summary ───────────────────────────────────────────────────────────────
    actor_counts: Counter = Counter()
    source_counts: Counter = Counter()
    for e in combined:
        for a in e.actors:
            actor_counts[a] += 1
        source_counts[e.source] += 1

    print(f"\nSources: " + "  ".join(f"{s}={n}" for s, n in source_counts.most_common()))
    print("\nEvents per actor:")
    for actor in ACTORS:
        bar = "█" * min(actor_counts.get(actor, 0), 40)
        print(f"  {actor:<8}  {actor_counts.get(actor, 0):>4}  {bar}")


if __name__ == "__main__":
    main()
