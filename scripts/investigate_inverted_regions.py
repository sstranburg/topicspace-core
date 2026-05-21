"""
F-007 V2 phase 2: investigate the inverted-region bias.

V2 phase 1 surfaced 10 public regions with hit_5d <= 30%, 7 of which are
sign=-1 (bearish L2 reads that the market consistently faded). This script
pulls the actual L2 evidence behind each flagged region so we can judge
which hypothesis fits:

  A. extractor bug   - direction extractor over-reads bearish on mixed text
  B. fade dynamic    - L2 reads correctly bearish; market rewards contrarian
  C. mislabel        - cluster label doesn't match member content
  D. small-sample    - n=10 is just noise

For each inverted region we surface:
  - theme label, sign, n_obs, corpus hit_5d, member tickers
  - 6 representative analyst-note headlines + near_term_view excerpts
  - per-actor n + corpus hit_5d
  - opposite-sign cross-check (does the +1 version of this theme exist? hit?)

Output:
  data/derived/inverted_regions_investigation.md  (human-readable)
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

CALIBRATION_JSON = SITE_PUB / "region_calibration.json"
VERSIONS_PARQ    = DERIVED / "expectation_versions.parquet"
PERF_REG_PARQ    = DERIVED / "performance_regions.parquet"
OUT_MD           = DERIVED / "inverted_regions_investigation.md"

SAMPLE_NOTE_COUNT = 6   # how many headlines / near_term_views to surface per region


def _hit_rate(v: float | None) -> str:
    return "n/a" if v is None else f"{v*100:.0f}%"


def main() -> None:
    print("=== F-007 V2 phase 2: inverted-region bias investigation ===")
    cal = json.loads(CALIBRATION_JSON.read_text())
    inverted = sorted(
        [r for r in cal["regions"] if r.get("flagged_inverted")],
        key=lambda r: r["horizons"]["5d"]["full"]["hit_rate"] or 0,
    )
    print(f"  {len(inverted)} inverted public regions")

    ver = pd.read_parquet(VERSIONS_PARQ)
    pr  = pd.read_parquet(PERF_REG_PARQ)

    # Build a corpus-wide per-(theme_id, direction_sign) hit_5d index so we can
    # cross-check the opposite sign quickly.
    sign_hit_lookup: dict[tuple[str, int], dict] = {}
    for (tid, sgn), grp in pr.groupby(["theme_id", "direction_sign"]):
        h5 = grp["hit_5d"].dropna()
        sign_hit_lookup[(tid, int(sgn))] = {
            "n": int(len(grp)),
            "hit_5d": float(h5.mean()) if len(h5) else None,
        }

    lines: list[str] = []
    def w(s: str = ""):
        lines.append(s)

    w(f"# Inverted-region bias investigation")
    w(f"")
    w(f"_F-007 V2 phase 2 · generated {dt.date.today().isoformat()}_")
    w(f"")
    w(f"Investigation purpose: 10 public regions flagged with hit_5d ≤ 30%; "
      f"7 of 10 are sign=−1. This document surfaces the underlying analyst-note "
      f"evidence to distinguish (A) extractor bug, (B) fade dynamic, "
      f"(C) mislabel, (D) small-sample noise.")
    w(f"")
    w(f"For each region: theme label, sign, n_obs, corpus hit_5d, member tickers, "
      f"sample headlines + near_term_views, per-actor breakdown, and an "
      f"opposite-sign cross-check.")
    w(f"")
    w(f"---")
    w(f"")

    # Overview table
    w(f"## Overview")
    w(f"")
    w(f"| # | Region | Theme label | sign | n | hit_5d | opp sign hit | candidate |")
    w(f"|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(inverted, start=1):
        tid  = r["theme_id"]
        sgn  = int(r["direction_sign"])
        opp  = sign_hit_lookup.get((tid, -sgn))
        opp_str = (
            f"{_hit_rate(opp['hit_5d'])} (n={opp['n']})"
            if opp and opp["hit_5d"] is not None
            else "—"
        )
        w(f"| {i} | `{r['region_id']}` | {r['theme_label'][:48]} | "
          f"{sgn:+d} | {r['n_obs_total']} | "
          f"{_hit_rate(r['horizons']['5d']['full']['hit_rate'])} | {opp_str} | _tbd_ |")
    w(f"")
    w(f"---")
    w(f"")

    # Detail per region
    for i, r in enumerate(inverted, start=1):
        tid   = r["theme_id"]
        sgn   = int(r["direction_sign"])
        n     = r["n_obs_total"]
        hr5   = r["horizons"]["5d"]["full"]["hit_rate"]
        hr10  = r["horizons"]["10d"]["full"]["hit_rate"]
        hr20  = r["horizons"]["20d"]["full"]["hit_rate"]
        members = sorted(r.get("member_tickers", []))

        w(f"## {i}. {r['theme_label']}  ({_hit_rate(hr5)} 5d, sign={sgn:+d}, n={n})")
        w(f"")
        w(f"- **region_id:** `{r['region_id']}`")
        w(f"- **theme_id:**  `{tid}`")
        w(f"- **hit rates:** 5d {_hit_rate(hr5)} · 10d {_hit_rate(hr10)} · 20d {_hit_rate(hr20)}")
        w(f"- **member tickers** ({len(members)}): {', '.join(members)}")

        # Opposite-sign cross-check
        opp = sign_hit_lookup.get((tid, -sgn))
        if opp is None or opp["hit_5d"] is None:
            w(f"- **opposite sign (sign={-sgn:+d}):** does not exist in corpus")
        else:
            w(f"- **opposite sign (sign={-sgn:+d}):** "
              f"hit_5d = {_hit_rate(opp['hit_5d'])} on n={opp['n']} observations")
            if hr5 is not None and opp["hit_5d"] is not None:
                delta = opp["hit_5d"] - hr5
                w(f"  - flip-back signal: opposite-sign hit_5d is "
                  f"{delta*100:+.0f}pp higher than this region's. "
                  + ("**Strong sign-flip candidate.**" if delta >= 0.30
                     else "_Mild flip-back signal._" if delta >= 0.10
                     else "_Weak; opposite sign isn't much better._"))
        w(f"")

        # Sample notes
        ver_sub = ver[
            (ver["stable_cluster_id"] == tid) & (ver["direction_sign"] == sgn)
        ].copy()
        if ver_sub.empty:
            w(f"- **sample analyst notes:** none found in versions parquet")
        else:
            # Sample: prioritize highest conviction (the strongest reads) so we
            # see what the L2 layer was most confident about.
            ver_sub = ver_sub.sort_values("conviction", ascending=False).head(SAMPLE_NOTE_COUNT)
            w(f"- **sample analyst notes** (top by conviction, max {SAMPLE_NOTE_COUNT}):")
            w(f"")
            for _, row in ver_sub.iterrows():
                head = (row.get("headline") or "(no headline)").strip()
                view = (row.get("near_term_view") or "").strip()
                w(f"  - **{row['ticker']}** · {row['date']} · conv={row['conviction']:.2f}")
                w(f"    - headline: _{head}_")
                if view:
                    snippet = view[:220] + ("…" if len(view) > 220 else "")
                    w(f"    - near_term_view: {snippet}")
        w(f"")

        # Per-actor breakdown
        pr_sub = pr[pr["region_id"] == r["region_id"]]
        if not pr_sub.empty:
            per_actor = (
                pr_sub.assign(_n=1)
                .groupby("ticker")
                .agg(
                    n     = ("_n",     "sum"),
                    hit_5 = ("hit_5d", lambda s: s.dropna().mean() if s.dropna().size else None),
                )
                .reset_index()
                .sort_values("n", ascending=False)
            )
            w(f"- **per-actor breakdown:**")
            w(f"")
            w(f"  | ticker | n | hit_5d |")
            w(f"  |---|---|---|")
            for _, row in per_actor.iterrows():
                w(f"  | {row.ticker} | {int(row.n)} | {_hit_rate(row.hit_5)} |")
        w(f"")
        w(f"---")
        w(f"")

    # Synthesis placeholder
    w(f"## Synthesis")
    w(f"")
    w(f"_To be filled in by reviewer after reading the evidence above._")
    w(f"")
    w(f"Suggested template:")
    w(f"")
    w(f"- **Per-region verdicts:** which of (A/B/C/D) each of the 10 best fits.")
    w(f"- **Dominant pattern:** is there a single hypothesis that explains the "
      f"sign=−1 dominance, or is it a mix?")
    w(f"- **Recommended next action:** extractor fix (which prompt/rule?), "
      f"sign-flip rule (per-region? per-theme?), recluster, or wait for data.")
    w(f"")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"  wrote {OUT_MD.relative_to(ROOT)} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
