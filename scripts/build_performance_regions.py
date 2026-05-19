#!/usr/bin/env python3
"""
build_performance_regions.py  —  F-007 V1, step 1

Joins F-006 expectation_versions with realized price data to produce a
per-observation table for region calibration:

  region_id = sha("theme|sign"); see below
  For each (date, ticker, theme_id, direction_sign) attachment,
  compute forward 5D / 10D / 20D relative-to-QQQ returns and a
  direction-hit flag per horizon.

The hit flag is direction-aligned:
  - direction_sign = +1 → hit if rel_forward > 0
  - direction_sign = -1 → hit if rel_forward < 0
  - direction_sign =  0 → hit undefined (excluded from hit-rate stats
                                          but kept in the observation
                                          table)

Walk-forward discipline: each observation uses ONLY information
available on its observation date. Future returns are NOT used to
revise the attachment — the prediction was the prediction.

Reads:
  data/derived/expectation_versions.parquet
  data/derived/cluster_labels.json
  data/derived/prices/{TICKER}.parquet
  data/derived/prices/QQQ.parquet

Writes:
  data/derived/performance_regions.parquet
    one row per (date, ticker, theme, direction_sign):
      date, ticker, theme_id, theme_label, direction_sign,
      conviction, rel_5d, rel_10d, rel_20d,
      hit_5d, hit_10d, hit_20d,
      fold_5d, fold_10d, fold_20d, region_id

Usage:
  source venv/bin/activate && python scripts/build_performance_regions.py
"""

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"

VER_PATH    = ROOT / "data" / "derived" / "expectation_versions.parquet"
LABELS_PATH = ROOT / "data" / "derived" / "cluster_labels.json"
PRICES_DIR  = ROOT / "data" / "derived" / "prices"
BENCHMARK   = "QQQ"
OUT_PARQ    = ROOT / "data" / "derived" / "performance_regions.parquet"

HORIZONS = [5, 10, 20]


def region_id(theme_id: str, sign: int) -> str:
    s = f"{theme_id}::{sign}"
    return "reg-" + hashlib.sha1(s.encode()).hexdigest()[:10]


def load_price_series(ticker: str) -> pd.DataFrame | None:
    """Returns a DataFrame indexed by date (sorted) with 'close' column."""
    p = PRICES_DIR / f"{ticker}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df = df.rename(columns={"timestamp": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").drop_duplicates("date", keep="last")
    df = df[["date", "close"]].dropna()
    return df.set_index("date")


def forward_return(close_idx: pd.DataFrame, d: dt.date, n: int) -> float | None:
    """(close[d+n] - close[d]) / close[d] using TRADING days available in the index."""
    if d not in close_idx.index:
        return None
    dates = close_idx.index.tolist()
    try:
        i = dates.index(d)
    except ValueError:
        return None
    j = i + n
    if j >= len(dates):
        return None
    p0 = float(close_idx.iloc[i]["close"])
    pN = float(close_idx.iloc[j]["close"])
    if p0 <= 0:
        return None
    return (pN - p0) / p0


def main():
    # ── Inputs ──────────────────────────────────────────────────────────────
    if not VER_PATH.exists():
        sys.exit(f"Missing {VER_PATH} — run build_expectation_lifecycle.py first.")
    labels = json.loads(LABELS_PATH.read_text()) if LABELS_PATH.exists() else {}

    print("  loading expectation_versions…")
    ver = pd.read_parquet(VER_PATH)
    ver["date"] = pd.to_datetime(ver["date"]).dt.date
    print(f"    {len(ver):,} rows · {ver['ticker'].nunique()} tickers · {ver['stable_cluster_id'].nunique()} themes")

    print(f"  loading benchmark {BENCHMARK}…")
    bench = load_price_series(BENCHMARK)
    if bench is None:
        sys.exit(f"Missing benchmark prices: {PRICES_DIR / f'{BENCHMARK}.parquet'}")
    print(f"    {len(bench)} trading days")

    # Cache per-ticker price series so we touch each parquet once
    price_cache: dict[str, pd.DataFrame | None] = {}

    def get_prices(tk: str):
        if tk not in price_cache:
            price_cache[tk] = load_price_series(tk)
        return price_cache[tk]

    # Define walk-forward fold edges per horizon: non-overlapping windows of
    # length N starting at the earliest date with any expectation. Each
    # observation gets a fold_id (which N-day bucket its observation date
    # falls into).
    first_date = ver["date"].min()
    last_date  = ver["date"].max()
    print(f"  fold-anchor first L2 date: {first_date}")

    def fold_id_for(d: dt.date, n: int) -> int:
        return (d - first_date).days // n

    # ── Build observations ──────────────────────────────────────────────────
    rows: list[dict] = []
    skipped_no_price = 0
    skipped_no_window: dict[int, int] = {n: 0 for n in HORIZONS}
    for _, r in ver.iterrows():
        d = r["date"]
        tk = r["ticker"]
        sign = int(r["direction_sign"])

        ticker_prices = get_prices(tk)
        if ticker_prices is None:
            skipped_no_price += 1
            continue

        # Compute forward returns at each horizon
        rels: dict[int, float | None] = {}
        for n in HORIZONS:
            fr_t = forward_return(ticker_prices, d, n)
            fr_b = forward_return(bench,        d, n)
            if fr_t is None or fr_b is None:
                rels[n] = None
                skipped_no_window[n] += 1
            else:
                rels[n] = fr_t - fr_b  # actor minus benchmark

        # Hit per horizon
        hits: dict[int, int | None] = {}
        for n in HORIZONS:
            rel = rels[n]
            if rel is None or sign == 0:
                hits[n] = None
            else:
                hits[n] = 1 if (rel > 0 and sign > 0) or (rel < 0 and sign < 0) else 0

        theme_id = r["stable_cluster_id"]
        theme_label = (labels.get(theme_id) or {}).get("label") or ""

        rows.append({
            "date":             d.isoformat(),
            "ticker":           tk,
            "theme_id":         theme_id,
            "theme_label":      theme_label,
            "direction_sign":   sign,
            "conviction":       float(r.get("conviction") or 0.0),
            "rel_5d":           rels[5],
            "rel_10d":          rels[10],
            "rel_20d":          rels[20],
            "hit_5d":           hits[5],
            "hit_10d":          hits[10],
            "hit_20d":          hits[20],
            "fold_5d":          fold_id_for(d, 5),
            "fold_10d":         fold_id_for(d, 10),
            "fold_20d":         fold_id_for(d, 20),
            "region_id":        region_id(theme_id, sign),
        })

    print(f"  observations: {len(rows):,}")
    if skipped_no_price:
        print(f"  skipped (no price data): {skipped_no_price}")
    for n in HORIZONS:
        if skipped_no_window[n]:
            print(f"  no {n}D forward window: {skipped_no_window[n]}")

    df = pd.DataFrame(rows)
    OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQ, index=False)
    print(f"\n  wrote {OUT_PARQ} ({len(df):,} rows)")

    # ── Quick sanity summary ────────────────────────────────────────────────
    print()
    print("  ─── SAMPLE REGIONS ────────────────────────────────────────")
    grp = df[df["direction_sign"] != 0].groupby(["theme_label", "direction_sign"])
    agg = grp.agg(
        n_obs=("date", "count"),
        n_unique_tickers=("ticker", "nunique"),
        hit_5d=("hit_5d", "mean"),
        hit_10d=("hit_10d", "mean"),
        hit_20d=("hit_20d", "mean"),
    ).reset_index()
    agg = agg.sort_values("n_obs", ascending=False).head(10)
    print(f"  {'theme':<55} {'sign':>4} {'n':>4} {'5d':>5} {'10d':>5} {'20d':>5}")
    for _, r in agg.iterrows():
        lbl = (r["theme_label"] or "untagged")[:55]
        sign_lbl = "↑" if r["direction_sign"] > 0 else "↓" if r["direction_sign"] < 0 else "─"
        h5  = f"{r['hit_5d']:.0%}"  if pd.notna(r['hit_5d'])  else " n/a "
        h10 = f"{r['hit_10d']:.0%}" if pd.notna(r['hit_10d']) else " n/a "
        h20 = f"{r['hit_20d']:.0%}" if pd.notna(r['hit_20d']) else " n/a "
        print(f"  {lbl:<55} {sign_lbl:>4} {int(r['n_obs']):>4} {h5:>5} {h10:>5} {h20:>5}")


if __name__ == "__main__":
    main()
