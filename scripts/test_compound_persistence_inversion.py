"""
F-007 V2 phase 2 - compound persistence x inversion gating test.

Both F-006 #6 (persistence as L1 prior weight) and F-007 V2 phase 2 sign-flip
rule apply at the same 5d horizon. Before either ships independently we need
to know whether they interact. This is the gate.

For each scored (entity, date) observation:
  - persistence_bucket   from lifecycle_walkforward (emerging / forming /
                         persistent / entrenched)
  - flagged_inverted     join from region_calibration.json via
                         (stable_cluster_id, direction_sign) -> region_id
  - hit_5d_raw           = (dir_fwd_5d > 0)  i.e. price confirmed entity's
                         stated direction
  - hit_5d_flipped       = (dir_fwd_5d < 0)  i.e. price confirmed the OPPOSITE
                         of entity's stated direction

For inverted regions the "right" trade is the contrarian; hit_5d_flipped is
what an INVERT decision class would actually score against.

2x2 of (persistence x inverted) -> mean hit, with both raw and flipped scoring:

                            inverted=False   inverted=True
                            ------------     -------------
    persistent_bundle       <baseline>       <sign-flip cells>
    emerging                <baseline>       <sign-flip cells>

Expected (if hypothesis B from inverted-region investigation holds):
  - emerging      inverted=False -> ~50% (baseline)
  - persistent    inverted=False -> baseline + spread (F-006 #4 finding)
  - emerging      inverted=True  -> hit_raw <30%, hit_flipped >70% (the
                                    INVERT case)
  - persistent    inverted=True  -> hit_flipped > emerging inverted_flipped
                                    (the COMPOUND case - both signals stack)

Output:
  data/derived/compound_persistence_inversion.parquet  (joined per-row table)
  data/derived/compound_persistence_inversion_summary.txt
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT       = Path(__file__).resolve().parents[1]
DERIVED    = ROOT / "data" / "derived"
SITE_PUB   = ROOT.parent / "topicspace-site" / "public"

IN_LIFECYCLE_PARQ = DERIVED / "lifecycle_walkforward.parquet"
IN_CALIB_JSON     = SITE_PUB / "region_calibration.json"
OUT_PARQ          = DERIVED / "compound_persistence_inversion.parquet"
OUT_TXT           = DERIVED / "compound_persistence_inversion_summary.txt"

PERSISTENT_BUNDLE = {"persistent", "entrenched"}
EMERGING_BUCKET   = "emerging"
HORIZON           = 5   # the only horizon where both F-006 #6 and F-007 inversion landed signal


def _hit_raw(dir_fwd: float) -> float | None:
    if pd.isna(dir_fwd): return None
    return 1.0 if dir_fwd > 0 else 0.0


def _hit_flipped(dir_fwd: float) -> float | None:
    if pd.isna(dir_fwd): return None
    return 1.0 if dir_fwd < 0 else 0.0


def main() -> None:
    print("=== F-007 V2 phase 2: compound persistence x inversion gating test ===")

    lwf = pd.read_parquet(IN_LIFECYCLE_PARQ)
    cal = json.loads(IN_CALIB_JSON.read_text())

    # Build (stable_cluster_id, direction_sign) -> flagged_inverted map
    inv_map: dict[tuple[str, int], bool] = {}
    region_meta: dict[tuple[str, int], dict] = {}
    for r in cal["regions"]:
        key = (r["theme_id"], int(r["direction_sign"]))
        inv_map[key] = bool(r.get("flagged_inverted", False))
        region_meta[key] = {
            "region_id": r["region_id"],
            "theme_label": r["theme_label"],
            "n_obs_total": r["n_obs_total"],
            "tier": r["horizons"]["5d"]["full"]["tier"],
            "corpus_hit_5d": r["horizons"]["5d"]["full"]["hit_rate"],
        }

    # Filter: only score signed observations with a defined 5d return
    df = lwf[
        (lwf["direction_sign"] != 0)
        & lwf[f"dir_fwd_{HORIZON}d"].notna()
    ].copy()
    print(f"  scoreable observations: {len(df):,}")

    # Join inversion + region tier
    def _lookup_inv(row):
        return inv_map.get((row["stable_cluster_id"], int(row["direction_sign"])), False)
    def _lookup_tier(row):
        m = region_meta.get((row["stable_cluster_id"], int(row["direction_sign"])))
        return m["tier"] if m else "unknown"
    def _lookup_region_id(row):
        m = region_meta.get((row["stable_cluster_id"], int(row["direction_sign"])))
        return m["region_id"] if m else None

    df["region_inverted"] = df.apply(_lookup_inv, axis=1)
    df["region_tier"]     = df.apply(_lookup_tier, axis=1)
    df["region_id"]       = df.apply(_lookup_region_id, axis=1)
    df["hit_raw"]         = df[f"dir_fwd_{HORIZON}d"].apply(_hit_raw)
    df["hit_flipped"]     = df[f"dir_fwd_{HORIZON}d"].apply(_hit_flipped)
    df["persistent_side"] = df["persistence_bucket"].apply(
        lambda b: "persistent_bundle" if b in PERSISTENT_BUNDLE
                  else "emerging" if b == EMERGING_BUCKET
                  else "middle"
    )

    # Diagnostic on coverage
    n_inv_obs = int(df["region_inverted"].sum())
    n_public  = int((df["region_tier"] == "public").sum())
    print(f"  observations on inverted regions: {n_inv_obs:,}  "
          f"on public-tier regions: {n_public:,}")
    n_match_any_region = int((df["region_id"].notna()).sum())
    print(f"  observations matched to a calibration region: {n_match_any_region:,}")

    lines: list[str] = []
    def w(s: str = ""):
        print(s); lines.append(s)

    w("\n" + "=" * 78)
    w("F-007 V2 phase 2 - compound persistence x inversion at 5d")
    w("=" * 78)
    w(f"as-of: {dt.date.today().isoformat()}")
    w(f"scoreable observations: {len(df):,}   "
      f"on inverted regions: {n_inv_obs:,}   on public-tier regions: {n_public:,}")
    w(f"horizon: {HORIZON}d (only horizon where both F-006 #6 and the "
      f"inversion finding showed signal)")
    w("")

    # --- 2x2: persistence_side x region_inverted, hit_raw (the L2-as-stated metric)
    w("-- 2x2: hit_raw (price confirmed L2's stated direction) ----------------")
    w(f"{'persistence_side':<20}  {'inverted=False':>18}  {'inverted=True':>18}")
    for ps in ["emerging", "middle", "persistent_bundle"]:
        cells = []
        for inv in [False, True]:
            sub = df[(df["persistent_side"] == ps) & (df["region_inverted"] == inv)]
            hr  = sub["hit_raw"].dropna()
            n   = len(hr)
            cells.append(f"{hr.mean()*100:5.1f}% (n={n:>4})" if n else f"{'  --':>18}")
        w(f"{ps:<20}  " + "  ".join(f"{c:>18}" for c in cells))
    w("")

    # --- 2x2: persistence_side x region_inverted, hit_flipped (the contrarian metric)
    w("-- 2x2: hit_flipped (price confirmed the OPPOSITE of L2's direction) ---")
    w(f"{'persistence_side':<20}  {'inverted=False':>18}  {'inverted=True':>18}")
    for ps in ["emerging", "middle", "persistent_bundle"]:
        cells = []
        for inv in [False, True]:
            sub = df[(df["persistent_side"] == ps) & (df["region_inverted"] == inv)]
            hf  = sub["hit_flipped"].dropna()
            n   = len(hf)
            cells.append(f"{hf.mean()*100:5.1f}% (n={n:>4})" if n else f"{'  --':>18}")
        w(f"{ps:<20}  " + "  ".join(f"{c:>18}" for c in cells))
    w("")

    # --- the "effective hit" view: take hit_flipped for inverted, hit_raw otherwise
    df["hit_effective"] = np.where(df["region_inverted"], df["hit_flipped"], df["hit_raw"])
    w("-- effective hit (apply sign-flip to inverted cells only) --------------")
    w(f"{'persistence_side':<20}  {'inverted=False':>18}  "
      f"{'inverted=True_flip':>22}  {'overall':>10}")
    for ps in ["emerging", "middle", "persistent_bundle"]:
        sub = df[df["persistent_side"] == ps]
        a = sub[~sub["region_inverted"]]["hit_raw"].dropna()
        b = sub[ sub["region_inverted"]]["hit_flipped"].dropna()
        overall = pd.concat([a, b])
        def cell(s):
            return f"{s.mean()*100:5.1f}% (n={len(s):>4})" if len(s) else f"{'  --':>22}"
        w(f"{ps:<20}  {cell(a):>18}  {cell(b):>22}  {cell(overall):>10}")
    w("")

    # --- spread analysis: persistent_bundle vs emerging within each inversion side
    w("-- compound spread analysis -------------------------------------------")
    def grab(ps, inv, metric):
        s = df[(df["persistent_side"] == ps) & (df["region_inverted"] == inv)][metric].dropna()
        return float(s.mean()) if len(s) else None, int(len(s))

    for inv in [False, True]:
        metric = "hit_flipped" if inv else "hit_raw"
        pb, pb_n = grab("persistent_bundle", inv, metric)
        em, em_n = grab("emerging",          inv, metric)
        if pb is None or em is None:
            w(f"  inverted={inv}  pb={pb}  em={em}  -- one side empty, skip")
            continue
        spread = pb - em
        w(f"  inverted={str(inv):<5}  metric={metric:<11}  "
          f"persistent_bundle={pb*100:5.1f}% (n={pb_n})  "
          f"emerging={em*100:5.1f}% (n={em_n})  "
          f"spread={spread*100:+5.1f}pp")
    w("")

    # --- verdict
    w("-- verdict -------------------------------------------------------------")
    inv_pb_flip, n_inv_pb = grab("persistent_bundle", True, "hit_flipped")
    inv_em_flip, n_inv_em = grab("emerging",          True, "hit_flipped")
    noninv_pb,   n_npb    = grab("persistent_bundle", False, "hit_raw")
    noninv_em,   n_nem    = grab("emerging",          False, "hit_raw")

    def show(name, v, n):
        if v is None: return f"  {name}: n/a"
        return f"  {name}: {v*100:5.1f}%  (n={n})"

    w(show("non-inverted, emerging         (raw  )", noninv_em, n_nem))
    w(show("non-inverted, persistent_bundle (raw  )", noninv_pb, n_npb))
    w(show("inverted,     emerging         (flip )", inv_em_flip, n_inv_em))
    w(show("inverted,     persistent_bundle (flip )", inv_pb_flip, n_inv_pb))
    w("")

    # Hypothesis tests
    flags = []
    if inv_em_flip is not None and inv_em_flip > 0.55:
        flags.append("sign-flip on inverted regions earns its keep on its own "
                     f"({inv_em_flip*100:.0f}% on n={n_inv_em})")
    elif inv_em_flip is not None:
        flags.append("sign-flip alone is only marginal "
                     f"({inv_em_flip*100:.0f}% on n={n_inv_em})")
    if (inv_pb_flip is not None and inv_em_flip is not None
            and inv_pb_flip > inv_em_flip + 0.05):
        flags.append("persistence COMPOUNDS with sign-flip "
                     f"(persistent {inv_pb_flip*100:.0f}% > emerging "
                     f"{inv_em_flip*100:.0f}%, n={n_inv_pb})")
    elif inv_pb_flip is not None and inv_em_flip is not None:
        flags.append("persistence does NOT compound on inverted cells "
                     f"({inv_pb_flip*100:.0f}% vs {inv_em_flip*100:.0f}%) -- ship the two rules independently")
    if (noninv_pb is not None and noninv_em is not None
            and noninv_pb > noninv_em + 0.05):
        flags.append("persistence still has its own non-inverted edge "
                     f"({noninv_pb*100:.0f}% vs {noninv_em*100:.0f}%)")
    for f in flags:
        w(f"  -> {f}")
    w("")
    w("Honest reading guide:")
    w("  - hit_raw and hit_flipped are complementary on non-NaN rows: their")
    w("    sum is 1 because dir_fwd_5d is either positive or negative.")
    w("  - 'inverted=True' cell sizes are small (the whole point of public-tier:")
    w("    only ~10 such regions in the corpus). Read those numbers as directional,")
    w("    not authoritative.")
    w("  - Sample-size honesty: cells with n < 20 deserve a 'wait for data' caveat.")
    w("")

    OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQ, index=False)
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_PARQ.relative_to(ROOT)}  ({len(df):,} rows)")
    print(f"wrote {OUT_TXT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
