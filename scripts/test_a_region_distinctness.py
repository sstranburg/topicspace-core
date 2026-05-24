"""
Test A — Region Distinctness (TKOS existential gate).

The question this test answers:
    Are per-region outcome distributions statistically distinguishable from
    the global marginal? If P(outcome | region) approximately equals
    P(outcome), then the regions are decorative — spatial proximity in
    embedding space adds no predictive structure, and the TKOS architecture
    cannot honestly claim "regional governance."

This is the existential test for the TKOS substrate's central claim.
Thresholds are locked BEFORE running (per the discipline call):

    Test A PASS criteria (ALL must hold):
      [1] Chi-square p < 0.05 in >= 30% of public-tier regions (n >= 10)
          (vs ~5% expected from random chance)
      [2] Median KL divergence (P_region || P_global) across public regions
          >= 0.02 nats (~5pp typical difference from global marginal)
      [3] >= 5 public regions with KL >= 0.1 nats
          (some regions strongly distinct, not just marginal)

If all three pass: regions are distinct, framing-batch can proceed.
If any fail:        pause, recovery conversation needed.

Reads:
    data/derived/performance_regions.parquet
    data/derived/region_calibration.json   (for tier classification)

Writes:
    data/derived/test_a_region_distinctness.parquet  (per-region rows)
    data/derived/test_a_region_distinctness.md       (human-readable verdict)
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


ROOT          = Path(__file__).resolve().parents[1]
PERF_PARQ     = ROOT / "data" / "derived" / "performance_regions.parquet"
CAL_JSON      = ROOT / "data" / "derived" / "region_calibration.json"
OUT_PARQ      = ROOT / "data" / "derived" / "test_a_region_distinctness.parquet"
OUT_MD        = ROOT / "data" / "derived" / "test_a_region_distinctness.md"

HORIZONS = ["5d", "10d", "20d"]
PRIMARY_HORIZON = "5d"   # The horizon the test is gated on

# LOCKED THRESHOLDS — do not adjust after seeing the data
PUBLIC_MIN_N           = 10
CHI_SQUARE_ALPHA       = 0.05
CRITERION_1_FRACTION   = 0.30    # >= 30% of public regions must have p < 0.05
CRITERION_2_MEDIAN_KL  = 0.02    # median KL across public regions must be >= 0.02 nats
CRITERION_3_MIN_REGIONS = 5      # at least 5 public regions with...
CRITERION_3_KL_BAR     = 0.10    # ...KL >= 0.10 nats


def kl_divergence_binary(p: float, q: float, eps: float = 1e-9) -> float:
    """
    KL(P || Q) for a binary distribution where P = (p, 1-p), Q = (q, 1-q).
    Returns 0 if p == q. Uses natural log (nats).
    """
    if p <= 0 or p >= 1 or q <= 0 or q >= 1:
        # Clip to avoid log(0). For our use case, hit rates of exactly
        # 0 or 1 happen on small samples; we treat them as informative
        # but clip them just enough to keep KL finite.
        p = min(max(p, eps), 1 - eps)
        q = min(max(q, eps), 1 - eps)
    if p == q:
        return 0.0
    return (
        p * math.log(p / q)
        + (1 - p) * math.log((1 - p) / (1 - q))
    )


def chi_square_region_vs_global(
    n_hit_region: int, n_obs_region: int,
    p_global: float,
) -> tuple[float, float]:
    """
    Chi-square goodness-of-fit: does the region's (hit, miss) match the
    global (hit, miss) proportions, given the region's n_obs?

    Returns (chi2_statistic, p_value).
    Returns (nan, nan) if expected cells are too small (< 5) for the test.
    """
    observed = np.array([n_hit_region, n_obs_region - n_hit_region])
    expected = np.array([
        n_obs_region * p_global,
        n_obs_region * (1 - p_global),
    ])
    # Chi-square requires expected >= 5 in each cell to be valid
    if (expected < 5).any():
        return float("nan"), float("nan")
    chi2 = ((observed - expected) ** 2 / expected).sum()
    # 1 degree of freedom (binary outcome)
    p_value = 1 - stats.chi2.cdf(chi2, df=1)
    return float(chi2), float(p_value)


def main() -> None:
    print("=== TEST A: Region Distinctness (TKOS existential gate) ===")
    print(f"  primary horizon: {PRIMARY_HORIZON}")
    print(f"  locked thresholds:")
    print(f"    [1] chi-square p<{CHI_SQUARE_ALPHA} fraction >= {CRITERION_1_FRACTION:.0%}")
    print(f"    [2] median KL >= {CRITERION_2_MEDIAN_KL} nats")
    print(f"    [3] >= {CRITERION_3_MIN_REGIONS} regions with KL >= {CRITERION_3_KL_BAR} nats")
    print()

    # ── Load
    pr = pd.read_parquet(PERF_PARQ)
    print(f"  loaded performance_regions: {len(pr):,} rows")

    # Restrict to signed observations (the only ones with defined hit values)
    signed = pr[pr["direction_sign"] != 0].copy()
    print(f"  signed observations:        {len(signed):,}")

    # Compute global marginals per horizon
    globals_: dict[str, float] = {}
    for h in HORIZONS:
        col = f"hit_{h}"
        hits = signed[col].dropna()
        globals_[h] = float(hits.mean()) if len(hits) else float("nan")
    print(f"  global marginals (P(hit)):  "
          + ", ".join(f"{h}={globals_[h]:.3f}" for h in HORIZONS))

    # Per-region analysis
    rows: list[dict] = []
    for region_id, grp in signed.groupby("region_id"):
        n_obs_total = len(grp)
        tier = (
            "public"       if n_obs_total >= 10
            else "limited" if n_obs_total >= 5
            else "insufficient"
        )
        theme = grp["theme_label"].iloc[0] if "theme_label" in grp.columns else ""
        sign  = int(grp["direction_sign"].iloc[0])

        row: dict = {
            "region_id":   region_id,
            "theme_label": theme,
            "sign":        sign,
            "n_obs_total": n_obs_total,
            "tier":        tier,
        }
        for h in HORIZONS:
            col   = f"hit_{h}"
            hits  = grp[col].dropna()
            n_obs = len(hits)
            n_hit = int(hits.sum())
            p_reg = float(hits.mean()) if n_obs else float("nan")
            kl    = kl_divergence_binary(p_reg, globals_[h]) if n_obs else float("nan")
            chi2, pval = chi_square_region_vs_global(n_hit, n_obs, globals_[h]) \
                if n_obs else (float("nan"), float("nan"))
            row[f"n_obs_{h}"]   = n_obs
            row[f"p_region_{h}"] = round(p_reg, 4) if not math.isnan(p_reg) else None
            row[f"kl_{h}"]      = round(kl, 4)    if not math.isnan(kl) else None
            row[f"chi2_{h}"]    = round(chi2, 3)  if not math.isnan(chi2) else None
            row[f"pval_{h}"]    = round(pval, 4)  if not math.isnan(pval) else None
        rows.append(row)

    df = pd.DataFrame(rows)
    print(f"  scored {len(df):,} regions  "
          f"(public={int((df['tier']=='public').sum())}, "
          f"limited={int((df['tier']=='limited').sum())}, "
          f"insufficient={int((df['tier']=='insufficient').sum())})")

    # Restrict gate evaluation to public-tier regions on the primary horizon
    public = df[df["tier"] == "public"].copy()
    n_public = len(public)
    kl_col   = f"kl_{PRIMARY_HORIZON}"
    pval_col = f"pval_{PRIMARY_HORIZON}"
    public_kl = public[kl_col].dropna()
    public_pv = public[pval_col].dropna()

    # ── Apply locked criteria
    print()
    print("=== GATE EVALUATION ===")
    print(f"  public regions ({PRIMARY_HORIZON}): {n_public}")

    # Criterion 1
    n_pv = len(public_pv)
    n_significant = int((public_pv < CHI_SQUARE_ALPHA).sum())
    frac_significant = n_significant / n_pv if n_pv else 0.0
    c1_pass = frac_significant >= CRITERION_1_FRACTION
    print(f"  [1] chi-square p<{CHI_SQUARE_ALPHA}: "
          f"{n_significant}/{n_pv} = {frac_significant:.1%}  "
          f"(threshold >= {CRITERION_1_FRACTION:.0%})  "
          f"-> {'PASS' if c1_pass else 'FAIL'}")

    # Criterion 2
    median_kl = float(public_kl.median()) if len(public_kl) else float("nan")
    c2_pass = (not math.isnan(median_kl)) and median_kl >= CRITERION_2_MEDIAN_KL
    print(f"  [2] median KL across public regions: "
          f"{median_kl:.4f} nats  "
          f"(threshold >= {CRITERION_2_MEDIAN_KL} nats)  "
          f"-> {'PASS' if c2_pass else 'FAIL'}")

    # Criterion 3
    n_strong = int((public_kl >= CRITERION_3_KL_BAR).sum())
    c3_pass = n_strong >= CRITERION_3_MIN_REGIONS
    print(f"  [3] public regions with KL >= {CRITERION_3_KL_BAR}: "
          f"{n_strong}  (threshold >= {CRITERION_3_MIN_REGIONS})  "
          f"-> {'PASS' if c3_pass else 'FAIL'}")

    overall = c1_pass and c2_pass and c3_pass
    verdict = "PASS" if overall else "FAIL"
    print()
    print(f"  TEST A OVERALL: {verdict}")
    print()

    # Top distinguishing regions for the markdown
    public_sorted = (
        public.dropna(subset=[kl_col])
              .sort_values(kl_col, ascending=False)
              .head(15)
    )

    # ── Write outputs
    df.to_parquet(OUT_PARQ, index=False)

    lines: list[str] = []
    def w(s: str = ""): lines.append(s)
    w(f"# Test A — Region Distinctness (TKOS existential gate)")
    w("")
    w(f"_Generated {dt.date.today().isoformat()}_")
    w("")
    w(f"## The question")
    w("")
    w(f"Are per-region outcome distributions statistically distinguishable from "
      f"the global marginal? If `P(outcome | region) ≈ P(outcome)`, the regions "
      f"are decorative — spatial proximity in embedding space adds no predictive "
      f"structure, and the TKOS architecture cannot honestly claim 'regional "
      f"governance.'")
    w("")
    w(f"This is the **existential gate** for the substrate.")
    w("")
    w(f"## Locked thresholds (set before seeing the data)")
    w("")
    w(f"| # | Criterion | Threshold |")
    w(f"|---|---|---|")
    w(f"| 1 | Chi-square `p<{CHI_SQUARE_ALPHA}` fraction in public regions | ≥ {CRITERION_1_FRACTION:.0%} |")
    w(f"| 2 | Median KL divergence across public regions | ≥ {CRITERION_2_MEDIAN_KL} nats |")
    w(f"| 3 | Public regions with KL ≥ {CRITERION_3_KL_BAR} nats | ≥ {CRITERION_3_MIN_REGIONS} regions |")
    w("")
    w(f"All three must hold. Primary horizon: `{PRIMARY_HORIZON}`.")
    w("")
    w(f"## Verdict")
    w("")
    w(f"**Overall:** `{verdict}`")
    w("")
    w(f"| Criterion | Observed | Threshold | Pass? |")
    w(f"|---|---|---|---|")
    w(f"| 1 chi-square p<{CHI_SQUARE_ALPHA} | {n_significant}/{n_pv} = {frac_significant:.1%} | ≥ {CRITERION_1_FRACTION:.0%} | {'✅' if c1_pass else '❌'} |")
    w(f"| 2 median KL | {median_kl:.4f} nats | ≥ {CRITERION_2_MEDIAN_KL} | {'✅' if c2_pass else '❌'} |")
    w(f"| 3 regions with KL ≥ {CRITERION_3_KL_BAR} | {n_strong} | ≥ {CRITERION_3_MIN_REGIONS} | {'✅' if c3_pass else '❌'} |")
    w("")
    w(f"## Corpus stats")
    w("")
    w(f"- Total signed observations: **{len(signed):,}**")
    w(f"- Total scored regions:      **{len(df):,}**")
    w(f"- Public-tier regions (n ≥ {PUBLIC_MIN_N}): **{n_public}**")
    w(f"- Global P(hit) by horizon:  "
      + ", ".join(f"{h}={globals_[h]:.3f}" for h in HORIZONS))
    w("")
    w(f"## Top 15 public regions by KL divergence ({PRIMARY_HORIZON})")
    w("")
    w(f"| # | region | theme | sign | n | P_region | KL | chi² p |")
    w(f"|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(public_sorted.itertuples(), start=1):
        label = (r.theme_label or "_(no label)_")[:50]
        p_reg = getattr(r, f"p_region_{PRIMARY_HORIZON}")
        kl_v  = getattr(r, f"kl_{PRIMARY_HORIZON}")
        pval  = getattr(r, f"pval_{PRIMARY_HORIZON}")
        n_obs = getattr(r, f"n_obs_{PRIMARY_HORIZON}")
        p_reg_s = f"{p_reg:.2f}" if p_reg is not None else "n/a"
        pval_s  = f"{pval:.4f}" if pval is not None else "n/a"
        w(f"| {i} | `{r.region_id}` | {label} | {r.sign:+d} | {n_obs} | {p_reg_s} | {kl_v:.4f} | {pval_s} |")
    w("")
    w(f"## Interpretation")
    w("")
    if overall:
        w(f"All three locked criteria pass on the primary horizon (`{PRIMARY_HORIZON}`). "
          f"Per-region outcome distributions are statistically distinguishable from "
          f"the global marginal: {frac_significant:.0%} of public regions reject "
          f"the null hypothesis of equality at p<0.05, the median region differs "
          f"from global by {median_kl:.4f} nats, and {n_strong} public regions "
          f"show strong distinctness (KL ≥ {CRITERION_3_KL_BAR}).")
        w("")
        w(f"**The spatial-proximity premise of the TKOS substrate holds.** "
          f"Regions are not decorative; they carry distinct outcome information "
          f"that the global marginal does not. The framing batch (6-layer rename, "
          f"value-proposition update, internal vocabulary sweep) can proceed.")
    else:
        failed = []
        if not c1_pass: failed.append(f"chi-square fraction ({frac_significant:.1%} < {CRITERION_1_FRACTION:.0%})")
        if not c2_pass: failed.append(f"median KL ({median_kl:.4f} < {CRITERION_2_MEDIAN_KL})")
        if not c3_pass: failed.append(f"strong regions ({n_strong} < {CRITERION_3_MIN_REGIONS})")
        w(f"At least one locked criterion failed: {', '.join(failed)}.")
        w("")
        w(f"**The spatial-proximity premise is not unambiguously supported.** "
          f"Before proceeding with the framing batch, the recovery conversation "
          f"is needed: are the regions clustered on the wrong features, are the "
          f"outcomes too coarse, or do only a subset of regions carry signal? "
          f"Halt vocabulary calcification until this is resolved.")
    w("")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {OUT_PARQ.relative_to(ROOT)}")
    print(f"  wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
