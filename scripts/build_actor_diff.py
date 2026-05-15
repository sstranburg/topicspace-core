#!/usr/bin/env python3
"""
build_actor_diff.py

Compares today's actor snapshot to the prior trading day's snapshot and writes
a compact diff to topicspace-site/public/actor_diff_daily.json. The actor page
reads this and renders an inline "what changed" panel.

Reads:
  topicspace-site/public/actors.json              (today's snapshot)
  data/derived/backtest_history.parquet           (historical snapshots)
  data/derived/actor_predictive_score.json        (reliability classification)

Writes:
  topicspace-site/public/actor_diff_daily.json

For each actor the diff captures:
  nds_change         — today.nds - prior.nds
  rel_change         — today.rel - prior.rel
  narr_change        — today.narr - prior.narr
  state_today        — current state string
  state_yesterday    — prior state string
  state_changed      — bool
  reliability_today  — engine_reliable / engine_inverted / engine_unreliable / insufficient
  notable            — short summary string when something material changed

Usage:
  source venv/bin/activate && python scripts/build_actor_diff.py
"""

import argparse
import datetime as dt
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).parent.parent
HIST_PATH    = ROOT / "data" / "derived" / "backtest_history.parquet"
ACTORS_PATH  = ROOT.parent / "topicspace-site" / "public" / "actors.json"
SCORE_PATH   = ROOT / "data" / "derived" / "actor_predictive_score.json"
OUT_PATH     = ROOT.parent / "topicspace-site" / "public" / "actor_diff_daily.json"


def _round(x: float, n: int = 1) -> float:
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return 0.0


def _make_notable(d: dict) -> str | None:
    """Produce a one-line summary of what materially changed, or None."""
    parts = []
    if d.get("state_changed"):
        parts.append(f"state {d['state_yesterday']} → {d['state_today']}")
    if abs(d.get("nds_change") or 0) >= 10:
        sign = "+" if d["nds_change"] > 0 else ""
        parts.append(f"NDS {sign}{d['nds_change']:.0f}")
    if abs(d.get("rel_change") or 0) >= 2.0:
        sign = "+" if d["rel_change"] > 0 else ""
        parts.append(f"rel {sign}{d['rel_change']:.1f}%")
    if abs(d.get("narr_change") or 0) >= 5:
        sign = "+" if d["narr_change"] > 0 else ""
        parts.append(f"narr {sign}{d['narr_change']:.0f}")
    return " · ".join(parts) if parts else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    if not HIST_PATH.exists():
        raise SystemExit(f"Missing {HIST_PATH}")
    if not ACTORS_PATH.exists():
        raise SystemExit(f"Missing {ACTORS_PATH}")

    df = pd.read_parquet(HIST_PATH).copy()
    df["date"] = pd.to_datetime(df["date"])
    if "variant" in df.columns:
        df = df[df["variant"] == df["variant"].mode().iloc[0]].copy()

    actors_today = json.loads(ACTORS_PATH.read_text())["actors"]
    score_by_t = {}
    if SCORE_PATH.exists():
        score_by_t = {a["ticker"]: a for a in json.loads(SCORE_PATH.read_text()).get("actors", [])}

    # Determine "today" and "yesterday" dates from the parquet
    available_dates = sorted(df["date"].unique())
    if len(available_dates) < 2:
        raise SystemExit("backtest_history.parquet has fewer than 2 dates; cannot diff")

    today_date = available_dates[-1]
    prior_date = available_dates[-2]

    today_rows = df[df["date"] == today_date]
    prior_rows = df[df["date"] == prior_date]
    today_by_t = {r["ticker"]: r for _, r in today_rows.iterrows()}
    prior_by_t = {r["ticker"]: r for _, r in prior_rows.iterrows()}

    diffs = []
    for actor in actors_today:
        t = actor.get("t")
        if not t:
            continue
        today_row = today_by_t.get(t)
        prior_row = prior_by_t.get(t)
        if today_row is None or prior_row is None:
            # New actor or missing prior data; emit a stub
            diffs.append({
                "ticker":     t,
                "available":  False,
                "reliability_today": (score_by_t.get(t) or {}).get("reliability"),
                "state_today":       actor.get("state"),
                "notable":           "new — no prior snapshot for diff",
            })
            continue

        nds_change  = _round(today_row["nds"]  - prior_row["nds"],  1)
        rel_change  = _round(today_row["rel"]  - prior_row["rel"],  2)
        narr_change = int(today_row["narr"] - prior_row["narr"])
        state_today = today_row["state"]
        state_prior = prior_row["state"]
        state_changed = state_today != state_prior

        d = {
            "ticker":             t,
            "available":          True,
            "as_of":              str(today_date.date()),
            "vs":                 str(prior_date.date()),
            "nds_today":          _round(today_row["nds"], 1),
            "nds_yesterday":      _round(prior_row["nds"], 1),
            "nds_change":         nds_change,
            "rel_today":          _round(today_row["rel"], 2),
            "rel_yesterday":      _round(prior_row["rel"], 2),
            "rel_change":         rel_change,
            "narr_today":         int(today_row["narr"]),
            "narr_yesterday":     int(prior_row["narr"]),
            "narr_change":        narr_change,
            "state_today":        state_today,
            "state_yesterday":    state_prior,
            "state_changed":      state_changed,
            "reliability_today":  (score_by_t.get(t) or {}).get("reliability"),
        }
        d["notable"] = _make_notable(d)
        diffs.append(d)

    out = {
        "as_of":        str(today_date.date()),
        "vs":           str(prior_date.date()),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "n_actors":     len(diffs),
        "actors":       diffs,
    }
    Path(args.out).write_text(json.dumps(out, indent=2))

    notable = [d for d in diffs if d.get("notable")]
    print(f"  wrote {args.out}")
    print(f"  {today_date.date()} vs {prior_date.date()}  ·  {len(diffs)} actors  ·  {len(notable)} notable changes")


if __name__ == "__main__":
    main()
