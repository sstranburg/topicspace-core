#!/usr/bin/env python3
"""
run_event_studies.py

Phase 1 backtest: event studies for each actor state.

Signal definition: first trading day an actor enters a state (state[D] != state[D-1]).
                   Day 0 of an actor's data is always excluded (prior state unknown).

Variant: mid_floor (floor=20, no AI-signal boosts — core signal only)
Universe: actors with ≥40% sufficient-data coverage (computed from backtest history)

Exclusion rules (logged to exclusions.csv):
  first_day          — state on day 0 of actor's data; prior state unknown
  insufficient_data  — entry date has sufficient_data=False (events_7d < 3)
  no_fwd_data        — price data unavailable for the full horizon window
  state_override     — actor has a hardcoded permanent state; no real transitions

Outputs (all in data/derived/event_studies/):
  trade_log.csv     — one row per (valid entry × horizon) with all metrics
  state_summary.csv — aggregated by state × horizon
  sector_summary.csv — aggregated by sector × state × horizon
  exclusions.csv    — every excluded candidate entry with reason

Usage:
  source venv/bin/activate && python scripts/run_event_studies.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT         = Path(__file__).parent.parent
HISTORY_FILE = ROOT / "data" / "derived" / "backtest_history.parquet"
PRICES_DIR   = ROOT / "data" / "derived" / "prices"
OUT_DIR      = ROOT / "data" / "derived" / "event_studies"

VARIANT      = "mid_floor"
MIN_COVERAGE = 40.0      # % sufficient-data days required for universe inclusion
HORIZONS     = [5, 10, 20]

# Actors with a hardcoded permanent state — they will never produce a real transition
PERMANENT_OVERRIDES: set[str] = {"TSLA"}

SECTORS: dict[str, str] = {
    "NVDA":  "Semiconductors",
    "TSM":   "Semiconductors",
    "AMD":   "Semiconductors",
    "INTC":  "Semiconductors",
    "ARM":   "Semiconductors",
    "AVGO":  "Semiconductors",
    "ASML":  "Semiconductors",
    "MU":    "Semiconductors",
    "MRVL":  "Semiconductors",
    "MSFT":  "AI Platform",
    "META":  "AI Platform",
    "GOOGL": "AI Platform",
    "PLTR":  "AI Platform",
    "AMZN":  "Cloud / Hyperscaler",
    "ORCL":  "Cloud / Hyperscaler",
    "SMCI":  "AI Infrastructure",
    "DELL":  "AI Infrastructure",
    "ANET":  "AI Infrastructure",
    "NBIS":  "AI Infrastructure",
    "VRT":   "AI Infrastructure",
    "VST":   "AI Infrastructure",
    "CEG":   "Energy / Power",
    "MP":    "Materials",
    "CRWV":  "Growth Software",
    "SNOW":  "Growth Software",
    "CRM":   "Growth Software",
    "ADBE":  "Growth Software",
    "DDOG":  "Growth Software",
    "NFLX":  "Growth Software",
    "TTD":   "Growth Software",
    "TSLA":  "EV / Consumer",
    "AAPL":  "Consumer Tech",
}


# ── Data loading ──────────────────────────────────────────────────────────────

def load_history() -> tuple[pd.DataFrame, list[str], dict]:
    """
    Load backtest history, compute universe, return:
      (full_variant_df, universe_tickers, coverage_dict)
    Full variant df includes all rows (sufficient and not) for transition detection.
    """
    hist = pd.read_parquet(HISTORY_FILE)
    hist = hist[hist["variant"] == VARIANT].copy()
    hist["date"] = pd.to_datetime(hist["date"])
    hist = hist.sort_values(["ticker", "date"]).reset_index(drop=True)

    coverage = (
        hist.groupby("ticker")
        .agg(total=("date", "count"), sufficient=("sufficient_data", "sum"))
        .assign(pct=lambda x: (x["sufficient"] / x["total"] * 100).round(1))
    )
    universe = sorted(coverage[coverage["pct"] >= MIN_COVERAGE].index.tolist())
    return hist, universe, coverage.to_dict("index")


def load_close_prices(tickers: list[str]) -> pd.DataFrame:
    """
    Return DataFrame indexed by trading date, columns = tickers + QQQ.
    Only close prices.
    """
    needed = set(tickers) | {"QQQ"}
    frames = []
    for ticker in needed:
        p = PRICES_DIR / f"{ticker}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)[["timestamp", "close"]].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")["close"].rename(ticker)
        frames.append(df)
    prices = pd.concat(frames, axis=1).sort_index()
    return prices


# ── Entry detection ───────────────────────────────────────────────────────────

def find_candidate_entries(hist: pd.DataFrame, universe: list[str]) -> pd.DataFrame:
    """
    For each actor in universe, find every state transition (state[D] != state[D-1]).
    Includes transitions on both sufficient and insufficient data days —
    validation happens downstream.
    Returns one row per transition with is_first_day flag.
    """
    sub = hist[hist["ticker"].isin(universe)].copy()
    sub = sub.sort_values(["ticker", "date"]).reset_index(drop=True)

    # Within each actor, shift state to get previous-day state
    sub["prev_state"] = sub.groupby("ticker")["state"].shift(1)
    sub["is_first_day"] = sub["prev_state"].isna()

    # Keep only days where state changed (or it's the first day)
    transitions = sub[
        sub["is_first_day"] | (sub["state"] != sub["prev_state"])
    ].copy()

    return transitions


# ── Forward return computation ────────────────────────────────────────────────

def forward_excess(
    ticker: str,
    entry_date: pd.Timestamp,
    prices: pd.DataFrame,
    horizons: list[int],
) -> dict | None:
    """
    Compute forward excess return and MAE/MFE vs QQQ for each horizon.
    Returns None if entry_date not in price index or QQQ missing.
    Returns dict with exc_5d / mae_5d / mfe_5d etc.; NaN if horizon exceeds data.
    """
    if ticker not in prices.columns:
        return None
    if prices.index.get_indexer([entry_date], method=None)[0] == -1:
        return None

    try:
        idx = prices.index.get_loc(entry_date)
    except KeyError:
        return None

    entry_t = prices[ticker].iloc[idx]
    entry_q = prices["QQQ"].iloc[idx]
    if pd.isna(entry_t) or pd.isna(entry_q) or entry_t == 0 or entry_q == 0:
        return None

    result: dict = {}
    for h in horizons:
        fwd_idx = idx + h
        if fwd_idx >= len(prices):
            result[f"exc_{h}d"] = np.nan
            result[f"mae_{h}d"] = np.nan
            result[f"mfe_{h}d"] = np.nan
            continue

        exit_t = prices[ticker].iloc[fwd_idx]
        exit_q = prices["QQQ"].iloc[fwd_idx]
        if pd.isna(exit_t) or pd.isna(exit_q):
            result[f"exc_{h}d"] = np.nan
            result[f"mae_{h}d"] = np.nan
            result[f"mfe_{h}d"] = np.nan
            continue

        exc = (exit_t / entry_t - 1) - (exit_q / entry_q - 1)
        result[f"exc_{h}d"] = round(exc * 100, 3)

        # Daily cumulative excess over [entry+1 .. entry+h]
        path_t = prices[ticker].iloc[idx + 1 : fwd_idx + 1]
        path_q = prices["QQQ"].iloc[idx + 1 : fwd_idx + 1]
        daily_exc = (path_t.values / entry_t - 1) - (path_q.values / entry_q - 1)
        valid = daily_exc[~np.isnan(daily_exc)]
        result[f"mae_{h}d"] = round(float(valid.min()) * 100, 3) if len(valid) else np.nan
        result[f"mfe_{h}d"] = round(float(valid.max()) * 100, 3) if len(valid) else np.nan

    return result


# ── Aggregation ───────────────────────────────────────────────────────────────

def aggregate(trades: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """
    Compute per-group stats for each horizon.
    Returns a long-format DataFrame with one row per (group × horizon).
    """
    rows = []
    for keys, grp in trades.groupby(group_cols):
        keys = keys if isinstance(keys, tuple) else (keys,)
        base = dict(zip(group_cols, keys))
        for h in HORIZONS:
            col = f"exc_{h}d"
            mae_col = f"mae_{h}d"
            mfe_col = f"mfe_{h}d"
            valid = grp[col].dropna()
            if len(valid) == 0:
                continue
            row = {**base, "horizon": f"{h}D", "n": len(valid)}
            row["hit_rate"]   = round((valid > 0).mean() * 100, 1)
            row["avg_exc"]    = round(valid.mean(), 3)
            row["med_exc"]    = round(valid.median(), 3)
            row["avg_mae"]    = round(grp[mae_col].dropna().mean(), 3)
            row["avg_mfe"]    = round(grp[mfe_col].dropna().mean(), 3)
            row["std_exc"]    = round(valid.std(), 3)
            rows.append(row)
    return pd.DataFrame(rows)


# ── Printing ──────────────────────────────────────────────────────────────────

def fmt_pct(v) -> str:
    if pd.isna(v):
        return "   n/a"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.1f}%"


def print_state_summary(summary: pd.DataFrame, excl_counts: dict) -> None:
    states = summary["state"].unique()
    for state in sorted(states):
        state_rows = summary[summary["state"] == state]
        n_max = state_rows["n"].max()
        excl = excl_counts.get(state, {})
        excl_str = "  ".join(f"{v} {k}" for k, v in sorted(excl.items()) if v > 0)
        excl_str = f"  ({excl_str})" if excl_str else ""
        print(f"\n  {state:<20}  n={n_max}{excl_str}")
        header = f"    {'HOR':>4}  {'N':>4}  {'HIT':>5}  {'AVG':>7}  {'MED':>7}  {'AVG MAE':>8}  {'AVG MFE':>8}"
        print(header)
        print("    " + "-" * 56)
        for _, r in state_rows.sort_values("horizon").iterrows():
            print(
                f"    {r['horizon']:>4}  {int(r['n']):>4}  "
                f"{r['hit_rate']:>4.0f}%  "
                f"{fmt_pct(r['avg_exc']):>7}  "
                f"{fmt_pct(r['med_exc']):>7}  "
                f"{fmt_pct(r['avg_mae']):>7}  "
                f"{fmt_pct(r['avg_mfe']):>7}"
            )


def print_sector_summary(sector_sum: pd.DataFrame) -> None:
    for sector in sorted(sector_sum["sector"].unique()):
        sec_rows = sector_sum[sector_sum["sector"] == sector]
        print(f"\n  {sector}")
        for state in sorted(sec_rows["state"].unique()):
            st_rows = sec_rows[sec_rows["state"] == state]
            n_max = st_rows["n"].max()
            print(f"    {state:<20}  n={n_max}")
            for _, r in st_rows.sort_values("horizon").iterrows():
                print(
                    f"      {r['horizon']:>4}  hit={r['hit_rate']:.0f}%  "
                    f"avg={fmt_pct(r['avg_exc'])}  med={fmt_pct(r['med_exc'])}"
                )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    print("Loading backtest history…")
    hist, universe, coverage = load_history()
    excluded_actors = {t: v for t, v in coverage.items() if v["pct"] < MIN_COVERAGE}

    print(f"  Variant     : {VARIANT}")
    print(f"  Universe    : {len(universe)} actors (≥{MIN_COVERAGE}% sufficient-data coverage)")
    print(f"  Excluded    : {len(excluded_actors)} actors below threshold")
    print(f"  Date window : {hist['date'].min().date()} → {hist['date'].max().date()}")

    print("\nLoading close prices…")
    prices = load_close_prices(universe)
    print(f"  {len(prices.columns)} tickers loaded, {len(prices)} trading days")

    # ── Find candidate entries ─────────────────────────────────────────────────
    print("\nDetecting state transitions…")
    candidates = find_candidate_entries(hist, universe)
    print(f"  {len(candidates)} candidate entries (including first-day and thin-data)")

    # ── Build trade log ────────────────────────────────────────────────────────
    trade_rows: list[dict] = []
    excl_rows:  list[dict] = []
    excl_counts: dict[str, dict] = {}   # state → reason → count

    def log_excl(ticker, date, state, prev_state, reason, **extra):
        excl_rows.append({
            "ticker": ticker, "date": date, "state": state,
            "prev_state": prev_state, "reason": reason, **extra,
        })
        excl_counts.setdefault(state, {})
        excl_counts[state][reason] = excl_counts[state].get(reason, 0) + 1

    for _, row in candidates.iterrows():
        ticker     = row["ticker"]
        entry_date = row["date"]
        state      = row["state"]
        prev_state = row.get("prev_state", None)

        # ── Exclusion: first day of actor's data ──────────────────────────────
        if row["is_first_day"]:
            log_excl(ticker, entry_date, state, None, "first_day")
            continue

        # ── Exclusion: permanent state override — no real transition ──────────
        if ticker in PERMANENT_OVERRIDES:
            log_excl(ticker, entry_date, state, prev_state, "state_override")
            continue

        # ── Exclusion: entry date has insufficient event coverage ─────────────
        if not row["sufficient_data"]:
            log_excl(ticker, entry_date, state, prev_state, "insufficient_data",
                     events_7d=int(row.get("events_7d", 0)))
            continue

        # ── Compute forward returns ───────────────────────────────────────────
        fwd = forward_excess(ticker, entry_date, prices, HORIZONS)
        if fwd is None:
            log_excl(ticker, entry_date, state, prev_state, "no_fwd_data",
                     note="ticker not in price index on entry date")
            continue

        # Exclude if ANY horizon is missing (keeps study clean and comparable)
        if any(pd.isna(fwd.get(f"exc_{h}d")) for h in HORIZONS):
            log_excl(ticker, entry_date, state, prev_state, "no_fwd_data",
                     note=f"entry too close to window end for {HORIZONS[-1]}D horizon")
            continue

        # ── Valid entry ───────────────────────────────────────────────────────
        trade_rows.append({
            "ticker":      ticker,
            "entry_date":  entry_date,
            "state":       state,
            "prev_state":  prev_state,
            "sector":      SECTORS.get(ticker, "Other"),
            "narr":        row.get("narr"),
            "nds":         row.get("nds"),
            "rel":         row.get("rel"),
            "events_7d":   int(row.get("events_7d", 0)),
            **fwd,
        })

    trades = pd.DataFrame(trade_rows)
    excl   = pd.DataFrame(excl_rows)

    # ── Aggregate ─────────────────────────────────────────────────────────────
    state_summary  = aggregate(trades, ["state"])
    sector_summary = aggregate(trades, ["sector", "state"])

    # ── Print results ──────────────────────────────────────────────────────────
    sep = "=" * 68
    print(f"\n{sep}")
    print(f"  TOPICSPACE EVENT STUDIES  ·  {VARIANT}  ·  "
          f"{hist['date'].min().date()} → {hist['date'].max().date()}")
    print(sep)

    print(f"\nUniverse ({len(universe)} actors, ≥{MIN_COVERAGE}% coverage):")
    print("  " + "  ".join(universe))

    print(f"\nExcluded actors ({len(excluded_actors)}, below {MIN_COVERAGE}%):")
    for t, v in sorted(excluded_actors.items(), key=lambda x: -x[1]["pct"]):
        print(f"  {t:<6} {v['pct']:.1f}%")

    print(f"\nTrade candidates : {len(candidates)}")
    print(f"Valid entries    : {len(trades)}")
    print(f"Excluded entries : {len(excl)}")
    if not excl.empty:
        for reason, n in excl["reason"].value_counts().items():
            print(f"  {n:>4}  {reason}")

    print(f"\n{'-' * 68}")
    print("  STATE EVENT STUDIES")
    print(f"{'-' * 68}")
    print_state_summary(state_summary, excl_counts)

    print(f"\n{'-' * 68}")
    print("  SECTOR CUTS")
    print(f"{'-' * 68}")
    print_sector_summary(sector_summary)

    # ── Write outputs ──────────────────────────────────────────────────────────
    trades_out = OUT_DIR / "trade_log.csv"
    state_out  = OUT_DIR / "state_summary.csv"
    sector_out = OUT_DIR / "sector_summary.csv"
    excl_out   = OUT_DIR / "exclusions.csv"

    trades.to_csv(trades_out, index=False)
    state_summary.to_csv(state_out, index=False)
    sector_summary.to_csv(sector_out, index=False)
    excl.to_csv(excl_out, index=False)

    print(f"\nOutputs:")
    print(f"  {trades_out.relative_to(ROOT)}  ({len(trades)} trades)")
    print(f"  {state_out.relative_to(ROOT)}")
    print(f"  {sector_out.relative_to(ROOT)}")
    print(f"  {excl_out.relative_to(ROOT)}  ({len(excl)} exclusions)")


if __name__ == "__main__":
    main()
