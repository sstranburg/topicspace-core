#!/usr/bin/env python3
"""
build_storm_trace.py

For 1-2 auto-selected storms, emit the full per-day timeline so the
/architecture L1 panel can show "trace one storm over time" — the
clearest demonstration of how L1 + L3 cohere (a storm is a persistent
entity that grows, drifts, merges, splits, retires).

Selection: score each storm by (n_dates × n_unique_lifecycles ×
log1p(total_events) × (1 + bonus for merge/split/drift events)). Top
N are chosen so the trace is information-dense and shows lifecycle
variety, not a flat "persisted-every-day" run.

Reads:
  data/derived/cluster_lineage.parquet
  data/derived/cluster_members.parquet
  data/derived/cluster_labels.json
  data/normalized/tech_ecosystem_filtered.jsonl + backfill

Writes:
  data/derived/storm_traces.json
  topicspace-site/public/storm_traces.json

Schema:
  {
    "as_of": "YYYY-MM-DD",
    "traces": [
      {
        "stable_cluster_id": "theme-...",
        "label": "...",
        "first_seen": "YYYY-MM-DD",
        "last_seen":  "YYYY-MM-DD",
        "n_dates":    26,
        "total_events": 25485,
        "lifecycle_counts": {"persisted": 18, "merge_target": 4, ...},
        "days": [
          {
            "date":      "YYYY-MM-DD",
            "lifecycle": "born" | "persisted" | "drift" | "merge_target" | "split_target",
            "n_events":  234,
            "n_actors":  12,
            "drift":     0.034,
            "top_actors": ["NVDA", "AMD", "INTC"],     // top 3 by event count this day
            "sample_title": "..." | null,              // one representative title
          },
          ...
        ]
      },
      ...
    ]
  }

Usage:
  source venv/bin/activate && python scripts/build_storm_trace.py
  python scripts/build_storm_trace.py --top 2
  python scripts/build_storm_trace.py --cluster-id theme-b9892d63
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


ROOT        = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"

LINEAGE_PATH = ROOT / "data" / "derived" / "cluster_lineage.parquet"
MEMBERS_PATH = ROOT / "data" / "derived" / "cluster_members.parquet"
LABELS_PATH  = ROOT / "data" / "derived" / "cluster_labels.json"
SOURCES      = [
    ROOT / "data" / "normalized" / "tech_ecosystem_filtered.jsonl",
    ROOT / "data" / "normalized" / "tech_ecosystem_backfill.jsonl",
]

OUT_DERIVED = ROOT / "data" / "derived" / "storm_traces.json"
OUT_SITE    = SITE_PUBLIC / "storm_traces.json"


def select_storms(lineage: pd.DataFrame, top_n: int) -> list[str]:
    """Auto-select the most interesting storms — favors lifecycle variety."""
    agg = lineage.groupby("stable_cluster_id").agg(
        n_dates=("date", "nunique"),
        total_events=("n_events", "sum"),
        n_unique_lifecycles=("lifecycle", "nunique"),
        has_merge=("lifecycle", lambda x: "merge_target" in set(x)),
        has_split=("lifecycle", lambda x: "split_target" in set(x)),
        has_drift=("lifecycle", lambda x: "drift" in set(x)),
    ).reset_index()
    agg["bonus"] = (
        agg["has_merge"].astype(int)
        + agg["has_split"].astype(int)
        + agg["has_drift"].astype(int)
    )
    agg["score"] = (
        agg["n_dates"] * agg["n_unique_lifecycles"]
        * np.log1p(agg["total_events"]) * (1 + agg["bonus"])
    )
    return agg.nlargest(top_n, "score")["stable_cluster_id"].tolist()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=2,
                    help="number of storms to trace (default 2)")
    ap.add_argument("--cluster-id", default=None,
                    help="trace a specific stable_cluster_id instead of auto-selecting")
    args = ap.parse_args()

    if not LINEAGE_PATH.exists():
        sys.exit(f"Missing {LINEAGE_PATH}")
    if not MEMBERS_PATH.exists():
        sys.exit(f"Missing {MEMBERS_PATH}")

    lineage = pd.read_parquet(LINEAGE_PATH)
    lineage["date"] = lineage["date"].astype(str)
    members = pd.read_parquet(MEMBERS_PATH)
    members["date"] = members["date"].astype(str)
    labels_cache = json.loads(LABELS_PATH.read_text()) if LABELS_PATH.exists() else {}

    selected = [args.cluster_id] if args.cluster_id else select_storms(lineage, args.top)
    print(f"  selected storms: {selected}")

    # We need per-day actor + title info, which requires joining
    # cluster_members with event metadata. Loading the JSONL once into a
    # dict is cheap (~70k events).
    selected_member_rows = members[members["stable_cluster_id"].isin(selected)]
    needed_event_ids = set(selected_member_rows["event_id"])
    print(f"  events to look up: {len(needed_event_ids):,}")

    event_meta: dict[str, dict] = {}
    for src in SOURCES:
        if not src.exists():
            continue
        with open(src) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                eid = e.get("event_id")
                if not eid or eid not in needed_event_ids or eid in event_meta:
                    continue
                event_meta[eid] = {
                    "actors": e.get("actors", []) or [],
                    "title":  e.get("title", "") or "",
                }
    print(f"  event meta loaded for {len(event_meta):,} / {len(needed_event_ids):,}")

    # Build per-storm trace
    traces: list[dict] = []
    for sid in selected:
        storm_lineage = lineage[lineage["stable_cluster_id"] == sid].sort_values("date")
        if storm_lineage.empty:
            print(f"  ! no lineage rows for {sid}")
            continue
        label = (labels_cache.get(sid) or {}).get("label", "")

        # Per-day actors + sample title
        storm_members = selected_member_rows[
            selected_member_rows["stable_cluster_id"] == sid
        ]

        days = []
        for _, lrow in storm_lineage.iterrows():
            d_iso = lrow["date"]
            day_rows = storm_members[storm_members["date"] == d_iso]
            ac: Counter = Counter()
            titles: list[str] = []
            for _, mrow in day_rows.iterrows():
                meta = event_meta.get(mrow["event_id"], {})
                for a in meta.get("actors", []):
                    ac[a] += 1
                t = (meta.get("title") or "").strip()
                if t and len(t) > 8:
                    titles.append(t)
            # First non-duplicate title
            sample_title = None
            seen = set()
            for t in titles:
                key = t.strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                sample_title = t[:140]
                break
            days.append({
                "date":         d_iso,
                "lifecycle":    lrow["lifecycle"],
                "n_events":     int(lrow["n_events"]),
                "n_actors":     int(lrow["n_actors"]),
                "drift":        (None if pd.isna(lrow["drift_from_prior"])
                                  else round(float(lrow["drift_from_prior"]), 3)),
                "top_actors":   [a for a, _ in ac.most_common(3)],
                "sample_title": sample_title,
            })

        lifecycle_counts = dict(Counter(d["lifecycle"] for d in days))
        traces.append({
            "stable_cluster_id":  sid,
            "label":              label,
            "first_seen":         days[0]["date"],
            "last_seen":          days[-1]["date"],
            "n_dates":            len(days),
            "total_events":       sum(d["n_events"] for d in days),
            "lifecycle_counts":   lifecycle_counts,
            "days":               days,
        })

    payload = {
        "as_of":  lineage["date"].max(),
        "traces": traces,
    }

    OUT_DERIVED.parent.mkdir(parents=True, exist_ok=True)
    OUT_DERIVED.write_text(json.dumps(payload, indent=2))
    OUT_SITE.write_text(json.dumps(payload, indent=2))

    print(f"  wrote {OUT_DERIVED}")
    print(f"  wrote {OUT_SITE}")
    print()
    for t in traces:
        print(f"  ─── {t['label'][:60]} ───")
        print(f"    {t['n_dates']}d · {t['total_events']:,} events · {t['first_seen']} → {t['last_seen']}")
        print(f"    lifecycles: {t['lifecycle_counts']}")


if __name__ == "__main__":
    main()
