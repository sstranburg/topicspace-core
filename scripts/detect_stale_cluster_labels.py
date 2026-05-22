"""
F-007 V2 phase 2 sister-fix: stale cluster label detector (v2).

The Datadog mislabel ("Datadog's strong Q4 earnings performance" attached to
predominantly bearish DDOG/SNOW expectations) reveals the actual staleness
pattern in this stack:

  The label was named based on the cluster's EVENT MEMBERS (Q4 earnings news,
  positive framing). But the EXPECTATIONS attaching to the cluster — which is
  what downstream consumers see via /actor/[ticker] Thesis Trail and
  /architecture L4 — are nearest-centroid LLM outputs that may have a totally
  different direction distribution than the source news.

So a label can be "stale" from day one if it captures the news framing while
attached expectations capture a different sentiment.

Method (v2 — replaces the broken pre/post-date logic):

For each labeled cluster with at least MIN_ATTACHED expectation versions:
  1. Compute attached-direction skew = (n_pos - n_neg) / n_signed
     ranges from -1 (all bearish) to +1 (all bullish)
  2. Compute label-implied sentiment by keyword scan over the label text
     -1 = clearly negative framing, +1 = clearly positive, 0 = ambiguous
  3. Flag as stale candidate when:
     - |label_sentiment| >= LABEL_SENT_FLOOR  (label commits to a direction)
     - |attached_skew|   >= SKEW_FLOOR        (expectations commit too)
     - sign(label_sentiment) != sign(attached_skew)  (and they disagree)

Output:
    data/derived/stale_label_candidates.parquet
    data/derived/stale_label_candidates.md
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT     = Path(__file__).resolve().parents[1]
DERIVED  = ROOT / "data" / "derived"

LABELS_PATH   = DERIVED / "cluster_labels.json"
VERSIONS_PARQ = DERIVED / "expectation_versions.parquet"
OUT_PARQ      = DERIVED / "stale_label_candidates.parquet"
OUT_MD        = DERIVED / "stale_label_candidates.md"

MIN_ATTACHED      = 5      # need this many signed attached expectations
LABEL_SENT_FLOOR  = 0.5    # label must commit to a direction
SKEW_FLOOR        = 0.5    # attached expectations must commit too
TOP_N_SURFACE     = 25

# Word lists for label sentiment scoring. Deliberately small + transparent;
# this is a heuristic to catch the OBVIOUS mismatches, not a sentiment-
# analysis pipeline. False negatives on ambiguous labels are fine
# (they don't get flagged, which is the right behavior).
POSITIVE_WORDS = {
    "strong", "growth", "momentum", "boom", "rally", "surge", "soar",
    "beat", "beats", "upbeat", "bullish", "expansion", "expanding",
    "leadership", "leading", "tailwind", "tailwinds", "outperform",
    "opportunity", "opportunities", "ascend", "ascendant", "thriving",
    "robust", "accelerating", "winning", "breakthrough", "record",
}
NEGATIVE_WORDS = {
    "weakness", "pressure", "fade", "fades", "fading", "decline",
    "declining", "selloff", "sell-off", "headwind", "headwinds",
    "challenges", "struggles", "struggle", "missed", "miss", "bearish",
    "uncertainty", "concerns", "concern", "warning", "weak", "softness",
    "pullback", "stagnant", "stagnation", "slowdown", "shrink",
    "shrinking", "deteriorating", "contradiction", "contradicted",
    "disappointing", "underperform",
}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def label_sentiment(label: str) -> float:
    """
    Score in [-1, +1]. Counts pos/neg keyword hits; normalized by total hits.
    Returns 0 if no signal.
    """
    toks = _tokenize(label)
    pos  = sum(1 for t in toks if t in POSITIVE_WORDS)
    neg  = sum(1 for t in toks if t in NEGATIVE_WORDS)
    if pos + neg == 0:
        return 0.0
    return (pos - neg) / (pos + neg)


def _skew(signs: list[int]) -> tuple[float, int]:
    """Return (skew in [-1,+1], n_signed). 0 signs excluded."""
    nonzero = [s for s in signs if s != 0]
    if not nonzero:
        return 0.0, 0
    p = sum(1 for s in nonzero if s ==  1)
    n = sum(1 for s in nonzero if s == -1)
    total = p + n
    return (p - n) / total, total


def main() -> None:
    print("=== stale cluster label detector (v2) ===")
    labels = json.loads(LABELS_PATH.read_text())
    ver    = pd.read_parquet(VERSIONS_PARQ)
    today  = dt.date.today()
    print(f"  labels: {len(labels):,}  expectation_versions: {len(ver):,}")

    rows: list[dict] = []
    for sid, lbl in labels.items():
        label_str = (lbl.get("label") or "").strip()
        if not label_str:
            continue

        sub = ver[ver["stable_cluster_id"] == sid]
        if sub.empty:
            continue

        signs = sub["direction_sign"].astype(int).tolist()
        skew, n_signed = _skew(signs)
        n_total = len(sub)
        label_sent = label_sentiment(label_str)

        # Stale candidate?
        is_candidate = (
            n_signed >= MIN_ATTACHED
            and abs(label_sent) >= LABEL_SENT_FLOOR
            and abs(skew)       >= SKEW_FLOOR
            and (label_sent * skew) < 0      # opposing signs
        )

        last_labeled = lbl.get("last_labeled_at")
        try:
            age_days = (today - dt.date.fromisoformat(last_labeled)).days if last_labeled else None
        except ValueError:
            age_days = None

        rows.append({
            "stable_cluster_id":  sid,
            "label":              label_str,
            "last_labeled_at":    last_labeled or "",
            "age_days":           age_days if age_days is not None else -1,
            "n_attached_total":   n_total,
            "n_attached_signed":  n_signed,
            "attached_skew":      round(skew, 3),
            "label_sentiment":    round(label_sent, 3),
            "is_candidate":       bool(is_candidate),
        })

    df = pd.DataFrame(rows)
    print(f"  scored {len(df):,} labeled clusters with attached expectations")
    candidates = df[df["is_candidate"]].sort_values(
        by=["n_attached_signed", "attached_skew"],
        ascending=[False, False],
        key=lambda c: c.abs() if c.name == "attached_skew" else c,
    )
    print(f"  stale-label candidates: {len(candidates):,}")

    OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQ, index=False)

    # Markdown
    lines: list[str] = []
    def w(s: str = ""): lines.append(s)

    w("# Stale cluster label candidates")
    w("")
    w(f"_F-007 V2 phase 2 sister-fix · generated {today.isoformat()}_")
    w("")
    w("**The pattern caught here:** a cluster label expresses one sentiment "
      "(e.g. *\"Datadog's strong Q4 earnings performance\"*) while the L2 "
      "expectations that attach to that cluster skew the opposite direction "
      "(predominantly bearish DDOG / SNOW reads). The label was named from "
      "the cluster's event members (news headlines); attached expectations "
      "are nearest-centroid LLM outputs that need not share the news framing.")
    w("")
    w(f"Method: for each labeled cluster with ≥ {MIN_ATTACHED} signed attached "
      f"expectations, score the label's sentiment via a small positive / "
      f"negative keyword list (`label_sentiment` in [-1, +1]) and compute the "
      f"attached expectations' direction skew (`attached_skew` in [-1, +1]). "
      f"Flag when |label_sentiment| ≥ {LABEL_SENT_FLOOR} **and** |attached_skew| ≥ "
      f"{SKEW_FLOOR} **and** the two signs oppose.")
    w("")
    w(f"Total scored clusters: **{len(df):,}**")
    w(f"Stale-label candidates: **{len(candidates):,}**")
    w("")
    w("---")
    w("")
    w(f"## Top {min(TOP_N_SURFACE, len(candidates))} candidates")
    w("")
    if candidates.empty:
        w("_(no candidates above thresholds. Either the corpus is too small, "
          "the heuristics are too strict, or labels and attached expectations "
          "currently agree.)_")
    else:
        w("| # | cluster | label | label_sent | n | attached_skew | age |")
        w("|---|---|---|---|---|---|---|")
        for i, r in enumerate(candidates.head(TOP_N_SURFACE).itertuples(), start=1):
            label = (r.label or "_(no label)_")[:55]
            sent  = f"{r.label_sentiment:+.2f}"
            skew  = f"{r.attached_skew:+.2f}"
            age   = "n/a" if r.age_days < 0 else f"{int(r.age_days)}d"
            w(f"| {i} | `{r.stable_cluster_id}` | {label} | {sent} | "
              f"{int(r.n_attached_signed)} | {skew} | {age} |")
    w("")
    w("---")
    w("")
    w("## How to act")
    w("")
    w("- Flagged clusters need a label that reflects what's *attaching* to "
      "them, not just what the source news was framed as. The Datadog case "
      "is canonical: the label promises bullish Q4-earnings but consumers "
      "see bearish DDOG / SNOW reads via the same `stable_cluster_id`.")
    w("- **Manual round first** (V1 measures): re-label the candidates by "
      "hand or with a one-off LLM prompt that includes both the label-time "
      "news titles AND a sample of currently-attached expectation headlines. "
      "Inspect that the new labels actually describe the merged content.")
    w("- **Automated relabel** (V2 acts): wire the labeler in "
      "`build_cluster_lineage.py` to consider attached expectations alongside "
      "member titles when scoring need_relabel, AND to include attached "
      "expectations in the LLM relabel prompt context. Ships once V1 has "
      "validated the threshold logic on a few rounds.")
    w("")
    w("## Caveats")
    w("")
    w("- The label-sentiment scorer is a small keyword heuristic. It will "
      "miss labels whose sentiment is conveyed via domain words not in the "
      "list (e.g. \"foundry pivot\" reads neutral here but may carry "
      "implicit framing). Edit `POSITIVE_WORDS` / `NEGATIVE_WORDS` at the "
      "top of this script to extend.")
    w("- A skew threshold of "
      f"{SKEW_FLOOR} requires fairly uniform attachment direction. Mixed "
      "clusters (where the label is technically wrong but skew is weak) "
      "won't surface. That's intentional — V1 should only flag the obvious.")
    w("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nwrote {OUT_PARQ.relative_to(ROOT)}  ({len(df):,} rows)")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")

    # Console summary
    print()
    print("  top stale-label candidates:")
    for r in candidates.head(10).itertuples():
        label = (r.label or "")[:60]
        print(f"    {r.stable_cluster_id}  sent={r.label_sentiment:+.2f}  "
              f"skew={r.attached_skew:+.2f}  n={int(r.n_attached_signed):>3}  "
              f"  label: {label}")


if __name__ == "__main__":
    main()
