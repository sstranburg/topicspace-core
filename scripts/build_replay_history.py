#!/usr/bin/env python3
"""
build_replay_history.py

Exports backtest_history.parquet as a single JSON file consumed by the
/replay page on the site. Lets users scrub through ~120 trading days and
see the full ecosystem state at any prior date.

Output shape:
  {
    "first_date": "2025-11-24",
    "last_date":  "2026-05-14",
    "n_dates":    120,
    "n_actors":   32,
    "snapshots": [
      {
        "date": "2025-11-24",
        "actors": [
          {"t": "AMD", "state": "REPRICING", "narr": 64, "nds": 18.2,
           "rel": 3.1, "dir": 1},
          ...
        ]
      },
      ...
    ]
  }

Reads:  data/derived/backtest_history.parquet
Writes: topicspace-site/public/replay_history.json
"""

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
HIST_PATH = ROOT / "data" / "derived" / "backtest_history.parquet"
OUT_PATH  = ROOT.parent / "topicspace-site" / "public" / "replay_history.json"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    if not HIST_PATH.exists():
        raise SystemExit(f"Missing {HIST_PATH}")

    df = pd.read_parquet(HIST_PATH).copy()
    df["date"] = pd.to_datetime(df["date"])
    if "variant" in df.columns:
        df = df[df["variant"] == df["variant"].mode().iloc[0]].copy()

    dates = sorted(df["date"].unique())
    print(f"  {len(dates)} dates × {df['ticker'].nunique()} tickers")

    snapshots = []
    for d in dates:
        sub = df[df["date"] == d].sort_values("ticker")
        actors = []
        for _, r in sub.iterrows():
            actors.append({
                "t":     r["ticker"],
                "state": r["state"],
                "narr":  int(r["narr"]),
                "nds":   round(float(r["nds"]), 1),
                "rel":   round(float(r["rel"]), 2),
                "dir":   int(r["direction"]),
            })
        snapshots.append({"date": str(d.date()), "actors": actors})

    out = {
        "first_date": str(dates[0].date()),
        "last_date":  str(dates[-1].date()),
        "n_dates":    len(dates),
        "n_actors":   int(df["ticker"].nunique()),
        "snapshots":  snapshots,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, separators=(",", ":")))
    size_kb = out_path.stat().st_size / 1024
    print(f"  wrote {out_path}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
