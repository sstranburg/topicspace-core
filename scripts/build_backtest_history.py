#!/usr/bin/env python3
"""
build_backtest_history.py

Reconstructs (date, ticker, narr, state, nds, rel) for every trading day in
the price window using a strict no-lookahead replay of the events corpus.
Produces data/derived/backtest_history.parquet.

Three narr formula variants test floor sensitivity:
  baseline  — floor=35, matches production formula minus AI-signal layer
  mid_floor — floor=20, intermediate
  low_floor — floor=0,  maximum spread; tests compression hypothesis

Corpus modes (--corpus flag):
  combined    (default) — production corpus + backfill file
                          use for all backtest work after running
                          fetch_backfill_historical.py
  production  — production corpus only (tech_ecosystem_filtered.jsonl)
                use to reproduce original v1 results on the 60-day window

Usage:
  source venv/bin/activate && python scripts/build_backtest_history.py
  source venv/bin/activate && python scripts/build_backtest_history.py --corpus production
"""

import argparse
import json
import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT             = Path(__file__).parent.parent
EVENTS_FILE      = ROOT / "data" / "normalized" / "tech_ecosystem_filtered.jsonl"
BACKFILL_FILE    = ROOT / "data" / "normalized" / "tech_ecosystem_backfill.jsonl"
PRICES_DIR       = ROOT / "data" / "derived" / "prices"
OUTPUT_FILE      = ROOT / "data" / "derived" / "backtest_history.parquet"

# Exclude thin-coverage actors (SOFI, ZETA, USAR, ODC)
TICKERS = [
    "NVDA", "MRVL", "MSFT", "ARM",  "PLTR", "META", "ADBE", "MU",
    "ORCL", "SMCI", "INTC", "AMD",  "TSLA", "DELL", "GOOGL", "ANET",
    "NBIS", "AVGO", "AMZN", "TSM",  "VRT",  "CRM",  "CRWV",
    "AAPL", "ASML", "SNOW", "DDOG", "CEG",  "VST",  "NFLX", "TTD", "MP",
]
TICKERS_SET = set(TICKERS)

# Narrative direction: -1 = bearish actor, +1 = bullish
ACTOR_DIRECTIONS: dict[str, int] = {
    "MU":   -1,
    "TSLA": -1,
    "SNOW": -1,
    "CRWV": -1,
    "CRM":  -1,
    "INTC": -1,
}

# Persistent state overrides — same as production
STATE_OVERRIDES: dict[str, str] = {
    "TSLA": "DISAGREEMENT",
}


# ── Narr formula variants ─────────────────────────────────────────────────────

@dataclass
class NarrConfig:
    name: str
    floor: float            # narr floor when activity = 0
    pressure_weight: float  # max pts from 7d event pressure (0–1 normalized)
    recency_weight: float   # max pts from 48h recency burst
    pressure_baseline: int  # events_7d count that saturates pressure
    recency_cap: int        # events_48h count that saturates recency


VARIANTS: list[NarrConfig] = [
    # Mirrors production formula minus AI-signal boosts
    NarrConfig("baseline",  floor=35, pressure_weight=60, recency_weight=15,
               pressure_baseline=30, recency_cap=250),
    # Intermediate floor
    NarrConfig("mid_floor", floor=20, pressure_weight=60, recency_weight=15,
               pressure_baseline=30, recency_cap=250),
    # No floor — maximum spread; tests compression hypothesis
    NarrConfig("low_floor", floor=0,  pressure_weight=60, recency_weight=15,
               pressure_baseline=30, recency_cap=250),
]


# ── Core computation ──────────────────────────────────────────────────────────

def compute_narr(events_48h: int, events_7d: int, cfg: NarrConfig) -> int:
    pressure = min(1.0, events_7d / cfg.pressure_baseline)
    recency  = min(events_48h, cfg.recency_cap) / cfg.recency_cap
    raw      = cfg.floor + pressure * cfg.pressure_weight + recency * cfg.recency_weight
    return min(95, round(raw))


def classify_state(ticker: str, narr: int, rel: float, direction: int) -> str:
    if ticker in STATE_OVERRIDES:
        return STATE_OVERRIDES[ticker]
    if direction < 0:
        return "DISAGREEMENT" if rel > 2.0 else "NEG_CONFIRMATION"
    if narr >= 65 and rel >= 5.0:
        return "CONFIRMED"
    if narr >= 55 and rel >= 1.5:
        return "EARLY"
    if narr >= 45 and rel < -5.0:
        return "DIVERGENCE"
    if narr >= 45 and -5.0 <= rel < 1.5:
        return "REPRICING"
    if rel < -6.0:
        return "DIVERGENCE"
    price_score = max(0, min(100, 50 + rel * 5))
    nds = narr - price_score
    if rel > 2.0 and narr < 60 and nds < -20:
        return "PRICE-LED"
    if narr < 40:
        return "UNCLEAR"
    return "MACRO"


def compute_nds(direction: int, narr: int, rel: float) -> float:
    return round(direction * (narr - 50) - rel * 5, 1)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_events(corpus: str = "combined") -> dict[str, list[str]]:
    """
    Return {ticker: sorted list of YYYY-MM-DD date strings from events corpus}.

    corpus="combined"   reads production corpus + backfill file (default)
    corpus="production" reads production corpus only
    """
    files_to_read: list[Path] = [EVENTS_FILE]
    if corpus == "combined":
        if BACKFILL_FILE.exists():
            files_to_read.append(BACKFILL_FILE)
        else:
            print("  [warn] --corpus combined requested but backfill file not found; "
                  "run fetch_backfill_historical.py first. Falling back to production only.")

    # Deduplicate across files by event_id so a cross-corpus duplicate is counted once.
    seen_ids: set[str] = set()
    actor_dates: dict[str, list[str]] = defaultdict(list)
    counts: dict[str, int] = {}

    for path in files_to_read:
        n = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                eid = e.get("event_id", "")
                if eid and eid in seen_ids:
                    continue
                if eid:
                    seen_ids.add(eid)
                ts = e.get("timestamp", "")[:10]
                if not ts:
                    continue
                for actor in e.get("actors", []):
                    if actor in TICKERS_SET:
                        actor_dates[actor].append(ts)
                        n += 1
        counts[path.name] = n

    label = "combined" if len(files_to_read) > 1 else "production"
    print(f"  corpus={label}  " + "  ".join(f"{k}: {v:,}" for k, v in counts.items()))

    return {t: sorted(v) for t, v in actor_dates.items()}


def load_prices() -> dict[str, pd.DataFrame]:
    """Return {ticker: DataFrame indexed by Timestamp, cols include return_5d}."""
    prices: dict[str, pd.DataFrame] = {}
    for f in PRICES_DIR.glob("*.parquet"):
        df = pd.read_parquet(f)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        prices[f.stem] = df.set_index("timestamp").sort_index()
    return prices


def get_rel(ticker: str, d: date, prices: dict[str, pd.DataFrame]) -> Optional[float]:
    """5-day trailing return of ticker minus QQQ as of date d, in percentage points."""
    t_df = prices.get(ticker)
    q_df = prices.get("QQQ")
    if t_df is None or q_df is None:
        return None
    ts = pd.Timestamp(d)
    t_rows = t_df[t_df.index <= ts]
    q_rows = q_df[q_df.index <= ts]
    if t_rows.empty or q_rows.empty:
        return None
    t_ret = t_rows.iloc[-1].get("return_5d", np.nan)
    q_ret = q_rows.iloc[-1].get("return_5d", np.nan)
    if pd.isna(t_ret) or pd.isna(q_ret):
        return None
    # return_5d stored as decimal (e.g. 0.05 = 5%) — convert to pct points
    return round((float(t_ret) - float(q_ret)) * 100, 3)


def count_events(dates: list[str], lo: str, hi: str) -> int:
    """Count events with lo <= date <= hi on a sorted list of date strings."""
    return bisect_right(dates, hi) - bisect_left(dates, lo)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build backtest history parquet")
    parser.add_argument(
        "--corpus",
        choices=["combined", "production"],
        default="combined",
        help="combined (default): production + backfill; production: production only",
    )
    args = parser.parse_args()

    print(f"Loading events (--corpus {args.corpus})…")
    actor_dates = load_events(corpus=args.corpus)
    total_event_pairs = sum(len(v) for v in actor_dates.values())
    print(f"  {total_event_pairs:,} event-date pairs across {len(actor_dates)} actors")

    print("Loading prices…")
    prices = load_prices()
    qqq = prices.get("QQQ")
    if qqq is None:
        sys.exit("ERROR: QQQ price data not found in prices dir")

    trading_days = [ts.date() for ts in qqq.index]
    print(f"  {len(trading_days)} trading days: {trading_days[0]} → {trading_days[-1]}")

    print(f"Building history ({len(TICKERS)} tickers × {len(trading_days)} days × {len(VARIANTS)} variants)…")
    records: list[dict] = []

    for d in trading_days:
        d_str  = d.isoformat()
        lo_48h = (d - timedelta(days=2)).isoformat()
        lo_7d  = (d - timedelta(days=7)).isoformat()

        for ticker in TICKERS:
            direction = ACTOR_DIRECTIONS.get(ticker, 1)
            rel       = get_rel(ticker, d, prices)
            if rel is None:
                continue

            dates  = actor_dates.get(ticker, [])
            e_48h  = count_events(dates, lo_48h, d_str)
            e_7d   = count_events(dates, lo_7d, d_str)
            # Flag dates where event coverage is too thin to trust narr
            sufficient = e_7d >= 3

            for cfg in VARIANTS:
                narr  = compute_narr(e_48h, e_7d, cfg)
                state = classify_state(ticker, narr, rel, direction)
                nds   = compute_nds(direction, narr, rel)
                records.append({
                    "date":            d_str,
                    "ticker":          ticker,
                    "variant":         cfg.name,
                    "narr":            narr,
                    "state":           state,
                    "nds":             nds,
                    "rel":             rel,
                    "events_48h":      e_48h,
                    "events_7d":       e_7d,
                    "direction":       direction,
                    "sufficient_data": sufficient,
                })

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df.to_parquet(OUTPUT_FILE, index=False)
    print(f"\nWrote {len(df):,} rows → {OUTPUT_FILE.relative_to(ROOT)}")

    # ── Diagnostics ───────────────────────────────────────────────────────────
    print("\n=== NARR DISTRIBUTION BY VARIANT (sufficient_data rows only) ===")
    dense = df[df["sufficient_data"]]
    for variant in [v.name for v in VARIANTS]:
        sub = dense[dense["variant"] == variant]["narr"]
        cfg = next(v for v in VARIANTS if v.name == variant)
        print(f"\n  {variant}  (floor={cfg.floor})")
        print(f"    min={sub.min()}  p10={sub.quantile(0.1):.0f}  "
              f"p25={sub.quantile(0.25):.0f}  median={sub.median():.0f}  "
              f"p75={sub.quantile(0.75):.0f}  p90={sub.quantile(0.9):.0f}  max={sub.max()}")

    print("\n=== STATE DISTRIBUTION BY VARIANT (sufficient_data rows only) ===")
    for variant in [v.name for v in VARIANTS]:
        sub = dense[dense["variant"] == variant]
        dist = sub["state"].value_counts()
        print(f"\n  {variant}")
        for state, n in dist.items():
            pct = n / len(sub) * 100
            print(f"    {state:<20} {n:>5}  ({pct:.1f}%)")

    print("\n=== SUFFICIENT-DATA COVERAGE BY TICKER ===")
    coverage = (df[df["variant"] == "baseline"]
                .groupby("ticker")
                .agg(total=("date", "count"), sufficient=("sufficient_data", "sum"))
                .assign(pct=lambda x: (x["sufficient"] / x["total"] * 100).round(1))
                .sort_values("sufficient", ascending=False))
    print(coverage.to_string())

    # ── Daily actor diff (today vs prior trading day) ───────────────────────
    print("\n=== BUILDING DAILY ACTOR DIFF ===")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "build_actor_diff.py")],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.strip():
                    print(f"  {line.strip()}")
        else:
            print(f"  actor diff failed (exit {result.returncode}): {result.stderr[:200]}")
    except Exception as e:
        print(f"  actor diff failed: {e}")

    # ── Confidence decomposition ────────────────────────────────────────────
    print("\n=== BUILDING CONFIDENCE DECOMPOSITION ===")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "build_confidence_decomposition.py")],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.strip():
                    print(f"  {line.strip()}")
        else:
            print(f"  confidence build failed (exit {result.returncode}): {result.stderr[:200]}")
    except Exception as e:
        print(f"  confidence build failed: {e}")

    # ── Replay history export ───────────────────────────────────────────────
    print("\n=== EXPORTING REPLAY HISTORY ===")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "build_replay_history.py")],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.strip():
                    print(f"  {line.strip()}")
        else:
            print(f"  replay history failed (exit {result.returncode}): {result.stderr[:200]}")
    except Exception as e:
        print(f"  replay history failed: {e}")

    # ── L1 Field Instrumentation (V1) ───────────────────────────────────────
    # Runs alongside narr — does not replace it. Validation period 2-3 weeks.
    print("\n=== EMBEDDING NEW EVENTS (incremental) ===")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "embed_events.py")],
            capture_output=True, text=True, timeout=900,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                s = line.strip()
                if s and ("cached" in s or "embedded" in s or "to embed" in s or "wrote" in s):
                    print(f"  {s}")
        else:
            print(f"  embedding failed (exit {result.returncode}): {result.stderr[:200]}")
    except Exception as e:
        print(f"  embedding failed: {e}")

    print("\n=== BUILDING FIELD INSTRUMENTATION (L1 V1) ===")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "build_field_instrumentation.py")],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                s = line.strip()
                if s and ("processed" in s or "wrote" in s or "events loaded" in s):
                    print(f"  {s}")
        else:
            print(f"  field instrumentation failed (exit {result.returncode}): {result.stderr[:200]}")
    except Exception as e:
        print(f"  field instrumentation failed: {e}")

    # ── Cluster lineage (F-002) ───────────────────────────────────────────
    # Stable theme IDs across days via centroid matching. Labels are cached
    # and only LLM-relabeled when cluster membership churns ≥40%. Daily
    # incremental: ~5-10 new clusters at most, ~$0.005/day in LLM cost.
    print("\n=== BUILDING CLUSTER LINEAGE (F-002) ===")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "build_cluster_lineage.py")],
            capture_output=True, text=True, timeout=1200,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                s = line.strip()
                if s and ("wrote" in s or "unique stable" in s or "lifecycle events" in s
                         or s.startswith(("born", "persisted", "drift", "merge", "split", "retired", "large_drift"))):
                    print(f"  {s}")
        else:
            print(f"  cluster lineage failed (exit {result.returncode}): {result.stderr[:200]}")
    except Exception as e:
        print(f"  cluster lineage failed: {e}")

    # ── Daily totals for /architecture L0 + L1 panels ─────────────────────
    # All three are thin shapers that read existing artifacts (the JSONL
    # corpus + field_instrumentation.parquet + cluster_lineage.parquet
    # + cluster_members.parquet). Fast and idempotent.
    print("\n=== BUILDING EVENTS-DAILY + FIELD-ACTOR-HISTORY + NARRATIVE-CLUSTERS (/architecture L0 + L1) ===")
    for script_name in (
        "build_events_daily.py",
        "build_field_actor_history.py",
        "build_narrative_clusters.py",
        "build_storm_trace.py",
    ):
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, str(Path(__file__).parent / script_name)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    s = line.strip()
                    if s and ("wrote" in s or "actors:" in s or "events" in s):
                        print(f"  [{script_name}] {s}")
            else:
                print(f"  {script_name} failed (exit {result.returncode}): {result.stderr[:200]}")
        except Exception as e:
            print(f"  {script_name} failed: {e}")


if __name__ == "__main__":
    main()
