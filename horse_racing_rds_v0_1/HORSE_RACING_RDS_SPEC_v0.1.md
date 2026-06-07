# Horse Racing RDS — Spec v0.1

**Date:** 2026-06-07
**Status:** v0.1 scope draft. Toy side experiment, NOT a main Belief Stack research branch.
**Audience:** anyone curious about whether the Belief Stack layer model carries useful structure into a noisy real-world prediction domain.

---

## §0 What this is (and isn't)

This document scopes a horse-racing analog of TopicSpace's NDS (Narrative Divergence Score), called **RDS — Readiness Divergence Score**. RDS measures the gap between a horse's lifecycle-supported readiness for a *specific outcome* and the market's implied expectation for that same outcome.

It is **not**:
- A betting system. It does not promise to beat the market.
- A part of the main Belief Stack paper. It lives in a separate side-experiment directory.
- A demonstration of predictive power. Falsifiability is the design goal; we're testing whether lifecycle-aware, action-specific divergence improves *bet construction*, not whether it picks winners.

It **is**:
- A miniature dogfooding of the layer model (L1 evidence → L2 belief families → L3 lifecycle → L4 calibration) in a noisy domain where outcomes are immediately measurable.
- A vehicle for the Belmont 2026 lesson: *the substrate proposes, the action-policy disposes*. RDS makes the proposal action-specific.

---

## §1 RDS ↔ NDS relationship

TopicSpace's NDS measures the gap between an actor's narrative pressure (derived from a maintained belief substrate) and the actor's price movement. Positive NDS = narrative says more than the market is pricing; negative NDS = market has priced in more than the narrative supports.

RDS is the structural analog for horse-racing outcomes:

| | NDS (TopicSpace) | RDS (this experiment) |
|---|---|---|
| Substrate signal | narrative pressure (from belief substrate) | calibrated lifecycle-supported readiness (from horse belief lifecycle) |
| Market signal | price movement / option pricing | win-pool / place-pool / exotic-pool implied probabilities |
| Divergence semantics | overpriced vs underpriced narrative-vs-price | overrated vs underrated readiness-vs-pool |
| Action surface | trading / leaning into a thesis | bet *type* selection (win / place / exacta / hedge) |

**Both are signals, not predictions.** Both can be positive without the outcome materializing (the market is right on average; signals identify potential value, not guarantees).

---

## §2 Why action-specific RDS

A horse with a strong *closing authority* lifecycle but a heavy-pace requirement is:
- A weak RDS_win bet in a small field with slow pace
- A strong RDS_board bet in any field (he hits the wire close enough)
- A strong RDS_exacta_anchor bet over likely speed types
- A weak RDS_longshot_upside bet (he's not getting the price for it)

A *single* "RDS" score collapses these into one number and discards the structure the lifecycle actually surfaces. The Belmont 2026 dogfooding showed exactly this: all four models had the correct lifecycle signal on Golden Tempo and all four converted it into the wrong bet shape (single-horse value-win bets against the chalk, instead of board / exotic-underneath exposure).

**Action-specific RDS forces the divergence to be expressed in the right bet category.**

The v0.1 RDS types:

- `RDS_win` — divergence on the win-pool implied probability
- `RDS_board` — divergence on place/show pool implied probability (top-2 or top-3 finish)
- `RDS_exacta_anchor` — divergence on the horse-as-2nd-or-1st in a typed exotic structure
- `RDS_longshot_upside` — divergence on the very-low-probability win at the very-high-price tail
- `RDS_weather_hedge` — divergence on outcome-under-realized-track-conditions (a separate axis from the others)

A horse can have positive RDS on one type and negative on another. That's the whole point.

---

## §3 Why L3 lifecycle may add signal beyond static L2 state

Static L2 state (today's belief snapshot: "this horse is fresh," "this horse has strong pedigree") is what handicapping notes already do. The L3 addition is the **lifecycle** of those beliefs across prior races:

- Was the closing_authority belief *born* in one race, *reconfirmed* in the next, or *contradicted* by a flat performance?
- Was the freshness belief *strengthened* by a productive break, or *weakened* by a stale layoff pattern?
- Did the distance_fit belief *survive* a stretch-out, or get *contradicted* by a fade?

A static snapshot says "Golden Tempo is a deep closer." The L3 view says "Golden Tempo's closing_authority was born in the Risen Star, confirmed in the Louisiana Derby, reconfirmed in the Kentucky Derby under traffic and a soft pace, then *reconfirmed again* in the Belmont under different pace conditions." That's a much stronger thesis than the snapshot.

The hypothesis being tested: **multi-confirmed lifecycle beliefs carry more weight than single-snapshot beliefs, in ways the market does not always price**.

Falsifiable. If multi-confirmed L3 patterns don't outperform single-snapshot L2 patterns in backtest, the L3 add is noise.

---

## §4 L1 — Raw evidence inputs

L1 is the evidence floor. Every L2 belief must trace to L1 evidence via a warrant. No vibes.

Core L1 inputs (per-horse, per-race):

- **Race results** — finish position, beaten lengths, fractional times, sectional/late times
- **Speed figures** — Beyer, Brisnet, or Trakus equivalents
- **Pace figures** — early/late pace numbers, running style classification
- **Class movement** — race-class grade, purse level, field strength
- **Distance/surface history** — every prior start's distance, surface, and fit
- **Workouts** — bullet works, drill patterns, time between works
- **Equipment / connections** — blinkers, Lasix, trainer, jockey, jockey switch
- **Pedigree** — dosage indices, stamina ratings, surface affinity from sire and damsire
- **Layoff data** — days since last start, freshness pattern

**Trip / replay-derived evidence (added per Sue 2026-06-07 — these update specific L2 beliefs, not vibes):**

- Traffic trouble (forced wide, blocked, checked)
- Ability to split horses or pick paths through a field
- Sustained late acceleration (not just a single furlong burst)
- Whether the horse passed *tired* rivals or created his own move
- Response to actual pace shape (did he overcome a slow pace? a hot one?)
- Visual confirmation of closing authority (the eye test, with specific behaviors)
- Whether prior race patterns *repeated* (e.g., same finishing kick under different conditions)

Each replay-derived datum updates a specific L2 belief:
- Traffic trouble + ability to split → `traffic_tolerance`
- Sustained late acceleration + passing tired rivals + creating own move → `closing_authority`
- Repeated performance under different pace setups → `pace_independence`
- Hitting the board across varied trips → `board_resilience`

Replay evidence is L1, not L2. The L2 belief is the abstraction; the replay is its warrant.

---

## §5 L2 — Belief families about this horse's current state

Each L2 belief is a typed claim with a warrant trail to L1 evidence and a lifecycle history at L3.

**Locked L2 belief families (v0.1):**

| Belief family | One-line meaning |
|---|---|
| `form_trajectory` | improving / steady / declining over recent starts |
| `freshness` | rested productively / over-raced / over-rested |
| `class_trajectory` | moving up / staying in class / dropping |
| `distance_fit` | suited to today's trip / questionable / unproven |
| `board_resilience` | reliably hits the board (1st-3rd) under varied conditions |
| `closing_authority` | can produce a decisive late move *independent* of perfect pace setup (added v0.1 per Belmont 2026 post-mortem) |
| `traffic_tolerance` | can navigate or recover from traffic trouble |
| `pace_independence` | can run a winning race across different pace shapes |
| `trainer_intent` | spot/prep work indicates today is a primary target |
| `pedigree_distance_match` | sire/dam page supports today's distance |

`closing_authority` is the new addition the Belmont 2026 post-mortem motivated. It's the belief models underweighted on Golden Tempo: they read "deep closer needs pace" but the lifecycle evidence suggested "creates his own closing opportunity."

The list is intentionally finite. New families can be added in v0.2+; that's a re-version event.

---

## §6 L3 — Lifecycle transitions

Each L2 belief has a lifecycle across the horse's race history. Borrowing from RULES_SPEC v0.3.2:

```
born          → first race where evidence supports the belief
strengthened  → reconfirmed by a subsequent race
weakened      → contradicted by a race but not fully refuted
contradicted  → directly disproven by a race
retired       → no longer applicable (e.g., distance/surface change makes the belief moot)
```

A belief's L3 history is the trail of these transitions. Examples:

- **Golden Tempo / closing_authority:** born (Risen Star) → strengthened (Louisiana Derby) → strengthened (Kentucky Derby under traffic + soft pace) → strengthened (Belmont under different pace setup). Four-times-confirmed.
- **Chief Wallabee / board_resilience:** born (early stakes appearances) → strengthened (multiple in-money finishes) → strengthened (Saratoga form). Reliable board-hitter.
- **Chief Wallabee / closing_authority:** never born — he's a grinder, not a burst-closer.
- **Commandment / pedigree_distance_match:** born (Florida Derby) → weakened (Kentucky Derby fade). Lifecycle says distance is the open question.

The L3 transitions are mechanical from the race record + replay evidence; they don't require subjective re-rating each time.

---

## §7 L4 — Historical calibration

L4 is the calibration layer. Across many horses with similar L3 lifecycle patterns, what outcomes actually materialized?

Examples of L4 questions:

- Horses with `closing_authority` reconfirmed ≥3 times: what's their realized board-hit rate in stakes? What's their realized win rate?
- Horses with `board_resilience` strong but no `closing_authority`: what's their realized place rate at short prices vs longer prices?
- Horses with `freshness` strong but `class_trajectory` flat: how do they perform in step-up spots?

L4 is empirical. It comes from a backtest population (see BACKTEST_PLAN_v0.1.md). It produces calibrated probabilities per lifecycle pattern, per outcome type.

`calibrated_lifecycle_probability_type` in the RDS formula is the L4 output for the action-type in question.

---

## §8 L4 → L2 feedback

The calibration tells us which lifecycle patterns matter and how much. That feeds back to L2 in two ways:

1. **Weight tuning.** If `closing_authority` (reconfirmed ≥3 times) correlates strongly with board-hits but only weakly with wins, then the L2 abstraction should reflect that — the belief's *action-specific* utility differs.
2. **Family revision.** If a hypothesized belief family (e.g., `traffic_tolerance`) doesn't predict outcomes in backtest, demote or merge it. If a previously-absent pattern shows predictive lift (e.g., "horses whose closing authority was reconfirmed under traffic"), promote it to its own family.

This is the Belief Stack lifecycle discipline applied to the belief schema itself: belief families have their own L3 — born, strengthened, weakened, retired — driven by L4 evidence about what predicts.

---

## §9 Environmental overlay (separate from horse lifecycle)

Per Sue's constraint: **weather and track condition are NOT part of a horse's lifecycle.** They are a current-state overlay that modifies which lifecycle beliefs matter today.

Environmental overlay variables:

- Actual weather at post (vs forecast)
- Realized track condition (fast / good / muddy / sloppy / sealed)
- Late track bias (rail-favoring / outside-favoring / front-running / closer-favoring as the card progresses)
- Race-day scratches (changes pace shape and field composition)
- Late odds movement (informed money signal)

The overlay modifies which L2 beliefs are *operative* today, not which beliefs the horse has:

- If the track turns sloppy, `surface_affinity_for_slop` from L2 becomes operative (and most horses don't have a positive value for it).
- If a key pace-setter scratches, `pace_independence` becomes less critical and `early_position_speed` becomes more critical.
- If late odds drop on a horse, that's an informed-money signal that updates the `market_implied_probability` baseline.

In RDS terms: the environmental overlay is a `environmental_modifier` multiplier on the lifecycle probability, OR an adjustment to the market baseline. Both formulations are valid; v0.1 keeps it simple and treats the overlay as a multiplier on the lifecycle probability for action-types whose validity is environment-conditional.

---

## §10 RDS formulas

### §10.1 Simple form

```
RDS_type = calibrated_lifecycle_probability_type − market_implied_probability_type
```

Positive RDS = the lifecycle says this outcome is more likely than the market thinks for this horse, this type of bet.
Negative RDS = the market has priced this outcome higher than the lifecycle warrants.
Zero RDS = the market and the lifecycle agree.

`calibrated_lifecycle_probability_type` comes from L4. `market_implied_probability_type` comes from the relevant pool at takeout-adjusted odds.

### §10.2 Richer form

```
RDS_type = shrinkage(n) ⋅ (lifecycle_P_type − market_baseline_P_type) ⋅ environmental_modifier(type)
           ± confidence_band(type)
```

Where:

- `shrinkage(n)` — small-sample correction. When the L4 calibration is based on few similar lifecycle patterns, shrink the divergence toward zero. A Bayesian flavor with a prior of "no edge over market." Concretely: `shrinkage(n) = n / (n + k)` where k is a tuning parameter; k can be picked to make a 5-sample lifecycle pattern weigh 50%.
- `lifecycle_P_type` — the L4 calibrated probability for this outcome type given this horse's L3 lifecycle pattern.
- `market_baseline_P_type` — the takeout-adjusted, pool-implied probability for this outcome type.
- `environmental_modifier(type)` — a multiplier (default 1.0) that reflects current-state overlay effects on this specific action type. Slop turns most board_resilience modifiers below 1.0 unless the horse has slop form; a key scratch can push pace_independence's modifier above 1.0.
- `confidence_band(type)` — width of the interval around RDS. Wider when the sample is thin, the environmental modifier is large, or the lifecycle pattern is rare. Use it to gate "do I bet this divergence at all?"

A practical decision rule: only act on `RDS_type` if `RDS_type > confidence_band(type)`. Otherwise the signal is within noise.

### §10.3 Anti-overclaim caveats

- The L4 calibration may overfit if the backtest population is small or biased toward a single era / circuit. Cross-validate with held-out races.
- Market baselines drift across years (takeout changes, pool sizes, share of informed money). RDS values are not directly comparable across decades.
- A positive RDS on a specific bet type does not mean you should always bet it. Bankroll constraints, variance, and bet-shape integrity (the integration-pattern §7 discipline) still apply.
- The framework is most useful as a **bet-construction guide** (which action shape to use for which horse), not as a magic +EV detector.

---

## §11 What the v0.1 spec does NOT commit to

- A specific shrinkage formula. Multiple candidates exist; v0.2 picks one based on backtest sensitivity.
- A specific environmental_modifier schema. v0.1 leaves it as "multiplier, default 1.0, document per overlay variable in v0.2."
- An overall RDS aggregator. There is no "RDS_total." Action-specific is the point.
- A betting strategy. RDS informs bet selection; sizing is a separate concern.
- A live data ingestion pipeline. v0.1 is a backtest design. Live RDS computation is v0.3+.
- Any guarantee of edge over the market. The whole exercise is falsifiable, and the null result ("L3 didn't add signal") is genuinely possible.

---

## §12 What this spec does NOT cover

For implementation, evaluation, and Belmont-specific application, see companion documents:

- `BACKTEST_PLAN_v0.1.md` — minimum viable backtest design + falsifiability gates
- `BELMONT_POSTMORTEM_RDS_v0.1.md` — qualitative application of this framework to the Belmont 2026 field

---

*Toy side experiment. Designed to be falsifiable and contained. The architectural pattern matches Belief Stack; the domain is noisier and the outcome metric is more legible (ROI per race). If the lifecycle approach pays off here, that's a small additional data point for the main research program. If it doesn't, the architectural pattern is unchanged — racing was just the wrong substrate for it.*
