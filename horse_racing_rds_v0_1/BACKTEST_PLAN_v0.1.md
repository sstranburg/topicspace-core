# RDS Backtest Plan — v0.1

**Date:** 2026-06-07
**Status:** v0.1 scope draft. Minimum viable backtest design for the Horse Racing RDS framework.
**Predecessor:** [`HORSE_RACING_RDS_SPEC_v0.1.md`](./HORSE_RACING_RDS_SPEC_v0.1.md)

---

## §0 The research question

> *Does lifecycle-aware, action-specific divergence improve bet construction versus static handicapping notes?*

This is NOT "can we pick winners?" Picking winners is hard and noisy enough that even a real edge is hard to detect in small samples. The real test is whether the action-specific divergence reduces bet-shape mistakes — the failure mode the Belmont 2026 dogfooding surfaced.

The hypothesis being tested:

> *Adding L3 lifecycle structure to L2 belief snapshots, then mapping the resulting RDS into action-specific bet shapes, produces better bet construction than (a) the market baseline alone, (b) static L2 handicapping notes alone, or (c) lifecycle-aware analysis without typed-action discipline.*

Falsifiable. If RDS-typed bets don't outperform L2-static or market-baseline strategies on bet-construction metrics (defined in §4), the framework didn't add value.

---

## §1 Population

### §1.1 Race set

**Starter target:** 100–300 graded stakes races at distances ≥1¹⁄₈ miles from the NYRA circuit (Belmont, Saratoga, Aqueduct).

**Rationale for narrow scope:**
- Stakes races have richer trip data, better media coverage, and more reliable workout reporting.
- Distance ≥1⅛ miles keeps the substrate relevant to the Belmont/Travers use case.
- Single circuit controls for surface and bias variation.
- 100-300 races is small enough to be tractable, large enough to bucket lifecycle patterns.

**Time window:** 2018–2025 (8 years). Avoid pre-2017 if takeout structures changed significantly; avoid the current year to leave a held-out test set.

**Held-out test:** 2026 stakes (run after the backtest is locked) are the out-of-sample test. Belmont 2026 itself becomes one such data point.

### §1.2 Per-horse requirement

Each horse in the field must have at least 3 prior starts in the data window — otherwise L3 lifecycle cannot be constructed and the horse is excluded from RDS-based bets (the strategy treats them as N/A, not as a default-bet).

This means very early-career horses (most 2yos, some lightly-raced 3yos) are de facto excluded from the RDS strategies. That's a known limitation — the market often misprices these horses too, but the framework doesn't speak to them. Static-L2 strategies can include them.

---

## §2 Strategies compared

Five strategies generate per-race bet recommendations against the same odds and pool data. ROI and accuracy are compared across all five.

| Strategy | Inputs | Bet construction |
|---|---|---|
| **S1. Market baseline** | Final win odds only | Bet the favorite to win at $2; or bet the second favorite to place at $2. Two variants. |
| **S2. L2 static** | Today's belief snapshot per horse (form, freshness, class, distance, pedigree) | Top-rated L2 horse to win; second-rated to place. No lifecycle, no typed actions. |
| **S3. L2 + L3 lifecycle** | L2 + the lifecycle of each belief across prior races | Pick the strongest-L3 horse(s); bet according to a fixed sizing heuristic (e.g., $10 win, $10 place). |
| **S4. L2 + L3 + RDS (typed)** | S3 + action-specific RDS computation per horse, per outcome | Bet *only* where RDS_type > confidence_band(type); type-appropriate bet shapes from INTEGRATION_PATTERN §7 mapping. Hold cash if no positive-RDS bets. |
| **S5. L2 + L3 + RDS + environmental overlay** | S4 + post-time track condition + late scratches + odds movement adjustments | Same as S4 but with environmental_modifier applied per RULES_SPEC v0.1 §9. |

Each strategy gets a hypothetical $20 per race. Strategies that pass on a race carry over $0 (held cash counts as cash held, not as $20 spent).

### §2.1 What S4 vs S5 controls for

S4 vs S5 isolates the environmental-overlay's contribution. If S5 ≈ S4 across the backtest, the overlay didn't add signal (the L3 lifecycle already captured what mattered). If S5 > S4 on slop/weather-disrupted races but ≈ on clean ones, the overlay carries weather-specific signal.

### §2.2 What S3 vs S4 controls for

S3 vs S4 isolates the **typed-action discipline** — does mapping lifecycle to bet *shape* matter, given the same lifecycle analysis? This is the most direct test of the integration-pattern §7 hypothesis: typed action discipline bridges the substrate-to-action gap.

---

## §3 Backtest mechanics

### §3.1 Per-race procedure

1. Reconstruct each horse's L1 evidence as of race day (no future leakage).
2. Compute L2 beliefs from L1 per the schema.
3. Compute L3 lifecycle for each L2 belief by walking the horse's prior races in order.
4. Apply L4 calibration (from a training subset) to produce calibrated lifecycle probabilities per outcome type per horse.
5. Pull final market odds and pool sizes; compute market-implied probabilities per outcome type per horse.
6. Compute RDS_type for each (horse, outcome-type) pair.
7. Apply each strategy's bet-construction rule to produce the strategy's bet allocation.
8. After the race, settle each strategy's bets at official payouts.
9. Log per-strategy ROI, bet types, confidence buckets.

### §3.2 Training / calibration split

- **Training:** 70% of races (~70-210 depending on N) for L4 calibration. Group by lifecycle pattern; compute realized rates.
- **Backtest:** 30% (~30-90 races) for strategy comparison. Strategies use L4 calibrated probabilities computed *only* from the training subset.
- **Held-out (2026 onward):** future races, including Belmont 2026 and Travers 2026, are pure out-of-sample.

### §3.3 No future leakage rules

- Workouts only from prior to race day.
- Speed/pace figures only from prior races.
- Late odds movement allowed only up to a fixed cutoff (e.g., post – 10 minutes), not from after the race.
- Replay-derived L1 evidence (per RDS spec §4) only from races before today; never includes today's race.

---

## §4 Evaluation metrics

Six metrics per strategy, plus calibration analysis.

### §4.1 Outcome metrics

1. **Win accuracy** — fraction of races where the strategy's primary win bet (if any) hit.
2. **Board-hit rate** — fraction of races where the strategy had ≥1 horse hit the board (1st-3rd).
3. **Place/show ROI** — net return on all place + show bets across the backtest.
4. **Exacta-anchor usefulness** — when the strategy used a horse as an exacta anchor (top or bottom), how often did the exacta cash?
5. **Longshot ROI** — net return on all longshot (≥10-1) bets.
6. **Aggregate ROI** — net return across all bets, all races. Includes held cash where strategies pass.

### §4.2 Calibration analysis

Bucket each strategy's *win bets* by confidence (e.g., 0-25% / 25-50% / 50-75% / 75-100% implied confidence). For each bucket, compute realized win rate. A well-calibrated strategy has realized rates close to the bucket midpoints.

Same for place bets bucketed by board confidence.

The point: a strategy can have low ROI but be well-calibrated (it picks the right horses, just at the wrong prices), or high ROI but poorly calibrated (it gets lucky on a few longshots).

### §4.3 Bet-shape integrity metric (the load-bearing one)

For each strategy's bets, score whether the bet *shape* (win / place / show / exacta-anchor / longshot / hedge) matched the horse's typed RDS profile, per the integration-pattern §7 mapping. Strategies S1-S3 don't have typed RDS profiles — they're scored on whether the bet shape was *appropriate* for the static/lifecycle reading.

This is the metric the Belmont 2026 result would have flunked across the board: every model had the right horse but the wrong bet shape. Bet-shape integrity is what the typed RDS framework is supposed to fix.

If S4 and S5 have markedly better bet-shape integrity than S1-S3 — even if their ROI is similar — that's the positive result the framework predicts.

---

## §5 Falsifiability gates (pre-registered)

Before running the backtest, lock the criteria for "the framework added value":

| Criterion | Threshold |
|---|---|
| S4 aggregate ROI vs S2 | ≥ +5 percentage points over the backtest (60+ races) |
| S4 bet-shape integrity vs S2 | ≥ +15 percentage points (measurably more "right shape" bets) |
| S4 calibration (win bucket midpoint vs realized) | Mean absolute deviation ≤ 10 percentage points |
| S5 vs S4 on weather-disrupted races (subset) | S5 outperforms S4 by ≥ +5 ROI on those races |
| L4 → L2 feedback survives held-out test | The lifecycle patterns that were predictive in the training subset remain predictive in the backtest subset |

**If none of these clear:** the framework didn't add value. Document honestly; do not torture the data.

**Anti-overfitting discipline:**
- The strategy bet-construction rules are locked before the backtest runs.
- L4 calibration is computed only on the training subset; no peeking at backtest results before locking.
- Any post-hoc tuning becomes a v0.2 hypothesis to re-test on new races, not a claim to attach to v0.1.

---

## §6 What this backtest does NOT test

- Whether the framework works on non-stakes races (allowance, claiming, MSW). Different markets, different evidence quality.
- Whether the framework works on shorter distances or turf races. Surface and distance affinity matter.
- Whether real-money bankroll dynamics (Kelly sizing, variance survival) work. The backtest is bet-construction, not bet-sizing.
- Whether the framework works prospectively at scale. Markets adapt; an edge that existed in 2018-2025 may not exist now.
- Whether replay-derived evidence (RDS spec §4) is reliably extractable at scale. v0.1 uses chart comments and basic trip notes; v0.2 may add automated replay analysis.

---

## §7 What this backtest WOULD demonstrate, if it passes

A small, contained demonstration that:

- Lifecycle-aware belief modeling (Belief Stack pattern) produces better bet-construction decisions in a noisy real-world domain.
- Action-specific divergence (typed RDS) bridges the substrate-to-action gap that the Belmont 2026 dogfooding surfaced.
- The L1→L4 layer model, with L4→L2 feedback, applies meaningfully to a domain outside the original substrate (Claude Code session logs).

That's it. Not "AI beats horse racing." Not "Belief Stack is universal." Just: the architectural pattern surfaces useful structure here too.

---

## §8 Sequencing

1. **Lock this plan (v0.1).** Pre-register strategies, metrics, and falsifiability gates.
2. **Gather data.** Race population, results, pool data, charts. See §9.
3. **Build L1 → L2 → L3 pipeline.** Mechanical extraction of beliefs and lifecycle from race data.
4. **Train L4 calibration on training subset.**
5. **Run all five strategies on backtest subset.**
6. **Score against §4 metrics + §5 gates.**
7. **Write `BACKTEST_RESULT_v0.1.md`** — honest report, includes null results if applicable.
8. **Decide whether to iterate to v0.2** (richer beliefs, more strategies) or **declare the framework non-additive** in this domain.

Optional Travers 2026 application: hold the Travers field as another out-of-sample data point and apply S4/S5 live.

---

## §9 Data sources needed

For the backtest, in rough priority order:

1. **Historical race results** — Equibase, Daily Racing Form, NYRA results
2. **Odds and final pools** — TwinSpires, NYRA Bets archive, Equibase Premium
3. **Speed figures** — Beyer (Daily Racing Form), Brisnet, Trakus where available
4. **Running style / pace data** — Brisnet pace figures, Trakus sectional times
5. **Distance and surface history** — Equibase past performances
6. **Workouts** — DRF workouts database
7. **Trainer / jockey statistics** — Equibase, DRF stats packages, jockey-trainer pairings
8. **Weather and track condition** — race chart weather notes, NYRA track condition log
9. **Chart comments / trip notes** — Equibase chart, DRF result charts (for L1 trip evidence)
10. **Replays** — NYRA Bets video archive, TwinSpires replay center, individual track replay (for trip evidence beyond chart notes)
11. **Pedigree data** — equineline, BloodHorse stallion stats (for `pedigree_distance_match` and dosage)

Realistic assessment: items 1-7 are programmatically accessible (some behind paywalls). Items 8-11 require manual annotation or partial automation. **The v0.1 backtest scope should be sized to what's tractable to gather; if replay analysis at scale isn't feasible, drop it from v0.1 and document the limitation.**

---

*Minimum viable backtest. Designed to be falsifiable, contained, and honest. If it returns a null result, that's a valid outcome — the architectural pattern is unchanged, racing was just the wrong substrate for it. If it returns a positive result, that's a small additional data point for the main research program and a fun Travers v0.0.2 application.*
