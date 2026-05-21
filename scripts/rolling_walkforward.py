"""
Rolling walk-forward primitive (axis-agnostic).

The same machinery serves F-007 V2 (rolling region calibration) and F-006 #6
(persistence-as-prior-weight validation). Input shape contract:

    obs: DataFrame with
      - 'date'   (Timestamp)
      - <group_col>  (the grouping key — region_id, persistence_bucket, etc.)
      - one or more <outcome_col> columns: 0/1 hit, NaN where outcome unobserved

The primitive produces a fold table (group × fold × outcome) plus a per-group
stability summary. It is deliberately ignorant of what a "group" means.

Fold scheme: expanding-window. Fold k's train slice is everything strictly
before its test slice. Test slices are non-overlapping, equal-sized in count
of unique dates, covering (1 - min_train_frac) of the corpus split into
n_folds slices. The earliest training cut respects `min_train_frac` so the
first prediction always sees at least that much history.

This script has no main(); it is imported by the per-axis callers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Fold:
    fold_id:    int            # 1-based
    test_start: pd.Timestamp   # inclusive
    test_end:   pd.Timestamp   # inclusive


def expanding_window_folds(
    dates: pd.Series,
    n_folds: int = 3,
    min_train_frac: float = 0.50,
) -> list[Fold]:
    """
    Split the unique dates in `dates` into `n_folds` non-overlapping test
    slices, leaving the first `min_train_frac` of dates as the initial train
    floor. Returns one (test_start, test_end) per fold.
    """
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    if not 0.0 < min_train_frac < 1.0:
        raise ValueError("min_train_frac must be in (0, 1)")

    sorted_dates = pd.Series(dates.dropna().unique()).sort_values().reset_index(drop=True)
    n = len(sorted_dates)
    if n < n_folds + 2:
        raise ValueError(
            f"corpus too small: {n} unique dates, need at least {n_folds + 2}"
        )
    min_train_n = max(1, int(n * min_train_frac))
    remaining   = n - min_train_n
    if remaining < n_folds:
        raise ValueError(
            f"corpus too small for {n_folds} folds: "
            f"{remaining} unique dates after the train floor"
        )

    test_size = remaining // n_folds
    folds: list[Fold] = []
    for f in range(n_folds):
        test_start_idx = min_train_n + f * test_size
        # Last fold absorbs the remainder
        test_end_idx = (
            min_train_n + (f + 1) * test_size - 1
            if f < n_folds - 1
            else n - 1
        )
        folds.append(Fold(
            fold_id    = f + 1,
            test_start = sorted_dates.iloc[test_start_idx],
            test_end   = sorted_dates.iloc[test_end_idx],
        ))
    return folds


def rolling_hit_rate(
    obs: pd.DataFrame,
    group_col: str,
    outcome_cols: list[str],
    n_folds: int = 3,
    min_train_frac: float = 0.50,
) -> pd.DataFrame:
    """
    For each (group, fold, outcome), compute n_obs + hit_rate in the test slice.

    Returns a long-form DataFrame with columns:
        fold | test_start | test_end | group | outcome | n_obs | hit_rate

    Hit rate is the mean of the (already 0/1) outcome column over non-NaN rows
    in the test slice. NaN rows are excluded from both numerator and denominator.
    """
    if "date" not in obs.columns:
        raise ValueError("obs must have a 'date' column")
    missing_outcome = [c for c in outcome_cols if c not in obs.columns]
    if missing_outcome:
        raise ValueError(f"missing outcome columns: {missing_outcome}")
    if group_col not in obs.columns:
        raise ValueError(f"missing group column: {group_col}")

    folds = expanding_window_folds(obs["date"], n_folds, min_train_frac)
    rows: list[dict] = []
    for fold in folds:
        test_slice = obs[(obs["date"] >= fold.test_start) & (obs["date"] <= fold.test_end)]
        if test_slice.empty:
            continue
        for group_val, grp in test_slice.groupby(group_col):
            for outcome in outcome_cols:
                non_null = grp[outcome].dropna()
                rows.append({
                    "fold":       fold.fold_id,
                    "test_start": fold.test_start,
                    "test_end":   fold.test_end,
                    "group":      group_val,
                    "outcome":    outcome,
                    "n_obs":      int(len(non_null)),
                    "hit_rate":   float(non_null.mean()) if len(non_null) else None,
                })
    return pd.DataFrame(rows)


def stability_score(
    rolling_df: pd.DataFrame,
    *,
    min_obs_per_fold: int = 1,
) -> pd.DataFrame:
    """
    Per (group, outcome): aggregate fold-level hit rates into a stability view.

    Returns columns:
        group | outcome | n_folds_with_data | total_n_obs |
        mean_hit | std_hit | range_hit | min_hit | max_hit

    `min_obs_per_fold` filters out fold cells whose n_obs is too small to trust
    individually (they don't enter the per-group aggregate).
    """
    df = rolling_df[
        (rolling_df["n_obs"] >= min_obs_per_fold)
        & rolling_df["hit_rate"].notna()
    ]
    if df.empty:
        return pd.DataFrame(columns=[
            "group", "outcome",
            "n_folds_with_data", "total_n_obs",
            "mean_hit", "std_hit", "range_hit", "min_hit", "max_hit",
        ])
    g = df.groupby(["group", "outcome"]).agg(
        n_folds_with_data = ("hit_rate", "count"),
        total_n_obs       = ("n_obs",    "sum"),
        mean_hit          = ("hit_rate", "mean"),
        std_hit           = ("hit_rate", "std"),
        min_hit           = ("hit_rate", "min"),
        max_hit           = ("hit_rate", "max"),
    ).reset_index()
    g["range_hit"] = g["max_hit"] - g["min_hit"]
    g["std_hit"]   = g["std_hit"].fillna(0.0)
    return g[[
        "group", "outcome",
        "n_folds_with_data", "total_n_obs",
        "mean_hit", "std_hit", "range_hit", "min_hit", "max_hit",
    ]]


def aggregate_rolling(
    rolling_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Per (fold, outcome): pool across all groups to get a corpus-wide read.

    Useful when individual groups are too small to interpret fold-by-fold and
    the corpus-wide trajectory across folds IS the headline. (This is the
    honest answer to "are public-region hit rates stable across folds?" when
    per-region per-fold cells are n=1-2.)
    """
    df = rolling_df.dropna(subset=["hit_rate"])
    if df.empty:
        return pd.DataFrame(columns=[
            "fold", "test_start", "test_end", "outcome", "n_obs", "hit_rate",
        ])
    # Reconstitute counts: total successes / total obs across groups for the cell.
    df = df.assign(
        n_hits = (df["hit_rate"] * df["n_obs"]).round().astype(int),
    )
    grouped = df.groupby(
        ["fold", "test_start", "test_end", "outcome"]
    ).agg(
        n_hits = ("n_hits", "sum"),
        n_obs  = ("n_obs",  "sum"),
    ).reset_index()
    grouped["hit_rate"] = grouped["n_hits"] / grouped["n_obs"].replace(0, np.nan)
    return grouped[["fold", "test_start", "test_end", "outcome", "n_obs", "hit_rate"]]


# ─── presentation helpers ──────────────────────────────────────────────────

def fmt_pct(v: float | None, places: int = 1) -> str:
    """Render a hit rate as a percent, NaN-safe."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "  na "
    return f"{v*100:.{places}f}%"


def fold_table_lines(
    rolling_df: pd.DataFrame,
    title: str,
    outcome_cols: list[str],
) -> list[str]:
    """Build a printable per-fold aggregate table."""
    agg = aggregate_rolling(rolling_df)
    out = [f"-- {title} --"]
    header = f"{'fold':<6}  {'test_range':<28}  " + "  ".join(
        f"{c:>14}" for c in outcome_cols
    )
    out.append(header)
    for fold_id in sorted(agg["fold"].unique()):
        cells = []
        rng = ""
        for o in outcome_cols:
            row = agg[(agg["fold"] == fold_id) & (agg["outcome"] == o)]
            if row.empty:
                cells.append(f"{'  na':>14}")
                continue
            r = row.iloc[0]
            if not rng:
                rng = f"{r.test_start.date()} -> {r.test_end.date()}"
            cells.append(f"{fmt_pct(r.hit_rate):>9} (n={int(r.n_obs):>3})")
        out.append(f"{fold_id:<6}  {rng:<28}  " + "  ".join(cells))
    return out
