# RDS Data Requirements — v0.1

**Date:** 2026-06-07
**Status:** v0.1 data-acquisition checklist. Decision-focused, not theory.
**Predecessors:**
- [`HORSE_RACING_RDS_SPEC_v0.2.md`](./HORSE_RACING_RDS_SPEC_v0.2.md)
- [`BACKTEST_PLAN_v0.2.md`](./BACKTEST_PLAN_v0.2.md)

---

## §0 The decision this document supports

> **Can we run a first-pass RDS backtest using only free/available data, or do we need to pay for past-performance data and speed figures?**

If yes to free-only: do a cheap v0.1 backtest with N≈50 races, document honestly, decide whether results justify paid expansion.
If no: shelve the backtest until there's a real reason to pay. The conceptual frame stands either way.

---

## §1 Per-data-item table

| Data | Needed for | Source candidates | Free? | Manual vs automated | v0.1 priority |
|---|---|---|---|---|---|
| **Final win odds** | `market_expectation` (RDS_win, RDS_longshot_upside) | Equibase free results, NYRA results, DRF | Free | Automated scrape (medium); single race manual (easy) | REQUIRED |
| **Final place / show pools** | `market_expectation` (RDS_board) | NYRA, TwinSpires, BloodHorse | Free for aggregate; paid for pool decomposition | Manual (easy per race); automation requires login | NICE-TO-HAVE — final win odds is a reasonable proxy for board too |
| **Race results (order of finish + payouts)** | Outcomes (the truth label) | Equibase free charts, NYRA, BloodHorse | Free | Automated scrape (medium); single race manual (easy) | REQUIRED |
| **Track condition (fast / good / muddy / sloppy / sealed)** | `environment_state` | Equibase charts | Free | Same scrape as results | REQUIRED |
| **Field size + scratches** | `environment_state`, normalization | Equibase charts | Free | Same scrape | REQUIRED |
| **Chart comments / trip notes** | L1 evidence for `traffic_tolerance`, `closing_authority`, `pace_independence`, `board_authority` | Equibase chart "comments" column | Free | Manual annotation; chart text per horse per race | REQUIRED (load-bearing for L1) |
| **Prior starts (last 5-10 per horse)** | L2 belief snapshots + L3 lifecycle | DRF past performances, Brisnet PPs, Equibase Premium | **PAID** ($30-100/month subscription); free alternative is per-horse manual lookup on Equibase free pages | Paid: automatable; Free: extremely manual | LOAD-BEARING — but a free-only MVP can use chart commentary + headline results as a coarse proxy |
| **Speed figures (Beyer, Brisnet, Trakus)** | `form_trajectory`, calibrating "ran well in defeat" | DRF Beyer (paid), Brisnet (paid), Equibase Premium | **PAID** (~$30-100/month) | Paid: automatable; Free: no standardized free speed figures | NICE-TO-HAVE — chart comments + finish positions are a coarse proxy |
| **Pace figures + sectional times** | `pace_independence`, `closing_authority` calibration | Brisnet (paid), Trakus where available | **PAID** | Paid: automatable | DEFER — qualitative chart comments cover this for v0.1 |
| **Workouts** | `trainer_intent` | DRF workouts (paid), some free on Equibase | Mixed | Automated for paid; manual for free | DEFER — single-race signal that's hard to validate at scale |
| **Trainer/jockey stats** | `trainer_intent` | Equibase paid, DRF stats, free jockey/trainer names on charts | Mixed | Automated for paid stats; manual for free | NICE-TO-HAVE — use coarse "Mott / Pletcher / Brown" name recognition for v0.1 |
| **Pedigree (dosage indices)** | `pedigree_distance_match` | equineline (paid), BloodHorse (limited free), Brisnet (paid) | Mixed | Manual lookups for free | DEFER — pedigree adds a feature but isn't load-bearing for v0.1 |
| **Weather (post-time conditions beyond track)** | `environment_state` weather_realized | NOAA archive (free), chart weather notes | Free | Manual cross-reference per race | DEFER — track condition is the key proxy |
| **Late odds movement (last 10 min before post)** | `environment_state` informed-money signal | NYRA Bets archive, TwinSpires (paid for historical) | Paid | Paid: automatable; otherwise unavailable | DEFER — v0.1 uses final odds only |
| **Replay videos** | Visual confirmation of L1 trip evidence | NYRA Bets video archive (free with account), TwinSpires | Free with account | Manual viewing | DEFER — chart comments are the v0.1 proxy |

---

## §2 The free-only MVP

**Hypothesis: a free-only first-pass backtest is feasible** at the cost of coarser L2/L3 inputs.

**Stack:**
- Population: 30-50 NYRA graded stakes from 2023-2025 (recent enough that all chart data is online; pre-2026 so 2026 is out-of-sample)
- Per race: pull Equibase chart (free) → extract final odds, finish, track condition, chart comments
- Per horse: pull last 3-5 prior starts from Equibase free per-horse pages → coarse L3 lifecycle (was the horse a closer last 3 starts? a board-hitter? a one-paced grinder?)
- L2 beliefs: derived from chart comment patterns + finish positions, no Beyer figures
- L4 calibration: small (30-50 races × 9 horses = 270-450 horse-races); shrinkage will dominate; expect wide confidence bands

**Limitations of free-only MVP:**
- No quantitative speed figures → form_trajectory is coarser
- No pace figures → closing_authority and pace_independence rely on chart commentary alone
- Tiny sample for L4 calibration → most patterns won't clear the shrinkage threshold
- Manual annotation per race (~30-60 min per race for L1 trip notes) → 30 races = 15-30 hours of manual work

**What the free-only MVP CAN test:**
- Does the conceptual pipeline (L1 chart-comment evidence → L2 belief snapshot → L3 coarse lifecycle → L4b runtime heuristic → bet-shape decision) produce coherent recommendations?
- Are the bet shapes the framework recommends *qualitatively different* from market-baseline bet shapes? (The bet-shape integrity metric from BACKTEST_PLAN_v0.2 §4.3.)
- Does the Market Mispricing Study (BACKTEST_PLAN_v0.2 §7) identify any patterns that survive even a small sample?

**What the free-only MVP CANNOT test:**
- Statistical significance of ROI lift (sample too small)
- Sensitivity to factor weights (no calibration to tune against)
- Generalization across surfaces/distances (single-circuit, single-class scope)

In short: the free-only MVP can validate the *plumbing* and produce a qualitative read on whether the framework feels right. It cannot prove edge.

---

## §3 The paid stretch

If the free-only MVP yields plausible-looking recommendations and you want to actually falsify the framework:

**Stack additions:**
- DRF subscription (~$50/month) → Beyer speed figures + past performances → real L2 form_trajectory and L3 lifecycle quality
- Brisnet (~$30-50/month) → pace figures + class ratings → calibrated `closing_authority` and `pace_independence`
- Optional: Equibase Premium (~$15/month) → equipment changes + medication + trainer stats

**Total cost:** ~$80-100/month while building the dataset. Could close subscriptions once historical data is captured (1-2 months).

**What this enables:**
- 200-300 race population (the v0.2 backtest target)
- Calibrated L2 beliefs (Beyer-grounded form_trajectory)
- Pace-figure-derived `closing_authority` validation
- Confidence bands narrow enough that some patterns clear the shrinkage threshold

---

## §4 Recommended decision

| Path | Cost | Effort | Result quality |
|---|---|---|---|
| **A. Skip the backtest entirely.** Accept the cross-substrate-pattern insight as the real payload. | $0 | 0 hours | Conceptual frame intact; no empirical validation |
| **B. Cheap free-only MVP (30-50 races).** Validate plumbing, produce qualitative read, document honestly. | $0 | 15-30 hours manual annotation | Plumbing validated; no statistical claim possible |
| **C. Paid stretch (200-300 races).** Real backtest per BACKTEST_PLAN_v0.2. | ~$200 (2 months subscriptions) | 40-80 hours data wrangling + scripting | Falsifiable test possible; null result is informative |

**Recommendation: A is the right default unless you genuinely want to play.**

The insight that came out of this side experiment was the cross-substrate-pattern memory (`project_nds_is_cross_substrate_pattern.md`) and the L4a/L4b split (`project_l4_split_batch_calibration_vs_runtime_heuristics.md`). Those are the real payload. The backtest would either confirm the framework's bet-shape discipline (probably) or fail to (also possibly), but either result is a minor data point compared to the conceptual moves the side experiment already produced.

**B is worth doing only if** you want a fun weekend project AND the Travers 2026 application would benefit from having a small "this is what the framework actually outputs" reference dataset. The Travers run can otherwise apply the framework qualitatively per the Belmont post-mortem pattern, no backtest needed.

**C is the right path only if** the free MVP turns up something genuinely interesting (a pattern that looks like real edge), AND you want to stand up the framework as a real backtest-able product. Probably not the right call now.

---

## §5 Containment

Per Sue's note: *"The conceptual frame is now done. More theorizing will probably add noise."*

This doc is the bounded next step. Beyond this, the next decision points are:

- **A.** Close the loop. RDS is now a fully-scoped side experiment with a clear decision tree for whether to run it.
- **B or C.** Spend the time / money. Document honestly; do not torture data.
- **Travers application.** Apply RDS qualitatively pre-race (same as Belmont post-mortem). No backtest needed.

The cross-substrate-pattern insight stands on its own. The backtest is optional unless you want to play.

---

*Bounded data-acquisition checklist. Decision-focused. No new framework theory. Closes the v0.2 RDS scope cycle with a clear "what would it take to actually run this, and is it worth it?" answer.*
