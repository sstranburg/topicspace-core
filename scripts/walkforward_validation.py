#!/usr/bin/env python3
"""
walkforward_validation.py

Out-of-sample sanity check on the reliability filter.

The in-sample baseline comparison (baseline_comparison.py) uses reliability
classifications derived from the same window being scored. This script
splits the backtest window into train + test, classifies reliability
*only on train data*, and scores predictions on the held-out test window.

If the trusted variant's edge survives, the in-sample-fit caveat closes.
If it collapses to near-random, the trust filter is curve-fitting.

Train/test split:
  - First 70% of trading dates → train (used to derive reliability)
  - Last 30% of trading dates  → test  (used to score predictions)

Outputs:
  data/derived/walkforward_summary.csv
  data/derived/walkforward_summary.md
  data/derived/walkforward_reliability_train.json   (the train-derived map)

Usage:
  source venv/bin/activate && python scripts/walkforward_validation.py
  python scripts/walkforward_validation.py --train-ratio 0.6
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
HIST_PATH = ROOT / "data" / "derived" / "backtest_history.parquet"
PRICES_DIR = ROOT / "data" / "derived" / "prices"
OUT_DIR = ROOT / "data" / "derived"

HORIZONS = [5, 10, 20]
DEADBAND = 0.5
MOMENTUM_DEADBAND = 0.005
NARR_DEADBAND = 5

# Reliability classification thresholds — match backtest_actor_expectations.py
MIN_DIRECTIONAL_FOR_CLASSIFICATION = 20   # relaxed from 30 since train window is shorter
HIT_RATE_RELIABLE   = 0.60
HIT_RATE_INVERTED   = 0.40


# ── Engine ──────────────────────────────────────────────────────────────────

def predict_engine(state: str, narr_dir: int) -> int:
    if narr_dir > 0:
        if state in ("CONFIRMED", "EARLY", "REPRICING", "DISAGREEMENT"):
            return +1
        if state == "NEG_CONFIRMATION":
            return -1
        return 0
    else:
        if state in ("NEG_CONFIRMATION", "CONFIRMED"):
            return -1
        if state == "DISAGREEMENT":
            return +1
        return 0


def predict_price_momentum(date, prices_df) -> int:
    rec = prices_df.loc[prices_df["timestamp"] == date]
    if rec.empty:
        return 0
    r = rec.iloc[0].get("return_5d")
    if pd.isna(r) or abs(r) < MOMENTUM_DEADBAND:
        return 0
    return +1 if r > 0 else -1


def predict_relative_strength(idx: int, df_ticker, lag: int = 5) -> int:
    if idx - lag < 0:
        return 0
    past_rel = df_ticker.iloc[idx - lag]["rel"]
    if pd.isna(past_rel) or abs(past_rel) < DEADBAND:
        return 0
    return +1 if past_rel > 0 else -1


def predict_news_volume(narr: float, narr_dir: int) -> int:
    score = (narr - 50) * narr_dir
    if abs(score) < NARR_DEADBAND:
        return 0
    return +1 if score > 0 else -1


def predict_random(ticker: str, idx: int) -> int:
    rng = np.random.default_rng(hash((ticker, idx)) & 0xFFFFFFFF)
    return int(rng.choice([+1, -1]))


def hit(predicted: int, forward_rel: float) -> Optional[bool]:
    if predicted == 0:
        return None
    if pd.isna(forward_rel) or abs(forward_rel) < DEADBAND:
        return None
    if predicted > 0 and forward_rel > 0:
        return True
    if predicted < 0 and forward_rel < 0:
        return True
    return False


# ── Reliability classification (train-only) ─────────────────────────────────

def classify_reliability_for_ticker(df_t: pd.DataFrame) -> tuple[str, dict]:
    """Mirror backtest_actor_expectations.py reliability logic on a subset.
    Returns (reliability_label, per_horizon_stats)."""
    n = len(df_t)
    if n == 0:
        return ("insufficient", {})

    rels = df_t["rel"].tolist()
    states = df_t["state"].tolist()
    narr_dirs = df_t["direction"].tolist()

    per_h: dict[int, dict] = {h: {"directional": 0, "scored": 0, "hits": 0} for h in HORIZONS}

    for i in range(n):
        p = predict_engine(states[i], narr_dirs[i])
        for h in HORIZONS:
            if i + h >= n:
                continue
            fwd = rels[i + h]
            if p != 0:
                per_h[h]["directional"] += 1
            r = hit(p, fwd)
            if r is not None:
                per_h[h]["scored"] += 1
                if r:
                    per_h[h]["hits"] += 1

    # Best/worst hit rate across horizons
    horizon_hit_rates = []
    for h in HORIZONS:
        s = per_h[h]
        if s["scored"] > 0:
            hr = s["hits"] / s["scored"]
            horizon_hit_rates.append(hr)
            s["hit_rate"] = round(hr, 3)
        else:
            s["hit_rate"] = None

    total_directional = sum(s["directional"] for s in per_h.values())
    if total_directional < MIN_DIRECTIONAL_FOR_CLASSIFICATION or not horizon_hit_rates:
        return ("insufficient", per_h)

    best  = max(horizon_hit_rates)
    worst = min(horizon_hit_rates)

    if best >= HIT_RATE_RELIABLE:
        return ("engine_reliable", per_h)
    if worst <= HIT_RATE_INVERTED:
        return ("engine_inverted", per_h)
    return ("engine_unreliable", per_h)


# ── Test-set scoring ────────────────────────────────────────────────────────

def predict_trusted(state: str, narr_dir: int, reliability: str) -> int:
    if reliability == "engine_reliable":
        return predict_engine(state, narr_dir)
    if reliability == "engine_inverted":
        return -predict_engine(state, narr_dir)
    return 0


def _accum():
    return {"n_directional": 0, "n_scored": 0, "n_hits": 0, "sum_excess": 0.0}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-ratio", type=float, default=0.7,
                    help="Fraction of dates assigned to train (default 0.7)")
    args = ap.parse_args()

    if not HIST_PATH.exists():
        raise SystemExit(f"Missing {HIST_PATH}")

    df = pd.read_parquet(HIST_PATH).copy()
    df["date"] = pd.to_datetime(df["date"])
    if "variant" in df.columns:
        chosen = df["variant"].value_counts().idxmax()
        df = df[df["variant"] == chosen].copy()

    dates = sorted(df["date"].unique())
    split_idx = int(len(dates) * args.train_ratio)
    split_date = dates[split_idx]
    train_df = df[df["date"] < split_date].copy()
    test_df  = df[df["date"] >= split_date].copy()

    print(f"  full window: {dates[0].date()} → {dates[-1].date()} ({len(dates)} trading days)")
    print(f"  train: {len(train_df)} rows up to {split_date.date()} (excl)")
    print(f"  test:  {len(test_df)} rows from {split_date.date()} forward")

    # ── Classify reliability per ticker on TRAIN only ───────────────────────
    print("\n  classifying reliability on train window only…")
    reliability_train: dict[str, str] = {}
    train_class_counts = defaultdict(int)
    for ticker in sorted(train_df["ticker"].unique()):
        df_t = train_df[train_df["ticker"] == ticker].sort_values("date").reset_index(drop=True)
        rel, _ = classify_reliability_for_ticker(df_t)
        reliability_train[ticker] = rel
        train_class_counts[rel] += 1

    print(f"    train classifications: " + ", ".join(
        f"{k}={v}" for k, v in train_class_counts.items()
    ))

    # Save the train-derived reliability map for transparency
    (OUT_DIR / "walkforward_reliability_train.json").write_text(json.dumps({
        "train_end_excl": str(split_date.date()),
        "min_directional": MIN_DIRECTIONAL_FOR_CLASSIFICATION,
        "thresholds":      {"reliable": HIT_RATE_RELIABLE, "inverted": HIT_RATE_INVERTED},
        "reliability":     reliability_train,
    }, indent=2))

    # ── Score TEST set with train-derived reliability ───────────────────────
    print("\n  scoring test window with train-derived reliability…")
    agg = defaultdict(_accum)  # (strategy, horizon)

    for ticker in sorted(test_df["ticker"].unique()):
        df_t_test  = test_df[test_df["ticker"] == ticker].sort_values("date").reset_index(drop=True)
        n = len(df_t_test)
        if n == 0:
            continue

        # Load price file once (for momentum predictor)
        price_path = PRICES_DIR / f"{ticker}.parquet"
        if price_path.exists():
            prices_df = pd.read_parquet(price_path).copy()
            prices_df["timestamp"] = pd.to_datetime(prices_df["timestamp"])
        else:
            prices_df = pd.DataFrame(columns=["timestamp", "return_5d"])

        reliability = reliability_train.get(ticker, "insufficient")
        rels = df_t_test["rel"].tolist()

        for i in range(n):
            row = df_t_test.iloc[i]
            preds = {
                "topicspace_engine":  predict_engine(row["state"], row["direction"]),
                "topicspace_trusted": predict_trusted(row["state"], row["direction"], reliability),
                "price_momentum":     predict_price_momentum(row["date"], prices_df),
                "relative_strength":  predict_relative_strength(i, df_t_test, lag=5),
                "news_volume":        predict_news_volume(row["narr"], row["direction"]),
                "random":             predict_random(ticker, i),
            }
            for h in HORIZONS:
                if i + h >= n:
                    continue
                fwd = rels[i + h]
                for strat, p in preds.items():
                    a = agg[(strat, h)]
                    if p != 0:
                        a["n_directional"] += 1
                    r = hit(p, fwd)
                    if r is not None:
                        a["n_scored"] += 1
                        if r:
                            a["n_hits"] += 1
                        a["sum_excess"] += p * fwd

    # ── Write summary CSV ────────────────────────────────────────────────────
    rows = []
    for (strat, h), a in sorted(agg.items()):
        hr = round(a["n_hits"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
        avg_ex = round(a["sum_excess"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
        rows.append({
            "strategy":         strat,
            "horizon_d":        h,
            "n_directional":    a["n_directional"],
            "n_scored":         a["n_scored"],
            "n_hits":           a["n_hits"],
            "hit_rate":         hr,
            "avg_excess_pct":   avg_ex,
        })
    csv_path = OUT_DIR / "walkforward_summary.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    print(f"\n  wrote {csv_path}  ({len(rows)} rows)")

    # ── Write markdown ──────────────────────────────────────────────────────
    md = []
    md.append("# Walk-forward validation")
    md.append("")
    md.append(f"Reliability classification fit on train window "
              f"({dates[0].date()} → {split_date.date()}, excl). "
              f"Predictions scored on held-out test window "
              f"({split_date.date()} → {dates[-1].date()}).")
    md.append("")
    md.append(f"Train tickers classified as: " + ", ".join(
        f"`{k}` = {v}" for k, v in train_class_counts.items()
    ))
    md.append("")
    md.append("## Out-of-sample hit rates")
    md.append("")
    md.append("| Strategy | Horizon | n_calls | n_scored | Hit rate | Avg excess (pp) |")
    md.append("|---|---|---|---|---|---|")
    strat_order = ["topicspace_trusted", "topicspace_engine", "price_momentum",
                   "relative_strength", "news_volume", "random"]
    for strat in strat_order:
        for h in HORIZONS:
            r = next((x for x in rows if x["strategy"] == strat and x["horizon_d"] == h), None)
            if r is None:
                continue
            hr_str = f"{int(round(r['hit_rate'] * 100))}%" if r["hit_rate"] is not None else "—"
            ex_str = f"{r['avg_excess_pct']:+.2f}" if r["avg_excess_pct"] is not None else "—"
            md.append(
                f"| `{strat}` | {r['horizon_d']}d "
                f"| {r['n_directional']} | {r['n_scored']} "
                f"| **{hr_str}** | {ex_str} |"
            )
    md.append("")
    md.append("**Reading.** Trust filter classifications were assigned using the train "
              "window only. If `topicspace_trusted` retains an edge on this out-of-sample "
              "test set, the in-sample caveat on the headline 64% number closes — the "
              "filter generalizes. If it collapses, the trust filter was curve-fitting.")
    md.append("")
    md.append("**Caveats.**")
    md.append("- Train window is shorter than the full backtest, so per-ticker sample "
              "sizes are smaller. The minimum-directional threshold was relaxed from 30 "
              "to 20 to accommodate this.")
    md.append("- Test window is ~6-8 weeks of trading days only. Statistical power is "
              "limited; one volatile actor can move aggregate numbers.")
    md.append("- Forward `rel` is still a ±5d centered measure; partial overlap with "
              "the test boundary is possible at the test/train edge.")
    md.append("")

    md_path = OUT_DIR / "walkforward_summary.md"
    md_path.write_text("\n".join(md))
    print(f"  wrote {md_path}")

    # ── Console summary ─────────────────────────────────────────────────────
    print()
    print("  ─── OUT-OF-SAMPLE HIT RATES ───────────────────────────────────")
    print(f"  {'STRATEGY':<24} {'H':>4} {'N_DIR':>7} {'N_SCO':>7} {'HIT':>7} {'EXC':>8}")
    for strat in strat_order:
        for h in HORIZONS:
            r = next((x for x in rows if x["strategy"] == strat and x["horizon_d"] == h), None)
            if r is None:
                continue
            hr_str = f"{int(round(r['hit_rate'] * 100))}%" if r["hit_rate"] is not None else "  —"
            ex_str = f"{r['avg_excess_pct']:+.2f}" if r["avg_excess_pct"] is not None else "   —"
            print(f"  {strat:<24} {r['horizon_d']:>3}d {r['n_directional']:>7} "
                  f"{r['n_scored']:>7} {hr_str:>7} {ex_str:>8}")
    print()


if __name__ == "__main__":
    main()
