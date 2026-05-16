#!/usr/bin/env python3
"""
baseline_comparison.py

Compares the deterministic topicspace engine against simple baselines on the
same backtest history. Outputs per-strategy hit rates at 5/10/20 trading-day
horizons plus per-actor breakdown.

Strategies compared:
  topicspace_engine    — state + narr_direction → predicted direction (raw, all actors)
  topicspace_trusted   — engine restricted to engine_reliable actors;
                         predictions flipped for engine_inverted actors
                         (this is closer to how the system is actually used)
  price_momentum       — sign of trailing 5d raw stock return
  relative_strength    — sign of trailing rel (lagged 5d to avoid leak)
  news_volume          — sign of (narr - 50) * direction
  random               — deterministic ±1 (seeded by ticker + index)

Scoring:
  Forward outcome = rel[i+h] (matches the existing engine backtest convention).
  A "hit" requires: prediction != 0, |forward_rel| > deadband (0.5%),
  and signs agree.

Outputs:
  data/derived/baseline_comparison_per_actor.csv
  data/derived/baseline_comparison_summary.csv
  data/derived/baseline_comparison_summary.md

Usage:
  source venv/bin/activate && python scripts/baseline_comparison.py
"""

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


ROOT = Path(__file__).parent.parent
HIST_PATH = ROOT / "data" / "derived" / "backtest_history.parquet"
RELIABILITY_PATH = ROOT / "data" / "derived" / "actor_predictive_score.json"
PRICES_DIR = ROOT / "data" / "derived" / "prices"
OUT_DIR = ROOT / "data" / "derived"

HORIZONS = [5, 10, 20]
DEADBAND = 0.5   # percentage points; matches existing engine backtest
MOMENTUM_DEADBAND = 0.005   # 0.5% raw return deadband for momentum predictor
NARR_DEADBAND = 5            # |narr - 50| deadband for news-volume predictor


# ── Strategy predictions ────────────────────────────────────────────────────

def predict_engine(state: str, narr_dir: int) -> int:
    """Mirror existing engine logic from backtest_actor_expectations.py."""
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
    """sign(trailing 5d raw return) on the date. 0 if missing."""
    rec = prices_df.loc[prices_df["timestamp"] == date]
    if rec.empty:
        return 0
    r = rec.iloc[0].get("return_5d")
    if pd.isna(r) or abs(r) < MOMENTUM_DEADBAND:
        return 0
    return +1 if r > 0 else -1


def predict_relative_strength(idx: int, df_ticker, lag: int = 5) -> int:
    """sign(rel[i-lag]) — strictly lagged trailing relative strength."""
    if idx - lag < 0:
        return 0
    past_rel = df_ticker.iloc[idx - lag]["rel"]
    if pd.isna(past_rel) or abs(past_rel) < DEADBAND:
        return 0
    return +1 if past_rel > 0 else -1


def predict_news_volume(narr: float, narr_dir: int) -> int:
    """sign((narr - 50) * direction)."""
    score = (narr - 50) * narr_dir
    if abs(score) < NARR_DEADBAND:
        return 0
    return +1 if score > 0 else -1


def predict_random(ticker: str, idx: int) -> int:
    """Deterministic ±1 — seeded by ticker + idx so it's reproducible."""
    rng = np.random.default_rng(hash((ticker, idx)) & 0xFFFFFFFF)
    return int(rng.choice([+1, -1]))


def predict_trusted(state: str, narr_dir: int, reliability: str) -> int:
    """topicspace engine restricted to actors the backtest classifies as
    engine_reliable or engine_inverted. For engine_inverted, the prediction
    sign is flipped (which is exactly how the actor pages render direction).
    Everything else returns 0 — no call."""
    if reliability == "engine_reliable":
        return predict_engine(state, narr_dir)
    if reliability == "engine_inverted":
        return -predict_engine(state, narr_dir)
    return 0  # engine_unreliable, insufficient, or unknown


# ── Scoring ─────────────────────────────────────────────────────────────────

def hit(predicted: int, forward_rel: float) -> Optional[bool]:
    """Match the existing engine backtest's hit function."""
    if predicted == 0:
        return None
    if pd.isna(forward_rel) or abs(forward_rel) < DEADBAND:
        return None
    if predicted > 0 and forward_rel > 0:
        return True
    if predicted < 0 and forward_rel < 0:
        return True
    return False


# ── Main loop ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--per-actor", default=str(OUT_DIR / "baseline_comparison_per_actor.csv"))
    ap.add_argument("--summary",   default=str(OUT_DIR / "baseline_comparison_summary.csv"))
    ap.add_argument("--markdown",  default=str(OUT_DIR / "baseline_comparison_summary.md"))
    args = ap.parse_args()

    if not HIST_PATH.exists():
        raise SystemExit(f"Missing {HIST_PATH} — run build_backtest_history.py first.")

    # Reliability map for the trusted-engine variant
    reliability_map: dict[str, str] = {}
    if RELIABILITY_PATH.exists():
        import json
        rdata = json.loads(RELIABILITY_PATH.read_text())
        reliability_map = {a["ticker"]: a.get("reliability", "unknown")
                           for a in rdata.get("actors", [])}
        print(f"  reliability map: {len(reliability_map)} actors loaded")
    else:
        print(f"  (no reliability file found — topicspace_trusted will be empty)")

    df = pd.read_parquet(HIST_PATH).copy()
    df["date"] = pd.to_datetime(df["date"])

    # If multiple variants exist, prefer the one used in the rest of the pipeline.
    if "variant" in df.columns:
        # Pick the most common variant (mid_floor is the production one)
        variant_counts = df["variant"].value_counts()
        chosen = variant_counts.idxmax()
        df = df[df["variant"] == chosen].copy()
        print(f"  using variant: {chosen} ({len(df)} rows)")

    tickers = sorted(df["ticker"].unique())
    print(f"  tickers: {len(tickers)}")
    print(f"  date range: {df['date'].min().date()} → {df['date'].max().date()}")

    # Per (strategy, horizon, ticker) accumulators
    per_actor_rows = []
    # Per (strategy, horizon) global accumulators
    def _accum():
        return {
            "n_directional": 0,
            "n_scored":      0,
            "n_hits":        0,
            "sum_excess":    0.0,
        }

    agg          = defaultdict(_accum)  # (strategy, horizon)
    agg_by_rel   = defaultdict(_accum)  # (strategy, horizon, reliability_class)
    agg_by_state = defaultdict(_accum)  # (strategy, horizon, state)

    for ticker in tickers:
        df_t = df[df["ticker"] == ticker].sort_values("date").reset_index(drop=True)
        n = len(df_t)
        if n == 0:
            continue

        # Load price file once per ticker (for momentum)
        price_path = PRICES_DIR / f"{ticker}.parquet"
        if price_path.exists():
            prices_df = pd.read_parquet(price_path).copy()
            prices_df["timestamp"] = pd.to_datetime(prices_df["timestamp"])
        else:
            prices_df = pd.DataFrame(columns=["timestamp", "return_5d"])

        rels = df_t["rel"].tolist()

        reliability = reliability_map.get(ticker, "unknown")

        for i in range(n):
            row = df_t.iloc[i]
            preds = {
                "topicspace_engine":  predict_engine(row["state"], row["direction"]),
                "topicspace_trusted": predict_trusted(row["state"], row["direction"], reliability),
                "price_momentum":     predict_price_momentum(row["date"], prices_df),
                "relative_strength":  predict_relative_strength(i, df_t, lag=5),
                "news_volume":        predict_news_volume(row["narr"], row["direction"]),
                "random":             predict_random(ticker, i),
            }

            current_state = row["state"]

            for h in HORIZONS:
                if i + h >= n:
                    continue
                fwd = rels[i + h]
                for strat, p in preds.items():
                    h_result = hit(p, fwd)

                    # Pivot 1 — (strategy, horizon)
                    a = agg[(strat, h)]
                    if p != 0:
                        a["n_directional"] += 1
                    if h_result is not None:
                        a["n_scored"] += 1
                        if h_result:
                            a["n_hits"] += 1
                        a["sum_excess"] += p * fwd

                    # Pivot 2 — (strategy, horizon, reliability_class)
                    a_rel = agg_by_rel[(strat, h, reliability)]
                    if p != 0:
                        a_rel["n_directional"] += 1
                    if h_result is not None:
                        a_rel["n_scored"] += 1
                        if h_result:
                            a_rel["n_hits"] += 1
                        a_rel["sum_excess"] += p * fwd

                    # Pivot 3 — (strategy, horizon, state)
                    a_state = agg_by_state[(strat, h, current_state)]
                    if p != 0:
                        a_state["n_directional"] += 1
                    if h_result is not None:
                        a_state["n_scored"] += 1
                        if h_result:
                            a_state["n_hits"] += 1
                        a_state["sum_excess"] += p * fwd

        # Per-actor breakdown — recompute per (strategy, horizon)
        for strat in ["topicspace_engine", "topicspace_trusted", "price_momentum",
                      "relative_strength", "news_volume", "random"]:
            for h in HORIZONS:
                n_dir = n_sco = n_hit = 0
                sum_ex = 0.0
                for i in range(n):
                    row = df_t.iloc[i]
                    if strat == "topicspace_engine":
                        p = predict_engine(row["state"], row["direction"])
                    elif strat == "topicspace_trusted":
                        p = predict_trusted(row["state"], row["direction"], reliability)
                    elif strat == "price_momentum":
                        p = predict_price_momentum(row["date"], prices_df)
                    elif strat == "relative_strength":
                        p = predict_relative_strength(i, df_t, lag=5)
                    elif strat == "news_volume":
                        p = predict_news_volume(row["narr"], row["direction"])
                    else:
                        p = predict_random(ticker, i)

                    if i + h >= n:
                        continue
                    fwd = rels[i + h]
                    if p != 0:
                        n_dir += 1
                    h_result = hit(p, fwd)
                    if h_result is not None:
                        n_sco += 1
                        if h_result:
                            n_hit += 1
                        sum_ex += p * fwd

                hr = round(n_hit / n_sco, 3) if n_sco > 0 else None
                avg_ex = round(sum_ex / n_sco, 3) if n_sco > 0 else None
                per_actor_rows.append({
                    "ticker":          ticker,
                    "reliability":     reliability,
                    "strategy":        strat,
                    "horizon_d":       h,
                    "n_directional":   n_dir,
                    "n_scored":        n_sco,
                    "n_hits":          n_hit,
                    "hit_rate":        hr,
                    "avg_excess_pct":  avg_ex,
                })

    # ── Write per-actor CSV ─────────────────────────────────────────────────
    per_actor_df = pd.DataFrame(per_actor_rows)
    per_actor_path = Path(args.per_actor)
    per_actor_path.parent.mkdir(parents=True, exist_ok=True)
    per_actor_df.to_csv(per_actor_path, index=False)
    print(f"\n  wrote {per_actor_path}  ({len(per_actor_df)} rows)")

    # ── Write summary CSV ───────────────────────────────────────────────────
    summary_rows = []
    for (strat, h), a in sorted(agg.items()):
        hr = round(a["n_hits"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
        avg_ex = round(a["sum_excess"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
        summary_rows.append({
            "strategy":        strat,
            "horizon_d":       h,
            "n_directional":   a["n_directional"],
            "n_scored":        a["n_scored"],
            "n_hits":          a["n_hits"],
            "hit_rate":        hr,
            "avg_excess_pct":  avg_ex,
        })
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(args.summary, index=False)
    print(f"  wrote {args.summary}  ({len(summary_df)} rows)")

    # ── Write by-reliability CSV ────────────────────────────────────────────
    by_rel_rows = []
    for (strat, h, rel), a in sorted(agg_by_rel.items()):
        hr = round(a["n_hits"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
        avg_ex = round(a["sum_excess"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
        by_rel_rows.append({
            "strategy":         strat,
            "horizon_d":        h,
            "reliability_class": rel,
            "n_directional":    a["n_directional"],
            "n_scored":         a["n_scored"],
            "n_hits":           a["n_hits"],
            "hit_rate":         hr,
            "avg_excess_pct":   avg_ex,
        })
    by_rel_path = OUT_DIR / "baseline_comparison_by_reliability.csv"
    pd.DataFrame(by_rel_rows).to_csv(by_rel_path, index=False)
    print(f"  wrote {by_rel_path}  ({len(by_rel_rows)} rows)")

    # ── Write by-state CSV ──────────────────────────────────────────────────
    by_state_rows = []
    for (strat, h, state), a in sorted(agg_by_state.items()):
        hr = round(a["n_hits"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
        avg_ex = round(a["sum_excess"] / a["n_scored"], 3) if a["n_scored"] > 0 else None
        by_state_rows.append({
            "strategy":         strat,
            "horizon_d":        h,
            "state":            state,
            "n_directional":    a["n_directional"],
            "n_scored":         a["n_scored"],
            "n_hits":           a["n_hits"],
            "hit_rate":         hr,
            "avg_excess_pct":   avg_ex,
        })
    by_state_path = OUT_DIR / "baseline_comparison_by_state.csv"
    pd.DataFrame(by_state_rows).to_csv(by_state_path, index=False)
    print(f"  wrote {by_state_path}  ({len(by_state_rows)} rows)")

    # ── Write markdown table ────────────────────────────────────────────────
    def _get(strat, h):
        return next((x for x in summary_rows
                     if x["strategy"] == strat and x["horizon_d"] == h), None)

    md_lines = []
    md_lines.append(f"# Baseline comparison")
    md_lines.append("")
    md_lines.append(f"Backtest window: {df['date'].min().date()} → {df['date'].max().date()}  ·  "
                    f"Tickers: {len(tickers)}  ·  Deadband: ±{DEADBAND}% on forward `rel`")
    md_lines.append("")
    md_lines.append("## Key finding")
    md_lines.append("")

    # Compute the key contrast for the summary line
    trust_20 = _get("topicspace_trusted", 20)
    engine_20 = _get("topicspace_engine", 20)
    rand_20 = _get("random", 20)
    best_baseline_hr = max(
        (_get(s, 20)["hit_rate"] for s in ["price_momentum", "relative_strength", "news_volume"]
         if _get(s, 20) and _get(s, 20)["hit_rate"] is not None),
        default=None,
    )

    if trust_20 and trust_20["hit_rate"] is not None:
        md_lines.append(
            f"At the 20-day horizon, **`topicspace_trusted` hits "
            f"{int(round(trust_20['hit_rate'] * 100))}% with +{trust_20['avg_excess_pct']:.2f}pp avg excess** "
            f"— vs. {int(round(rand_20['hit_rate'] * 100))}% random and "
            f"{int(round(best_baseline_hr * 100))}% best baseline. The raw "
            f"`topicspace_engine` (no reliability filter) hits "
            f"{int(round(engine_20['hit_rate'] * 100))}% — near coin-flip. **The edge lives "
            f"in the reliability filter**, not in the deterministic state engine on its own."
        )
        md_lines.append("")

    md_lines.append("## Method")
    md_lines.append("")
    md_lines.append("Hit rate = % of directional calls that moved the right way beyond the deadband. "
                    "Average excess = mean sign-adjusted forward return per scored call (in "
                    "percentage points). Forward outcome uses `rel[i+h]` from "
                    "`backtest_history.parquet`.")
    md_lines.append("")
    md_lines.append("## Results")
    md_lines.append("")
    md_lines.append("| Strategy | Horizon | n_calls | n_scored | Hit rate | Avg excess (pp) |")
    md_lines.append("|---|---|---|---|---|---|")
    # Order: trusted-first (production use), then raw engine, then baselines
    strat_order = ["topicspace_trusted", "topicspace_engine", "price_momentum",
                   "relative_strength", "news_volume", "random"]
    for strat in strat_order:
        for h in HORIZONS:
            r = next((x for x in summary_rows
                      if x["strategy"] == strat and x["horizon_d"] == h), None)
            if r is None:
                continue
            hr_str = f"{int(round(r['hit_rate'] * 100))}%" if r["hit_rate"] is not None else "—"
            ex_str = f"{r['avg_excess_pct']:+.2f}" if r["avg_excess_pct"] is not None else "—"
            md_lines.append(
                f"| `{r['strategy']}` | {r['horizon_d']}d "
                f"| {r['n_directional']} | {r['n_scored']} "
                f"| **{hr_str}** | {ex_str} |"
            )
    md_lines.append("")
    md_lines.append("**Reading the table.** Hit rates around 50% are coin-flip "
                    "(see `random` baseline). A strategy is informative if its "
                    "hit rate beats the relevant alternatives at the same horizon "
                    "and the average excess return is positive after deadband "
                    "filtering. Excess is sign-adjusted: positive means the "
                    "strategy made money on its directional calls.")
    md_lines.append("")
    # ── Sliced sections ─────────────────────────────────────────────────────
    md_lines.append("")
    md_lines.append("## Where the edge lives — by reliability class")
    md_lines.append("")
    md_lines.append("Same six strategies, but partitioned by the actor's backtested reliability "
                    "class. This tells you whether trusted-variant performance is broad or "
                    "concentrated in the `engine_reliable` bucket. Showing the 20-day horizon only.")
    md_lines.append("")
    md_lines.append("| Strategy | Reliability class | n_scored | Hit rate | Avg excess (pp) |")
    md_lines.append("|---|---|---|---|---|")

    REL_DISPLAY = [
        ("engine_reliable",   "trusted"),
        ("engine_inverted",   "contrarian (flipped)"),
        ("engine_unreliable", "uncertain"),
        ("insufficient",      "new"),
    ]
    for strat in strat_order:
        for rel_key, rel_label in REL_DISPLAY:
            row = next((r for r in by_rel_rows
                        if r["strategy"] == strat and r["horizon_d"] == 20
                        and r["reliability_class"] == rel_key), None)
            if row is None or (row.get("hit_rate") is None and row.get("n_scored", 0) == 0):
                continue
            hr_str = (f"{int(round(row['hit_rate'] * 100))}%"
                      if row['hit_rate'] is not None else "—")
            ex_str = (f"{row['avg_excess_pct']:+.2f}"
                      if row['avg_excess_pct'] is not None else "—")
            md_lines.append(
                f"| `{strat}` | {rel_label} | {row['n_scored']} | "
                f"**{hr_str}** | {ex_str} |"
            )

    md_lines.append("")
    md_lines.append("## Where the edge lives — by state (20-day horizon, trusted only)")
    md_lines.append("")
    md_lines.append("Which states does `topicspace_trusted` actually make money in? "
                    "States like CONFIRMED and EARLY should show edge; PRICE-LED and DIVERGENCE may not.")
    md_lines.append("")
    md_lines.append("| State | n_scored | Hit rate | Avg excess (pp) |")
    md_lines.append("|---|---|---|---|")

    state_order = ["CONFIRMED", "EARLY", "REPRICING", "DISAGREEMENT", "NEG_CONFIRMATION",
                   "DIVERGENCE", "PRICE-LED", "UNCLEAR", "MACRO"]
    for st in state_order:
        row = next((r for r in by_state_rows
                    if r["strategy"] == "topicspace_trusted"
                    and r["horizon_d"] == 20
                    and r["state"] == st), None)
        if row is None or row.get("n_scored", 0) == 0:
            continue
        hr_str = (f"{int(round(row['hit_rate'] * 100))}%"
                  if row['hit_rate'] is not None else "—")
        ex_str = (f"{row['avg_excess_pct']:+.2f}"
                  if row['avg_excess_pct'] is not None else "—")
        md_lines.append(f"| **{st}** | {row['n_scored']} | **{hr_str}** | {ex_str} |")

    md_lines.append("")
    md_lines.append("**Caveats.**")
    md_lines.append("")
    md_lines.append("- Backtest window is ~6 months. Sample sizes per actor are small for narrow horizons.")
    md_lines.append("- No walk-forward validation. Reliability classifications used by `topicspace_trusted` "
                    "are derived from the same window being tested, so this is an in-sample fit on the trust filter.")
    md_lines.append("- Forward `rel` is a ±5d centered return, which overlaps near-horizon outcomes; "
                    "this is consistent across all strategies but inflates 5d signal/noise.")
    md_lines.append("- `news_volume` and `relative_strength` baselines are intentionally crude; "
                    "they exist as floor checks, not as serious alternative strategies.")
    md_lines.append("")

    Path(args.markdown).write_text("\n".join(md_lines))
    print(f"  wrote {args.markdown}")

    # ── Console summary ─────────────────────────────────────────────────────
    print()
    print("  ─── HIT RATE SUMMARY ───────────────────────────────────────────")
    print(f"  {'STRATEGY':<24} {'H':>4} {'N_DIR':>7} {'N_SCO':>7} {'HIT':>7} {'EXC':>8}")
    for strat in strat_order:
        for h in HORIZONS:
            r = next((x for x in summary_rows
                      if x["strategy"] == strat and x["horizon_d"] == h), None)
            if r is None:
                continue
            hr_str = f"{int(round(r['hit_rate'] * 100))}%" if r["hit_rate"] is not None else "  —"
            ex_str = f"{r['avg_excess_pct']:+.2f}" if r["avg_excess_pct"] is not None else "   —"
            print(f"  {strat:<24} {r['horizon_d']:>3}d {r['n_directional']:>7} "
                  f"{r['n_scored']:>7} {hr_str:>7} {ex_str:>8}")
    print()


if __name__ == "__main__":
    main()
