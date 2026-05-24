# Test A — Region Distinctness (TKOS existential gate)

_Generated 2026-05-24_

## The question

Are per-region outcome distributions statistically distinguishable from the global marginal? If `P(outcome | region) ≈ P(outcome)`, the regions are decorative — spatial proximity in embedding space adds no predictive structure, and the TKOS architecture cannot honestly claim 'regional governance.'

This is the **existential gate** for the substrate.

## Locked thresholds (set before seeing the data)

| # | Criterion | Threshold |
|---|---|---|
| 1 | Chi-square `p<0.05` fraction in public regions | ≥ 30% |
| 2 | Median KL divergence across public regions | ≥ 0.02 nats |
| 3 | Public regions with KL ≥ 0.1 nats | ≥ 5 regions |

All three must hold. Primary horizon: `5d`.

## Verdict

**Overall:** `FAIL`

| Criterion | Observed | Threshold | Pass? |
|---|---|---|---|
| 1 chi-square p<0.05 | 8/51 = 15.7% | ≥ 30% | ❌ |
| 2 median KL | 0.0270 nats | ≥ 0.02 | ✅ |
| 3 regions with KL ≥ 0.1 | 11 | ≥ 5 | ✅ |

## Corpus stats

- Total signed observations: **2,405**
- Total scored regions:      **506**
- Public-tier regions (n ≥ 10): **63**
- Global P(hit) by horizon:  5d=0.484, 10d=0.493, 20d=0.487

## Top 15 public regions by KL divergence (5d)

| # | region | theme | sign | n | P_region | KL | chi² p |
|---|---|---|---|---|---|---|---|
| 1 | `reg-769eaeee65` | Broadcom's AI Growth and Investment Potential | +1 | 10 | 1.00 | 0.7256 | nan |
| 2 | `reg-e42d12e53e` | Market Movers and Analyst Insights | -1 | 10 | 1.00 | 0.7256 | nan |
| 3 | `reg-04ce05e4f5` | Salesforce's AI-driven market dynamics | -1 | 15 | 0.93 | 0.4764 | 0.0005 |
| 4 | `reg-83de2ee3ed` | Intel's AI Strategy and Challenges | -1 | 14 | 0.07 | 0.4089 | 0.0020 |
| 5 | `reg-bdf4e73cd0` | AI infrastructure investment dynamics | -1 | 12 | 0.17 | 0.2218 | 0.0278 |
| 6 | `reg-3a20339b9b` | Salesforce stock outlook and analysis | -1 | 10 | 0.80 | 0.2124 | nan |
| 7 | `reg-fa97d6d4fe` | Datadog's strong Q4 earnings performance | -1 | 10 | 0.20 | 0.1741 | nan |
| 8 | `reg-94fd0186ad` | Local AI model performance benchmarks | -1 | 13 | 0.77 | 0.1707 | 0.0396 |
| 9 | `reg-98f1e5d930` | AI-driven growth and investment strategies | +1 | 13 | 0.23 | 0.1362 | 0.0677 |
| 10 | `reg-74c386f0c2` | Micron stock volatility and market sentiment | -1 | 29 | 0.24 | 0.1245 | 0.0089 |
| 11 | `reg-b4092e65b4` | Amazon's Satellite Strategy and Competition | +1 | 14 | 0.71 | 0.1091 | 0.0847 |
| 12 | `reg-b548702a9e` | AI chip market dynamics and trends | -1 | 30 | 0.27 | 0.0988 | 0.0172 |
| 13 | `reg-fa3c18b522` | AI stock investment opportunities | -1 | 17 | 0.29 | 0.0747 | 0.1172 |
| 14 | `reg-08c0a6a5ba` | AI-driven growth in tech stocks | +1 | 27 | 0.30 | 0.0729 | 0.0509 |
| 15 | `reg-74e4c4238a` | AI investment strategies and outlook | -1 | 10 | 0.30 | 0.0700 | nan |

## Interpretation

At least one locked criterion failed: chi-square fraction (15.7% < 30%).

**The spatial-proximity premise is not unambiguously supported.** Before proceeding with the framing batch, the recovery conversation is needed: are the regions clustered on the wrong features, are the outcomes too coarse, or do only a subset of regions carry signal? Halt vocabulary calcification until this is resolved.

