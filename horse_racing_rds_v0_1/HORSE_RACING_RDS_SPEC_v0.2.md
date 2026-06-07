# Horse Racing RDS — Spec v0.2

**Date:** 2026-06-07
**Status:** v0.2 scope draft. Supersedes v0.1.
**Predecessor:** [`HORSE_RACING_RDS_SPEC_v0.1.md`](./HORSE_RACING_RDS_SPEC_v0.1.md) (retained as audit trail; do not implement against)

**v0.1 → v0.2 amendments (six structural improvements, per Sue 2026-06-07):**

1. **Multi-dimensional RDS, not scalar.** RDS decomposes into five factors (readiness / lifecycle_confirmation / novelty / crowding / market_expectation), echoing how TopicSpace NDS actually composes signal. Single-scalar formulation discarded.
2. **Belief recency + belief momentum as first-class L3 outputs.** A belief strengthened 7 races ago ≠ a belief strengthened last race. Decay matters; the Belief Stack lifecycle vocabulary already supports this.
3. **`win_authority` and `board_authority` are separate L2 belief families.** The Belmont 2026 Wallabee error — a board-hitter bet to win — was a structural failure that one combined "readiness" score would have permitted.
4. **Environmental overlay carries `environment_state` with REALIZED values.** "Track condition forecast" is not the same as "track turned sloppy at post." The overlay updates beliefs based on what actually happened, not what was projected.
5. **L4 calibration adds the Market Mispricing Study question.** Not just "does L3 add ROI" but "which specific lifecycle patterns repeatedly fool the market." That is the TopicSpace question, applied here.
6. **Backtest structure is the architectural test** (L2 vs L2+L3 vs L2+L3+L4 feedback) per `BACKTEST_PLAN_v0.2.md`. The point is not "did the horse model make money" but "did lifecycle matter? did calibration of lifecycle matter?"

This document inherits §0–§9 framing from v0.1 with updates and rewrites §5, §6, §9, §10, §11 substantively.

---

## §0 What this is (and isn't)

Unchanged from v0.1. Toy side experiment. Falsifiable. Not part of the main Belief Stack paper.

One addition in framing: **the RDS framework is one of three known instances** of the cross-substrate divergence pattern. See `project_nds_is_cross_substrate_pattern.md`. RDS is interesting partly because it's a test of whether the geometry (maintained state + lifecycle + market expectation + realized outcome) transfers to a noisy real-world prediction domain.

---

## §1 RDS ↔ NDS relationship (v0.2 — sharpened)

**The pattern, abstracted:**

```
Divergence_signal =
    maintained_state_strength
  + lifecycle_reconfirmation
  + novelty_in_field
  − crowding_with_others
  − market_already_pricing_it_in
```

Both NDS and RDS instantiate this geometry. The substrate names change; the shape doesn't.

| Factor | TopicSpace (NDS) | RDS (horse-racing) |
|---|---|---|
| `maintained_state_strength` | belief substrate over actor (narrative pressure) | L2 belief snapshot for this horse |
| `lifecycle_reconfirmation` | belief life-events: born / strengthened / contradicted | L3 lifecycle of L2 beliefs across prior races |
| `novelty_in_field` | distinctiveness of narrative vs other actors | distinctiveness of this horse's profile vs others in the field |
| `crowding_with_others` | how many actors share a similar narrative | how many other horses share the same thesis |
| `market_already_pricing_it_in` | option pricing / price movement | pool-implied probability per outcome type |

The v0.1 framing (RDS = lifecycle_P − market_P) was a single-axis collapse of these. v0.2 keeps the multi-factor decomposition because it tells you *what kind of divergence you're seeing*, which informs *what kind of action shape is appropriate*.

---

## §2 Why action-specific RDS

Unchanged from v0.1. RDS_win / RDS_board / RDS_exacta_anchor / RDS_longshot_upside / RDS_weather_hedge remain the v0.2 action-type set.

NEW in v0.2: each action type can have its OWN factor profile. A horse with strong readiness + lifecycle but low novelty (everyone in the field is also a closer) may have positive RDS_board (the L4 calibration for that profile is high board rate) and weak RDS_win (the crowding eats the win edge). The multi-factor view makes this legible.

---

## §3 Why L3 lifecycle may add signal beyond static L2 state

Unchanged from v0.1, plus the recency addition:

**v0.2 addition (per Sue's update):** lifecycle reconfirmation is not binary. A belief strengthened 7 races ago is not the same as a belief strengthened last race. v0.2 makes `belief_recency` and `belief_momentum` first-class L3 outputs.

```
belief_recency  = races since last strengthened (or born, if never strengthened)
belief_momentum = number of strengthened events in last N races / N
```

Where N is a tuning parameter (default N=5 races).

A belief with high momentum (strengthened in 3 of last 5 races) and low recency (last strengthened was last race) is the strongest possible L3 signal. A belief with low momentum (strengthened once 8 races ago, then dormant) is weakly supported.

In RDS terms: the `lifecycle_reconfirmation` factor is computed using recency and momentum, not just total-confirmations-ever.

---

## §4 L1 — Raw evidence inputs

Unchanged from v0.1. Core L1 + trip/replay-derived L1 evidence as previously specified. The trip/replay inputs (traffic, splitting horses, sustained late acceleration, passing tired vs creating own move, pace response, closing-authority confirmation, pattern repetition) update specific L2 beliefs and carry their own warrants.

---

## §5 L2 — Belief families (v0.2 — split readiness into win_authority + board_authority)

Each L2 belief is a typed claim with a warrant trail to L1 evidence and an L3 lifecycle.

**v0.2 belief families:**

| Belief family | One-line meaning |
|---|---|
| `form_trajectory` | improving / steady / declining |
| `freshness` | rested productively / over-raced / over-rested |
| `class_trajectory` | moving up / staying in class / dropping |
| `distance_fit` | suited to today's trip / questionable / unproven |
| **`win_authority`** | demonstrated ability to *win* races, not just finish them (NEW v0.2 per Sue's point 3) |
| **`board_authority`** | demonstrated ability to *hit the board* (1st-3rd) under varied conditions (renamed from `board_resilience`) |
| `closing_authority` | ability to produce decisive late move INDEPENDENT of perfect pace setup |
| `traffic_tolerance` | can navigate or recover from traffic trouble |
| `pace_independence` | can run a winning race across different pace shapes |
| `trainer_intent` | spot/prep indicates today is a primary target |
| `pedigree_distance_match` | sire/dam page supports today's distance |
| `surface_affinity_for_slop` | demonstrated form on off-tracks (conditional belief — operative only when env overlay says slop) |

**The win_authority vs board_authority split (v0.2 — the load-bearing addition):**

A horse can have strong `board_authority` (consistently hits 1st-3rd) without strong `win_authority` (rarely actually wins). The market knows this — chronic place horses get heavy place-pool action and lighter win-pool action.

The Belmont 2026 lesson: Chief Wallabee had multi-confirmed `board_authority` but no `win_authority` lifecycle. The models (including me) treated him as a primary win bet at 3-1, which was a *category error* — a board-authority horse maps to board/show/exotic-underneath actions, not to win bets. Splitting these into two belief families forces the action-policy mapping to honor the distinction.

`win_authority` and `board_authority` can be strengthened independently:
- Chief Wallabee's `board_authority` was strengthened in every recent stakes start; his `win_authority` was strengthened in zero (never won a graded stakes).
- Golden Tempo's `win_authority` was strengthened in the Risen Star and the Kentucky Derby; his `board_authority` was strengthened across many more races.
- An ideal exotics target (high board_authority, no win_authority, longish price): a pure underneath horse.

The L4 calibration in §7 should bucket horses by their win_authority/board_authority profile and check whether the realized rates differ systematically.

---

## §6 L3 — Lifecycle transitions + recency + momentum (v0.2 expansion)

Belief lifecycle vocabulary unchanged from v0.1 / RULES_SPEC v0.3.2:

```
born → strengthened → weakened → contradicted → retired
```

**v0.2 — three first-class L3 outputs per belief:**

1. **Confirmation count** — total strengthened events since birth (the v0.1 view)
2. **Belief recency** — races since the last strengthened event
3. **Belief momentum** — strengthened events in the last N=5 races, divided by 5

Combined, these give a richer view than confirmation-count alone. Two horses with the same total confirmation count can have very different recency and momentum profiles, which the L4 calibration may show predict differently.

Examples:

| Horse / belief | Confirmations | Recency | Momentum | L3 signal |
|---|---|---|---|---|
| Golden Tempo / closing_authority | 4 (Risen Star, La. Derby, KY Derby, Belmont) | 0 races (just confirmed) | 0.8 (4 of last 5 races) | Very strong |
| Hypothetical horse with same total | 4 (all 8+ races ago) | 8 races | 0.0 | Weak — stale belief |

The v0.1 framing would have rated these identically. v0.2 distinguishes them sharply.

`lifecycle_reconfirmation` in the multi-factor RDS formula uses recency and momentum, not raw confirmation count.

---

## §7 L4 — Calibration + Market Mispricing Study (v0.2 addition per Sue's point 5)

L4 unchanged from v0.1 conceptually: across many horses with similar L3 lifecycle patterns, what outcomes actually materialized?

**v0.2 — primary L4 research question shifts:**

Old (v0.1):
> Does L3 lifecycle improve ROI?

New (v0.2):
> Which lifecycle patterns repeatedly fool the market?

This is the TopicSpace question applied here. The L4 layer becomes a **Market Mispricing Study**:

```
For each candidate lifecycle pattern (e.g., "closing_authority confirmed ≥3 times with recency ≤2 races"):
    1. Identify all horses in the L4 training population matching the pattern
    2. Compare their realized outcomes to the market's implied probabilities at post
    3. Compute the mispricing edge per outcome type
    4. Flag patterns where the market systematically underprices (positive edge)
       or overprices (negative edge) the outcome
```

Candidate lifecycle patterns to test for systematic mispricing:

- 3+ confirmed `closing_authority` with high momentum
- Improving `class_trajectory` with strong `freshness`
- Strong `pedigree_distance_match` × strong `freshness`
- Pace-independent closers in fields with light early speed
- Multi-confirmed `board_authority` without `win_authority` (board-hitters)
- Lightly-raced horses with `trainer_intent` strongly positive (sharp work pattern + prime spot)

The Market Mispricing Study produces the L4 calibration data that feeds RDS computation. It also produces its own report — *here are the lifecycle profiles that are systematically mispriced* — which is the closest analog to TopicSpace's NDS-discovery work.

---

## §8 L4 → L2 feedback

Unchanged from v0.1. The calibration tells us which belief families and which lifecycle patterns matter, which feeds back to L2 belief schema (weight tuning, family revision).

**v0.2 addition:** the win_authority / board_authority split is itself an example of L4→L2 feedback in action. The single `readiness` concept in v0.1 was empirically inadequate (the Belmont Wallabee case); v0.2 splits it into two families based on observation. Future L4 evidence may produce further splits or merges.

---

## §9 Environmental overlay — realized values (v0.2 sharpening per Sue's point 4)

Per Sue's constraint reaffirmed and tightened: weather, track condition, scratches, late odds are NOT part of horse lifecycle. They are a current-state overlay that modifies which lifecycle beliefs are operative today.

**v0.2 introduces `environment_state` with explicit REALIZED values:**

```
environment_state = {
    track_condition:      <realized_at_post>,    # fast / good / muddy / sloppy / sealed
    track_bias:           <realized_during_card>, # closer-favoring / front-favoring / rail / outside
    pace_realization:     <observed_after_start>, # faster-than-expected / slower / as-expected
    weather_realized:     <at_post>,              # clear / light-rain / heavy-rain / wet-but-not-raining
    field_scratches:      <list_of_scratched_horses>,
    late_odds_movement:   <delta_in_last_10_min_per_horse>,
}
```

Each field has a **realized** value distinct from any pre-race forecast. The Belmont 2026 lesson:

> The Belmont lesson wasn't "rain forecast existed." It was "what actually happened?"

The environmental_modifier in the RDS formula is computed from `environment_state`, not from forecasts. Forecasts are L1 evidence inputs that *predict* the environment_state; the actual environment_state is what updates which beliefs are operative.

For backtest purposes (per `BACKTEST_PLAN_v0.2.md`), the environment_state is observable after each race. For live application, it requires a post-time-cutoff capture (e.g., the track condition reported at 10 minutes to post is the value used).

---

## §10 RDS formulas (v0.2 — multi-dimensional)

### §10.1 The decomposition form (v0.2 canonical)

```
RDS_type(horse) = 
       w_R   ⋅ readiness(horse, type)
     + w_L   ⋅ lifecycle_confirmation(horse, type)
     + w_N   ⋅ novelty(horse, field, type)
     − w_C   ⋅ crowding(horse, field, type)
     − w_M   ⋅ market_expectation(horse, type)
       ⋅ environmental_modifier(type, environment_state)
       ± confidence_band(horse, type)
```

Where:

- **`readiness(horse, type)`** — the L2 belief snapshot strength for the outcome type. For RDS_win: weighted score of `win_authority` + `class_trajectory` + `distance_fit` + `freshness`. For RDS_board: weighted by `board_authority` instead.
- **`lifecycle_confirmation(horse, type)`** — the L3 reconfirmation strength using recency and momentum, weighted toward beliefs relevant to the type.
- **`novelty(horse, field, type)`** — how distinctive this horse's profile is in this specific field. Field-relative.
- **`crowding(horse, field, type)`** — how many other horses share a similar profile (deflates expected edge).
- **`market_expectation(horse, type)`** — the takeout-adjusted, pool-implied probability for this outcome type.
- **`environmental_modifier(type, environment_state)`** — multiplier (default 1.0) that scales based on realized environment. Sloppy track + closing horses without slop form → modifier < 1.0 for RDS_win.
- **`confidence_band(horse, type)`** — uncertainty width. Wider for thin L3 samples, rare patterns, large environmental modifiers.
- **`w_R, w_L, w_N, w_C, w_M`** — factor weights. Initial v0.2 values: w_R = 0.3, w_L = 0.35, w_N = 0.15, w_C = 0.10, w_M = 0.10. To be calibrated empirically against the backtest.

A positive RDS_type indicates the lifecycle profile + market structure suggests this outcome type is underpriced for this horse. The decomposition lets you see *which factor* is contributing — readiness vs lifecycle confirmation vs market mispricing vs anti-signal from crowding.

### §10.2 Decision rule

Bet on `RDS_type > confidence_band(horse, type)` AND only via action shapes from the integration-pattern §7 mapping appropriate for that type:

- Positive RDS_board → place / show / exacta-bottom
- Positive RDS_win → win bet (only if positive; never just "value against the chalk")
- Positive RDS_longshot_upside → small probe; never primary
- Positive RDS_weather_hedge → tiny asymmetric flyer, conditional on environment_state confirming the hedge thesis

Sue's Belmont post-mortem caught this directly: a positive RDS_board on Chief Wallabee did NOT license a win bet, even though my handicapping read on him was sound.

### §10.3 Anti-overclaim caveats (unchanged from v0.1)

- L4 calibration may overfit small/biased populations
- Market baselines drift across years
- Positive RDS on a type doesn't mean you should always bet it
- The framework is bet-construction guide, not magic +EV detector
- The factor weights w_R...w_M are v0.2 initial guesses; revising them requires backtest evidence, not vibes

---

## §11 What this spec does NOT commit to

Unchanged from v0.1 plus:

- A specific calibration of factor weights (w_R, w_L, w_N, w_C, w_M). v0.2 sets initial values; backtest sensitivity determines whether to keep them.
- A specific environmental_modifier schema per overlay variable. v0.2 documents `environment_state` shape; specific multipliers are tuned empirically.
- A claim that win_authority and board_authority should remain split forever. If L4 evidence shows they collapse to a single dimension, v0.3 may merge them.

---

## §12 What this spec does NOT cover

For implementation, evaluation, and Belmont-specific application:

- `BACKTEST_PLAN_v0.2.md` — restructured around the L2 vs L2+L3 vs L2+L3+L4 architectural question
- `BELMONT_POSTMORTEM_RDS_v0.2.md` — re-renders the field using the multi-dimensional decomposition

---

*v0.2 of a toy side experiment. The framework is closer in shape to TopicSpace NDS now. The architectural test (does L3 lifecycle add value? does L4 calibration of lifecycle add value beyond that?) is what the backtest is designed to falsify. The cross-substrate-geometry insight is in `project_nds_is_cross_substrate_pattern.md` — this spec is one of three known instances of the pattern.*
