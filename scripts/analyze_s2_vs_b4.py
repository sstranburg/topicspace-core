#!/usr/bin/env python3
"""
analyze_s2_vs_b4.py  (v3 — S2-dir directional sector relaxation test)

Compares S2 (post-fix), S2-dir (directional), B4 (narrative-only), B3 (momentum).

Core question: does replacing the hard sector exclusion in S2 with a
direction-aware eligibility rule (direction==1 + constructive state) close
the structural Sub-W2 gap without making S2 a clone of B4?

Sections:
  1. Sector composition  — does S2-dir gain Growth Software exposure?
  2. State composition   — does S2-dir shift state mix toward B4?
  3. Subwindow returns   — does Sub-W2 gap close?
  4. Drawdown episodes   — does S2-dir track S2 or B4 during stress?
  5. Trade overlap       — S2 vs B4 and S2-dir vs B4 Jaccard comparison
  6. State discipline    — does S2-dir maintain downside protection vs B3?

Usage:
  source venv/bin/activate && python scripts/analyze_s2_vs_b4.py
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
    "NVDA":  "Semiconductors",   "TSM":   "Semiconductors",
    "AMD":   "Semiconductors",   "INTC":  "Semiconductors",
    "ARM":   "Semiconductors",   "AVGO":  "Semiconductors",
    "ASML":  "Semiconductors",   "MU":    "Semiconductors",
    "MRVL":  "Semiconductors",
    "MSFT":  "AI Platform",      "META":  "AI Platform",
    "GOOGL": "AI Platform",      "PLTR":  "AI Platform",
    "AMZN":  "Cloud / Hyperscaler", "ORCL": "Cloud / Hyperscaler",
    "SMCI":  "AI Infrastructure","DELL":  "AI Infrastructure",
    "ANET":  "AI Infrastructure","NBIS":  "AI Infrastructure",
    "VRT":   "AI Infrastructure","VST":   "AI Infrastructure",
    "CEG":   "Energy / Power",
    "MP":    "Materials",
    "CRWV":  "Growth Software",  "CRM":   "Growth Software",
    "ADBE":  "Growth Software",  "DDOG":  "Growth Software",
    "SNOW":  "Growth Software",  "NFLX":  "Growth Software",
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

    hist["_run"] = hist.groupby("ticker")["state"].transform(
        lambda s: (s != s.shift()).cumsum()
    )
    hist["days_in_state"] = hist.groupby(["ticker", "_run"]).cumcount() + 1
    hist = hist.drop(columns="_run")

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

    equity  = pd.read_csv(OUT_DIR / "strategy_equity.csv",  parse_dates=["date"])
    trades  = pd.read_csv(OUT_DIR / "strategy_trades.csv",  parse_dates=["date"])
    s2_tr   = trades[trades["strategy"] == "S2 Sector-Aware"].copy()
    s2d_tr  = trades[trades["strategy"] == "S2-dir Directional"].copy()

    return hist, universe, closes, daily_rets, equity, s2_tr, s2d_tr


# ── Portfolio reconstruction ──────────────────────────────────────────────────

def build_b4_portfolio(hist: pd.DataFrame, universe: list[str]) -> pd.DataFrame:
    rows = []
    for d, day_df in hist[hist["ticker"].isin(universe)].groupby("date"):
        eligible  = day_df[day_df["nds"] > 0].sort_values("nds", ascending=False)
        portfolio = list(eligible["ticker"].head(MAX_POSITIONS))
        rows.append({"date": d, "portfolio": "|".join(sorted(portfolio)), "n_held": len(portfolio)})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def build_b3_portfolio(hist: pd.DataFrame, universe: list[str]) -> pd.DataFrame:
    rows = []
    for d, day_df in hist[hist["ticker"].isin(universe)].groupby("date"):
        ranked    = day_df.sort_values("rel", ascending=False)
        portfolio = list(ranked["ticker"].head(MAX_POSITIONS))
        rows.append({"date": d, "portfolio": "|".join(sorted(portfolio)), "n_held": len(portfolio)})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def parse_portfolio(s) -> list[str]:
    if pd.isna(s) or s == "":
        return []
    return [t for t in str(s).split("|") if t]


# ── Helpers ───────────────────────────────────────────────────────────────────

def sector_composition(trades_df: pd.DataFrame) -> dict[str, float]:
    counts: Counter = Counter()
    total = 0
    for _, row in trades_df.iterrows():
        for t in parse_portfolio(row["portfolio"]):
            counts[SECTORS.get(t, "Other")] += 1
            total += 1
    return {k: round(v / total * 100, 1) for k, v in counts.most_common()} if total else {}


def state_composition(trades_df: pd.DataFrame, hist: pd.DataFrame) -> dict[str, float]:
    counts: Counter = Counter()
    total = 0
    hist_idx = hist.set_index(["date", "ticker"])
    for _, row in trades_df.iterrows():
        d = pd.Timestamp(row["date"])
        for t in parse_portfolio(row["portfolio"]):
            try:
                state = hist_idx.loc[(d, t), "state"]
                counts[state] += 1
                total += 1
            except KeyError:
                pass
    return {k: round(v / total * 100, 1) for k, v in counts.most_common()} if total else {}


def sector_return_contribution(
    trades_df: pd.DataFrame, daily_rets: pd.DataFrame
) -> dict[str, float]:
    sector_exc: dict[str, list[float]] = {}
    trading_days = list(daily_rets.index)
    td_set = set(trading_days)

    for _, row in trades_df.iterrows():
        d = pd.Timestamp(row["date"])
        port = parse_portfolio(row["portfolio"])
        if not port or d not in td_set:
            continue
        idx = trading_days.index(d)
        if idx + 1 >= len(trading_days):
            continue
        next_d  = trading_days[idx + 1]
        qqq_ret = float(daily_rets.loc[next_d, "QQQ"]) if "QQQ" in daily_rets.columns else 0.0
        for t in port:
            if t not in daily_rets.columns:
                continue
            exc = float(daily_rets.loc[next_d, t]) - qqq_ret
            sector_exc.setdefault(SECTORS.get(t, "Other"), []).append(exc)

    return {
        sec: round(sum(v) / len(v) * 100, 3)
        for sec, v in sector_exc.items() if v
    }


def subwindow_cum_exc(equity: pd.DataFrame, strategy: str, start, end) -> float:
    sub  = equity[equity["strategy"] == strategy].sort_values("date")
    mask = (sub["date"] >= pd.Timestamp(start)) & (sub["date"] <= pd.Timestamp(end))
    window = sub[mask]["daily_exc"].values
    if len(window) == 0:
        return 0.0
    return round(float(np.sum(window)), 2)


def find_drawdown_episodes(
    equity: pd.DataFrame, strategy: str, threshold: float = -2.0
) -> list[dict]:
    sub   = equity[equity["strategy"] == strategy].sort_values("date").copy()
    cum   = sub["cum_exc"].values
    dates = sub["date"].values

    peak_val = cum[0]
    peak_idx = 0
    in_dd    = False
    episodes = []
    current  = {}

    for i, (d, c) in enumerate(zip(dates, cum)):
        if c > peak_val:
            if in_dd:
                current["end"]     = d
                current["end_cum"] = c
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
        current["end"]     = dates[-1]
        current["end_cum"] = cum[-1]
        episodes.append(current)

    return episodes


def strategy_return_during(equity: pd.DataFrame, strategy: str, start, end) -> float:
    sub  = equity[equity["strategy"] == strategy].sort_values("date")
    mask = (sub["date"] >= pd.Timestamp(start)) & (sub["date"] <= pd.Timestamp(end))
    vals = sub[mask]["daily_exc"].values
    return round(float(np.sum(vals)), 2) if len(vals) else 0.0


def daily_overlap(tr_a: pd.DataFrame, tr_b: pd.DataFrame) -> pd.DataFrame:
    merged = tr_a.merge(tr_b, on="date", suffixes=("_a", "_b"))
    rows = []
    for _, row in merged.iterrows():
        a = set(parse_portfolio(row["portfolio_a"]))
        b = set(parse_portfolio(row["portfolio_b"]))
        jaccard = len(a & b) / len(a | b) if (a | b) else 1.0
        rows.append({
            "date":   row["date"],
            "jaccard": round(jaccard, 3),
            "a_only": "|".join(sorted(a - b)),
            "b_only": "|".join(sorted(b - a)),
            "shared": "|".join(sorted(a & b)),
        })
    return pd.DataFrame(rows)


def sep(char: str = "-", width: int = 70) -> str:
    return char * width


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Loading data…")
    hist, universe, closes, daily_rets, equity, s2_trades, s2d_trades = load_data()

    print("Reconstructing B4 and B3 daily portfolios…")
    b4_trades = build_b4_portfolio(hist, universe)
    b3_trades = build_b3_portfolio(hist, universe)

    w1_label = f"{SUBWINDOW_1[0].date()} → {SUBWINDOW_1[1].date()}"
    w2_label = f"{SUBWINDOW_2[0].date()} → {SUBWINDOW_2[1].date()}"

    print(f"\n{'=' * 72}")
    print(f"  S2  vs  S2-dir  vs  B4 (NDS>0)  vs  B3 (Momentum)")
    print(f"  Directional sector relaxation test")
    print(f"  {VARIANT}  ·  {BACKTEST_START.date()} → {hist['date'].max().date()}")
    print(f"  Universe: {len(universe)} actors")
    print(f"{'=' * 72}")

    # ── 1. Sector composition ──────────────────────────────────────────────────
    print(f"\n{sep()}")
    print("  1. SECTOR COMPOSITION  (% position-days)")
    print(f"  Key question: does S2-dir gain Growth Software / Consumer Tech exposure?")
    print(sep())

    s2_sec  = sector_composition(s2_trades)
    s2d_sec = sector_composition(s2d_trades)
    b4_sec  = sector_composition(b4_trades)
    b3_sec  = sector_composition(b3_trades)
    all_sec = sorted(set(s2_sec) | set(s2d_sec) | set(b4_sec) | set(b3_sec),
                     key=lambda s: -(s2_sec.get(s, 0) + s2d_sec.get(s, 0)))

    print(f"\n  {'SECTOR':<26} {'S2':>6}  {'S2-dir':>6}  {'B4':>6}  {'B3':>6}  "
          f"{'dir-S2':>7}  {'dir-B4':>7}")
    print("  " + "-" * 70)
    for sec in all_sec:
        s2v  = s2_sec.get(sec, 0.0)
        s2dv = s2d_sec.get(sec, 0.0)
        b4v  = b4_sec.get(sec, 0.0)
        b3v  = b3_sec.get(sec, 0.0)
        flag = " ◀" if abs(s2dv - s2v) >= 5 else ""
        print(f"  {sec:<26} {s2v:>5.1f}%  {s2dv:>5.1f}%  {b4v:>5.1f}%  {b3v:>5.1f}%  "
              f"{s2dv-s2v:>+6.1f}%  {s2dv-b4v:>+6.1f}%{flag}")

    print(f"\n  Avg held/day — S2: {s2_trades['n_held'].mean():.1f}  "
          f"S2-dir: {s2d_trades['n_held'].mean():.1f}  "
          f"B4: {b4_trades['n_held'].mean():.1f}  B3: {b3_trades['n_held'].mean():.1f}")

    print(f"\n  Average daily excess by sector")
    s2_sret  = sector_return_contribution(s2_trades,  daily_rets)
    s2d_sret = sector_return_contribution(s2d_trades, daily_rets)
    b4_sret  = sector_return_contribution(b4_trades,  daily_rets)
    b3_sret  = sector_return_contribution(b3_trades,  daily_rets)
    all_sret = sorted(set(s2_sret) | set(s2d_sret) | set(b4_sret) | set(b3_sret),
                      key=lambda s: -(s2_sret.get(s, 0) + s2d_sret.get(s, 0)))
    fmt = lambda v: f"{v:>+.3f}%" if not np.isnan(v) else "    n/a"
    print(f"\n  {'SECTOR':<26} {'S2 avg':>9}  {'S2-dir':>9}  {'B4 avg':>9}  {'B3 avg':>9}")
    print("  " + "-" * 66)
    for sec in all_sret:
        print(f"  {sec:<26} "
              f"{fmt(s2_sret.get(sec, float('nan'))):>9}  "
              f"{fmt(s2d_sret.get(sec, float('nan'))):>9}  "
              f"{fmt(b4_sret.get(sec, float('nan'))):>9}  "
              f"{fmt(b3_sret.get(sec, float('nan'))):>9}")

    # ── 2. State composition ───────────────────────────────────────────────────
    print(f"\n{sep()}")
    print("  2. STATE COMPOSITION  (% position-days)")
    print(f"  Key question: does S2-dir shift state mix toward B4 (more NEG_CONFIRMATION)?")
    print(sep())

    s2_st  = state_composition(s2_trades,  hist)
    s2d_st = state_composition(s2d_trades, hist)
    b4_st  = state_composition(b4_trades,  hist)
    b3_st  = state_composition(b3_trades,  hist)
    all_st = sorted(set(s2_st) | set(s2d_st) | set(b4_st) | set(b3_st),
                    key=lambda s: -(s2_st.get(s, 0) + s2d_st.get(s, 0)))

    print(f"\n  {'STATE':<22} {'S2':>6}  {'S2-dir':>6}  {'B4':>6}  {'B3':>6}  {'dir-S2':>7}")
    print("  " + "-" * 60)
    for st in all_st:
        s2v  = s2_st.get(st, 0.0)
        s2dv = s2d_st.get(st, 0.0)
        b4v  = b4_st.get(st, 0.0)
        b3v  = b3_st.get(st, 0.0)
        flag = " ◀" if abs(s2dv - s2v) >= 5 else ""
        print(f"  {st:<22} {s2v:>5.1f}%  {s2dv:>5.1f}%  {b4v:>5.1f}%  {b3v:>5.1f}%  "
              f"{s2dv-s2v:>+6.1f}%{flag}")

    # ── 3. Subwindow returns ───────────────────────────────────────────────────
    print(f"\n{sep()}")
    print("  3. SUBWINDOW RETURNS  (cumulative excess vs QQQ)")
    print(f"  Key question: does S2-dir close the Sub-W2 gap?")
    print(sep())
    print(f"\n  Sub-W1: {w1_label}  (backfill window)")
    print(f"  Sub-W2: {w2_label}  (v1-equivalent window)")

    strats = [
        ("S2 Sector-Aware",           "S2"),
        ("S2-dir Directional",        "S2-dir"),
        ("B4 Narrative-Only (NDS>0)", "B4"),
        ("B3 Momentum (top rel)",     "B3"),
        ("S1 Constructive Catch-Up",  "S1"),
        ("S3 Horizon-Aware",          "S3"),
        ("B2 Equal-Weight Universe",  "B2"),
    ]

    print(f"\n  {'STRATEGY':<22} {'FULL':>8}  {'Sub-W1':>8}  {'Sub-W2':>8}")
    print("  " + "-" * 54)
    for full_name, short in strats:
        full = subwindow_cum_exc(equity, full_name, BACKTEST_START, pd.Timestamp("2026-04-29"))
        w1   = subwindow_cum_exc(equity, full_name, *SUBWINDOW_1)
        w2   = subwindow_cum_exc(equity, full_name, *SUBWINDOW_2)
        print(f"  {short:<22} {full:>+7.1f}%  {w1:>+7.1f}%  {w2:>+7.1f}%")

    # ── 4. Drawdown episodes ───────────────────────────────────────────────────
    print(f"\n{sep()}")
    print("  4. DRAWDOWN EPISODES  (≥ -3% cumulative excess; cross-strategy returns)")
    print(f"  Key question: does S2-dir track S2 or B4 during stress?")
    print(sep())

    for anchor_name, anchor_short in [
        ("S2 Sector-Aware",           "S2"),
        ("S2-dir Directional",        "S2-dir"),
        ("B4 Narrative-Only (NDS>0)", "B4"),
        ("B3 Momentum (top rel)",     "B3"),
    ]:
        episodes = find_drawdown_episodes(equity, anchor_name, threshold=-3.0)
        print(f"\n  {anchor_short} episodes ({len(episodes)}):")
        if not episodes:
            print("    none")
            continue
        print(f"  {'START':<12} {'END':<12} {'DEPTH':>7}  "
              f"{'S2 ret':>8}  {'S2-dir':>8}  {'B4 ret':>8}  {'B3 ret':>8}")
        print("  " + "-" * 76)
        for ep in episodes:
            end_d = ep.get("end") or ep["trough"]
            s2r  = strategy_return_during(equity, "S2 Sector-Aware",            ep["start"], end_d)
            s2dr = strategy_return_during(equity, "S2-dir Directional",          ep["start"], end_d)
            b4r  = strategy_return_during(equity, "B4 Narrative-Only (NDS>0)",   ep["start"], end_d)
            b3r  = strategy_return_during(equity, "B3 Momentum (top rel)",        ep["start"], end_d)
            end_str = str(pd.Timestamp(end_d).date())
            print(f"  {str(pd.Timestamp(ep['start']).date()):<12} {end_str:<12} "
                  f"{ep['depth']:>+6.1f}%  "
                  f"{s2r:>+7.2f}%  {s2dr:>+7.2f}%  {b4r:>+7.2f}%  {b3r:>+7.2f}%")

    # ── 5. Trade overlap ───────────────────────────────────────────────────────
    print(f"\n{sep()}")
    print("  5. TRADE OVERLAP")
    print(f"  Key question: does S2-dir converge toward B4's actor set?")
    print(sep())

    for label_a, tr_a, label_b, tr_b in [
        ("S2",     s2_trades,  "B4", b4_trades),
        ("S2-dir", s2d_trades, "B4", b4_trades),
        ("S2",     s2_trades,  "S2-dir", s2d_trades),
    ]:
        ov = daily_overlap(tr_a, tr_b)
        print(f"\n  {label_a} vs {label_b}:")
        print(f"    Avg daily Jaccard: {ov['jaccard'].mean():.2f}  "
              f"J=0 days: {(ov['jaccard'] == 0).sum()}  "
              f"J=1 days: {(ov['jaccard'] == 1).sum()}  "
              f"low-overlap (J<0.2): {(ov['jaccard'] < 0.2).sum()}")

        exc_a = equity[equity["strategy"] == (
            "S2 Sector-Aware" if label_a == "S2" else
            "S2-dir Directional" if label_a == "S2-dir" else label_a
        )].set_index("date")["daily_exc"]
        exc_b = equity[equity["strategy"] == (
            "B4 Narrative-Only (NDS>0)" if label_b == "B4" else
            "S2-dir Directional" if label_b == "S2-dir" else label_b
        )].set_index("date")["daily_exc"]

        lo = ov[ov["jaccard"] < 0.2].copy()
        if not lo.empty:
            lo["a_exc"] = lo["date"].map(exc_a)
            lo["b_exc"] = lo["date"].map(exc_b)
            lo["edge"]  = lo["a_exc"] - lo["b_exc"]
            a_wins = (lo["edge"] > 0).sum()
            b_wins = (lo["edge"] < 0).sum()
            print(f"    On low-overlap days (n={len(lo)}): "
                  f"{label_a} wins={a_wins}  {label_b} wins={b_wins}  "
                  f"avg {label_a} edge={lo['edge'].mean():+.3f}%")

    # Most-exclusive actors across all pairs
    print(f"\n  Actors held by S2-dir not B4 (top 8):")
    s2d_b4_ov = daily_overlap(s2d_trades, b4_trades)
    s2d_excl: Counter = Counter()
    b4_excl:  Counter = Counter()
    for _, row in s2d_b4_ov.iterrows():
        for t in str(row["a_only"]).split("|"):
            if t: s2d_excl[t] += 1
        for t in str(row["b_only"]).split("|"):
            if t: b4_excl[t] += 1
    for t, n in s2d_excl.most_common(8):
        print(f"    {t:<8} {n:>3}d  {SECTORS.get(t,'?')}")

    print(f"\n  Actors held by B4 not S2-dir (top 8):")
    for t, n in b4_excl.most_common(8):
        print(f"    {t:<8} {n:>3}d  {SECTORS.get(t,'?')}")

    print(f"\n  Actors S2-dir added vs S2 (top 8 new entries):")
    s2_s2d_ov = daily_overlap(s2d_trades, s2_trades)
    new_in_s2d: Counter = Counter()
    for _, row in s2_s2d_ov.iterrows():
        for t in str(row["a_only"]).split("|"):
            if t: new_in_s2d[t] += 1
    for t, n in new_in_s2d.most_common(8):
        print(f"    {t:<8} {n:>3}d  {SECTORS.get(t,'?')}")

    # ── 6. State discipline vs momentum ───────────────────────────────────────
    print(f"\n{sep()}")
    print("  6. STATE DISCIPLINE vs MOMENTUM  (S2 and S2-dir vs B3)")
    print(sep())
    print("""
  Framing: if state/sector filtering adds value beyond momentum (B3), it should:
    a) outperform B3 on days when B3 momentum is negative (downside protection)
    b) have different actor exposure from B3 in subwindows where B3 struggles
    c) maintain protection advantage after directional relaxation (S2 vs S2-dir)
""")

    b3_daily = equity[equity["strategy"] == "B3 Momentum (top rel)"][["date", "daily_exc"]].rename(
        columns={"daily_exc": "b3"})

    for strat_name, strat_short in [
        ("S2 Sector-Aware",    "S2"),
        ("S2-dir Directional", "S2-dir"),
    ]:
        s_daily = equity[equity["strategy"] == strat_name][["date", "daily_exc"]].rename(
            columns={"daily_exc": "s"})
        merged = s_daily.merge(b3_daily, on="date")
        merged["edge"] = merged["s"] - merged["b3"]

        b3_neg = merged[merged["b3"] < 0]
        b3_pos = merged[merged["b3"] > 0]

        print(f"  {strat_short}  (n={len(merged)} days, B3-neg={len(b3_neg)}, B3-pos={len(b3_pos)})")
        if len(b3_neg):
            s_avg  = b3_neg["s"].mean()
            b3_avg = b3_neg["b3"].mean()
            pos_rt = (b3_neg["s"] > 0).mean()
            print(f"    When B3 negative — {strat_short}: {s_avg:+.3f}%  B3: {b3_avg:+.3f}%  "
                  f"edge: {s_avg - b3_avg:+.3f}%  {strat_short} positive: {pos_rt:.0%}")
        if len(b3_pos):
            s_avg  = b3_pos["s"].mean()
            b3_avg = b3_pos["b3"].mean()
            print(f"    When B3 positive — {strat_short}: {s_avg:+.3f}%  B3: {b3_avg:+.3f}%  "
                  f"edge: {s_avg - b3_avg:+.3f}%")
        print()

    # Subwindow comparison: S2, S2-dir, B3
    print(f"  Subwindow returns: S2, S2-dir, B3")
    print(f"  {'':22} {'Sub-W1':>9}  {'Sub-W2':>9}  {'Full':>9}")
    print("  " + "-" * 48)
    for name, short in [
        ("S2 Sector-Aware",    "S2"),
        ("S2-dir Directional", "S2-dir"),
        ("B3 Momentum (top rel)", "B3"),
    ]:
        w1  = subwindow_cum_exc(equity, name, *SUBWINDOW_1)
        w2  = subwindow_cum_exc(equity, name, *SUBWINDOW_2)
        tot = subwindow_cum_exc(equity, name, BACKTEST_START, pd.Timestamp("2026-04-29"))
        print(f"  {short:<22} {w1:>+8.1f}%  {w2:>+8.1f}%  {tot:>+8.1f}%")

    # ── Key findings ───────────────────────────────────────────────────────────
    print(f"\n{sep('=', 72)}")
    print("  KEY FINDINGS")
    print(sep("=", 72))
    print(f"""
  Directional sector relaxation test  ({BACKTEST_START.date()} → 2026-04-29)

  Does S2-dir close the structural Sub-W2 gap?
    See section 3. If S2-dir Sub-W2 > S2 Sub-W2 by 5pp+, directional
    relaxation is earning its keep. If Sub-W2 stays negative or barely
    improves, the fix is insufficient and the sector eligibility matrix
    itself needs rethinking.

  Does S2-dir become a B4 clone?
    Check section 1 (Growth Software %, dir-B4 column) and section 5
    (S2-dir vs B4 Jaccard). If Jaccard >> S2 vs B4, and Growth Software
    rises to near B4 levels, S2-dir has converged. If Jaccard stays < 0.5
    and Growth Software stays below B4, the directional filter is
    maintaining differentiation.

  Is downside protection preserved?
    Section 6 compares S2 and S2-dir vs B3 on negative-B3 days.
    If S2-dir edge ≈ S2 edge on B3-negative days, the NDS + constructive-
    state discipline is still filtering out momentum noise even with the
    expanded actor pool.

  Verdict framing:
    Strong result: S2-dir Sub-W2 ≥ 0, Jaccard(S2-dir, B4) < 0.5,
      B3-neg edge preserved → directional fix works; publish S2-dir as S2.
    Weak result: Sub-W2 still negative or Jaccard too high →
      sector eligibility matrix needs event-study re-derivation on full
      250-day window, or accept B4 as the deployment strategy.
""")


if __name__ == "__main__":
    main()
