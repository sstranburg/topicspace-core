"""
F-007 V2 phase 1: rolling walk-forward over (theme, direction) regions.

Reads `data/derived/performance_regions.parquet` (one row per (date, ticker,
theme_id, direction_sign) observation with direction-aligned hit flags) and
runs the shared rolling primitive over public-tier regions (n_obs >= 10).

Why public-only: insufficient (<5) and limited (5-9) tiers don't have enough
observations to meaningfully appear in 3 expanding-window folds. They keep
their V1 in-sample hit rate + tier badge unchanged.

Outputs:
    data/derived/region_rolling_walkforward.parquet      (group=region_id, fold-level)
    data/derived/region_rolling_walkforward_summary.txt  (human-readable verdict)
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

# Local import. Adding storm root to path so this works from either CWD.
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
IN_PARQ    = DERIVED / "performance_regions.parquet"
OUT_PARQ   = DERIVED / "region_rolling_walkforward.parquet"
OUT_TXT    = DERIVED / "region_rolling_walkforward_summary.txt"

OUTCOME_COLS = ["hit_5d", "hit_10d", "hit_20d"]
PUBLIC_MIN_N = 10
N_FOLDS      = 3
MIN_TRAIN_FRACTION = 0.50
INVERTED_HIT_FLOOR = 0.30   # public regions below this are flagged inverted
STABILITY_RANGE_MAX = 0.20  # if max-min hit across folds <= this, region is "stable"


def main() -> None:
    print("=== F-007 V2 phase 1: region rolling walk-forward ===")
    if not IN_PARQ.exists():
        raise SystemExit(f"missing {IN_PARQ}; run build_performance_regions.py first")

    obs = pd.read_parquet(IN_PARQ)
    obs["date"] = pd.to_datetime(obs["date"])

    # direction_sign == 0 has no directional bet -> no hit definable.
    obs = obs[obs["direction_sign"] != 0].copy()
    print(f"  observations (signed): {len(obs):,}  "
          f"unique regions: {obs['region_id'].nunique():,}  "
          f"dates: {obs['date'].nunique()}  "
          f"({obs['date'].min().date()} -> {obs['date'].max().date()})")

    # Restrict to public-tier regions (n >= 10 across the FULL corpus).
    region_n = obs.groupby("region_id").size()
    public_region_ids = set(region_n[region_n >= PUBLIC_MIN_N].index)
    obs_public = obs[obs["region_id"].isin(public_region_ids)].copy()
    print(f"  public regions: {len(public_region_ids):,} "
          f"({len(obs_public):,} observations)")

    # Folds
    folds = expanding_window_folds(obs_public["date"], N_FOLDS, MIN_TRAIN_FRACTION)
    fold_str = "  ".join(
        f"f{f.fold_id}[{f.test_start.date()}->{f.test_end.date()}]" for f in folds
    )
    print(f"  folds: {fold_str}")

    rolling = rolling_hit_rate(
        obs_public, "region_id", OUTCOME_COLS,
        n_folds=N_FOLDS, min_train_frac=MIN_TRAIN_FRACTION,
    )
    stability = stability_score(rolling)

    # Inverted-region flag (corpus-wide hit_5d, not per-fold)
    full_hit_5d = (
        obs[obs["region_id"].isin(public_region_ids)]
        .groupby("region_id")["hit_5d"]
        .apply(lambda s: s.dropna().mean() if s.dropna().size else None)
    )
    inverted_ids = sorted([
        rid for rid, hr in full_hit_5d.items()
        if hr is not None and hr <= INVERTED_HIT_FLOOR
    ])

    lines: list[str] = []
    def w(s: str = ""):
        print(s); lines.append(s)

    w("\n" + "=" * 78)
    w("F-007 V2 phase 1 - region rolling walk-forward summary")
    w("=" * 78)
    w(f"as-of: {dt.date.today().isoformat()}")
    w(f"public regions: {len(public_region_ids)}   "
      f"n_folds: {N_FOLDS}   min_train_frac: {MIN_TRAIN_FRACTION}")
    w(f"public-tier definition: corpus n_obs >= {PUBLIC_MIN_N}")
    w(f"outcomes: {OUTCOME_COLS}")
    w(f"inverted-region threshold: hit_5d <= {INVERTED_HIT_FLOOR}")
    w(f"stability threshold: range(hit_rate across folds) <= {STABILITY_RANGE_MAX}")

    # --- corpus-wide aggregate per fold (the headline)
    w("")
    w("\n".join(fold_table_lines(
        rolling, "public-region AGGREGATE hit rate per fold", OUTCOME_COLS,
    )))

    # --- per-region stability for hit_5d (the primary horizon)
    w("")
    w("-- per-region stability (hit_5d only) -----------------------------------")
    s5 = stability[stability["outcome"] == "hit_5d"].copy()
    stable_mask = (s5["n_folds_with_data"] >= N_FOLDS - 1) & (s5["range_hit"] <= STABILITY_RANGE_MAX)
    w(f"regions appearing in >= {N_FOLDS - 1} folds with hit_5d "
      f"range <= {STABILITY_RANGE_MAX*100:.0f}pp: {int(stable_mask.sum())} of {len(s5)}")
    w(f"  median range across all regions: {s5['range_hit'].median():.2f}")
    w(f"  median std across all regions:   {s5['std_hit'].median():.2f}")

    # --- inverted regions
    w("")
    w("-- inverted regions (public, hit_5d <= "
      f"{INVERTED_HIT_FLOOR*100:.0f}%) -----------------------")
    if not inverted_ids:
        w("  (none)")
    else:
        # Join label
        label_map = (
            obs[obs["region_id"].isin(inverted_ids)]
            .drop_duplicates("region_id")
            .set_index("region_id")[["theme_label", "direction_sign"]]
            .to_dict("index")
        )
        for rid in inverted_ids:
            hr = full_hit_5d[rid]
            n  = int(region_n.get(rid, 0))
            info = label_map.get(rid, {})
            sign = info.get("direction_sign", "?")
            label = (info.get("theme_label") or "")[:55]
            w(f"  {rid}  hit_5d={fmt_pct(hr)}  n={n:>3}  sign={sign:+d}  {label}")
        w(f"  total: {len(inverted_ids)}")

    # --- verdict
    w("")
    w("-- verdict --------------------------------------------------------------")
    agg = aggregate_rolling(rolling)
    for o in OUTCOME_COLS:
        cells = agg[agg["outcome"] == o].sort_values("fold")
        if cells.empty:
            w(f"  {o}: no data"); continue
        hits = cells["hit_rate"].tolist()
        ns   = cells["n_obs"].tolist()
        rng  = max(hits) - min(hits) if hits else None
        if rng is None or any(h is None for h in hits):
            verdict = "inconclusive"
        elif rng <= STABILITY_RANGE_MAX:
            verdict = "STABLE across folds"
        else:
            verdict = "REGIME-DEPENDENT (fold-to-fold swing)"
        w(f"  {o:<8}  folds=" + " ".join(fmt_pct(h) for h in hits) +
          f"  (n=" + "/".join(str(int(n)) for n in ns) + f")  range={rng*100:+.1f}pp  -> {verdict}")

    w("")
    w("Honest reading guide:")
    w("  - Per-fold per-region cells are sparse (n=1-2 typical); read the AGGREGATE")
    w("    fold table as the primary signal, per-region stability as diagnostic.")
    w("  - Inverted-region list is corpus-wide hit, not fold-stable; treat as a")
    w("    candidate list for upstream review (sign-extractor bug? real fade?).")
    w("  - V2 phase 1 measures. Conviction reweighting (V2-acts) only ships if the")
    w("    aggregate is stable AND inverted regions cluster on a coherent cause.")
    w("")

    OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    rolling.to_parquet(OUT_PARQ, index=False)
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_PARQ.relative_to(ROOT)}  ({len(rolling):,} rows)")
    print(f"wrote {OUT_TXT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
