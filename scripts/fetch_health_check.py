#!/usr/bin/env python3
"""
fetch_health_check.py

Daily fetch-health check. Catches partial-ingest days BEFORE they cascade
into stale claims / theme transitions / lifecycle events downstream.

Compares today's ingest (events + actor coverage) against the 7-day
rolling median. Flags WARN / FAIL when any of:
  - today's total events < 0.30 × 7d median total
  - today's actors-with-events < 25 (out of 32 tracked)
  - any source delivers 0 events when its 7d median is ≥ 10

Appends a row to data/derived/fetch_health.jsonl (one row per date) and
prints a one-line status. Exit code is non-zero if status is FAIL so it
can be used as a gate in CI / cron wrappers.

Reads:
  data/normalized/tech_ecosystem.jsonl       (canonical event corpus)

Writes:
  data/derived/fetch_health.jsonl            (history of health checks)

Usage:
  source venv/bin/activate && python scripts/fetch_health_check.py
  python scripts/fetch_health_check.py --as-of 2026-05-12     # backfill check
  python scripts/fetch_health_check.py --threshold 0.5        # stricter
  python scripts/fetch_health_check.py --window 60            # use 60d history
"""

import argparse
import datetime as dt
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).parent.parent
CORPUS = ROOT / "data" / "normalized" / "tech_ecosystem.jsonl"
OUT    = ROOT / "data" / "derived" / "fetch_health.jsonl"

DEFAULT_THRESHOLD       = 0.30   # today < 30% of median → flag
DEFAULT_MIN_ACTORS      = 25     # out of 32 tracked
DEFAULT_SOURCE_FLOOR    = 10     # source 7d median to be considered "normally productive"
DEFAULT_WINDOW          = 30     # days of history to compare against
DEFAULT_TRACKED_ACTORS  = 32     # for actor-coverage normalization


def load_events(path: Path):
    """Iterates events from a jsonl, yielding dicts."""
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", default=None,
                    help="check this date (default: max date in corpus)")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--min-actors", type=int, default=DEFAULT_MIN_ACTORS)
    ap.add_argument("--source-floor", type=int, default=DEFAULT_SOURCE_FLOOR)
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    ap.add_argument("--silent", action="store_true",
                    help="don't print human-readable line; still writes the row")
    args = ap.parse_args()

    if not CORPUS.exists():
        sys.exit(f"Missing {CORPUS}")

    # Roll up events per (date, source, actor)
    events_by_date    = defaultdict(int)
    actors_by_date    = defaultdict(set)
    src_by_date       = defaultdict(lambda: Counter())
    seen_ids: set[str] = set()
    for e in load_events(CORPUS):
        eid = e.get("event_id")
        if eid:
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
        d = (e.get("timestamp") or "")[:10]
        if not d:
            continue
        events_by_date[d] += 1
        for a in (e.get("actors") or []):
            actors_by_date[d].add(a)
        src = e.get("source") or "unknown"
        src_by_date[d][src] += 1

    if not events_by_date:
        sys.exit("No events parsed.")

    as_of = args.as_of or max(events_by_date.keys())
    as_of_d = dt.date.fromisoformat(as_of)
    # Window: as_of - window_days .. as_of - 1 (exclude today from the median)
    window_dates = [
        (as_of_d - dt.timedelta(days=i)).isoformat()
        for i in range(1, args.window + 1)
    ]
    window_dates = [d for d in window_dates if d in events_by_date]

    today_total   = events_by_date.get(as_of, 0)
    today_actors  = len(actors_by_date.get(as_of, set()))
    today_sources = src_by_date.get(as_of, Counter())

    if not window_dates:
        print(f"  ! no historical window to compare against for {as_of}")
        return

    hist_totals = [events_by_date[d] for d in window_dates]
    median_total = statistics.median(hist_totals)
    ratio = today_total / max(1, median_total)

    # Per-source 7d median (excluding today)
    src_history: dict[str, list[int]] = defaultdict(list)
    for d in window_dates:
        for src, n in src_by_date.get(d, Counter()).items():
            src_history[src].append(n)
    src_medians = {src: statistics.median(vals) for src, vals in src_history.items() if vals}
    silent_sources: list[tuple[str, int, float]] = []
    for src, med in src_medians.items():
        today_n = today_sources.get(src, 0)
        if med >= args.source_floor and today_n == 0:
            silent_sources.append((src, today_n, med))

    # Status
    flags: list[str] = []
    if ratio < args.threshold:
        flags.append(f"low_total({today_total} < {args.threshold:.0%} of {median_total:.0f})")
    if today_actors < args.min_actors:
        flags.append(f"low_actor_coverage({today_actors}/{DEFAULT_TRACKED_ACTORS})")
    for src, today_n, med in silent_sources:
        flags.append(f"silent_source({src}: 0 vs {med:.0f} median)")

    if flags:
        status = "FAIL" if (ratio < args.threshold or today_actors < args.min_actors) else "WARN"
    else:
        status = "OK"

    payload = {
        "as_of":            as_of,
        "status":           status,
        "today_total":      today_total,
        "today_actors":     today_actors,
        "median_total_7d":  round(median_total, 1),
        "ratio_to_median":  round(ratio, 3),
        "today_sources":    dict(today_sources),
        "silent_sources":   [s for s, _, _ in silent_sources],
        "flags":            flags,
        "window_days":      len(window_dates),
        "checked_at":       dt.datetime.now().isoformat(timespec="seconds"),
    }

    # Append (replace existing row for this as_of if present)
    existing: list[dict] = []
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if row.get("as_of") != as_of:
                    existing.append(row)
            except Exception:
                continue
    existing.append(payload)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(json.dumps(r) for r in existing) + "\n")

    # Site-facing compact summary (last 30 rows + today's flags) for the
    # /architecture banner. Light enough to ship in the public folder.
    SITE_OUT = ROOT.parent / "topicspace-site" / "public" / "fetch_health.json"
    SITE_OUT.parent.mkdir(parents=True, exist_ok=True)
    recent = sorted(existing, key=lambda r: r.get("as_of", ""))[-30:]
    SITE_OUT.write_text(json.dumps({
        "as_of":        as_of,
        "today_status": status,
        "today":        payload,
        "recent":       recent,
    }, indent=2))

    if not args.silent:
        emoji = {"OK": "✓", "WARN": "⚠", "FAIL": "✗"}[status]
        print(f"  {emoji} fetch health {as_of} · {status} · "
              f"{today_total} ev ({ratio*100:.0f}% of 7d median) · "
              f"{today_actors}/{DEFAULT_TRACKED_ACTORS} actors")
        if flags:
            for f in flags:
                print(f"      {f}")

    # Non-zero exit on FAIL so cron wrappers can alert
    if status == "FAIL":
        sys.exit(2)


if __name__ == "__main__":
    main()
