#!/usr/bin/env python3
"""
run_strategy_lab.py

Phase 2 backtest: daily portfolio simulation for 3 strategies + 5 baselines.

State interpretation (locked from event studies):
  DIVERGENCE        — entry-positive       best 10-20D  constructive catch-up; AI Infra strongest
  CONFIRMED         — sector-conditional   best 5-20D   semis: strong; all others: flat
  EARLY             — hold-positive        best 20D     timing-sensitive; weak at 5D entry
  REPRICING         — hold-positive        best 20D     mild drift; not a clean entry
  MACRO             — entry-positive       best 5-10D   fades by 20D; use fresh entry only
  DISAGREEMENT      — reversal             best 20D     delayed; avoid at 5D (avg -4%)
  NEG_CONFIRMATION  — reversal             best 20D     delayed mean-reversion; semis strong
  PRICE-LED         — avoid                —            weak across all horizons
  UNCLEAR           — avoid                —            inconsistent

Strategies:
  S1 — Constructive Catch-Up
         DIVERGENCE (all sectors) + CONFIRMED (semis only)
         Rank: NDS desc  Hold: daily rebalance
  S2 — Sector-Aware Selection
         Eligibility matrix driven by sector-state event study outcomes
         Rank: NDS desc  Hold: daily rebalance
  S3 — Horizon-Aware
         DIVERGENCE (days_in_state ≥3) + MACRO (days_in_state ≤5) + EARLY (days_in_state ≥5)
         Rank: NDS desc  Hold: daily rebalance with state-duration filters
  S4 — S2 + Reversal Overlay
         S2 core PLUS: Semiconductors × {NEG_CONFIRMATION, DISAGREEMENT} days_in_state ≥ 5
         Tests whether adding seasoned bearish-narrative reversal exposure improves on S2
         Rank: NDS desc  Hold: daily rebalance

Baselines:
  B1 — QQQ benchmark
  B2 — Equal-weight universe basket (all 22 actors)
  B3 — Momentum: top-5 by rel (5D return vs QQQ, buy recent outperformers)
  B4 — Narrative-only: top-5 by NDS > 0 (no state logic)
  B5 — Contrarian-price: bottom-5 by rel (buy underperformers, no narrative filter)
       Contrasts with S1/S2: tests whether narrative adds value over pure price reversal

Portfolio rules (v1):
  Equal weight · long-only · max 5 names · daily rebalance · no leverage

Outputs (data/derived/event_studies/):
  strategy_equity.csv    — daily cumulative excess return per strategy
  strategy_summary.csv   — CAGR, Sharpe, hit rate, max drawdown, turnover
  strategy_trades.csv    — daily portfolio snapshot per strategy

Usage:
  source venv/bin/activate && python scripts/run_strategy_lab.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT         = Path(__file__).parent.parent
HISTORY_FILE = ROOT / "data" / "derived" / "backtest_history.parquet"
PRICES_DIR   = ROOT / "data" / "derived" / "prices"
OUT_DIR      = ROOT / "data" / "derived" / "event_studies"

VARIANT         = "mid_floor"
MIN_COVERAGE    = 40.0
MAX_POSITIONS   = 5

# Backtest window start — must match run_event_studies.py exactly.
# Rows before this date are excluded from coverage calculation, universe
# selection, and portfolio simulation so all three scripts operate on
# the same window.
BACKTEST_START  = pd.Timestamp("2025-05-01")

# Minimum NDS required for S2 and S2-dir eligibility.
# S2 is designed to trade constructive narrative-price setups.
# Actors with NDS ≤ 0 have price already ahead of (or equal to) narrative
# signal direction — outside the intended trade policy.
# Set to 0 as a sign-correction only; no threshold optimisation.
NDS_FLOOR_S2    = 0.0

# S2-dir: sectors where hard exclusion is replaced with direction-aware eligibility.
# Only actors with direction==1 (bullish framing) in constructive states qualify.
DIRECTIONAL_SECTORS            = {"Growth Software", "Consumer Tech", "EV / Consumer"}
DIRECTIONAL_CONSTRUCTIVE_STATES = {"DIVERGENCE", "REPRICING", "EARLY"}

# Narrative direction: -1 = bearish-framing actor, +1 = bullish (default).
ACTOR_DIRECTIONS: dict[str, int] = {
    "MU": -1, "TSLA": -1, "SNOW": -1, "CRWV": -1, "CRM": -1, "INTC": -1,
}

# Full 32-actor sector map — used by S2 and S2-dir.
# Consolidated from the previous SECTORS (22-actor) and SECTORS_FULL (32-actor)
# after the full eligibility matrix re-derivation showed all Growth Software cells
# negative and AI Platform cells negative — the missing actors in the old map were
# either oversights (MRVL, ASML, MU, DELL) or map to permanently empty sectors.
SECTORS: dict[str, str] = {
    "NVDA":  "Semiconductors",     "TSM":   "Semiconductors",
    "AMD":   "Semiconductors",     "INTC":  "Semiconductors",
    "ARM":   "Semiconductors",     "AVGO":  "Semiconductors",
    "ASML":  "Semiconductors",     "MU":    "Semiconductors",
    "MRVL":  "Semiconductors",
    "MSFT":  "AI Platform",        "META":  "AI Platform",
    "GOOGL": "AI Platform",        "PLTR":  "AI Platform",
    "AMZN":  "Cloud / Hyperscaler","ORCL":  "Cloud / Hyperscaler",
    "SMCI":  "AI Infrastructure",  "DELL":  "AI Infrastructure",
    "ANET":  "AI Infrastructure",  "NBIS":  "AI Infrastructure",
    "VRT":   "AI Infrastructure",  "VST":   "AI Infrastructure",
    "CEG":   "Energy / Power",
    "MP":    "Materials",
    "CRWV":  "Growth Software",    "CRM":   "Growth Software",
    "ADBE":  "Growth Software",    "DDOG":  "Growth Software",
    "SNOW":  "Growth Software",    "NFLX":  "Growth Software",
    "TTD":   "Growth Software",
    "TSLA":  "EV / Consumer",
    "AAPL":  "Consumer Tech",
}

SEMI_TICKERS = {"NVDA", "TSM", "AMD", "INTC", "ARM", "AVGO", "ASML", "MU", "MRVL"}

# Sector × State eligibility matrix re-derived from event studies on the full
# 250-day combined corpus (May 2025 → Apr 2026).
# Criteria: n ≥ 5 and hit rate ≥ 55% at 10D horizon, avg_exc ≥ 0%.
#
# Key changes vs old matrix (derived on 60-day window):
#   AI Platform    → empty (DIVERGENCE removed: 42% hit, -1.3% avg — was wrong)
#   Cloud          → {"PRICE-LED","UNCLEAR"} only (DIVERGENCE/REPRICING/MACRO fail)
#   AI Infra       → CONFIRMED removed (-0.9% avg); REPRICING added (n=174, 58%)
#   Semis          → MACRO/PRICE-LED/UNCLEAR added (all well-supported)
#   Energy/Power   → DIVERGENCE removed (53% hit, below threshold)
#   Materials      → DIVERGENCE removed (50% hit); MACRO/PRICE-LED/UNCLEAR added
#   Consumer Tech  → REPRICING added (n=10, 60% hit)
#   Growth Software → still empty (all states negative across all horizons)
SECTOR_STATE_ELIGIBLE: dict[str, set[str]] = {
    "Semiconductors":      {"CONFIRMED", "DISAGREEMENT", "DIVERGENCE", "EARLY",
                            "MACRO", "NEG_CONFIRMATION", "PRICE-LED",
                            "REPRICING", "UNCLEAR"},
    "AI Infrastructure":   {"DIVERGENCE", "MACRO", "REPRICING", "UNCLEAR"},
    "AI Platform":         set(),
    "Cloud / Hyperscaler": {"PRICE-LED", "UNCLEAR"},
    "Energy / Power":      {"MACRO"},
    "Growth Software":     set(),
    "Materials":           {"MACRO", "PRICE-LED", "UNCLEAR"},
    "EV / Consumer":       set(),
    "Consumer Tech":       {"REPRICING"},
}


# ── State interpretation table ────────────────────────────────────────────────

STATE_INTERPRETATION = [
    # (state, classification, best_horizon, note) — stats from 250-day re-derivation
    ("DIVERGENCE",       "semi/infra positive",  "10-20D", "semis: 58%/+0.9%; AI Infra: 62%/+3.4%; AI Platform/Cloud: negative"),
    ("CONFIRMED",        "semis only",           "10-20D", "semis: 60%/+1.1%; AI Infra 56%/-0.9% (removed); others weak"),
    ("EARLY",            "semis only",           "20D",    "semis: 59%/+2.0% at 10D; AI Infra: 50% (below threshold)"),
    ("REPRICING",        "semi/infra positive",  "20D",    "semis: 56%/+1.8%; AI Infra: 58%/+1.9% (n=174); Cloud: 54% (removed)"),
    ("MACRO",            "semis/infra/energy",   "5-10D",  "semis: 60%/+1.9%; AI Infra: 62%/+3.3%; Materials: 62%/+6.2%"),
    ("DISAGREEMENT",     "semis reversal",       "20D",    "semis only: 64%/+6.1%; no other sector has data"),
    ("NEG_CONFIRMATION", "semis reversal",       "20D",    "semis only: 63%/+4.4%; Growth Software: 43% (below threshold)"),
    ("PRICE-LED",        "semis positive",       "10D",    "semis: 65%/+2.9%; Materials: 57%/+16.4%; Cloud n=6; others weak"),
    ("UNCLEAR",          "semis/materials",      "20D",    "semis: 59%/+1.9%; Materials: 86%/+24.1% (n=7 thin)"),
]


# ── Data loading ──────────────────────────────────────────────────────────────

def load_history() -> tuple[pd.DataFrame, list[str]]:
    hist = pd.read_parquet(HISTORY_FILE)
    hist = hist[hist["variant"] == VARIANT].copy()
    hist["date"] = pd.to_datetime(hist["date"])
    hist = hist[hist["date"] >= BACKTEST_START].copy()
    hist = hist.sort_values(["ticker", "date"]).reset_index(drop=True)

    coverage = (
        hist.groupby("ticker")
        .agg(total=("date", "count"), sufficient=("sufficient_data", "sum"))
        .assign(pct=lambda x: x["sufficient"] / x["total"] * 100)
    )
    universe = sorted(coverage[coverage["pct"] >= MIN_COVERAGE].index.tolist())

    # Compute consecutive days_in_state for horizon-aware strategy
    hist = hist.sort_values(["ticker", "date"])
    hist["_run"] = hist.groupby("ticker")["state"].transform(
        lambda s: (s != s.shift()).cumsum()
    )
    hist["days_in_state"] = hist.groupby(["ticker", "_run"]).cumcount() + 1
    hist = hist.drop(columns="_run")

    return hist, universe


def load_daily_returns(universe: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Return (close_prices, daily_returns) both indexed by trading date.
    Columns: universe tickers + QQQ.
    """
    needed = set(universe) | {"QQQ"}
    frames = []
    for ticker in needed:
        p = PRICES_DIR / f"{ticker}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)[["timestamp", "close"]].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")["close"].rename(ticker)
        frames.append(df)
    closes = pd.concat(frames, axis=1).sort_index()
    returns = closes.pct_change()
    return closes, returns


# ── Strategy eligibility functions ───────────────────────────────────────────

def eligible_s1(row: pd.Series) -> bool:
    """Constructive Catch-Up: DIVERGENCE all + CONFIRMED semis."""
    state = row["state"]
    if state == "DIVERGENCE":
        return True
    if state == "CONFIRMED" and row["ticker"] in SEMI_TICKERS:
        return True
    return False


def eligible_s2(row: pd.Series) -> bool:
    """Sector-Aware: eligibility matrix from event study outcomes, NDS > 0 floor."""
    sector = SECTORS.get(row["ticker"], "Other")
    if row["state"] not in SECTOR_STATE_ELIGIBLE.get(sector, set()):
        return False
    return row["nds"] > NDS_FLOOR_S2


def eligible_s4(row: pd.Series) -> bool:
    """S2 + Reversal Overlay: S2 core plus semis in seasoned reversal states."""
    if eligible_s2(row):
        return True
    state = row["state"]
    if (state in {"NEG_CONFIRMATION", "DISAGREEMENT"}
            and row["ticker"] in SEMI_TICKERS
            and int(row["days_in_state"]) >= 5):
        return True
    return False


def eligible_s2_dir(row: pd.Series) -> bool:
    """
    S2 Directional: least-invasive fix for the hard sector exclusion problem.

    Uses SECTORS_FULL (all 32 actors). For sectors where S2 base has an empty
    eligibility set (Growth Software, Consumer Tech, EV/Consumer), applies a
    direction-aware check instead: eligible when direction==1 AND state is
    constructive. All other sector rules are preserved from S2 base.

    NDS > 0 floor is retained (same spec as S2 post-fix).
    """
    if row["nds"] <= NDS_FLOOR_S2:
        return False
    sector = SECTORS.get(row["ticker"], "Other")
    if sector in DIRECTIONAL_SECTORS:
        direction = ACTOR_DIRECTIONS.get(row["ticker"], 1)
        return direction == 1 and row["state"] in DIRECTIONAL_CONSTRUCTIVE_STATES
    return row["state"] in SECTOR_STATE_ELIGIBLE.get(sector, set())


def eligible_s3(row: pd.Series) -> bool:
    """
    Horizon-Aware:
      DIVERGENCE  days ≥ 3  — seasoned; event study edge strengthens with hold
      MACRO       days ≤ 5  — fresh entry only; signal fades after 5D
      EARLY       days ≥ 5  — wait past 5D weakness; hold for 20D payoff
    """
    state = row["state"]
    d     = int(row["days_in_state"])
    if state == "DIVERGENCE" and d >= 3:
        return True
    if state == "MACRO" and d <= 5:
        return True
    if state == "EARLY" and d >= 5:
        return True
    return False


# ── Portfolio selection ───────────────────────────────────────────────────────

def select_portfolio(
    day_df: pd.DataFrame,
    eligible_fn,
    rank_col: str = "nds",
    ascending: bool = False,
    max_n: int = MAX_POSITIONS,
) -> list[str]:
    """
    Given a single-day slice of the history DataFrame, return top-N eligible tickers.
    eligible_fn takes a row (pd.Series) and returns bool.
    rank_col: column to sort by for ranking within eligible set.
    """
    mask = day_df.apply(eligible_fn, axis=1)
    eligible = day_df[mask].sort_values(rank_col, ascending=ascending)
    return list(eligible["ticker"].head(max_n))


# ── Portfolio simulation ──────────────────────────────────────────────────────

def simulate(
    hist: pd.DataFrame,
    daily_returns: pd.DataFrame,
    universe: list[str],
    eligible_fn,
    label: str,
    rank_col: str = "nds",
    ascending: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run daily portfolio simulation.
    Returns (daily_results_df, trades_df).
    """
    trading_days = sorted(daily_returns.index)
    hist_indexed = hist.set_index(["date", "ticker"])

    results = []
    trades  = []
    prev_portfolio: list[str] = []

    for i, d in enumerate(trading_days[:-1]):   # last day has no next-day return
        next_d = trading_days[i + 1]

        # Get today's state snapshot for universe actors
        try:
            day_df = hist.loc[hist["date"] == d, ["ticker", "state", "nds", "narr", "rel", "days_in_state", "sufficient_data"]]
            day_df = day_df[day_df["ticker"].isin(universe)].copy()
        except Exception:
            day_df = pd.DataFrame()

        if day_df.empty:
            portfolio = []
        else:
            portfolio = select_portfolio(day_df, eligible_fn, rank_col, ascending)

        # Daily portfolio excess return (next day close-to-close vs QQQ)
        if portfolio:
            ticker_rets = daily_returns.loc[next_d, portfolio].dropna()
            qqq_ret     = daily_returns.loc[next_d, "QQQ"] if "QQQ" in daily_returns.columns else 0.0
            excess      = float((ticker_rets - qqq_ret).mean()) if len(ticker_rets) else 0.0
            port_ret    = float(ticker_rets.mean()) if len(ticker_rets) else 0.0
        else:
            excess   = 0.0
            port_ret = float(daily_returns.loc[next_d, "QQQ"]) if "QQQ" in daily_returns.columns else 0.0

        turnover = len(set(portfolio) ^ set(prev_portfolio)) / max(len(prev_portfolio), len(portfolio), 1)

        results.append({
            "date":        d,
            "strategy":    label,
            "n_held":      len(portfolio),
            "tickers":     "|".join(sorted(portfolio)),
            "excess":      round(excess, 5),
            "port_ret":    round(port_ret, 5),
            "turnover":    round(turnover, 3),
        })
        trades.append({
            "date":       d,
            "strategy":   label,
            "portfolio":  "|".join(sorted(portfolio)),
            "n_held":     len(portfolio),
        })
        prev_portfolio = portfolio

    return pd.DataFrame(results), pd.DataFrame(trades)


def simulate_basket(
    daily_returns: pd.DataFrame,
    universe: list[str],
    label: str,
) -> pd.DataFrame:
    """Equal-weight universe basket baseline."""
    trading_days = sorted(daily_returns.index)
    results = []
    for i, d in enumerate(trading_days[:-1]):
        next_d = trading_days[i + 1]
        ticker_rets = daily_returns.loc[next_d, universe].dropna()
        qqq_ret = float(daily_returns.loc[next_d, "QQQ"]) if "QQQ" in daily_returns.columns else 0.0
        excess  = float((ticker_rets - qqq_ret).mean()) if len(ticker_rets) else 0.0
        results.append({"date": d, "strategy": label, "excess": round(excess, 5)})
    return pd.DataFrame(results)


def simulate_ranked_baseline(
    hist: pd.DataFrame,
    daily_returns: pd.DataFrame,
    universe: list[str],
    label: str,
    rank_col: str,
    ascending: bool = False,
    extra_filter=None,
) -> pd.DataFrame:
    """Top/bottom-N baseline by a single column, no state logic."""
    trading_days = sorted(daily_returns.index)
    results = []
    for i, d in enumerate(trading_days[:-1]):
        next_d = trading_days[i + 1]
        day_df = hist[(hist["date"] == d) & hist["ticker"].isin(universe)].copy()
        if extra_filter is not None:
            day_df = day_df[extra_filter(day_df)]
        ranked = day_df.sort_values(rank_col, ascending=ascending).head(MAX_POSITIONS)
        portfolio = list(ranked["ticker"])
        if portfolio:
            ticker_rets = daily_returns.loc[next_d, portfolio].dropna()
            qqq_ret     = float(daily_returns.loc[next_d, "QQQ"])
            excess      = float((ticker_rets - qqq_ret).mean()) if len(ticker_rets) else 0.0
        else:
            excess = 0.0
        results.append({"date": d, "strategy": label, "excess": round(excess, 5)})
    return pd.DataFrame(results)


# ── Performance metrics ───────────────────────────────────────────────────────

def compute_metrics(result_df: pd.DataFrame) -> dict:
    exc = result_df["excess"].values
    cum = np.cumprod(1 + exc) - 1
    n_days = len(exc)

    # Annualised return approximation (252 trading days)
    total_ret = float(cum[-1]) if len(cum) else 0.0
    cagr      = (1 + total_ret) ** (252 / max(n_days, 1)) - 1

    # Sharpe: excess daily / std * sqrt(252)
    sharpe = float(np.mean(exc) / np.std(exc) * np.sqrt(252)) if np.std(exc) > 0 else 0.0

    # Max drawdown on cumulative excess curve
    wealth = np.cumprod(1 + exc)
    peak   = np.maximum.accumulate(wealth)
    dd     = (wealth - peak) / peak
    max_dd = float(dd.min())

    hit_rate = float((exc > 0).mean())

    # Turnover (strategy only, if column exists)
    turnover_mean = (
        float(result_df["turnover"].mean())
        if "turnover" in result_df.columns else float("nan")
    )

    return {
        "total_exc":  round(total_ret * 100, 2),
        "cagr":       round(cagr * 100, 2),
        "sharpe":     round(sharpe, 2),
        "hit_rate":   round(hit_rate * 100, 1),
        "max_dd":     round(max_dd * 100, 2),
        "avg_daily":  round(float(np.mean(exc)) * 100, 3),
        "turnover":   round(turnover_mean * 100, 1) if not np.isnan(turnover_mean) else float("nan"),
        "n_days":     n_days,
    }


def cumulative_excess(result_df: pd.DataFrame, label: str) -> pd.DataFrame:
    exc = result_df["excess"].values
    cum = np.cumprod(1 + exc) - 1
    return pd.DataFrame({
        "date":     result_df["date"].values,
        "strategy": label,
        "cum_exc":  np.round(cum * 100, 4),
        "daily_exc":np.round(exc * 100, 4),
    })


# ── Printing ──────────────────────────────────────────────────────────────────

def print_interpretation_table() -> None:
    print("\n  State interpretation (locked from event studies)")
    print(f"  {'STATE':<20} {'CLASSIFICATION':<22} {'BEST HOR':<10} NOTE")
    print("  " + "-" * 92)
    for state, cls, hor, note in STATE_INTERPRETATION:
        print(f"  {state:<20} {cls:<22} {hor:<10} {note}")


def print_summary_table(summary: pd.DataFrame) -> None:
    print(f"\n  {'STRATEGY':<28} {'CUM EXC':>8} {'CAGR':>6} {'SHARPE':>7} "
          f"{'HIT':>5} {'MAX DD':>7} {'AVG/D':>7} {'TURN':>6}")
    print("  " + "-" * 82)
    for _, r in summary.iterrows():
        turn = f"{r['turnover']:.0f}%" if not np.isnan(r['turnover']) else "  n/a"
        print(
            f"  {r['strategy']:<28} "
            f"{r['total_exc']:>+7.1f}%  "
            f"{r['cagr']:>+5.1f}%  "
            f"{r['sharpe']:>6.2f}  "
            f"{r['hit_rate']:>4.0f}%  "
            f"{r['max_dd']:>+6.1f}%  "
            f"{r['avg_daily']:>+6.3f}%  "
            f"{turn:>5}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading backtest history…")
    hist, universe = load_history()
    print(f"  {len(universe)} actors, {VARIANT} variant")
    print(f"  {hist['date'].min().date()} → {hist['date'].max().date()}")

    print("Loading daily returns…")
    closes, daily_returns = load_daily_returns(universe)
    # Trim to backtest window — hist is already filtered to BACKTEST_START,
    # and daily_returns must match so simulation, hit rates, and Sharpe all
    # use the same day count. Price data before BACKTEST_START is irrelevant
    # to strategy evaluation and distorts metrics if left in.
    closes        = closes[closes.index >= BACKTEST_START]
    daily_returns = daily_returns[daily_returns.index >= BACKTEST_START]
    print(f"  {len(daily_returns)} trading days, {len(daily_returns.columns)} tickers")

    # ── Run strategies ─────────────────────────────────────────────────────────
    print("\nRunning simulations…")

    s1_res, s1_tr  = simulate(hist, daily_returns, universe, eligible_s1,     "S1 Constructive Catch-Up")
    s2_res, s2_tr  = simulate(hist, daily_returns, universe, eligible_s2,     "S2 Sector-Aware")
    s2d_res, s2d_tr = simulate(hist, daily_returns, universe, eligible_s2_dir, "S2-dir Directional")
    s3_res, s3_tr  = simulate(hist, daily_returns, universe, eligible_s3,     "S3 Horizon-Aware")
    s4_res, s4_tr  = simulate(hist, daily_returns, universe, eligible_s4,     "S4 S2+Reversal")

    # ── Run baselines ──────────────────────────────────────────────────────────
    b2_res = simulate_basket(daily_returns, universe, "B2 Equal-Weight Universe")
    # B3: top-5 by rel descending (momentum — buy recent outperformers)
    b3_res = simulate_ranked_baseline(hist, daily_returns, universe, "B3 Momentum (top rel)", "rel", ascending=False)
    # B4: top-5 by NDS > 0 (narrative signal, no state filter)
    b4_res = simulate_ranked_baseline(
        hist, daily_returns, universe, "B4 Narrative-Only (NDS>0)", "nds",
        ascending=False, extra_filter=lambda df: df["nds"] > 0
    )
    # B5: bottom-5 by rel (contrarian price — buy worst performers, no narrative)
    b5_res = simulate_ranked_baseline(hist, daily_returns, universe, "B5 Contrarian-Price (bot rel)", "rel", ascending=True)

    # B1 (QQQ) is the benchmark itself — excess = 0 by definition
    qqq_days = sorted(daily_returns.index)[:-1]
    b1_res = pd.DataFrame({"date": qqq_days, "strategy": "B1 QQQ", "excess": 0.0})

    # ── Compute metrics ────────────────────────────────────────────────────────
    all_results = [s1_res, s2_res, s2d_res, s3_res, s4_res, b1_res, b2_res, b3_res, b4_res, b5_res]
    labels      = [df["strategy"].iloc[0] for df in all_results]

    metrics_rows = []
    equity_frames = []
    for df in all_results:
        label = df["strategy"].iloc[0]
        m = compute_metrics(df)
        metrics_rows.append({"strategy": label, **m})
        equity_frames.append(cumulative_excess(df, label))

    summary    = pd.DataFrame(metrics_rows)
    equity_all = pd.concat(equity_frames, ignore_index=True)
    trades_all = pd.concat([s1_tr, s2_tr, s2d_tr, s3_tr, s4_tr], ignore_index=True)

    # ── Print results ──────────────────────────────────────────────────────────
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  TOPICSPACE STRATEGY LAB  ·  {VARIANT}  ·  "
          f"{hist['date'].min().date()} → {hist['date'].max().date()}")
    print(sep)
    print(f"  Universe: {len(universe)} actors  ·  max {MAX_POSITIONS} positions  ·  daily rebalance")

    print_interpretation_table()

    print(f"\n{'-' * 70}")
    print("  PERFORMANCE SUMMARY  (vs QQQ)")
    print(f"{'-' * 70}")
    print_summary_table(summary)

    # ── Strategy diagnostics ───────────────────────────────────────────────────
    for strat_res, strat_tr in [(s1_res, s1_tr), (s2_res, s2_tr), (s2d_res, s2d_tr), (s3_res, s3_tr), (s4_res, s4_tr)]:
        label = strat_res["strategy"].iloc[0]
        avg_held = strat_res["n_held"].mean()
        zero_days = (strat_res["n_held"] == 0).sum()
        # Most common states in portfolio
        all_tickers = [t for row in strat_tr["portfolio"] for t in row.split("|") if t]
        from collections import Counter
        top_tickers = Counter(all_tickers).most_common(8)
        print(f"\n  {label}")
        print(f"    avg held: {avg_held:.1f}   zero-position days: {zero_days}")
        print(f"    top actors: " + "  ".join(f"{t}({n}d)" for t, n in top_tickers))

    # ── Write outputs ──────────────────────────────────────────────────────────
    equity_out  = OUT_DIR / "strategy_equity.csv"
    summary_out = OUT_DIR / "strategy_summary.csv"
    trades_out  = OUT_DIR / "strategy_trades.csv"

    equity_all.to_csv(equity_out, index=False)
    summary.to_csv(summary_out, index=False)
    trades_all.to_csv(trades_out, index=False)

    print(f"\nOutputs:")
    print(f"  {equity_out.relative_to(ROOT)}")
    print(f"  {summary_out.relative_to(ROOT)}")
    print(f"  {trades_out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
