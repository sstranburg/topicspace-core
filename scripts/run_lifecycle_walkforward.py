"""
F-006 V2 #4 - per-expectation walk-forward.

Does an entity's lifecycle character predict its directional forward return?

Inputs:
    data/derived/expectation_versions.parquet         (entity-day rows)
    data/derived/expectation_lifecycle_events.parquet (typed events per entity)
    data/derived/prices/<TICKER>.parquet              (close, return_1d/5d/20d)

For each (entity_id, date_t) version row we compute, as-of date_t:
    - n_versions_to_date      (entity age in observed days)
    - n_strengthened_to_date  (cumulative strengthened events at or before t)
    - n_weakened_to_date      (cumulative weakened events at or before t)
    - lifecycle_score         = n_strengthened - n_weakened
    - direction_sign          (entity's signed direction)
    - latest_conviction       (the version's conviction value)

We join the row's ticker forward return at horizons 5 / 10 / 20 trading days,
then form the *directional* return = direction_sign * fwd_return so that
positive numbers mean "the entity was right."

We pick a chronological split date that puts ~70% of rows in train and ~30%
in test, summarize directional returns by lifecycle bucket in each slice,
and print whether the train ordering survives in test.

Outputs:
    data/derived/lifecycle_walkforward.parquet          (one row per scored entity-date)
    data/derived/lifecycle_walkforward_summary.txt      (human-readable verdict)

This is V1 of V2: it MEASURES. It does not yet act. F-006 #6 (use persistence
as an L1 prior weight) is the V2-acts step and only gets built if the
findings here justify it.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd


ROOT       = Path(__file__).resolve().parents[1]
DERIVED    = ROOT / "data" / "derived"
PRICES_DIR = DERIVED / "prices"
OUT_PARQ   = DERIVED / "lifecycle_walkforward.parquet"
OUT_TXT    = DERIVED / "lifecycle_walkforward_summary.txt"

HORIZONS              = [5, 10, 20]   # trading days
TRAIN_FRACTION        = 0.70
MIN_VERSIONS_FOR_ROW  = 2             # don't score newborns
PERSISTENCE_BUCKETS   = [
    ("just_born",   1, 1),
    ("emerging",    2, 2),
    ("forming",     3, 4),
    ("persistent",  5, 9),
    ("entrenched", 10, 9999),
]
LIFECYCLE_BUCKETS = [
    ("strengthened_net", lambda s: s > 0),
    ("weakened_net",     lambda s: s < 0),
    ("neutral",          lambda s: s == 0),
]


# ─── data loading ──────────────────────────────────────────────────────────

def load_versions() -> pd.DataFrame:
    df = pd.read_parquet(DERIVED / "expectation_versions.parquet")
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["entity_id", "date"]).reset_index(drop=True)


def load_events() -> pd.DataFrame:
    df = pd.read_parquet(DERIVED / "expectation_lifecycle_events.parquet")
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["entity_id", "date"]).reset_index(drop=True)


def load_forward_returns() -> dict[str, pd.DataFrame]:
    """
    Returns {ticker: DataFrame(date -> fwd_5d, fwd_10d, fwd_20d)}.

    Forward return at date t over h days = (close[t+h] - close[t]) / close[t].
    Computed by shifting the precomputed trailing returns.
    """
    out: dict[str, pd.DataFrame] = {}
    for f in sorted(PRICES_DIR.glob("*.parquet")):
        df = pd.read_parquet(f)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        # Compute forward returns from close prices directly (no precision loss).
        for h in HORIZONS:
            df[f"fwd_{h}d"] = df["close"].shift(-h) / df["close"] - 1.0
        out[df["ticker"].iloc[0]] = df[["timestamp"] + [f"fwd_{h}d" for h in HORIZONS]].rename(
            columns={"timestamp": "date"}
        )
    return out


# ─── feature build ─────────────────────────────────────────────────────────

def build_features(versions: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """For each version row, compute cumulative lifecycle counts as-of the row's date."""
    # Pre-filter events to strengthened / weakened only (the directional signal).
    sw_events = events[events["event_type"].isin(["strengthened", "weakened"])].copy()
    sw_events["is_strengthened"] = (sw_events["event_type"] == "strengthened").astype(int)
    sw_events["is_weakened"]     = (sw_events["event_type"] == "weakened").astype(int)

    # For an as-of join we sort both sides by date and use merge_asof per entity.
    feature_rows: list[pd.DataFrame] = []
    for entity_id, ver_grp in versions.groupby("entity_id"):
        ver_grp = ver_grp.sort_values("date").reset_index(drop=True)
        # cumulative n_versions = row index within the entity's history (1-based)
        ver_grp["n_versions_to_date"] = np.arange(1, len(ver_grp) + 1)

        ev_grp = sw_events[sw_events["entity_id"] == entity_id].sort_values("date")
        if ev_grp.empty:
            ver_grp["n_strengthened_to_date"] = 0
            ver_grp["n_weakened_to_date"]     = 0
        else:
            cum_str = ev_grp["is_strengthened"].cumsum().rename("n_strengthened_to_date")
            cum_wkn = ev_grp["is_weakened"].cumsum().rename("n_weakened_to_date")
            ev_cum  = pd.concat([ev_grp[["date"]].reset_index(drop=True),
                                 cum_str.reset_index(drop=True),
                                 cum_wkn.reset_index(drop=True)], axis=1)
            ver_grp = pd.merge_asof(
                ver_grp.sort_values("date"),
                ev_cum.sort_values("date"),
                on="date", direction="backward",
            )
            ver_grp[["n_strengthened_to_date", "n_weakened_to_date"]] = ver_grp[
                ["n_strengthened_to_date", "n_weakened_to_date"]
            ].fillna(0).astype(int)
        feature_rows.append(ver_grp)

    out = pd.concat(feature_rows, ignore_index=True)
    out["lifecycle_score"] = out["n_strengthened_to_date"] - out["n_weakened_to_date"]
    return out


def attach_forward_returns(
    features: pd.DataFrame,
    fwd_returns: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Join (ticker, date) -> fwd_5d / fwd_10d / fwd_20d."""
    out_parts: list[pd.DataFrame] = []
    for ticker, fwd in fwd_returns.items():
        sub = features[features["ticker"] == ticker]
        if sub.empty:
            continue
        merged = sub.merge(fwd, on="date", how="left")
        out_parts.append(merged)
    out = pd.concat(out_parts, ignore_index=True) if out_parts else features.iloc[0:0].copy()
    # Directional return = direction_sign * fwd_return (positive = entity was right).
    # Skip neutral entities (direction_sign == 0) - they have no directional bet.
    for h in HORIZONS:
        out[f"dir_fwd_{h}d"] = out["direction_sign"] * out[f"fwd_{h}d"]
    return out


# ─── walk-forward summary ──────────────────────────────────────────────────

def pick_split_date(features: pd.DataFrame, frac: float) -> pd.Timestamp:
    """Return a split date that puts ~`frac` of rows in train."""
    dates = features["date"].sort_values().reset_index(drop=True)
    idx = int(len(dates) * frac)
    return dates.iloc[min(idx, len(dates) - 1)]


def persistence_bucket(n_versions: int) -> str:
    for name, lo, hi in PERSISTENCE_BUCKETS:
        if lo <= n_versions <= hi:
            return name
    return "unknown"


def lifecycle_bucket(score: int) -> str:
    for name, pred in LIFECYCLE_BUCKETS:
        if pred(score):
            return name
    return "unknown"


def summarize_by_bucket(
    df: pd.DataFrame, bucket_col: str, horizon: int,
) -> pd.DataFrame:
    """Per-bucket count + mean + std of directional forward return."""
    col = f"dir_fwd_{horizon}d"
    sub = df.dropna(subset=[col])
    if sub.empty:
        return pd.DataFrame(columns=[bucket_col, "n", f"mean_{horizon}d", f"std_{horizon}d"])
    g = sub.groupby(bucket_col)[col].agg(["count", "mean", "std"]).reset_index()
    g.columns = [bucket_col, "n", f"mean_{horizon}d", f"std_{horizon}d"]
    return g


def fmt_pct(x: float | None, places: int = 2) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "  na "
    return f"{x*100:+.{places}f}%"


# ─── main ──────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== F-006 V2 #4: per-expectation walk-forward ===")
    print(f"loaded from {DERIVED}")

    versions    = load_versions()
    events      = load_events()
    fwd_returns = load_forward_returns()
    print(f"  versions: {len(versions):,}  entities: {versions['entity_id'].nunique():,}")
    print(f"  events:   {len(events):,}    "
          f"({events['event_type'].value_counts().to_dict()})")
    print(f"  prices:   {len(fwd_returns)} tickers")

    feats = build_features(versions, events)
    feats = attach_forward_returns(feats, fwd_returns)

    # Filter to rows we'd actually score: ≥ MIN_VERSIONS, non-neutral direction,
    # at least one horizon's forward return defined.
    scored = feats[
        (feats["n_versions_to_date"] >= MIN_VERSIONS_FOR_ROW)
        & (feats["direction_sign"] != 0)
        & feats[[f"dir_fwd_{h}d" for h in HORIZONS]].notna().any(axis=1)
    ].copy()
    print(f"\n  scoreable rows: {len(scored):,}  "
          f"(after dropping newborns + neutral direction + no-fwd-return)")

    scored["persistence_bucket"] = scored["n_versions_to_date"].apply(persistence_bucket)
    scored["lifecycle_bucket"]   = scored["lifecycle_score"].apply(lifecycle_bucket)

    split_date = pick_split_date(scored, TRAIN_FRACTION)
    train = scored[scored["date"] <  split_date].copy()
    test  = scored[scored["date"] >= split_date].copy()
    print(f"\n  walk-forward split: {split_date.date()}")
    print(f"  train rows: {len(train):,}  test rows: {len(test):,}")

    lines: list[str] = []
    def w(s: str = ""):
        print(s); lines.append(s)

    w("\n" + "=" * 78)
    w("F-006 V2 #4 - per-expectation walk-forward summary")
    w("=" * 78)
    w(f"as-of: {dt.date.today().isoformat()}")
    w(f"split_date: {split_date.date()}   "
      f"train={len(train):,}   test={len(test):,}")
    w(f"horizons: {HORIZONS} trading days")
    w(f"min_versions_for_row: {MIN_VERSIONS_FOR_ROW}   "
      f"(skips entities with only one observation)")

    # --- by persistence bucket
    for slice_name, slice_df in [("TRAIN", train), ("TEST", test)]:
        w("")
        w(f"-- by persistence bucket [{slice_name}] -----------------------------------")
        w(f"{'bucket':<14}  {'n':>5}  " + "  ".join(
            f"{f'mean_{h}d':>10}" for h in HORIZONS))
        for name, _, _ in PERSISTENCE_BUCKETS:
            sub = slice_df[slice_df["persistence_bucket"] == name]
            if sub.empty:
                continue
            cells = []
            for h in HORIZONS:
                col = f"dir_fwd_{h}d"
                m = sub[col].dropna().mean()
                cells.append(fmt_pct(m if not np.isnan(m) else None, places=2))
            w(f"{name:<14}  {len(sub):>5}  " + "  ".join(f"{c:>10}" for c in cells))

    # --- by lifecycle bucket
    for slice_name, slice_df in [("TRAIN", train), ("TEST", test)]:
        w("")
        w(f"-- by lifecycle bucket [{slice_name}] ------------------------------------")
        w(f"{'bucket':<18}  {'n':>5}  " + "  ".join(
            f"{f'mean_{h}d':>10}" for h in HORIZONS))
        for name, _ in LIFECYCLE_BUCKETS:
            sub = slice_df[slice_df["lifecycle_bucket"] == name]
            if sub.empty:
                continue
            cells = []
            for h in HORIZONS:
                col = f"dir_fwd_{h}d"
                m = sub[col].dropna().mean()
                cells.append(fmt_pct(m if not np.isnan(m) else None, places=2))
            w(f"{name:<18}  {len(sub):>5}  " + "  ".join(f"{c:>10}" for c in cells))

    # --- verdict
    w("")
    w("-- verdict ---------------------------------------------------------------")
    for h in HORIZONS:
        col = f"dir_fwd_{h}d"
        def bucket_mean(slice_df: pd.DataFrame, bucket: str) -> float | None:
            sub = slice_df[slice_df["persistence_bucket"] == bucket][col].dropna()
            return float(sub.mean()) if len(sub) else None

        # Strongest possible signal: most-persistent buckets vs least-persistent.
        train_persistent = bucket_mean(train, "persistent")
        train_entrenched = bucket_mean(train, "entrenched")
        train_emerging   = bucket_mean(train, "emerging")
        test_persistent  = bucket_mean(test,  "persistent")
        test_entrenched  = bucket_mean(test,  "entrenched")
        test_emerging    = bucket_mean(test,  "emerging")

        # "Persistence pays" = combined persistent+entrenched > emerging, in both slices.
        def safe_diff(a, b):
            if a is None or b is None: return None
            return a - b

        train_persistent_bundle = np.nanmean([
            v for v in [train_persistent, train_entrenched] if v is not None
        ]) if (train_persistent is not None or train_entrenched is not None) else None
        test_persistent_bundle = np.nanmean([
            v for v in [test_persistent, test_entrenched] if v is not None
        ]) if (test_persistent is not None or test_entrenched is not None) else None

        train_spread = safe_diff(train_persistent_bundle, train_emerging)
        test_spread  = safe_diff(test_persistent_bundle,  test_emerging)

        w(f"  horizon={h}d   "
          f"train_spread(persistent_bundle - emerging) = {fmt_pct(train_spread)}   "
          f"test_spread = {fmt_pct(test_spread)}")
        if train_spread is None or test_spread is None:
            w(f"    -> inconclusive (one slice empty for the comparison)")
        elif train_spread > 0 and test_spread > 0:
            w(f"    -> persistence PAID in both slices "
              f"(F-006 #6 worth scoping: use persistence as L1 prior weight)")
        elif train_spread > 0 and test_spread <= 0:
            w(f"    -> in-sample only; OUT-OF-SAMPLE INVERTED or flat. "
              f"Do NOT build F-006 #6 on this evidence.")
        elif train_spread <= 0:
            w(f"    -> no in-sample edge. Persistence does not predict at h={h}d.")

    w("")
    w("Honest reading guide:")
    w("  - All metrics are *directional* (sign(entity) * fwd_return). Positive means")
    w("    the entity's stated direction was confirmed by price.")
    w("  - These bucket means are small-sample. Treat splits with n<10 as ornamental.")
    w("  - Walk-forward is a single chronological split, not rolling. A rolling")
    w("    walk-forward (F-007 V2) is the next discipline tier.")
    w("  - 'persistent_bundle - emerging' is a back-of-envelope test of whether the")
    w("    persistence-as-prior-weight hypothesis (F-006 #6) is worth building.")
    w("    A clean positive spread in both slices = green light. Anything else = pause.")
    w("")

    OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(OUT_PARQ, index=False)
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_PARQ.relative_to(ROOT)}  ({len(scored):,} rows)")
    print(f"wrote {OUT_TXT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
