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
EXP_HIST_DIR = ROOT.parent / "topicspace-site" / "public" / "expectations_history"
OUT_PATH  = ROOT.parent / "topicspace-site" / "public" / "replay_history.json"


# State → plain-English "read" interpretation. Mirrors generate_leaderboard.py
# (kept inline here so the replay export doesn't import live-pipeline code).
STATE_READS = {
    "CONFIRMED":        "price confirming narrative",
    "EARLY":            "price starting to follow",
    "REPRICING":        "price lagging narrative",
    "DIVERGENCE":       "story not being paid",
    "NEG_CONFIRMATION": "selloff confirming narrative",
    "DISAGREEMENT":     "price rejecting negative narrative",
    "MACRO":            "moving with tape",
    "PRICE-LED":        "price ahead of story",
    "UNCLEAR":          "no follow-through",
}

READ_OVERRIDES = {
    # Per-ticker editorial overrides. Should track generate_leaderboard.py.
    "INTC": "price confirming negative story",
}


def state_read(ticker: str, state: str) -> str:
    return READ_OVERRIDES.get(ticker) or STATE_READS.get(state, "no clean read")


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

    # Build (date, ticker) -> historical expectation lookup from per-ticker files.
    # Only the compact fields needed for tile display are kept.
    exp_lookup: dict[tuple[str, str], dict] = {}
    if EXP_HIST_DIR.exists():
        for f in EXP_HIST_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                for e in data.get("expectations", []):
                    d = e.get("date")
                    t = e.get("ticker") or data.get("ticker")
                    if not (d and t):
                        continue
                    exp_lookup[(d, t)] = {
                        "headline":  (e.get("headline") or "")[:120],
                        "direction": (e.get("direction") or "").replace("_", " "),
                        "conviction": round(float(e.get("conviction", 0.5)), 2),
                    }
            except Exception:
                continue
        print(f"  loaded {len(exp_lookup)} historical expectations")

    snapshots = []
    for d in dates:
        d_str = str(d.date())
        sub = df[df["date"] == d].sort_values("ticker")
        actors = []
        for _, r in sub.iterrows():
            t = r["ticker"]
            row = {
                "t":     t,
                "state": r["state"],
                "narr":  int(r["narr"]),
                "nds":   round(float(r["nds"]), 1),
                "rel":   round(float(r["rel"]), 2),
                "dir":   int(r["direction"]),
                "read":  state_read(t, r["state"]),
            }
            exp = exp_lookup.get((d_str, t))
            if exp:
                row["exp"] = exp
            actors.append(row)
        snapshots.append({"date": d_str, "actors": actors})

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
