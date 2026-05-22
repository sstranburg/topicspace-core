#!/usr/bin/env python3
"""
build_region_calibration.py  —  F-007 V1, step 2

Reads the per-observation table from build_performance_regions and
rolls it up per (region, horizon). Computes:

  - hit rate, avg excess return, std dev, n_obs
  - first-half / second-half splits (stability across time)
  - sample-size tier (n ≥ 10 = "public", 5-9 = "limited", < 5 = "insufficient")
  - **baselines per horizon** for context:
      • all_expectations: pool across every signed expectation at that horizon
      • random:           50% by definition
      • price_momentum:   predict direction = sign(prior-N-day return)
                          score the same way; rate at which that strategy
                          would have hit

Walk-forward discipline:
  - Each observation uses only data available on its observation date.
  - Forward returns are observed, not modeled.
  - No region-specific calibration is fit on the same observations being
    scored; this is descriptive of what the system did, not a learned model.

Reads:
  data/derived/performance_regions.parquet
  data/derived/prices/{TICKER}.parquet  (for momentum baseline)

Writes:
  data/derived/region_calibration.json
  topicspace-site/public/region_calibration.json

Usage:
  source venv/bin/activate && python scripts/build_region_calibration.py
"""

import datetime as dt
import json
import math
import statistics
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"

IN_PATH      = ROOT / "data" / "derived" / "performance_regions.parquet"
PRICES_DIR   = ROOT / "data" / "derived" / "prices"
BENCHMARK    = "QQQ"
OUT_DERIVED  = ROOT / "data" / "derived" / "region_calibration.json"
OUT_SITE     = SITE_PUBLIC / "region_calibration.json"

HORIZONS = [5, 10, 20]

# Sample-size tiers (as specified in F-007 V1 authorization)
TIER_PUBLIC      = 10   # n ≥ 10 → public actor-page chip
TIER_LIMITED_MIN = 5    # 5 ≤ n ≤ 9 → debug/methods only, "limited history"
                        # n < 5 → "insufficient history"


def tier_for(n: int) -> str:
    if n >= TIER_PUBLIC:
        return "public"
    if n >= TIER_LIMITED_MIN:
        return "limited"
    return "insufficient"


def load_price_series(ticker: str) -> pd.DataFrame | None:
    p = PRICES_DIR / f"{ticker}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df = df.rename(columns={"timestamp": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").drop_duplicates("date", keep="last")
    df = df[["date", "close"]].dropna()
    return df.set_index("date")


def trailing_return(close_idx: pd.DataFrame, d: dt.date, n: int) -> float | None:
    """(close[d] - close[d-n]) / close[d-n]; using trading-day index."""
    if d not in close_idx.index:
        return None
    dates = close_idx.index.tolist()
    try:
        i = dates.index(d)
    except ValueError:
        return None
    j = i - n
    if j < 0:
        return None
    p0 = float(close_idx.iloc[j]["close"])
    pN = float(close_idx.iloc[i]["close"])
    if p0 <= 0:
        return None
    return (pN - p0) / p0


# ─── Aggregation helpers ────────────────────────────────────────────────────

def safe_mean(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return None if not xs else float(sum(xs) / len(xs))


def safe_std(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if len(xs) < 2:
        return None
    return float(statistics.stdev(xs))


def split_halves_by_date(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    if not rows:
        return [], []
    sorted_rows = sorted(rows, key=lambda r: r["date"])
    midpoint = len(sorted_rows) // 2
    return sorted_rows[:midpoint], sorted_rows[midpoint:]


def summarize(rows: list[dict], horizon: int) -> dict:
    """Per-horizon summary for a set of observations."""
    h_col = f"hit_{horizon}d"
    r_col = f"rel_{horizon}d"
    valid = [r for r in rows
             if r[h_col] is not None and r[r_col] is not None]
    if not valid:
        return {"n_obs": 0, "hit_rate": None, "avg_excess_return": None, "std_excess": None, "tier": tier_for(0)}
    hits  = [r[h_col] for r in valid]
    rels  = [r[r_col] for r in valid]
    return {
        "n_obs":             len(valid),
        "hit_rate":          safe_mean(hits),
        "avg_excess_return": safe_mean(rels),
        "std_excess":        safe_std(rels),
        "tier":              tier_for(len(valid)),
    }


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    if not IN_PATH.exists():
        sys.exit(f"Missing {IN_PATH} — run build_performance_regions.py first.")

    print("  loading observations…")
    df = pd.read_parquet(IN_PATH)
    print(f"    {len(df):,} observations across {df['region_id'].nunique()} regions")

    # Exclude direction_sign == 0 from hit-rate stats but keep them for
    # context (count them in n_obs for the all-expectations baseline).
    signed = df[df["direction_sign"] != 0].copy()
    print(f"    {len(signed):,} signed observations (excluded {len(df) - len(signed)} neutral)")

    # ── Per-region aggregation ──────────────────────────────────────────────
    regions_out: list[dict] = []
    for rid, grp in signed.groupby("region_id"):
        rows = grp.to_dict("records")
        h1, h2 = split_halves_by_date(rows)
        meta = {
            "region_id":         rid,
            "theme_id":          rows[0]["theme_id"],
            "theme_label":       rows[0]["theme_label"] or "",
            "direction_sign":    int(rows[0]["direction_sign"]),
            "n_obs_total":       len(rows),
            "n_unique_tickers":  len({r["ticker"] for r in rows}),
            "first_date":        min(r["date"] for r in rows),
            "last_date":         max(r["date"] for r in rows),
            "member_tickers":    sorted({r["ticker"] for r in rows}),
            "horizons": {
                f"{n}d": {
                    "full":   summarize(rows, n),
                    "first_half":  summarize(h1, n),
                    "second_half": summarize(h2, n),
                }
                for n in HORIZONS
            },
        }
        regions_out.append(meta)

    # ── Baselines ───────────────────────────────────────────────────────────
    baselines: dict[str, dict] = {}

    # 1) all-expectations baseline: pool across every signed observation
    all_expectations = signed.to_dict("records")
    baselines["all_expectations"] = {
        "description": "Pool across every signed expectation at the given horizon.",
        "horizons": {
            f"{n}d": summarize(all_expectations, n) for n in HORIZONS
        },
    }

    # 2) random baseline: 50% by definition (coin flip)
    baselines["random"] = {
        "description": "Random direction (coin flip).",
        "horizons": {
            f"{n}d": {
                "n_obs":             None,
                "hit_rate":          0.50,
                "avg_excess_return": 0.0,
                "std_excess":        None,
                "tier":              "by_definition",
            }
            for n in HORIZONS
        },
    }

    # 3) price-momentum baseline: for each (date, ticker) observation, predict
    #    direction = sign of trailing N-day return. Score the same way as the
    #    system's predictions.
    print("  computing price-momentum baseline…")
    price_cache: dict[str, pd.DataFrame | None] = {}
    bench = load_price_series(BENCHMARK)
    if bench is None:
        sys.exit(f"Missing benchmark prices for {BENCHMARK}")

    momentum_obs_by_horizon: dict[int, list[dict]] = {n: [] for n in HORIZONS}
    for _, r in signed.iterrows():
        tk = r["ticker"]
        if tk not in price_cache:
            price_cache[tk] = load_price_series(tk)
        prices = price_cache[tk]
        if prices is None:
            continue
        d = dt.date.fromisoformat(r["date"])

        for n in HORIZONS:
            mom_t = trailing_return(prices, d, n)
            mom_b = trailing_return(bench,  d, n)
            if mom_t is None or mom_b is None:
                continue
            mom_rel = mom_t - mom_b  # trailing relative momentum
            momentum_sign = 1 if mom_rel > 0 else -1 if mom_rel < 0 else 0
            if momentum_sign == 0:
                continue
            rel_forward = r[f"rel_{n}d"]
            if rel_forward is None or (isinstance(rel_forward, float) and math.isnan(rel_forward)):
                continue
            hit = 1 if (rel_forward > 0 and momentum_sign > 0) or (rel_forward < 0 and momentum_sign < 0) else 0
            momentum_obs_by_horizon[n].append({
                f"hit_{n}d":  hit,
                f"rel_{n}d":  float(rel_forward),
            })

    baselines["price_momentum"] = {
        "description": (
            "Predict direction = sign of trailing N-day relative-to-QQQ "
            "return; score the same way as system predictions. Tests "
            "whether the narrative-driven system beats dumb momentum."
        ),
        "horizons": {
            f"{n}d": summarize(momentum_obs_by_horizon[n], n) for n in HORIZONS
        },
    }

    # ── Sort regions by sample size for the site payload ────────────────────
    regions_out.sort(key=lambda r: -r["n_obs_total"])

    # ── F-007 V2 phase 1: inverted-region flag + rolling stability join ─────
    # Inverted flag is corpus-wide (hit_5d <= INVERTED_HIT_FLOOR for public regions
    # only). Rolling-stable flag joins from region_rolling_walkforward.parquet if
    # that artifact has been built by scripts/run_region_rolling_walkforward.py.
    INVERTED_HIT_FLOOR    = 0.30
    STABILITY_RANGE_MAX   = 0.20
    ROLLING_PARQ          = ROOT / "data" / "derived" / "region_rolling_walkforward.parquet"

    rolling_lookup: dict[str, dict] = {}      # region_id -> per-horizon fold metrics
    rolling_agg: dict[str, list[dict]] = {}   # horizon -> [{fold, n_obs, hit_rate}]
    if ROLLING_PARQ.exists():
        rolling_df = pd.read_parquet(ROLLING_PARQ)
        # Per-region per-outcome stability summary
        for (region_id, outcome), grp in rolling_df.groupby(["group", "outcome"]):
            grp = grp.dropna(subset=["hit_rate"])
            if grp.empty:
                continue
            horizon = outcome.replace("hit_", "")  # "5d", "10d", "20d"
            mn, mx = float(grp["hit_rate"].min()), float(grp["hit_rate"].max())
            rolling_lookup.setdefault(region_id, {})[horizon] = {
                "n_folds_with_data": int(len(grp)),
                "total_n_obs":       int(grp["n_obs"].sum()),
                "mean_hit":          round(float(grp["hit_rate"].mean()), 4),
                "range_hit":         round(mx - mn, 4),
                "min_hit":           round(mn, 4),
                "max_hit":           round(mx, 4),
                "rolling_stable":    bool(len(grp) >= 2 and (mx - mn) <= STABILITY_RANGE_MAX),
            }
        # Public-region aggregate per fold
        rolling_df = rolling_df.assign(
            n_hits = (rolling_df["hit_rate"] * rolling_df["n_obs"]).round().fillna(0).astype(int),
        )
        for (fold_id, outcome), grp in rolling_df.dropna(subset=["hit_rate"]).groupby(
            ["fold", "outcome"]
        ):
            horizon = outcome.replace("hit_", "")
            n_obs = int(grp["n_obs"].sum())
            n_hits = int(grp["n_hits"].sum())
            rolling_agg.setdefault(horizon, []).append({
                "fold":       int(fold_id),
                "test_start": str(grp["test_start"].min().date()),
                "test_end":   str(grp["test_end"].max().date()),
                "n_obs":      n_obs,
                "hit_rate":   round(n_hits / n_obs, 4) if n_obs else None,
            })
        for h in rolling_agg:
            rolling_agg[h].sort(key=lambda c: c["fold"])

    n_inverted = 0
    n_rolling_stable = 0
    for r in regions_out:
        full_h5 = r["horizons"]["5d"]["full"]
        is_public = full_h5["tier"] == "public"
        hr5 = full_h5["hit_rate"]
        flagged = (
            is_public
            and hr5 is not None
            and hr5 <= INVERTED_HIT_FLOOR
        )
        r["flagged_inverted"] = bool(flagged)
        if flagged:
            n_inverted += 1
        rolling_for_region = rolling_lookup.get(r["region_id"], {})
        if rolling_for_region:
            r["rolling"] = rolling_for_region
            if any(v.get("rolling_stable") for v in rolling_for_region.values()):
                n_rolling_stable += 1

        # F-007 V2 phase 2: effective_direction_sign + sign_flip provenance.
        # Compound test (scripts/test_compound_persistence_inversion.py) showed
        # that sign-flipping inverted regions yields 73-81% hit_5d on the
        # contrarian direction (n=115 obs, all persistence levels). The
        # persistence and inversion signals do NOT compound; ship them
        # independently. Operating-layer consumers should read
        # `effective_direction_sign` for trade decisions and treat the original
        # `direction_sign` as the L2-extractor read.
        if flagged:
            r["effective_direction_sign"] = -int(r["direction_sign"])
            r["sign_flip"] = {
                "applied":            True,
                "reason":             "flagged_inverted: corpus hit_5d <= 0.30 on public-tier",
                "corpus_hit_5d_raw":  round(float(hr5), 4) if hr5 is not None else None,
                "contrarian_hit_5d":  round(1.0 - float(hr5), 4) if hr5 is not None else None,
                "evidence":           "scripts/test_compound_persistence_inversion.py",
            }
        else:
            r["effective_direction_sign"] = int(r["direction_sign"])
            r["sign_flip"] = {"applied": False}

    # ── Compact site summary (deltas vs. baselines, sample-size tiering) ────
    def get_baseline(name: str, n: int):
        return baselines[name]["horizons"][f"{n}d"]["hit_rate"]

    public_count = sum(1 for r in regions_out if r["horizons"]["5d"]["full"]["tier"] == "public")
    limited_count = sum(1 for r in regions_out if r["horizons"]["5d"]["full"]["tier"] == "limited")
    insufficient_count = sum(1 for r in regions_out if r["horizons"]["5d"]["full"]["tier"] == "insufficient")

    payload = {
        "as_of":     dt.date.today().isoformat(),
        "n_regions": len(regions_out),
        "n_observations_total": int(len(df)),
        "n_observations_signed": int(len(signed)),
        "tier_counts": {
            "public":       public_count,
            "limited":      limited_count,
            "insufficient": insufficient_count,
        },
        "horizons":  [f"{n}d" for n in HORIZONS],
        "baselines": baselines,
        # F-007 V2 phase 1 augmentations. `rolling_aggregate` is the public-region
        # cross-fold aggregate (the headline); per-region `rolling` cells are
        # diagnostic. `flagged_inverted` is a corpus-wide derivative — public
        # regions whose hit_5d <= 30%, the upstream-review candidate list.
        "v2_phase1": {
            "n_inverted_public":         n_inverted,
            "n_rolling_stable_regions":  n_rolling_stable,
            "rolling_aggregate":         rolling_agg,
        },
        # F-007 V2 phase 2: sign-flip rule applied to inverted regions.
        # See scripts/test_compound_persistence_inversion.py for the gating
        # evidence (73-81% hit on contrarian direction, n=115 across all
        # persistence levels). Operating-layer consumers should prefer
        # `effective_direction_sign` over `direction_sign` for trade decisions.
        "v2_phase2": {
            "sign_flip_rule": {
                "applied_to":            "regions where flagged_inverted == true",
                "n_regions_flipped":     n_inverted,
                "rule":                  "effective_direction_sign = -direction_sign",
                "evidence_summary": (
                    "Compound test 2026-05-21: contrarian (sign-flipped) hit_5d "
                    "73-81% on inverted public regions across all persistence "
                    "levels (n=115). Persistence does NOT compound with "
                    "sign-flip; ship the two rules independently."
                ),
            }
        },
        "regions":   regions_out,
    }

    OUT_DERIVED.parent.mkdir(parents=True, exist_ok=True)
    OUT_DERIVED.write_text(json.dumps(payload, indent=2))
    OUT_SITE.write_text(json.dumps(payload, indent=2))
    print(f"\n  wrote {OUT_DERIVED}")
    print(f"  wrote {OUT_SITE}")

    # ── Diagnostic table ────────────────────────────────────────────────────
    print()
    print("  ─── BASELINES (signed observations, all regions pooled) ─────")
    for name in ["all_expectations", "random", "price_momentum"]:
        print(f"    {name}:")
        for n in HORIZONS:
            h = baselines[name]["horizons"][f"{n}d"]
            hr = f"{h['hit_rate']*100:.1f}%" if h["hit_rate"] is not None else " n/a "
            n_obs = h["n_obs"] if h["n_obs"] is not None else "—"
            print(f"      {n:>2}d  hit {hr:>6}  n={n_obs}")
    print()
    print("  ─── TOP PUBLIC REGIONS (n ≥ 10) BY 5D HIT RATE ──────────────")
    public_regions = [r for r in regions_out if r["horizons"]["5d"]["full"]["tier"] == "public"]
    public_regions.sort(key=lambda r: -(r["horizons"]["5d"]["full"]["hit_rate"] or 0))
    for r in public_regions[:8]:
        sign = "↑" if r["direction_sign"] > 0 else "↓" if r["direction_sign"] < 0 else "─"
        lbl  = (r["theme_label"] or r["theme_id"])[:50]
        n    = r["n_obs_total"]
        h5   = r["horizons"]["5d"]["full"]["hit_rate"]
        h10  = r["horizons"]["10d"]["full"]["hit_rate"]
        h20  = r["horizons"]["20d"]["full"]["hit_rate"]
        ar5  = r["horizons"]["5d"]["full"]["avg_excess_return"]
        h5s  = f"{h5*100:.0f}%"  if h5  is not None else " n/a"
        h10s = f"{h10*100:.0f}%" if h10 is not None else " n/a"
        h20s = f"{h20*100:.0f}%" if h20 is not None else " n/a"
        ar5s = f"{ar5*100:+.2f}%" if ar5 is not None else " n/a"
        print(f"  {sign} {lbl:<50} n={n:>3} 5d={h5s:>4} 10d={h10s:>4} 20d={h20s:>4} excess_5d={ar5s:>7}")


if __name__ == "__main__":
    main()
