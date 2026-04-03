#!/usr/bin/env python3
"""
Fetch and store historical price data for all tracked actors + benchmarks.
Stores as parquet in data/derived/prices/.

Usage:
    python scripts/fetch_prices.py              # fetch all tickers, 6mo
    python scripts/fetch_prices.py --period 1y  # extend lookback
    python scripts/fetch_prices.py --tickers MSFT NVDA  # specific tickers only
"""

import argparse
import sys
from pathlib import Path
from datetime import date

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import ACTOR_ALIASES

PRICES_DIR = Path("data/derived/prices")
PRICES_DIR.mkdir(parents=True, exist_ok=True)

# Benchmarks always fetched for relative return context
BENCHMARKS = ["SPY", "QQQ", "IWM"]

# Skip private actors that have no tradeable ticker
PRIVATE = {"OPENAI", "ANTHROPIC", "SKHX", "SAMSNG"}


def fetchable_tickers() -> list[str]:
    return [t for t in ACTOR_ALIASES if t not in PRIVATE]


def fetch_one(ticker: str, period: str = "6mo") -> pd.DataFrame | None:
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval="1d")
        if df.empty:
            print(f"  [skip] {ticker} — no data returned")
            return None

        df = df.reset_index()
        df = df.rename(columns={"Date": "timestamp", "Close": "close", "Volume": "volume"})
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.date
        df["ticker"] = ticker
        df = df[["ticker", "timestamp", "close", "volume"]].copy()

        # Returns
        df = df.sort_values("timestamp").reset_index(drop=True)
        df["return_1d"]  = df["close"].pct_change(1)
        df["return_5d"]  = df["close"].pct_change(5)
        df["return_20d"] = df["close"].pct_change(20)

        return df

    except Exception as e:
        print(f"  [error] {ticker}: {e}")
        return None


def save(df: pd.DataFrame, ticker: str) -> None:
    path = PRICES_DIR / f"{ticker}.parquet"
    df.to_parquet(path, index=False)
    latest = df["timestamp"].max()
    print(f"  [ok] {ticker} — {len(df)} rows → {latest}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="6mo", help="yfinance period (6mo, 1y, 2y)")
    parser.add_argument("--tickers", nargs="+", help="specific tickers to fetch")
    args = parser.parse_args()

    tickers = args.tickers if args.tickers else fetchable_tickers() + BENCHMARKS
    tickers = list(dict.fromkeys(tickers))  # dedupe, preserve order

    print(f"Fetching {len(tickers)} tickers  period={args.period}")
    print("─" * 50)

    ok, skipped = 0, 0
    for ticker in tickers:
        df = fetch_one(ticker, period=args.period)
        if df is not None:
            save(df, ticker)
            ok += 1
        else:
            skipped += 1

    print("─" * 50)
    print(f"Done. {ok} fetched, {skipped} skipped.")
    print(f"Output: {PRICES_DIR.resolve()}/")


if __name__ == "__main__":
    main()
