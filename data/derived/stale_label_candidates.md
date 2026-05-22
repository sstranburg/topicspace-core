# Stale cluster label candidates

_F-007 V2 phase 2 sister-fix · generated 2026-05-21_

**The pattern caught here:** a cluster label expresses one sentiment (e.g. *"Datadog's strong Q4 earnings performance"*) while the L2 expectations that attach to that cluster skew the opposite direction (predominantly bearish DDOG / SNOW reads). The label was named from the cluster's event members (news headlines); attached expectations are nearest-centroid LLM outputs that need not share the news framing.

Method: for each labeled cluster with ≥ 5 signed attached expectations, score the label's sentiment via a small positive / negative keyword list (`label_sentiment` in [-1, +1]) and compute the attached expectations' direction skew (`attached_skew` in [-1, +1]). Flag when |label_sentiment| ≥ 0.5 **and** |attached_skew| ≥ 0.5 **and** the two signs oppose.

Total scored clusters: **430**
Stale-label candidates: **10**

---

## Top 10 candidates

| # | cluster | label | label_sent | n | attached_skew | age |
|---|---|---|---|---|---|---|
| 1 | `theme-4d240b54` | AI-driven growth and investment strategies | +1.00 | 88 | -0.70 | 112d |
| 2 | `theme-10d5592e` | Fintech growth and market disruptions | +1.00 | 26 | -0.61 | 125d |
| 3 | `theme-a38f55e6` | AI-driven growth and valuation debates | +1.00 | 22 | -0.91 | 104d |
| 4 | `theme-d71b596b` | AI stock investment opportunities | +1.00 | 21 | -0.62 | 36d |
| 5 | `theme-8ae763c4` | Nuclear energy investment surge | +1.00 | 15 | -0.73 | 155d |
| 6 | `theme-309a26c5` | Palantir's Controversial Positioning and Growth | +1.00 | 15 | -0.60 | 2d |
| 7 | `theme-0286d3ef` | Intel stock surge and optimism | +1.00 | 13 | -1.00 | 105d |
| 8 | `theme-f22efe9e` | Datadog's strong Q4 earnings performance | +1.00 | 10 | -1.00 | 70d |
| 9 | `theme-13285a1e` | AI-driven valuation opportunities in tech | +1.00 | 5 | -0.60 | 72d |
| 10 | `theme-67bd3e91` | AI chip market dynamics and growth | +1.00 | 5 | -0.60 | 2d |

---

## How to act

- Flagged clusters need a label that reflects what's *attaching* to them, not just what the source news was framed as. The Datadog case is canonical: the label promises bullish Q4-earnings but consumers see bearish DDOG / SNOW reads via the same `stable_cluster_id`.
- **Manual round first** (V1 measures): re-label the candidates by hand or with a one-off LLM prompt that includes both the label-time news titles AND a sample of currently-attached expectation headlines. Inspect that the new labels actually describe the merged content.
- **Automated relabel** (V2 acts): wire the labeler in `build_cluster_lineage.py` to consider attached expectations alongside member titles when scoring need_relabel, AND to include attached expectations in the LLM relabel prompt context. Ships once V1 has validated the threshold logic on a few rounds.

## Caveats

- The label-sentiment scorer is a small keyword heuristic. It will miss labels whose sentiment is conveyed via domain words not in the list (e.g. "foundry pivot" reads neutral here but may carry implicit framing). Edit `POSITIVE_WORDS` / `NEGATIVE_WORDS` at the top of this script to extend.
- A skew threshold of 0.5 requires fairly uniform attachment direction. Mixed clusters (where the label is technically wrong but skew is weak) won't surface. That's intentional — V1 should only flag the obvious.

