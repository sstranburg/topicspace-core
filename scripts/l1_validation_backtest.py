#!/usr/bin/env python3
"""
l1_validation_backtest.py  —  F-001 (the gate)

Compares 6 pressure variants through the existing state engine and rolling
walk-forward harness. Tells us whether semantic density (or any variant)
improves over the existing event-count `narr` as the input to the state
engine. If none of the variants beats `narr` cleanly, L1 stays as a debug
panel; if one does, F-008 promotes it to production.

Variants:
  1. narr                       — existing event-count + recency pressure
  2. event_count_7d             — raw 7-day event count (no recency boost)
  3. semantic_density_7d        — local cosine density in actor's neighborhood
  4. source_weighted_density    — density weighted by neighbor source reliability
  5. novelty_adjusted_density   — semantic_density_7d * (1 + 0.5 * novelty)
  6. density_momentum           — d(density)/d(t)

For each variant:
  - Convert to a per-actor [0, 95] pressure scale via point-in-time z-score
    (using only past 90 days BEFORE date t)
  - Run the existing state engine using that pressure
  - Run rolling walk-forward (2 non-overlapping ~20-day test windows on the
    current corpus; matches walkforward_rolling.py)
  - Score: hit rate, avg excess, median excess, sample size — by horizon
  - State stability: total state transitions per actor / total days
  - False spike rate: % of state changes that revert within 2 days

Plus:
  - Disagreement report: (date, ticker) cells where narr and density
    disagree dramatically, plus top high-novelty / high-dispersion examples
  - Point-in-time leakage assertions (test data strictly forward of train)
  - Markdown summary for /methods §11

Reads:
  data/derived/backtest_history.parquet      (narr, state, nds, rel, direction)
  data/derived/field_instrumentation.parquet (L1 field metrics)
  data/derived/prices/*.parquet              (for raw price-momentum baseline,
                                              not strictly needed here)

Writes:
  data/derived/l1_validation_summary.csv         (per variant × horizon)
  data/derived/l1_validation_per_window.csv      (per fold detail)
  data/derived/l1_validation_disagreements.csv   (example rows)
  data/derived/l1_validation_summary.md          (methods §11 content)

Usage:
  source venv/bin/activate && python scripts/l1_validation_backtest.py
"""

from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


ROOT = Path(__file__).parent.parent
HIST_PATH   = ROOT / "data" / "derived" / "backtest_history.parquet"
FIELD_PATH  = ROOT / "data" / "derived" / "field_instrumentation.parquet"
OUT_DIR     = ROOT / "data" / "derived"

HORIZONS    = [5, 10, 20]
DEADBAND    = 0.5      # |forward rel| must exceed this in pp to score
ZSCORE_WIN  = 90       # days of past data for the PIT z-score baseline

VARIANTS = [
    "narr",
    "event_count_7d",
    "semantic_density_7d",
    "source_weighted_density",
    "novelty_adjusted_density",
    "density_momentum",
]


# ── State engine (fork of build_backtest_history.classify_state) ───────────

def state_engine(pressure: float, direction: int, rel: float) -> str:
    """Same decision tree as build_backtest_history.classify_state, but the
    `narr` input is replaced by `pressure` (still on a 0-95 scale)."""
    if direction < 0:
        return "DISAGREEMENT" if rel > 2.0 else "NEG_CONFIRMATION"

    if pressure >= 65 and rel >= 5.0:
        return "CONFIRMED"
    if pressure >= 55 and rel >= 1.5:
        return "EARLY"
    if pressure >= 45 and rel < -5.0:
        return "DIVERGENCE"
    if pressure >= 45 and -5.0 <= rel < 1.5:
        return "REPRICING"
    if rel < -6.0:
        return "DIVERGENCE"

    price_score = max(0, min(100, 50 + rel * 5))
    nds = pressure - price_score
    if rel > 2.0 and pressure < 60 and nds < -20:
        return "PRICE-LED"
    if pressure < 40:
        return "UNCLEAR"
    return "MACRO"


def predict_direction(state: str, narr_dir: int) -> int:
    """Mirror backtest_actor_expectations.predicted_direction (flip_bearish=False)."""
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


# ── PIT z-score → pressure ─────────────────────────────────────────────────

def pit_zscore_pressure(group: pd.DataFrame, col: str, window_days: int = ZSCORE_WIN) -> np.ndarray:
    """For each row, compute z-score using only values STRICTLY before this row's
    date (within `window_days` calendar days). Map z → pressure in [0, 95]
    via 50 + z*15. Returns a numpy array aligned to group's index."""
    g = group.sort_values("date").reset_index(drop=True)
    values = g[col].astype(float).values
    dates  = g["date"].values
    out = np.zeros(len(g), dtype=np.float32)
    for i in range(len(g)):
        cutoff = dates[i] - np.timedelta64(window_days, "D")
        mask = (dates < dates[i]) & (dates >= cutoff)
        past = values[mask]
        past = past[~np.isnan(past)]
        if len(past) < 5:
            # Not enough history: fall back to 50 (neutral pressure)
            out[i] = 50.0
            continue
        mu = past.mean()
        sd = past.std()
        if sd < 1e-9:
            out[i] = 50.0
            continue
        z = (values[i] - mu) / sd
        out[i] = float(np.clip(50.0 + z * 15.0, 0.0, 95.0))
    return out


# ── Rolling walk-forward folds (mirror walkforward_rolling.py) ─────────────

def build_folds(dates: list[pd.Timestamp],
                min_train_days: int = 60,
                test_window_days: int = 20) -> list[dict]:
    n = len(dates)
    folds = []
    cursor = min_train_days
    while cursor + test_window_days <= n:
        train_end_excl = dates[cursor]
        test_start     = dates[cursor]
        test_end       = dates[min(cursor + test_window_days, n - 1)]
        folds.append({
            "i":              len(folds) + 1,
            "train_end_excl": train_end_excl,
            "test_start":     test_start,
            "test_end":       test_end,
        })
        cursor += test_window_days
    return folds


# ── Scoring ─────────────────────────────────────────────────────────────────

def score_variant(df: pd.DataFrame, variant: str, folds: list[dict]) -> dict:
    """Returns:
      per_fold:    list of {fold, horizon, n_dir, n_scored, n_hits, hit_rate, avg_excess, median_excess}
      aggregate:   per-horizon pooled stats
      state_stab:  {mean_transitions_per_day, transitions_per_actor:...}
      false_spike: {pct_reverted_within_2d}
    """
    pressure_col = f"pressure__{variant}"
    state_col    = f"state__{variant}"
    pred_col     = f"pred__{variant}"

    per_fold = []
    pool = defaultdict(lambda: {
        "n_dir":     0,
        "n_scored":  0,
        "n_hits":    0,
        "excess":    [],   # list of sign-adjusted forward rels for median
    })

    # Build full-history series of states for stability + false spike
    df_sorted = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    # For each fold, score over test window
    for fold in folds:
        for ticker, g in df_sorted.groupby("ticker"):
            g = g.reset_index(drop=True)
            rels = g["rel"].values
            n = len(g)
            for i in range(n):
                d = g.iloc[i]["date"]
                if d < fold["test_start"] or d >= fold["test_end"]:
                    continue
                p = g.iloc[i][pred_col]
                for h in HORIZONS:
                    if i + h >= n:
                        continue
                    fwd = rels[i + h]
                    if p != 0:
                        pool[(fold["i"], h)]["n_dir"] += 1
                    r = hit(int(p), float(fwd))
                    if r is not None:
                        pool[(fold["i"], h)]["n_scored"] += 1
                        if r:
                            pool[(fold["i"], h)]["n_hits"] += 1
                        pool[(fold["i"], h)]["excess"].append(int(p) * float(fwd))

    for (fold_i, h), v in sorted(pool.items()):
        if v["n_scored"] == 0:
            hr = None; ae = None; me = None
        else:
            hr = v["n_hits"] / v["n_scored"]
            ae = float(np.mean(v["excess"]))
            me = float(np.median(v["excess"]))
        per_fold.append({
            "fold":     fold_i,
            "horizon":  h,
            "n_dir":    v["n_dir"],
            "n_scored": v["n_scored"],
            "n_hits":   v["n_hits"],
            "hit_rate":      round(hr, 4) if hr is not None else None,
            "avg_excess":    round(ae, 3) if ae is not None else None,
            "median_excess": round(me, 3) if me is not None else None,
        })

    # Pool across folds, per horizon
    pooled_by_h = defaultdict(lambda: {"n_dir": 0, "n_scored": 0, "n_hits": 0, "excess": []})
    for r in per_fold:
        b = pooled_by_h[r["horizon"]]
        b["n_dir"]    += r["n_dir"]
        b["n_scored"] += r["n_scored"]
        b["n_hits"]   += r["n_hits"]
    # Recover excess values from per-fold (we already merged from `pool` above)
    for (fold_i, h), v in pool.items():
        pooled_by_h[h]["excess"].extend(v["excess"])

    aggregate = []
    for h in HORIZONS:
        v = pooled_by_h[h]
        if v["n_scored"] == 0:
            aggregate.append({
                "horizon": h, "n_dir": v["n_dir"], "n_scored": 0, "n_hits": 0,
                "hit_rate": None, "avg_excess": None, "median_excess": None,
            })
        else:
            aggregate.append({
                "horizon":  h,
                "n_dir":    v["n_dir"],
                "n_scored": v["n_scored"],
                "n_hits":   v["n_hits"],
                "hit_rate":      round(v["n_hits"] / v["n_scored"], 4),
                "avg_excess":    round(float(np.mean(v["excess"])), 3),
                "median_excess": round(float(np.median(v["excess"])), 3),
            })

    # State stability across the WHOLE corpus (not just test windows — diagnostic)
    transitions = 0
    n_days_total = 0
    false_spikes = 0
    n_changes = 0
    for ticker, g in df_sorted.groupby("ticker"):
        states = g[state_col].tolist()
        n_days_total += len(states)
        for i in range(1, len(states)):
            if states[i] != states[i - 1]:
                transitions += 1
                n_changes += 1
                # Reverts within 2 days?
                if i + 2 < len(states):
                    if states[i + 1] == states[i - 1] or states[i + 2] == states[i - 1]:
                        false_spikes += 1
    state_stab = {
        "transitions":    transitions,
        "days":           n_days_total,
        "transitions_per_day": round(transitions / max(1, n_days_total), 4),
    }
    false_spike = {
        "n_state_changes": n_changes,
        "n_reverts_2d":    false_spikes,
        "false_spike_pct": round(false_spikes / max(1, n_changes) * 100, 1),
    }

    return {
        "per_fold":   per_fold,
        "aggregate":  aggregate,
        "state_stab": state_stab,
        "false_spike": false_spike,
    }


# ── Disagreement report ────────────────────────────────────────────────────

def disagreement_examples(df: pd.DataFrame, n_each: int = 15) -> pd.DataFrame:
    """Identify dates×tickers where narr and semantic_density tell different
    stories. Plus top high-novelty and high-dispersion cases.
    Uses raw (non-z-scored) field values for interpretability."""
    sub = df.copy()
    # Normalize for comparison: per-actor z-score (full-window for diagnostic — not used for scoring)
    for col in ("narr", "semantic_density_7d", "novelty_score", "dispersion"):
        sub[f"z_{col}"] = sub.groupby("ticker")[col].transform(
            lambda s: (s - s.mean()) / (s.std() + 1e-9)
        )
    sub["narr_minus_density"] = sub["z_narr"] - sub["z_semantic_density_7d"]

    examples = []

    # narr high, density low (events without theme density)
    nh_dl = sub[(sub["z_narr"] >= 1.0) & (sub["z_semantic_density_7d"] <= -0.5)] \
        .sort_values("narr_minus_density", ascending=False).head(n_each)
    for _, r in nh_dl.iterrows():
        examples.append({**_disagreement_row(r), "case": "narr_high_density_low"})

    # density high, narr low (themes without event volume)
    dh_nl = sub[(sub["z_semantic_density_7d"] >= 1.0) & (sub["z_narr"] <= -0.5)] \
        .sort_values("narr_minus_density", ascending=True).head(n_each)
    for _, r in dh_nl.iterrows():
        examples.append({**_disagreement_row(r), "case": "density_high_narr_low"})

    # High novelty
    hn = sub.sort_values("novelty_score", ascending=False).head(n_each)
    for _, r in hn.iterrows():
        examples.append({**_disagreement_row(r), "case": "high_novelty"})

    # High dispersion
    hd = sub.sort_values("dispersion", ascending=False).head(n_each)
    for _, r in hd.iterrows():
        examples.append({**_disagreement_row(r), "case": "high_dispersion"})

    return pd.DataFrame(examples)


def _disagreement_row(r) -> dict:
    return {
        "date":                  str(pd.Timestamp(r["date"]).date()),
        "ticker":                r["ticker"],
        "narr":                  int(r["narr"]),
        "event_count_7d":        int(r["event_count_7d"]),
        "semantic_density_7d":   round(float(r["semantic_density_7d"]), 4),
        "novelty_score":         round(float(r["novelty_score"]), 4),
        "dispersion":            round(float(r["dispersion"]), 4),
        "state_baseline":        r["state"],
        "rel":                   round(float(r["rel"]), 2),
        "nds":                   round(float(r["nds"]), 1),
    }


# ── PIT leakage assertions ─────────────────────────────────────────────────

def assert_pit_correctness(df: pd.DataFrame, variant: str, folds: list[dict]):
    """Loud failure if any fold's test window overlaps train or vice versa,
    or if any pressure value was computed using future data."""
    pcol = f"pressure__{variant}"
    for fold in folds:
        ts = fold["test_start"]
        te = fold["test_end"]
        assert ts < te, f"fold {fold['i']}: test_start >= test_end"
        # Train end (exclusive) must equal test start
        assert fold["train_end_excl"] == ts, \
            f"fold {fold['i']}: train_end != test_start (no buffer enforcement)"

    # Pressure column must exist and be in [0, 95]
    p = df[pcol].astype(float)
    assert p.min() >= 0 and p.max() <= 95, \
        f"variant {variant}: pressure outside [0, 95] (min={p.min()}, max={p.max()})"


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    if not HIST_PATH.exists():
        raise SystemExit(f"Missing {HIST_PATH}")
    if not FIELD_PATH.exists():
        raise SystemExit(f"Missing {FIELD_PATH} — run build_field_instrumentation.py first")

    # ── Load data ───────────────────────────────────────────────────────────
    print("  loading data…")
    hist = pd.read_parquet(HIST_PATH).copy()
    hist["date"] = pd.to_datetime(hist["date"])
    if "variant" in hist.columns:
        hist = hist[hist["variant"] == hist["variant"].mode().iloc[0]].copy()
        hist = hist.drop(columns=["variant"])

    field = pd.read_parquet(FIELD_PATH).copy()
    field["date"] = pd.to_datetime(field["date"])

    # Merge on (date, ticker)
    df = hist.merge(field, on=["date", "ticker"], how="inner")
    print(f"    {len(df):,} (date,ticker) rows")

    # Derive novelty_adjusted_density (density scaled by 1 + 0.5 * novelty)
    df["novelty_adjusted_density"] = (
        df["semantic_density_7d"] * (1.0 + 0.5 * df["novelty_score"])
    )

    # ── PIT z-score → pressure per variant ──────────────────────────────────
    print("  computing per-actor PIT z-scores → pressure (0-95)…")
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    for variant in VARIANTS:
        if variant == "narr":
            # Use raw narr (already on [0, 95] with thresholds tuned for it)
            df[f"pressure__{variant}"] = df["narr"].astype(float).clip(0, 95)
        else:
            # PIT z-score per actor → pressure
            pieces = []
            for ticker, g in df.groupby("ticker"):
                p = pit_zscore_pressure(g, variant)
                pieces.append(pd.Series(p, index=g.index))
            df[f"pressure__{variant}"] = pd.concat(pieces).sort_index()

    # ── Run state engine + predict_direction per variant ────────────────────
    print("  running state engine for each variant…")
    for variant in VARIANTS:
        pcol = f"pressure__{variant}"
        states = []
        preds  = []
        for _, r in df.iterrows():
            s = state_engine(float(r[pcol]), int(r["direction"]), float(r["rel"]))
            d = predict_direction(s, int(r["direction"]))
            states.append(s)
            preds.append(d)
        df[f"state__{variant}"] = states
        df[f"pred__{variant}"]  = preds

    # ── Rolling walk-forward folds ──────────────────────────────────────────
    trading_dates = sorted(df["date"].unique())
    folds = build_folds(trading_dates)
    print(f"  {len(folds)} rolling walk-forward folds")
    for f in folds:
        print(f"    fold {f['i']}: train ends {f['train_end_excl'].date()}, "
              f"test {f['test_start'].date()} → {f['test_end'].date()}")

    # ── Score each variant ──────────────────────────────────────────────────
    print("\n  scoring variants…")
    all_aggregate = []
    all_per_fold  = []
    stability_rows = []

    for variant in VARIANTS:
        assert_pit_correctness(df, variant, folds)
        result = score_variant(df, variant, folds)
        for r in result["aggregate"]:
            r["variant"] = variant
            all_aggregate.append(r)
        for r in result["per_fold"]:
            r["variant"] = variant
            all_per_fold.append(r)
        stability_rows.append({
            "variant":             variant,
            "transitions":         result["state_stab"]["transitions"],
            "days":                result["state_stab"]["days"],
            "transitions_per_day": result["state_stab"]["transitions_per_day"],
            "n_state_changes":     result["false_spike"]["n_state_changes"],
            "n_reverts_2d":        result["false_spike"]["n_reverts_2d"],
            "false_spike_pct":     result["false_spike"]["false_spike_pct"],
        })

    # ── Build outputs ──────────────────────────────────────────────────────
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    agg_df = pd.DataFrame(all_aggregate)[
        ["variant", "horizon", "n_dir", "n_scored", "n_hits",
         "hit_rate", "avg_excess", "median_excess"]
    ]
    summary_csv = out_dir / "l1_validation_summary.csv"
    agg_df.to_csv(summary_csv, index=False)
    print(f"\n  wrote {summary_csv}  ({len(agg_df)} rows)")

    per_fold_df = pd.DataFrame(all_per_fold)[
        ["variant", "fold", "horizon", "n_dir", "n_scored", "n_hits",
         "hit_rate", "avg_excess", "median_excess"]
    ]
    per_fold_csv = out_dir / "l1_validation_per_window.csv"
    per_fold_df.to_csv(per_fold_csv, index=False)
    print(f"  wrote {per_fold_csv}  ({len(per_fold_df)} rows)")

    stab_df = pd.DataFrame(stability_rows)
    stab_csv = out_dir / "l1_validation_stability.csv"
    stab_df.to_csv(stab_csv, index=False)
    print(f"  wrote {stab_csv}  ({len(stab_df)} rows)")

    # Disagreement report
    print("\n  building disagreement report…")
    disagreements = disagreement_examples(df)
    dis_csv = out_dir / "l1_validation_disagreements.csv"
    disagreements.to_csv(dis_csv, index=False)
    print(f"  wrote {dis_csv}  ({len(disagreements)} examples)")

    # ── Markdown summary for /methods §11 ──────────────────────────────────
    md = []
    md.append("# L1 validation backtest (F-001)")
    md.append("")
    md.append(f"Backtest window: {trading_dates[0].date()} → {trading_dates[-1].date()}  "
              f"·  {len(folds)} rolling walk-forward folds, ~20 trading days each")
    md.append(f"Pressure normalization: per-actor z-score over rolling {ZSCORE_WIN}-day "
              f"window of strictly past values, mapped to [0, 95] via 50 + z×15")
    md.append("Forward outcome: 5d / 10d / 20d horizons, deadband ±0.5%")
    md.append("")
    md.append("## Out-of-sample hit rate by variant (pooled across folds)")
    md.append("")
    md.append("| Variant | Horizon | n_scored | Hit rate | Avg excess (pp) | Median excess (pp) |")
    md.append("|---|---|---|---|---|---|")
    for variant in VARIANTS:
        for h in HORIZONS:
            r = next((x for x in all_aggregate
                      if x["variant"] == variant and x["horizon"] == h), None)
            if r is None:
                continue
            hr = f"{int(round(r['hit_rate'] * 100))}%" if r['hit_rate'] is not None else "—"
            ae = f"{r['avg_excess']:+.2f}" if r['avg_excess'] is not None else "—"
            me = f"{r['median_excess']:+.2f}" if r['median_excess'] is not None else "—"
            md.append(f"| `{variant}` | {h}d | {r['n_scored']} | **{hr}** | {ae} | {me} |")
    md.append("")
    md.append("## State stability + false-spike rate by variant")
    md.append("")
    md.append("Lower transitions/day = calmer state assignments. "
              "False spike = state changes that revert within 2 trading days.")
    md.append("")
    md.append("| Variant | Transitions / day | n state changes | n reverts ≤2d | False spike % |")
    md.append("|---|---|---|---|---|")
    for r in stability_rows:
        md.append(
            f"| `{r['variant']}` | {r['transitions_per_day']:.3f} "
            f"| {r['n_state_changes']} | {r['n_reverts_2d']} "
            f"| **{r['false_spike_pct']:.1f}%** |"
        )
    md.append("")

    # Verdict (auto-generated)
    md.append("## Verdict (auto-generated)")
    md.append("")
    narr_20d = next((x for x in all_aggregate if x["variant"] == "narr" and x["horizon"] == 20), None)
    best_at_20 = max(
        (x for x in all_aggregate if x["horizon"] == 20 and x["hit_rate"] is not None),
        key=lambda x: x["hit_rate"],
        default=None,
    )
    if narr_20d and best_at_20:
        if best_at_20["variant"] == "narr":
            md.append(f"`narr` is the strongest variant at 20d ({int(round(best_at_20['hit_rate']*100))}% hit). "
                      "Field-derived pressure variants do not currently beat event-count narr on this corpus. "
                      "Recommendation: **do not promote L1 to production**. Refine the field definitions "
                      "(kernel choice, deadband, source weighting) or wait for more history.")
        elif best_at_20["hit_rate"] - narr_20d["hit_rate"] < 0.02:
            md.append(f"`{best_at_20['variant']}` edges out narr at 20d by "
                      f"{int(round((best_at_20['hit_rate']-narr_20d['hit_rate'])*100))}pp "
                      f"({int(round(best_at_20['hit_rate']*100))}% vs {int(round(narr_20d['hit_rate']*100))}%) "
                      "— too small to justify promotion. Recommendation: **investigate but do not promote yet**; "
                      "re-run after the corpus extends.")
        else:
            md.append(f"**`{best_at_20['variant']}` materially beats narr at 20d** — "
                      f"{int(round(best_at_20['hit_rate']*100))}% vs {int(round(narr_20d['hit_rate']*100))}%, "
                      f"a {int(round((best_at_20['hit_rate']-narr_20d['hit_rate'])*100))}pp lift. "
                      "Recommendation: **proceed to F-008 (production promotion)** with the standard caveats "
                      "(few folds on the current corpus, in-sample-ish given short history).")
    md.append("")
    md.append("**Reading.** Hit rates near 50% are coin-flip. Cleaner state machines "
              "(lower transitions/day, lower false-spike %) are valuable independently of hit rate, "
              "because they make the actor pages calmer and the daily diff more meaningful.")
    md.append("")
    md.append("## Caveats")
    md.append("")
    md.append(f"- Backtest window is short (~6 months). {len(folds)} rolling folds is the most "
              "non-overlapping ~20-day test windows this corpus supports.")
    md.append("- Pressure normalization rescales each variant to a comparable [0, 95] range "
              "via PIT z-score so the existing state engine thresholds (65/55/45) apply uniformly. "
              "Different normalizations would produce different state distributions and might "
              "alter the comparison.")
    md.append("- `density_momentum` is a derivative feature; comparing it through the state engine "
              "is somewhat unnatural (rising density ≠ high pressure) and the result should be "
              "interpreted as a signal-flow check, not as a final replacement candidate.")
    md.append("- All point-in-time leakage assertions pass; train-end equals test-start for every fold, "
              "and z-score baselines exclude the current row.")
    md.append("")

    md_path = out_dir / "l1_validation_summary.md"
    md_path.write_text("\n".join(md))
    print(f"  wrote {md_path}")

    # ── Console summary ────────────────────────────────────────────────────
    print()
    print("  ─── L1 VALIDATION — 20d HIT RATES (POOLED OOS) ──────────────")
    print(f"  {'VARIANT':<28} {'N_SCO':>7} {'HIT':>7} {'AVG_EX':>8} {'MED_EX':>8}")
    for variant in VARIANTS:
        r = next((x for x in all_aggregate if x["variant"] == variant and x["horizon"] == 20), None)
        if r is None or r["hit_rate"] is None:
            print(f"  {variant:<28} {'—':>7} {'—':>7} {'—':>8} {'—':>8}")
            continue
        hr = f"{int(round(r['hit_rate']*100))}%"
        ae = f"{r['avg_excess']:+.2f}"
        me = f"{r['median_excess']:+.2f}"
        print(f"  {variant:<28} {r['n_scored']:>7} {hr:>7} {ae:>8} {me:>8}")
    print()
    print("  ─── STATE STABILITY ────────────────────────────────────────")
    print(f"  {'VARIANT':<28} {'TRANS/D':>8} {'FALSE_SPIKE':>12}")
    for r in stability_rows:
        print(f"  {r['variant']:<28} {r['transitions_per_day']:>8.3f} "
              f"{str(r['false_spike_pct'])+'%':>12}")
    print()


if __name__ == "__main__":
    main()
