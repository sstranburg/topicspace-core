"""
F-006 #6 rolling re-test: persistence-bucket rolling walk-forward.

Reads `data/derived/lifecycle_walkforward.parquet` (produced by
run_lifecycle_walkforward.py — one row per scored (entity, date) version
with persistence_bucket, lifecycle_score, dir_fwd_{5,10,20}d) and re-runs
the shared rolling primitive over persistence buckets.

This validates (or refutes) the single-split finding from F-006 V2 #4:
does the persistent_bundle - emerging spread survive 3 expanding-window
folds, or was the single-split positive read a regime artifact?

Outputs:
    data/derived/persistence_rolling_walkforward.parquet
    data/derived/persistence_rolling_walkforward_summary.txt
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rolling_walkforward import (
    aggregate_rolling,
    expanding_window_folds,
    fmt_pct,
    fold_table_lines,
    rolling_hit_rate,
    stability_score,
)


ROOT       = Path(__file__).resolve().parents[1]
DERIVED    = ROOT / "data" / "derived"
IN_PARQ    = DERIVED / "lifecycle_walkforward.parquet"
OUT_PARQ   = DERIVED / "persistence_rolling_walkforward.parquet"
OUT_TXT    = DERIVED / "persistence_rolling_walkforward_summary.txt"

HORIZONS              = [5, 10, 20]
N_FOLDS               = 3
MIN_TRAIN_FRACTION    = 0.50
STABILITY_RANGE_MAX   = 0.20   # bucket stable if hit_rate range across folds <= this
BUCKET_ORDER          = ["emerging", "forming", "persistent", "entrenched"]


def main() -> None:
    print("=== F-006 #6 rolling re-test: persistence bucket walk-forward ===")
    if not IN_PARQ.exists():
        raise SystemExit(
            f"missing {IN_PARQ}; run scripts/run_lifecycle_walkforward.py first"
        )

    df = pd.read_parquet(IN_PARQ)
    df["date"] = pd.to_datetime(df["date"])
    # Binarize directional returns into hit columns.
    for h in HORIZONS:
        col_in  = f"dir_fwd_{h}d"
        col_out = f"hit_{h}d"
        df[col_out] = np.where(df[col_in].notna(),
                               (df[col_in] > 0).astype(float),
                               np.nan)
    outcome_cols = [f"hit_{h}d" for h in HORIZONS]

    print(f"  scoreable rows: {len(df):,}  "
          f"unique buckets: {df['persistence_bucket'].nunique()}  "
          f"dates: {df['date'].nunique()}  "
          f"({df['date'].min().date()} -> {df['date'].max().date()})")
    print(f"  rows per bucket:")
    for b, n in df.groupby("persistence_bucket").size().to_dict().items():
        print(f"    {b:<12}  n={n}")

    folds = expanding_window_folds(df["date"], N_FOLDS, MIN_TRAIN_FRACTION)
    fold_str = "  ".join(
        f"f{f.fold_id}[{f.test_start.date()}->{f.test_end.date()}]" for f in folds
    )
    print(f"  folds: {fold_str}")

    rolling = rolling_hit_rate(
        df, "persistence_bucket", outcome_cols,
        n_folds=N_FOLDS, min_train_frac=MIN_TRAIN_FRACTION,
    )
    stability = stability_score(rolling)

    lines: list[str] = []
    def w(s: str = ""):
        print(s); lines.append(s)

    w("\n" + "=" * 78)
    w("F-006 #6 rolling re-test - persistence bucket walk-forward summary")
    w("=" * 78)
    w(f"as-of: {dt.date.today().isoformat()}")
    w(f"n_folds: {N_FOLDS}   min_train_frac: {MIN_TRAIN_FRACTION}")
    w(f"buckets: {BUCKET_ORDER}  (n_versions: 1 / 2 / 3-4 / 5-9 / 10+)")
    w(f"hit = (dir_fwd_{{5,10,20}}d > 0)   "
      f"i.e. the entity's stated direction was confirmed by price")
    w(f"stability threshold: range(hit_rate across folds) <= {STABILITY_RANGE_MAX}")

    # --- corpus-wide aggregate per fold (sanity check on regime)
    w("")
    w("\n".join(fold_table_lines(
        rolling, "ALL-BUCKETS aggregate hit rate per fold (regime read)",
        outcome_cols,
    )))

    # --- per-bucket per-fold (the real signal)
    w("")
    w("-- per-bucket per-fold hit rate -----------------------------------------")
    header = f"{'bucket':<14}  {'outcome':<8}  " + "  ".join(
        f"{'f' + str(f.fold_id):>16}" for f in folds
    )
    w(header)
    for bucket in BUCKET_ORDER:
        for o in outcome_cols:
            cells = []
            for f in folds:
                row = rolling[
                    (rolling["group"] == bucket)
                    & (rolling["outcome"] == o)
                    & (rolling["fold"] == f.fold_id)
                ]
                if row.empty:
                    cells.append(f"{'  na':>16}")
                    continue
                r = row.iloc[0]
                cells.append(f"{fmt_pct(r.hit_rate):>10} (n={int(r.n_obs):>3})")
            w(f"{bucket:<14}  {o:<8}  " + "  ".join(cells))

    # --- bucket stability summary
    w("")
    w("-- bucket stability summary (across folds) ------------------------------")
    w(f"{'bucket':<14}  {'outcome':<8}  {'mean':>8}  {'range':>8}  {'std':>8}  "
      f"{'n_folds':>8}  {'n_total':>8}")
    for bucket in BUCKET_ORDER:
        for o in outcome_cols:
            row = stability[
                (stability["group"] == bucket) & (stability["outcome"] == o)
            ]
            if row.empty:
                continue
            r = row.iloc[0]
            w(f"{bucket:<14}  {o:<8}  "
              f"{fmt_pct(r.mean_hit):>8}  {r.range_hit*100:+7.1f}pp  "
              f"{r.std_hit*100:7.2f}pp  {int(r.n_folds_with_data):>8}  "
              f"{int(r.total_n_obs):>8}")

    # --- spread analysis: persistent_bundle vs emerging at each fold
    w("")
    w("-- spread: (persistent + entrenched) - emerging, per fold ---------------")
    w(f"{'outcome':<8}  " + "  ".join(f"{'f' + str(f.fold_id):>10}" for f in folds) +
      "   verdict")
    for o in outcome_cols:
        cells, signs = [], []
        for f in folds:
            def hit(bucket):
                row = rolling[
                    (rolling["group"] == bucket)
                    & (rolling["outcome"] == o)
                    & (rolling["fold"] == f.fold_id)
                ]
                return float(row.iloc[0]["hit_rate"]) if not row.empty and pd.notna(row.iloc[0]["hit_rate"]) else None
            pers = hit("persistent")
            entr = hit("entrenched")
            emer = hit("emerging")
            if emer is None:
                cells.append(f"{'  na':>10}"); signs.append(None); continue
            bundle_parts = [v for v in (pers, entr) if v is not None]
            if not bundle_parts:
                cells.append(f"{'  na':>10}"); signs.append(None); continue
            bundle = float(np.mean(bundle_parts))
            spread = bundle - emer
            cells.append(f"{spread*100:+9.1f}pp")
            signs.append(spread)

        if all(s is not None and s > 0 for s in signs):
            verdict = "POSITIVE in all folds -> persistence-as-prior-weight worth scoping"
        elif all(s is not None and s >= 0 for s in signs):
            verdict = "non-negative in all folds -> marginal, do not act"
        elif any(s is not None and s > 0 for s in signs) and any(
            s is not None and s < 0 for s in signs
        ):
            verdict = "SIGN FLIPS across folds -> regime-dependent, do not act"
        else:
            verdict = "negative or inconclusive -> persistence does not predict"
        w(f"{o:<8}  " + "  ".join(cells) + f"   {verdict}")

    w("")
    w("Honest reading guide:")
    w("  - Per-bucket per-fold cells have decent n (50-200 typical) but the cohort")
    w("    is single-pool: all bets in a fold share macro regime, so swings can be")
    w("    correlated. The spread is the right measure, not the absolute hit rate.")
    w("  - Spread positive in ALL folds = green light to scope F-006 #6 build.")
    w("  - Sign flips between folds = the single-split positive result from F-006 V2")
    w("    #4 was a regime artifact. Do not build #6 on this evidence.")
    w("")

    OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    rolling.to_parquet(OUT_PARQ, index=False)
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_PARQ.relative_to(ROOT)}  ({len(rolling):,} rows)")
    print(f"wrote {OUT_TXT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
