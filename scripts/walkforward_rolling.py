#!/usr/bin/env python3
"""
walkforward_rolling.py

Rolling (expanding-window) walk-forward validation of the trust filter.

The single 70/30 split in walkforward_validation.py showed the trusted
variant collapses from ~64% in-sample to ~50-55% out-of-sample. This
script asks: was that a one-time artifact of the specific split, or
does it hold across multiple held-out windows?

Method:
  - Non-overlapping test windows of ~20 trading days, starting 60 days in
  - For each test window: train on ALL prior data (expanding window),
    derive reliability per ticker, score predictions on the test window
  - Report per-window hit rates + aggregate across all windows

Outputs:
  data/derived/walkforward_rolling_summary.csv
  data/derived/walkforward_rolling_summary.md

Usage:
  source venv/bin/activate && python scripts/walkforward_rolling.py
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

MIN_TRAIN_DAYS    = 60   # minimum train window before scoring first test window
TEST_WINDOW_DAYS  = 20   # length of each held-out test window
MIN_DIRECTIONAL_FOR_CLASSIFICATION = 20
HIT_RATE_RELIABLE = 0.60
HIT_RATE_INVERTED = 0.40


# ── Engine + baselines ──────────────────────────────────────────────────────

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


def predict_trusted(state: str, narr_dir: int, reliability: str) -> int:
    if reliability == "engine_reliable":
        return predict_engine(state, narr_dir)
    if reliability == "engine_inverted":
        return -predict_engine(state, narr_dir)
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


# ── Reliability classification on train subset ──────────────────────────────

def classify_reliability_for_ticker(df_t: pd.DataFrame) -> str:
    n = len(df_t)
    if n == 0:
        return "insufficient"
    rels = df_t["rel"].tolist()
    states = df_t["state"].tolist()
    narr_dirs = df_t["direction"].tolist()

    per_h = {h: {"directional": 0, "scored": 0, "hits": 0} for h in HORIZONS}
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

    horizon_hit_rates = [s["hits"] / s["scored"] for s in per_h.values() if s["scored"] > 0]
    total_directional = sum(s["directional"] for s in per_h.values())
    if total_directional < MIN_DIRECTIONAL_FOR_CLASSIFICATION or not horizon_hit_rates:
        return "insufficient"
    best, worst = max(horizon_hit_rates), min(horizon_hit_rates)
    if best >= HIT_RATE_RELIABLE:
        return "engine_reliable"
    if worst <= HIT_RATE_INVERTED:
        return "engine_inverted"
    return "engine_unreliable"


# ── Per-window evaluation ───────────────────────────────────────────────────

def _accum():
    return {"n_directional": 0, "n_scored": 0, "n_hits": 0, "sum_excess": 0.0}


def evaluate_window(df, prices_cache: dict, train_end_excl, test_start, test_end):
    """Train reliability on all data before train_end_excl; score predictions
    in [test_start, test_end). Returns dict keyed by (strategy, horizon)."""
    train_df = df[df["date"] < train_end_excl]
    test_df  = df[(df["date"] >= test_start) & (df["date"] < test_end)]

    # Classify reliability per ticker on the train subset
    reliability = {}
    class_counts = defaultdict(int)
    for ticker in sorted(train_df["ticker"].unique()):
        df_t_train = train_df[train_df["ticker"] == ticker].sort_values("date").reset_index(drop=True)
        rel = classify_reliability_for_ticker(df_t_train)
        reliability[ticker] = rel
        class_counts[rel] += 1

    # We need each test row to know its own index within the WHOLE history
    # so the relative_strength predictor can look back 5 rows.
    # Build a per-ticker (sorted) view of the full history for this purpose.
    full_by_ticker = {
        t: df[df["ticker"] == t].sort_values("date").reset_index(drop=True)
        for t in df["ticker"].unique()
    }

    agg = defaultdict(_accum)
    for ticker in sorted(test_df["ticker"].unique()):
        df_t_full = full_by_ticker[ticker]
        # Within the full history, locate the index range that falls in [test_start, test_end)
        mask = (df_t_full["date"] >= test_start) & (df_t_full["date"] < test_end)
        test_idx_in_full = df_t_full.index[mask].tolist()
        if not test_idx_in_full:
            continue

        rels_full = df_t_full["rel"].tolist()
        n_full = len(df_t_full)
        prices_df = prices_cache.get(ticker, pd.DataFrame(columns=["timestamp", "return_5d"]))
        rel_class = reliability.get(ticker, "insufficient")

        for i in test_idx_in_full:
            row = df_t_full.iloc[i]
            preds = {
                "topicspace_engine":  predict_engine(row["state"], row["direction"]),
                "topicspace_trusted": predict_trusted(row["state"], row["direction"], rel_class),
                "price_momentum":     predict_price_momentum(row["date"], prices_df),
                "relative_strength":  predict_relative_strength(i, df_t_full, lag=5),
                "news_volume":        predict_news_volume(row["narr"], row["direction"]),
                "random":             predict_random(ticker, i),
            }
            for h in HORIZONS:
                if i + h >= n_full:
                    continue
                # The forward outcome may sit OUTSIDE the test window in terms
                # of the date axis — that's fine, it's still strictly forward.
                fwd = rels_full[i + h]
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

    return agg, dict(class_counts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()

    if not HIST_PATH.exists():
        raise SystemExit(f"Missing {HIST_PATH}")

    df = pd.read_parquet(HIST_PATH).copy()
    df["date"] = pd.to_datetime(df["date"])
    if "variant" in df.columns:
        df = df[df["variant"] == df["variant"].mode().iloc[0]].copy()

    dates = sorted(df["date"].unique())
    n_dates = len(dates)
    print(f"  full window: {dates[0].date()} → {dates[-1].date()} ({n_dates} trading days)")

    # Cache price files once
    prices_cache = {}
    for ticker in sorted(df["ticker"].unique()):
        p = PRICES_DIR / f"{ticker}.parquet"
        if p.exists():
            pdf = pd.read_parquet(p).copy()
            pdf["timestamp"] = pd.to_datetime(pdf["timestamp"])
            prices_cache[ticker] = pdf

    # Build non-overlapping test windows starting after MIN_TRAIN_DAYS
    windows = []
    cursor = MIN_TRAIN_DAYS
    while cursor + TEST_WINDOW_DAYS <= n_dates:
        train_end_excl = dates[cursor]
        test_start     = dates[cursor]
        test_end_idx   = min(cursor + TEST_WINDOW_DAYS, n_dates - 1)
        test_end       = dates[test_end_idx]
        windows.append({
            "i":              len(windows) + 1,
            "train_end_excl": train_end_excl,
            "test_start":     test_start,
            "test_end":       test_end,
        })
        cursor += TEST_WINDOW_DAYS

    print(f"  {len(windows)} non-overlapping test windows of ~{TEST_WINDOW_DAYS} days each")

    # ── Evaluate each window ────────────────────────────────────────────────
    per_window = []  # list of (window_meta, agg, class_counts)
    aggregate = defaultdict(_accum)

    strat_order = ["topicspace_trusted", "topicspace_engine", "price_momentum",
                   "relative_strength", "news_volume", "random"]

    for w in windows:
        print(f"\n  WINDOW {w['i']}: train ends {w['train_end_excl'].date()}, "
              f"test {w['test_start'].date()} → {w['test_end'].date()}")
        agg_w, cls_w = evaluate_window(df, prices_cache, w["train_end_excl"],
                                       w["test_start"], w["test_end"])
        per_window.append({"meta": w, "agg": agg_w, "classes": cls_w})

        # Print quick window result
        print(f"    train classes: " + ", ".join(f"{k}={v}" for k, v in cls_w.items()))
        for strat in ["topicspace_trusted"]:
            for h in HORIZONS:
                a = agg_w.get((strat, h), _accum())
                hr = a["n_hits"] / a["n_scored"] if a["n_scored"] > 0 else None
                hr_str = f"{int(round(hr*100))}%" if hr is not None else "—"
                print(f"    {strat:<22} {h:>2}d  n={a['n_scored']:<4} hit={hr_str}")

        # Roll into aggregate
        for k, v in agg_w.items():
            agg = aggregate[k]
            agg["n_directional"] += v["n_directional"]
            agg["n_scored"]      += v["n_scored"]
            agg["n_hits"]        += v["n_hits"]
            agg["sum_excess"]    += v["sum_excess"]

    # ── Build CSV rows ──────────────────────────────────────────────────────
    csv_rows = []
    for w_idx, w in enumerate(per_window):
        for (strat, h), a in w["agg"].items():
            hr = round(a["n_hits"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
            avg_ex = round(a["sum_excess"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
            csv_rows.append({
                "window":         w_idx + 1,
                "train_end_excl": str(w["meta"]["train_end_excl"].date()),
                "test_start":     str(w["meta"]["test_start"].date()),
                "test_end":       str(w["meta"]["test_end"].date()),
                "strategy":       strat,
                "horizon_d":      h,
                "n_directional":  a["n_directional"],
                "n_scored":       a["n_scored"],
                "n_hits":         a["n_hits"],
                "hit_rate":       hr,
                "avg_excess_pct": avg_ex,
            })
    # Aggregate row per (strategy, horizon)
    agg_rows = []
    for (strat, h), a in sorted(aggregate.items()):
        hr = round(a["n_hits"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
        avg_ex = round(a["sum_excess"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
        agg_rows.append({
            "strategy":       strat,
            "horizon_d":      h,
            "n_directional":  a["n_directional"],
            "n_scored":       a["n_scored"],
            "n_hits":         a["n_hits"],
            "hit_rate":       hr,
            "avg_excess_pct": avg_ex,
        })

    csv_path = OUT_DIR / "walkforward_rolling_per_window.csv"
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
    print(f"\n  wrote {csv_path}  ({len(csv_rows)} rows)")

    agg_path = OUT_DIR / "walkforward_rolling_summary.csv"
    pd.DataFrame(agg_rows).to_csv(agg_path, index=False)
    print(f"  wrote {agg_path}  ({len(agg_rows)} rows)")

    # ── Markdown summary ────────────────────────────────────────────────────
    md = []
    md.append("# Rolling walk-forward validation")
    md.append("")
    md.append(f"Method: expanding-window walk-forward. For each test window, "
              f"reliability classifications are derived using ALL data prior to the test "
              f"start. Test windows are non-overlapping; ~{TEST_WINDOW_DAYS} trading days each.")
    md.append("")
    md.append(f"{len(per_window)} test windows covering "
              f"{per_window[0]['meta']['test_start'].date()} → "
              f"{per_window[-1]['meta']['test_end'].date()}.")
    md.append("")
    md.append("## Aggregate out-of-sample hit rates (all windows pooled)")
    md.append("")
    md.append("| Strategy | Horizon | n_scored | Hit rate | Avg excess (pp) |")
    md.append("|---|---|---|---|---|")
    for strat in strat_order:
        for h in HORIZONS:
            r = next((x for x in agg_rows if x["strategy"] == strat and x["horizon_d"] == h), None)
            if r is None:
                continue
            hr_str = f"{int(round(r['hit_rate'] * 100))}%" if r["hit_rate"] is not None else "—"
            ex_str = f"{r['avg_excess_pct']:+.2f}" if r["avg_excess_pct"] is not None else "—"
            md.append(f"| `{strat}` | {r['horizon_d']}d | {r['n_scored']} | **{hr_str}** | {ex_str} |")
    md.append("")
    md.append("## Per-window trusted-variant hit rate (20d horizon)")
    md.append("")
    md.append("| Window | Train ends | Test range | n_scored | Hit rate | Avg excess (pp) |")
    md.append("|---|---|---|---|---|---|")
    for w in per_window:
        a = w["agg"].get(("topicspace_trusted", 20), _accum())
        hr = a["n_hits"] / a["n_scored"] if a["n_scored"] > 0 else None
        avg_ex = a["sum_excess"] / a["n_scored"] if a["n_scored"] > 0 else None
        hr_str = f"{int(round(hr*100))}%" if hr is not None else "—"
        ex_str = f"{avg_ex:+.2f}" if avg_ex is not None else "—"
        md.append(
            f"| W{w['meta']['i']} "
            f"| {w['meta']['train_end_excl'].date()} "
            f"| {w['meta']['test_start'].date()} → {w['meta']['test_end'].date()} "
            f"| {a['n_scored']} | **{hr_str}** | {ex_str} |"
        )
    md.append("")
    md.append("**Reading.** If the trusted hit rate is broadly stable across windows "
              "(narrow range), the in-sample fit caveat is weaker. If it varies wildly "
              "(say, one window at 70% and another at 40%), the per-window variance is "
              "itself an honest finding.")
    md.append("")

    md_path = OUT_DIR / "walkforward_rolling_summary.md"
    md_path.write_text("\n".join(md))
    print(f"  wrote {md_path}")

    # ── Console summary ─────────────────────────────────────────────────────
    print()
    print("  ─── AGGREGATE OUT-OF-SAMPLE ────────────────────────────────────")
    print(f"  {'STRATEGY':<24} {'H':>4} {'N_SCO':>7} {'HIT':>7} {'EXC':>8}")
    for strat in strat_order:
        for h in HORIZONS:
            r = next((x for x in agg_rows if x["strategy"] == strat and x["horizon_d"] == h), None)
            if r is None:
                continue
            hr_str = f"{int(round(r['hit_rate'] * 100))}%" if r["hit_rate"] is not None else "  —"
            ex_str = f"{r['avg_excess_pct']:+.2f}" if r["avg_excess_pct"] is not None else "   —"
            print(f"  {strat:<24} {h:>3}d {r['n_scored']:>7} {hr_str:>7} {ex_str:>8}")
    print()
    # Per-window variance for the trusted-20d cell
    trusted_20d_hits = []
    for w in per_window:
        a = w["agg"].get(("topicspace_trusted", 20), _accum())
        if a["n_scored"] > 0:
            trusted_20d_hits.append(a["n_hits"] / a["n_scored"])
    if trusted_20d_hits:
        mean = sum(trusted_20d_hits) / len(trusted_20d_hits)
        spread = max(trusted_20d_hits) - min(trusted_20d_hits)
        print(f"  trusted @ 20d per-window: " +
              ", ".join(f"{int(round(h*100))}%" for h in trusted_20d_hits))
        print(f"    mean={int(round(mean*100))}%, range={int(round(spread*100))}pp")


if __name__ == "__main__":
    main()
