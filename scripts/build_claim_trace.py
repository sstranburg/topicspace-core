#!/usr/bin/env python3
"""
build_claim_trace.py

Per-day L2 expectation aggregates for ONE cluster, so the architecture
page can show how the L2 view of the trace example evolved over time.

Reads:
  data/derived/expectation_versions.parquet  (per-(date, ticker, cluster) attachments)
  data/derived/cluster_labels.json           (LLM label for the cluster)

Writes:
  data/derived/claim_trace.json
  topicspace-site/public/claim_trace.json

Schema:
  {
    "as_of": "YYYY-MM-DD",
    "stable_cluster_id": "theme-...",
    "label": "...",
    "n_dates": N,
    "days": [
      {
        "date": "YYYY-MM-DD",
        "n_members": int,
        "member_tickers": [...],
        "direction_dist": {"bullish": n, "bearish": n, "neutral": n},
        "dominant_direction": "bullish" | "bearish" | "mixed",
        "avg_conviction": float,
        "alignment_score": float,        // max-bucket share
        "conflict_score": float,         // entropy / log2(3)
      },
      ...
    ]
  }

Usage:
  source venv/bin/activate && python scripts/build_claim_trace.py
  python scripts/build_claim_trace.py --cluster-id theme-b9ac8fff
"""

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT        = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"

VERSIONS_PATH = ROOT / "data" / "derived" / "expectation_versions.parquet"
LABELS_PATH   = ROOT / "data" / "derived" / "cluster_labels.json"

OUT_DERIVED = ROOT / "data" / "derived" / "claim_trace.json"
OUT_SITE    = SITE_PUBLIC / "claim_trace.json"

DEFAULT_TRACE = "theme-b9ac8fff"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cluster-id", default=DEFAULT_TRACE,
                    help=f"stable_cluster_id to trace (default: {DEFAULT_TRACE})")
    args = ap.parse_args()

    if not VERSIONS_PATH.exists():
        sys.exit(f"Missing {VERSIONS_PATH} — run build_expectation_lifecycle.py first.")

    df = pd.read_parquet(VERSIONS_PATH)
    df["date"] = df["date"].astype(str)
    sub = df[df["stable_cluster_id"] == args.cluster_id].copy()
    if sub.empty:
        sys.exit(f"No expectation_versions rows for {args.cluster_id}")

    labels_cache = json.loads(LABELS_PATH.read_text()) if LABELS_PATH.exists() else {}
    label = (labels_cache.get(args.cluster_id) or {}).get("label", "")

    days = []
    for d, grp in sub.sort_values("date").groupby("date"):
        signs = grp["direction_sign"].astype(int).tolist()
        c = Counter(signs)
        total = len(signs)
        max_bucket = max(c.values())
        alignment = max_bucket / total
        # Entropy normalized to [0, 1]
        entropy = 0.0
        for n in c.values():
            p = n / total
            if p > 0:
                entropy -= p * math.log2(p)
        conflict = entropy / math.log2(3) if entropy > 0 else 0.0

        dominant_sign = max(c.items(), key=lambda x: x[1])[0]
        dom_label = {1: "bullish", -1: "bearish", 0: "mixed"}[dominant_sign]

        days.append({
            "date":               d,
            "n_members":          total,
            "member_tickers":     grp["ticker"].tolist(),
            "direction_dist": {
                "bullish": int(c.get(1, 0)),
                "bearish": int(c.get(-1, 0)),
                "neutral": int(c.get(0, 0)),
            },
            "dominant_direction": dom_label,
            "avg_conviction":     round(float(grp["conviction"].mean()), 3),
            "alignment_score":    round(alignment, 3),
            "conflict_score":     round(conflict, 3),
        })

    payload = {
        "as_of":             df["date"].max(),
        "stable_cluster_id": args.cluster_id,
        "label":             label,
        "n_dates":           len(days),
        "days":              days,
    }

    OUT_DERIVED.parent.mkdir(parents=True, exist_ok=True)
    OUT_DERIVED.write_text(json.dumps(payload, indent=2))
    OUT_SITE.write_text(json.dumps(payload, indent=2))

    print(f"  wrote {OUT_DERIVED}")
    print(f"  wrote {OUT_SITE}")
    print()
    print(f"  ─── L2 EVOLUTION · {label} ───")
    for d in days:
        dd = d["direction_dist"]
        print(f"  {d['date']}  {d['n_members']}m  "
              f"↑{dd['bullish']}/↓{dd['bearish']}/─{dd['neutral']}  "
              f"dom={d['dominant_direction']:<7}  "
              f"conv={d['avg_conviction']:.2f}  "
              f"align={int(d['alignment_score']*100)}%  "
              f"conflict={int(d['conflict_score']*100)}%  "
              f"members={d['member_tickers']}")


if __name__ == "__main__":
    main()
