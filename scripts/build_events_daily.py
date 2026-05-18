#!/usr/bin/env python3
"""
build_events_daily.py

Counts events per UTC date from the same combined corpus the embedding /
field pipelines read (filtered + backfill). Writes a tiny JSON for the
site to render the L0 events-per-day sparkline / bar.

Reads:
  data/normalized/tech_ecosystem_filtered.jsonl
  data/normalized/tech_ecosystem_backfill.jsonl

Writes:
  data/derived/events_daily.json
  topicspace-site/public/events_daily.json

Usage:
  source venv/bin/activate && python scripts/build_events_daily.py
  python scripts/build_events_daily.py --days 60
"""

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"

SOURCES = [
    ROOT / "data" / "normalized" / "tech_ecosystem_filtered.jsonl",
    ROOT / "data" / "normalized" / "tech_ecosystem_backfill.jsonl",
]

OUT_DERIVED = ROOT / "data" / "derived" / "events_daily.json"
OUT_SITE    = SITE_PUBLIC / "events_daily.json"


def parse_date(ts: str) -> str | None:
    if not ts:
        return None
    # Tolerate trailing Z and ms; we only need YYYY-MM-DD.
    try:
        return ts[:10]
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=60,
                    help="trailing window length in days (default: 60)")
    args = ap.parse_args()

    counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    total_events = 0
    files_used   = 0
    for src in SOURCES:
        if not src.exists():
            print(f"  ! skipping (missing): {src}")
            continue
        files_used += 1
        with open(src) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                eid = e.get("event_id")
                if eid and eid in seen_ids:
                    continue
                if eid:
                    seen_ids.add(eid)
                d = parse_date(e.get("timestamp"))
                if d:
                    counts[d] += 1
                    total_events += 1

    if not counts:
        sys.exit("No event timestamps parsed — corpus empty?")

    # Trailing window
    max_date  = max(counts.keys())
    max_dt    = dt.date.fromisoformat(max_date)
    start_dt  = max_dt - dt.timedelta(days=args.days - 1)
    days: list[dict] = []
    cur = start_dt
    while cur <= max_dt:
        d_iso = cur.isoformat()
        days.append({"date": d_iso, "n": int(counts.get(d_iso, 0))})
        cur += dt.timedelta(days=1)

    payload = {
        "as_of":      max_date,
        "n_days":     len(days),
        "total_events_in_window": sum(d["n"] for d in days),
        "median_per_day":         sorted(d["n"] for d in days)[len(days) // 2],
        "max_per_day":            max((d["n"] for d in days), default=0),
        "days":       days,
    }

    OUT_DERIVED.parent.mkdir(parents=True, exist_ok=True)
    OUT_DERIVED.write_text(json.dumps(payload, indent=2))
    OUT_SITE.write_text(json.dumps(payload, indent=2))

    print(f"  read {files_used}/{len(SOURCES)} source files; {total_events:,} unique events")
    print(f"  window: {start_dt} → {max_date} ({len(days)} days)")
    print(f"  per-day: median={payload['median_per_day']}, max={payload['max_per_day']}")
    print(f"  wrote {OUT_DERIVED}")
    print(f"  wrote {OUT_SITE}")


if __name__ == "__main__":
    main()
