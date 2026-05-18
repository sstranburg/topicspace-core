#!/usr/bin/env python3
"""
build_field_actor_history.py

Extracts per-actor `semantic_density_7d` history over the corpus window
from the existing `field_instrumentation.parquet` (already point-in-time
computed by build_field_instrumentation.py). No re-compute needed; this
is just a thin shaper that emits a small JSON the architecture page can
draw as sparklines next to the L1 metrics table.

Reads:
  data/derived/field_instrumentation.parquet

Writes:
  data/derived/field_actor_history.json
  topicspace-site/public/field_actor_history.json

Usage:
  source venv/bin/activate && python scripts/build_field_actor_history.py
  python scripts/build_field_actor_history.py --days 60
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"

IN_PARQ     = ROOT / "data" / "derived" / "field_instrumentation.parquet"
OUT_DERIVED = ROOT / "data" / "derived" / "field_actor_history.json"
OUT_SITE    = SITE_PUBLIC / "field_actor_history.json"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=60,
                    help="trailing window length in days (default: 60)")
    args = ap.parse_args()

    if not IN_PARQ.exists():
        sys.exit(f"Missing {IN_PARQ} — run build_field_instrumentation.py first.")

    df = pd.read_parquet(IN_PARQ)
    df["date"] = df["date"].astype(str)
    max_date  = df["date"].max()
    cutoff    = (pd.Timestamp(max_date) - pd.Timedelta(days=args.days - 1)).date().isoformat()
    df = df[df["date"] >= cutoff].copy()

    # Per-actor compact history: ordered list of (date, density_7d, momentum)
    # density_momentum can be NaN early in the window; clamp to 0 in output.
    df["density_momentum"] = df["density_momentum"].fillna(0)
    df["semantic_density_7d"] = df["semantic_density_7d"].fillna(0)

    actors: dict[str, dict] = {}
    for ticker, grp in df.groupby("ticker"):
        grp_sorted = grp.sort_values("date")
        series = [
            {
                "d": r["date"],
                "v": round(float(r["semantic_density_7d"]), 4),
            }
            for _, r in grp_sorted.iterrows()
        ]
        actors[ticker] = {
            "series":    series,
            "last":      series[-1]["v"] if series else 0.0,
            "min":       min((s["v"] for s in series), default=0.0),
            "max":       max((s["v"] for s in series), default=0.0),
            "momentum":  round(float(grp_sorted["density_momentum"].iloc[-1]), 4),
        }

    payload = {
        "as_of":   max_date,
        "n_days":  args.days,
        "metric":  "semantic_density_7d",
        "actors":  actors,
    }

    OUT_DERIVED.parent.mkdir(parents=True, exist_ok=True)
    OUT_DERIVED.write_text(json.dumps(payload, indent=2))
    OUT_SITE.write_text(json.dumps(payload, indent=2))

    print(f"  actors:   {len(actors)}")
    print(f"  window:   {cutoff} → {max_date}")
    print(f"  wrote {OUT_DERIVED}")
    print(f"  wrote {OUT_SITE}")


if __name__ == "__main__":
    main()
