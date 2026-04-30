#!/usr/bin/env python3
"""
simulate_blended_portfolio.py

Equal-weight blended portfolio simulation: S2+B4 and S4+B4.

Each blend holds the union of both sleeve portfolios, equal-weighted.
If a ticker appears in both sleeves on the same day it is held once
(deduplicated), so the blend can hold between max_positions and
2×max_positions names.

Reports for each blend:
  - Cumulative excess vs QQQ
  - Sharpe, max drawdown, hit rate, avg held per day
  - Subwindow returns (Sub-W1 / Sub-W2)
  - Sector concentration vs each standalone sleeve
  - Drawdown overlap: when does the blend draw down vs each sleeve?
  - Recovery analysis: does the blend recover faster than either sleeve?

Baselines shown for comparison: S2, S4, B4, B3.

Usage:
  source venv/bin/activate && python scripts/simulate_blended_portfolio.py
"""

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT         = Path(__file__).parent.parent
HISTORY_FILE = ROOT / "data" / "derived" / "backtest_history.parquet"
PRICES_DIR   = ROOT / "data" / "derived" / "prices"
OUT_DIR      = ROOT / "data" / "derived" / "event_studies"

VARIANT        = "mid_floor"
MIN_COVERAGE   = 40.0
MAX_POSITIONS  = 5
BACKTEST_START = pd.Timestamp("2025-05-01")

SUBWINDOW_1 = (pd.Timestamp("2025-05-01"),  pd.Timestamp("2025-10-31"))
SUBWINDOW_2 = (pd.Timestamp("2025-11-01"),  pd.Timestamp("2026-04-29"))

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


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data():
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

    needed = set(universe) | {"QQQ"}
    frames = []
    for ticker in needed:
        p = PRICES_DIR / f"{ticker}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)[["timestamp", "close"]].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        frames.append(df.set_index("timestamp")["close"].rename(ticker))
    closes     = pd.concat(frames, axis=1).sort_index()
    closes     = closes[closes.index >= BACKTEST_START]
    daily_rets = closes.pct_change()

    equity = pd.read_csv(OUT_DIR / "strategy_equity.csv",  parse_dates=["date"])
    trades = pd.read_csv(OUT_DIR / "strategy_trades.csv",  parse_dates=["date"])

    return hist, universe, closes, daily_rets, equity, trades


# ── Portfolio parsing ─────────────────────────────────────────────────────────

def parse_portfolio(s) -> list[str]:
    if pd.isna(s) or s == "":
        return []
    return [t for t in str(s).split("|") if t]


def get_daily_portfolios(trades: pd.DataFrame, strategy: str) -> pd.DataFrame:
    """Pull portfolio snapshots for strategies that write to strategy_trades.csv."""
    return (trades[trades["strategy"] == strategy][["date", "portfolio"]]
            .set_index("date"))


def build_b4_portfolio(hist: pd.DataFrame, universe: list[str]) -> pd.DataFrame:
    """Reconstruct B4 daily portfolios from history (not in trades CSV)."""
    rows = []
    for d, day_df in hist[hist["ticker"].isin(universe)].groupby("date"):
        eligible  = day_df[day_df["nds"] > 0].sort_values("nds", ascending=False)
        portfolio = list(eligible["ticker"].head(MAX_POSITIONS))
        rows.append({"date": d, "portfolio": "|".join(sorted(portfolio))})
    return pd.DataFrame(rows).set_index("date")


# ── Blend simulation ──────────────────────────────────────────────────────────

def simulate_blend(
    sleeve_a: pd.DataFrame,   # daily portfolios, indexed by date
    sleeve_b: pd.DataFrame,   # daily portfolios, indexed by date
    daily_rets: pd.DataFrame,
    label: str,
) -> pd.DataFrame:
    """
    Simulate an equal-weight blend of two sleeves.
    Each sleeve is held at equal weight; within each sleeve tickers are
    equal-weighted. Deduplication: a ticker in both sleeves counts once,
    still at equal weight with the rest of the union.

    Returns daily results DataFrame.
    """
    trading_days = sorted(daily_rets.index)
    dates_a = set(sleeve_a.index)
    dates_b = set(sleeve_b.index)

    results = []
    for i, d in enumerate(trading_days[:-1]):
        next_d = trading_days[i + 1]

        port_a = set(parse_portfolio(sleeve_a.loc[d, "portfolio"]) if d in dates_a else [])
        port_b = set(parse_portfolio(sleeve_b.loc[d, "portfolio"]) if d in dates_b else [])
        union  = port_a | port_b

        if not union:
            excess   = 0.0
            port_ret = float(daily_rets.loc[next_d, "QQQ"]) if "QQQ" in daily_rets.columns else 0.0
        else:
            ticker_rets = daily_rets.loc[next_d, list(union)].dropna()
            qqq_ret     = float(daily_rets.loc[next_d, "QQQ"]) if "QQQ" in daily_rets.columns else 0.0
            excess      = float((ticker_rets - qqq_ret).mean()) if len(ticker_rets) else 0.0
            port_ret    = float(ticker_rets.mean()) if len(ticker_rets) else 0.0

        results.append({
            "date":     d,
            "strategy": label,
            "n_held":   len(union),
            "a_only":   len(port_a - port_b),
            "b_only":   len(port_b - port_a),
            "shared":   len(port_a & port_b),
            "tickers":  "|".join(sorted(union)),
            "excess":   round(excess, 5),
            "port_ret": round(port_ret, 5),
        })

    return pd.DataFrame(results)


# ── Performance metrics ───────────────────────────────────────────────────────

def compute_metrics(result_df: pd.DataFrame) -> dict:
    exc    = result_df["excess"].values
    cum    = np.cumprod(1 + exc) - 1
    n_days = len(exc)

    total_ret = float(cum[-1]) if len(cum) else 0.0
    cagr      = (1 + total_ret) ** (252 / max(n_days, 1)) - 1
    sharpe    = float(np.mean(exc) / np.std(exc) * np.sqrt(252)) if np.std(exc) > 0 else 0.0

    wealth = np.cumprod(1 + exc)
    peak   = np.maximum.accumulate(wealth)
    dd     = (wealth - peak) / peak
    max_dd = float(dd.min())

    hit_rate = float((exc > 0).mean())

    return {
        "total_exc": round(total_ret * 100, 2),
        "cagr":      round(cagr * 100, 2),
        "sharpe":    round(sharpe, 2),
        "hit_rate":  round(hit_rate * 100, 1),
        "max_dd":    round(max_dd * 100, 2),
        "avg_daily": round(float(np.mean(exc)) * 100, 3),
        "n_days":    n_days,
    }


def cumulative_excess(result_df: pd.DataFrame, label: str) -> pd.DataFrame:
    exc = result_df["excess"].values
    cum = np.cumprod(1 + exc) - 1
    return pd.DataFrame({
        "date":      result_df["date"].values,
        "strategy":  label,
        "cum_exc":   np.round(cum * 100, 4),
        "daily_exc": np.round(exc * 100, 4),
    })


# ── Subwindow helper ──────────────────────────────────────────────────────────

def subwindow_ret(equity_df: pd.DataFrame, strategy: str, start, end) -> float:
    sub  = equity_df[equity_df["strategy"] == strategy].sort_values("date")
    mask = (sub["date"] >= pd.Timestamp(start)) & (sub["date"] <= pd.Timestamp(end))
    vals = sub[mask]["daily_exc"].values
    return round(float(np.sum(vals)), 2) if len(vals) else 0.0


# ── Sector composition ────────────────────────────────────────────────────────

def sector_comp(result_df: pd.DataFrame) -> dict[str, float]:
    counts: Counter = Counter()
    total = 0
    for _, row in result_df.iterrows():
        for t in parse_portfolio(row["tickers"]):
            counts[SECTORS.get(t, "Other")] += 1
            total += 1
    return {k: round(v / total * 100, 1) for k, v in counts.most_common()} if total else {}


# ── Drawdown episodes ─────────────────────────────────────────────────────────

def find_drawdown_episodes(equity_df: pd.DataFrame, strategy: str,
                           threshold: float = -3.0) -> list[dict]:
    sub   = equity_df[equity_df["strategy"] == strategy].sort_values("date").copy()
    cum   = sub["cum_exc"].values
    dates = sub["date"].values

    peak_val = cum[0]
    in_dd    = False
    episodes = []
    current  = {}
    peak_idx = 0

    for i, (d, c) in enumerate(zip(dates, cum)):
        if c > peak_val:
            if in_dd:
                current["end"] = d
                episodes.append(current)
                current = {}
                in_dd   = False
            peak_val = c
            peak_idx = i
        dd = c - peak_val
        if dd <= threshold and not in_dd:
            in_dd   = True
            current = {"start": dates[peak_idx], "trough": d,
                       "depth": round(dd, 2), "end": None}
        elif in_dd and dd < current["depth"]:
            current["trough"] = d
            current["depth"]  = round(dd, 2)

    if in_dd:
        current["end"] = dates[-1]
        episodes.append(current)

    return episodes


def strategy_ret_during(equity_df: pd.DataFrame, strategy: str, start, end) -> float:
    sub  = equity_df[equity_df["strategy"] == strategy].sort_values("date")
    mask = (sub["date"] >= pd.Timestamp(start)) & (sub["date"] <= pd.Timestamp(end))
    vals = sub[mask]["daily_exc"].values
    return round(float(np.sum(vals)), 2) if len(vals) else 0.0


def sep(c="-", w=72) -> str:
    return c * w


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Loading data…")
    hist, universe, closes, daily_rets, equity, trades = load_data()

    # Pull daily portfolio snapshots for each sleeve.
    # B4 is a ranked baseline that doesn't write to strategy_trades.csv —
    # reconstruct it from history the same way analyze_s2_vs_b4.py does.
    print("Reconstructing B4 daily portfolios…")
    s2_port = get_daily_portfolios(trades, "S2 Sector-Aware")
    s4_port = get_daily_portfolios(trades, "S4 S2+Reversal")
    b4_port = build_b4_portfolio(hist, universe)

    print("Simulating blended portfolios…")
    blend_s2_b4 = simulate_blend(s2_port, b4_port, daily_rets, "Blend S2+B4")
    blend_s4_b4 = simulate_blend(s4_port, b4_port, daily_rets, "Blend S4+B4")

    # Build equity curves for blends
    eq_s2b4 = cumulative_excess(blend_s2_b4, "Blend S2+B4")
    eq_s4b4 = cumulative_excess(blend_s4_b4, "Blend S4+B4")

    # Combine with existing equity for reference strategies
    ref_names = [
        "S2 Sector-Aware",
        "S4 S2+Reversal",
        "B4 Narrative-Only (NDS>0)",
        "B3 Momentum (top rel)",
    ]
    ref_equity = equity[equity["strategy"].isin(ref_names)].copy()
    all_equity = pd.concat([ref_equity, eq_s2b4, eq_s4b4], ignore_index=True)

    print(f"\n{'=' * 72}")
    print("  BLENDED PORTFOLIO SIMULATION  (equal-weight sleeve blend)")
    print(f"  {VARIANT}  ·  {BACKTEST_START.date()} → {hist['date'].max().date()}")
    print(f"  Universe: {len(universe)} actors")
    print(f"{'=' * 72}")

    # ── 1. Performance summary ─────────────────────────────────────────────────
    print(f"\n{sep()}")
    print("  1. PERFORMANCE SUMMARY  (vs QQQ)")
    print(sep())

    display = [
        ("Blend S2+B4", "Blend S2+B4", blend_s2_b4),
        ("Blend S4+B4", "Blend S4+B4", blend_s4_b4),
        ("S2 Sector-Aware",           "S2",  None),
        ("S4 S2+Reversal",            "S4",  None),
        ("B4 Narrative-Only (NDS>0)", "B4",  None),
        ("B3 Momentum (top rel)",     "B3",  None),
    ]

    print(f"\n  {'STRATEGY':<22} {'CUM EXC':>8}  {'CAGR':>6}  {'SHARPE':>7}  "
          f"{'HIT':>5}  {'MAX DD':>7}  {'AVG/D':>7}  {'AVG N':>6}")
    print("  " + "-" * 76)

    all_metrics: dict[str, dict] = {}
    for full_name, short, blend_df in display:
        if blend_df is not None:
            m   = compute_metrics(blend_df)
            avg_n = blend_df["n_held"].mean()
            all_metrics[short] = m
        else:
            sub = equity[equity["strategy"] == full_name]
            exc = sub["daily_exc"].values
            arr = exc / 100.0
            m   = compute_metrics(pd.DataFrame({"excess": arr}))
            all_metrics[short] = m
            avg_n = float("nan")

        n_str = f"{avg_n:.1f}" if not (isinstance(avg_n, float) and np.isnan(avg_n)) else "  n/a"
        print(f"  {short:<22} {m['total_exc']:>+7.1f}%  {m['cagr']:>+5.1f}%  "
              f"{m['sharpe']:>6.2f}  {m['hit_rate']:>4.0f}%  "
              f"{m['max_dd']:>+6.1f}%  {m['avg_daily']:>+6.3f}%  {n_str:>6}")

    # ── 2. Subwindow returns ───────────────────────────────────────────────────
    print(f"\n{sep()}")
    print("  2. SUBWINDOW RETURNS  (cumulative excess vs QQQ)")
    print(sep())
    print(f"\n  Sub-W1: {SUBWINDOW_1[0].date()} → {SUBWINDOW_1[1].date()}  (backfill window)")
    print(f"  Sub-W2: {SUBWINDOW_2[0].date()} → {SUBWINDOW_2[1].date()}  (v1-equivalent window)")

    print(f"\n  {'STRATEGY':<22} {'FULL':>8}  {'Sub-W1':>8}  {'Sub-W2':>8}")
    print("  " + "-" * 52)
    for full_name, short, _ in display:
        strat = "Blend S2+B4" if short == "Blend S2+B4" else (
                "Blend S4+B4" if short == "Blend S4+B4" else full_name)
        full = subwindow_ret(all_equity, strat, BACKTEST_START, pd.Timestamp("2026-04-29"))
        w1   = subwindow_ret(all_equity, strat, *SUBWINDOW_1)
        w2   = subwindow_ret(all_equity, strat, *SUBWINDOW_2)
        print(f"  {short:<22} {full:>+7.1f}%  {w1:>+7.1f}%  {w2:>+7.1f}%")

    # ── 3. Sector concentration ────────────────────────────────────────────────
    print(f"\n{sep()}")
    print("  3. SECTOR CONCENTRATION  (% position-days)")
    print(sep())

    s2b4_sec = sector_comp(blend_s2_b4)
    s4b4_sec = sector_comp(blend_s4_b4)

    # Pull S2/S4/B4 sector from existing trades
    def trades_sector(strategy_label: str) -> dict[str, float]:
        t = trades[trades["strategy"] == strategy_label].copy()
        counts: Counter = Counter()
        total = 0
        for _, row in t.iterrows():
            for ticker in parse_portfolio(row["portfolio"]):
                counts[SECTORS.get(ticker, "Other")] += 1
                total += 1
        return {k: round(v / total * 100, 1) for k, v in counts.most_common()} if total else {}

    s2_sec = trades_sector("S2 Sector-Aware")
    b4_sec = trades_sector("B4 Narrative-Only (NDS>0)")

    all_sectors = sorted(
        set(s2b4_sec) | set(s4b4_sec) | set(s2_sec) | set(b4_sec),
        key=lambda s: -(s2b4_sec.get(s, 0) + s4b4_sec.get(s, 0))
    )

    print(f"\n  {'SECTOR':<26} {'S2+B4':>7}  {'S4+B4':>7}  {'S2':>7}  {'B4':>7}")
    print("  " + "-" * 60)
    for sec in all_sectors:
        print(f"  {sec:<26} "
              f"{s2b4_sec.get(sec, 0.0):>6.1f}%  "
              f"{s4b4_sec.get(sec, 0.0):>6.1f}%  "
              f"{s2_sec.get(sec, 0.0):>6.1f}%  "
              f"{b4_sec.get(sec, 0.0):>6.1f}%")

    print(f"\n  Avg position-days/day:")
    for short, df in [("Blend S2+B4", blend_s2_b4), ("Blend S4+B4", blend_s4_b4)]:
        print(f"    {short}: {df['n_held'].mean():.1f}  "
              f"(A-only: {df['a_only'].mean():.1f}  "
              f"B-only: {df['b_only'].mean():.1f}  "
              f"shared: {df['shared'].mean():.1f})")

    # ── 4. Drawdown overlap ────────────────────────────────────────────────────
    print(f"\n{sep()}")
    print("  4. DRAWDOWN OVERLAP  (≥ -3% cumulative excess)")
    print(f"  Key: do the blends draw down at the same time as their sleeves?")
    print(sep())

    ref_strats = {
        "Blend S2+B4": "Blend S2+B4",
        "Blend S4+B4": "Blend S4+B4",
        "S2":          "S2 Sector-Aware",
        "S4":          "S4 S2+Reversal",
        "B4":          "B4 Narrative-Only (NDS>0)",
        "B3":          "B3 Momentum (top rel)",
    }

    for blend_name in ["Blend S2+B4", "Blend S4+B4"]:
        episodes = find_drawdown_episodes(all_equity, blend_name, threshold=-3.0)
        print(f"\n  {blend_name} episodes ({len(episodes)}):")
        if not episodes:
            print("    none")
            continue
        print(f"  {'START':<12} {'END':<12} {'DEPTH':>7}  "
              f"{'S2 ret':>8}  {'B4 ret':>8}  {'B3 ret':>8}")
        print("  " + "-" * 66)
        for ep in episodes:
            end_d = ep.get("end") or ep["trough"]
            s2r = strategy_ret_during(all_equity, "S2 Sector-Aware",           ep["start"], end_d)
            b4r = strategy_ret_during(all_equity, "B4 Narrative-Only (NDS>0)", ep["start"], end_d)
            b3r = strategy_ret_during(all_equity, "B3 Momentum (top rel)",      ep["start"], end_d)
            print(f"  {str(pd.Timestamp(ep['start']).date()):<12} "
                  f"{str(pd.Timestamp(end_d).date()):<12} "
                  f"{ep['depth']:>+6.1f}%  "
                  f"{s2r:>+7.2f}%  {b4r:>+7.2f}%  {b3r:>+7.2f}%")

    # ── 5. Recovery analysis ───────────────────────────────────────────────────
    print(f"\n{sep()}")
    print("  5. RECOVERY SPEED  (time from trough to new equity high, trading days)")
    print(sep())

    def recovery_times(equity_df: pd.DataFrame, strategy: str) -> list[dict]:
        sub   = equity_df[equity_df["strategy"] == strategy].sort_values("date").copy()
        cum   = sub["cum_exc"].values
        dates = sub["date"].values
        peak  = cum[0]
        in_dd = False
        results = []

        for i, (d, c) in enumerate(zip(dates, cum)):
            if c > peak:
                if in_dd:
                    # Found new high after drawdown
                    results[-1]["recovery_days"] = i - results[-1]["trough_idx"]
                    results[-1]["recovered"] = True
                    in_dd = False
                peak = c
            if c < peak * 0.97 and not in_dd:
                in_dd = True
                results.append({
                    "start": d, "trough_idx": i, "depth": round(c - peak, 2),
                    "recovery_days": None, "recovered": False
                })
            elif in_dd and c - peak < results[-1]["depth"]:
                results[-1]["depth"]       = round(c - peak, 2)
                results[-1]["trough_idx"]  = i

        return results

    for blend_name in ["Blend S2+B4", "Blend S4+B4", "S2 Sector-Aware",
                       "B4 Narrative-Only (NDS>0)"]:
        recs = recovery_times(all_equity, blend_name)
        recovered = [r for r in recs if r["recovered"]]
        not_rec   = [r for r in recs if not r["recovered"]]
        short = blend_name.replace(" Narrative-Only (NDS>0)", "").replace(" Sector-Aware", "")
        if recovered:
            avg_days = sum(r["recovery_days"] for r in recovered) / len(recovered)
            max_days = max(r["recovery_days"] for r in recovered)
            print(f"\n  {short:<22}: {len(recovered)} recovered episodes  "
                  f"avg {avg_days:.0f}d  max {max_days}d  "
                  f"still open: {len(not_rec)}")
        else:
            print(f"\n  {short:<22}: 0 recovered episodes  still open: {len(not_rec)}")

    # ── 6. S2 discipline test in blend context ─────────────────────────────────
    print(f"\n{sep()}")
    print("  6. STATE DISCIPLINE IN BLEND  (blend vs B3 on B3-negative days)")
    print(sep())

    b3_daily = all_equity[all_equity["strategy"] == "B3 Momentum (top rel)"][
        ["date", "daily_exc"]].rename(columns={"daily_exc": "b3"})

    for blend_name in ["Blend S2+B4", "Blend S4+B4"]:
        s_daily = all_equity[all_equity["strategy"] == blend_name][
            ["date", "daily_exc"]].rename(columns={"daily_exc": "s"})
        merged = s_daily.merge(b3_daily, on="date")

        b3_neg = merged[merged["b3"] < 0]
        b3_pos = merged[merged["b3"] > 0]
        short  = blend_name

        print(f"\n  {short}  (B3-neg: {len(b3_neg)}d, B3-pos: {len(b3_pos)}d)")
        if len(b3_neg):
            s_avg  = b3_neg["s"].mean()
            b3_avg = b3_neg["b3"].mean()
            pos_rt = (b3_neg["s"] > 0).mean()
            print(f"    When B3 negative: blend {s_avg:+.3f}%  B3 {b3_avg:+.3f}%  "
                  f"edge {s_avg-b3_avg:+.3f}%  blend positive: {pos_rt:.0%}")
        if len(b3_pos):
            s_avg  = b3_pos["s"].mean()
            b3_avg = b3_pos["b3"].mean()
            print(f"    When B3 positive: blend {s_avg:+.3f}%  B3 {b3_avg:+.3f}%  "
                  f"edge {s_avg-b3_avg:+.3f}%")

    # ── Key findings ───────────────────────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print("  KEY FINDINGS")
    print("=" * 72)

    s2b4 = all_metrics["Blend S2+B4"]
    s4b4 = all_metrics["Blend S4+B4"]
    s2   = all_metrics["S2"]
    s4   = all_metrics["S4"]
    b4   = all_metrics["B4"]
    b3   = all_metrics["B3"]

    print(f"""
  Equal-weight sleeve blends  ({BACKTEST_START.date()} → 2026-04-29)

  Blend S2+B4: {s2b4['total_exc']:+.1f}%  Sharpe {s2b4['sharpe']:.2f}  max_dd {s2b4['max_dd']:+.1f}%
  Blend S4+B4: {s4b4['total_exc']:+.1f}%  Sharpe {s4b4['sharpe']:.2f}  max_dd {s4b4['max_dd']:+.1f}%
  S2 alone:    {s2['total_exc']:+.1f}%  Sharpe {s2['sharpe']:.2f}  max_dd {s2['max_dd']:+.1f}%
  S4 alone:    {s4['total_exc']:+.1f}%  Sharpe {s4['sharpe']:.2f}  max_dd {s4['max_dd']:+.1f}%
  B4 alone:    {b4['total_exc']:+.1f}%  Sharpe {b4['sharpe']:.2f}  max_dd {b4['max_dd']:+.1f}%
  B3 alone:    {b3['total_exc']:+.1f}%  Sharpe {b3['sharpe']:.2f}  max_dd {b3['max_dd']:+.1f}%

  Blend S2+B4 vs best sleeve alone (S4 or B4):
    Return:   {s2b4['total_exc'] - max(s4['total_exc'], b4['total_exc']):+.1f}pp vs best sleeve
    Sharpe:   {s2b4['sharpe'] - max(s4['sharpe'], b4['sharpe']):+.2f} vs best sleeve
    Max DD:   {s2b4['max_dd'] - min(s4['max_dd'], b4['max_dd']):+.1f}pp vs best sleeve

  Blend S4+B4 vs best sleeve alone:
    Return:   {s4b4['total_exc'] - max(s4['total_exc'], b4['total_exc']):+.1f}pp vs best sleeve
    Sharpe:   {s4b4['sharpe'] - max(s4['sharpe'], b4['sharpe']):+.2f} vs best sleeve
    Max DD:   {s4b4['max_dd'] - min(s4['max_dd'], b4['max_dd']):+.1f}pp vs best sleeve

  Diversification verdict:
    If blends improve Sharpe and/or reduce max_dd vs the best individual
    sleeve, the strategies are genuinely complementary (low return correlation).
    If blends merely average the standalone results, they are correlated enough
    that a single best sleeve dominates.
""")


if __name__ == "__main__":
    main()
