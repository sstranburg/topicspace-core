"""
Price analysis utilities — anchor price data to narrative events.

Usage:
    from src.price_analysis import load_prices, get_price_window, detect_price_move, relative_return
"""

from pathlib import Path
from functools import lru_cache

import pandas as pd

PRICES_DIR = Path("data/derived/prices")
BENCHMARKS = {"SPY", "QQQ", "IWM"}


@lru_cache(maxsize=64)
def load_prices(ticker: str) -> pd.DataFrame | None:
    path = PRICES_DIR / f"{ticker}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.date
    return df.sort_values("timestamp").reset_index(drop=True)


def get_price_window(
    ticker: str,
    event_date: str | pd.Timestamp,
    window: int = 5,
) -> pd.DataFrame | None:
    """Return rows within ±window calendar days of event_date."""
    df = load_prices(ticker)
    if df is None:
        return None

    event_date = pd.to_datetime(event_date).date()
    lo = event_date - pd.Timedelta(days=window).to_pytimedelta()
    hi = event_date + pd.Timedelta(days=window).to_pytimedelta()
    mask = (pd.to_datetime(df["timestamp"]).dt.date >= lo) & \
           (pd.to_datetime(df["timestamp"]).dt.date <= hi)

    return df[mask].copy()


def detect_price_move(
    ticker: str,
    event_date: str | pd.Timestamp,
    window: int = 5,
    threshold: float = 0.03,
) -> dict | None:
    """
    Detect whether a significant 1-day move occurred within window of event_date.

    Returns dict with timestamp + magnitude, or None if no move found.
    """
    window_df = get_price_window(ticker, event_date, window)
    if window_df is None or window_df.empty:
        return None

    window_df = window_df.dropna(subset=["return_1d"])
    moves = window_df[window_df["return_1d"].abs() >= threshold]
    if moves.empty:
        return None

    row = moves.iloc[0]
    return {
        "ticker": ticker,
        "event_date": str(event_date),
        "move_date": str(row["timestamp"]),
        "return_1d": round(row["return_1d"], 4),
        "close": round(row["close"], 2),
    }


def relative_return(
    ticker: str,
    event_date: str | pd.Timestamp,
    window: int = 5,
    benchmark: str = "SPY",
) -> dict | None:
    """
    Compute stock return vs benchmark over ±window days around event_date.

    Returns dict with stock_return, benchmark_return, relative_return.
    """
    stock_df = get_price_window(ticker, event_date, window)
    bench_df = get_price_window(benchmark, event_date, window)

    if stock_df is None or bench_df is None:
        return None
    if stock_df.empty or bench_df.empty:
        return None

    def window_return(df: pd.DataFrame) -> float | None:
        df = df.dropna(subset=["close"])
        if len(df) < 2:
            return None
        return (df.iloc[-1]["close"] - df.iloc[0]["close"]) / df.iloc[0]["close"]

    stock_ret = window_return(stock_df)
    bench_ret = window_return(bench_df)

    if stock_ret is None or bench_ret is None:
        return None

    return {
        "ticker": ticker,
        "benchmark": benchmark,
        "event_date": str(event_date),
        "window_days": window,
        "stock_return": round(stock_ret, 4),
        "benchmark_return": round(bench_ret, 4),
        "relative_return": round(stock_ret - bench_ret, 4),
    }
