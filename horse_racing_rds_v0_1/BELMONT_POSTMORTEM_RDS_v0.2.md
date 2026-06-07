# Belmont 2026 Post-Mortem through the RDS Lens — v0.2

**Date:** 2026-06-07
**Status:** v0.2 qualitative application of the v0.2 RDS framework. Supersedes v0.1.
**Predecessors:**
- [`BELMONT_POSTMORTEM_RDS_v0.1.md`](./BELMONT_POSTMORTEM_RDS_v0.1.md) (retained as audit trail)
- [`HORSE_RACING_RDS_SPEC_v0.2.md`](./HORSE_RACING_RDS_SPEC_v0.2.md)
- `project_action_policy_is_separate_layer.md` (the Belmont lesson)
- `/tmp/belmont_2026/` (the original betting experiment artifacts)

**v0.1 → v0.2 amendments:**
- Multi-dimensional RDS decomposition rendered per horse (readiness / lifecycle_confirmation / novelty / crowding / market_expectation)
- `win_authority` and `board_authority` split applied throughout (was combined as "readiness" in v0.1)
- `belief_recency` and `belief_momentum` annotated for key beliefs
- Realized `environment_state` from the actual race used instead of pre-race forecast where relevant

Still qualitative. Numerical RDS values would require L4 calibration from `BACKTEST_PLAN_v0.2.md`.

---

## §0 The single sentence (v0.2)

Golden Tempo's `closing_authority` belief was reconfirmed four times — Risen Star → Louisiana Derby → Kentucky Derby (under traffic + soft pace) → Belmont (under different pace conditions). That's **maximum lifecycle confirmation** with **zero recency lag** and **0.8 momentum** (4 of last 5 races strengthened). The market priced this 9-2 (~18% implied win); the multi-factor lifecycle reading suggested far higher board probability and modestly higher win probability than the market.

The models read the L2 snapshot ("deep closer needs pace") but missed the L3 reconfirmation signature.

---

## §1 Golden Tempo (#9, 9-2)

### §1.1 L2 belief snapshot

| Belief | Reading | Recency | Momentum |
|---|---|---|---|
| `win_authority` | Strong (Risen Star, Kentucky Derby wins) | 0 races (just confirmed) | 0.4 (2 of last 5) |
| `board_authority` | Very strong (multi-confirmed; in-money rate near 100%) | 0 races | 0.8 |
| `closing_authority` | Very strong (4× confirmed) | 0 races | 0.8 |
| `pace_independence` | Strong (Derby under soft pace + Belmont under different pace) | 0 races | 0.4 |
| `freshness` | Strong (5-week prep, skipped Preakness) | 0 races | n/a (single-event) |
| `pedigree_distance_match` | Strong (Curlin × Bernardini; classic dosage) | n/a | n/a |

### §1.2 Multi-dimensional RDS decomposition (v0.2)

| Factor | Reading | Notes |
|---|---|---|
| `readiness` (for win) | High | Strong win_authority + freshness + pedigree |
| `readiness` (for board) | Very High | Strong board_authority + everything else |
| `lifecycle_confirmation` | Very High | 4-times-confirmed closing_authority; high momentum |
| `novelty` | Low | Other closers exist in the field; not a one-of-a-kind profile |
| `crowding` | Moderate | A few horses share "closer with stamina" thesis (Renegade, Growth Equity partially) |
| `market_expectation` | Moderate | 9-2 already prices a meaningful win chance and a serious board chance |

**RDS_win estimate:** moderately positive. Lifecycle confirmation dominates; readiness adds; novelty doesn't help (he's not unique); crowding eats some edge; market gives him real credit at 9-2 but probably not full credit. Net: positive but bounded.

**RDS_board estimate:** strongly positive. Same components as RDS_win but readiness for board is higher, and the market typically underprices board-hit probability for closers (place pool is shallower than win pool intuition).

**RDS_exacta_anchor estimate:** strongly positive especially as exacta-bottom under speed/stalker types.

### §1.3 Action shape the v0.2 mapping would have produced

- **$5-10 PLACE** (capturing RDS_board)
- **$5 EXACTA-BOTTOM** under Renegade or Wallabee (capturing RDS_exacta_anchor)
- **$2-3 WIN** at 9-2 (modest RDS_win)
- **NOT** a single-horse win-against-the-chalk bet

Sue's $2 PLACE was structurally aligned with the strongest factor (RDS_board). She didn't capture the full bet shape the framework would propose (no exacta-bottom), but the place portion was correct.

### §1.4 What the models missed (v0.2 framing)

The L2 snapshot framing ("deep closer needs pace") collapses two distinct lifecycle observations:

1. *Was the closing belief ever confirmed?* — Yes, in the Derby.
2. *Was it confirmed REPEATEDLY across different conditions?* — Yes, four times now, including under different pace setups.

A single-confirmation closer needs pace. A four-times-confirmed closer with strong momentum has demonstrated the ability to create his own closing opportunity. The lifecycle distinction is what v0.2's `belief_recency` + `belief_momentum` measure.

The models had access to the L2 belief snapshot but did not articulate the L3 reconfirmation signature, and so converted "deep closer" into the conditional action shape ("needs pace") rather than the L3-supported action shape ("multi-pace-tested closer").

---

## §2 Renegade (#4, 2-1)

### §2.1 L2 belief snapshot

| Belief | Reading | Recency | Momentum |
|---|---|---|---|
| `win_authority` | Strong (Arkansas Derby win) | 1 race (Derby was a 2nd) | 0.4 |
| `board_authority` | Very strong | 0 races | 0.8 |
| `class_trajectory` | Improving | 0 races | 0.6 |
| `closing_authority` | Moderate (late kick is real but pace-dependent) | 0 races | 0.4 |
| `pedigree_distance_match` | Good (Into Mischief × Curlin mare) | n/a | n/a |

Note: the "Derby trip-compromise" framing relied on a single-race excuse — that's a `weakened` event for `win_authority`, not yet contradicted, not yet reconfirmed.

### §2.2 Multi-dimensional RDS decomposition

| Factor | Reading | Notes |
|---|---|---|
| `readiness` (for win) | High | Strong all-around profile |
| `lifecycle_confirmation` | Moderate | Class trajectory improving consistently; win_authority less reconfirmed than profile suggests |
| `novelty` | Low | "Improving favorite" is the most-priced-in pattern |
| `crowding` | Low | Few horses share his complete profile |
| `market_expectation` | Very High | 2-1 implies ~33% win, ~70% board |

**RDS_win:** near zero or slightly negative. Market priced his trajectory accurately at 2-1.

**RDS_board:** moderately positive only. Market gave him heavy place-pool action; harder to claim divergence.

### §2.3 Action shape

- Use as exacta-top
- Don't bet to win (no RDS_win edge)
- Don't bet against him just on price — value-against-chalk requires alternatives with positive RDS_win, not just lower implied probability

Most models handled Renegade structurally OK. The failure was misallocating bets AGAINST him without enough lifecycle support for the alternative.

---

## §3 Chief Wallabee (#3, 3-1)

### §3.1 L2 belief snapshot

| Belief | Reading | Recency | Momentum |
|---|---|---|---|
| `win_authority` | **Weak** (no graded stakes wins) | n/a | 0.0 |
| `board_authority` | **Very strong** (multi-confirmed; consistent in-money) | 0 races | 0.8 |
| `closing_authority` | Absent — grinder, not burst-closer | n/a | n/a |
| `form_trajectory` | Steady (no strengthenings, no contradictions) | 1 race | 0.2 |
| `pedigree_distance_match` | Strong (Constitution × Medaglia d'Oro; grade-A dosage) | n/a | n/a |

**The win_authority vs board_authority split (v0.2 — load-bearing):**

In v0.1 I lumped these as "readiness." That permitted the structural error of betting a board-hitter to win. v0.2 makes the asymmetry explicit:

- Wallabee's `board_authority` is multi-confirmed with high momentum → strongly licenses board/place/show/exotic-bottom bets
- Wallabee's `win_authority` is **never strengthened** → does not license a win bet at any price

The market at 3-1 was pricing him as a serious win contender. The lifecycle says he's a serious BOARD contender.

### §3.2 Multi-dimensional RDS decomposition

**For RDS_win:**

| Factor | Reading |
|---|---|
| `readiness` | Moderate-only (board_authority is strong but win_authority is weak; pedigree fits) |
| `lifecycle_confirmation` | Weak for win specifically (zero confirmed win_authority events) |
| `novelty` | Low |
| `crowding` | Moderate (Renegade also a stalker, also chalk-priced) |
| `market_expectation` | High (3-1 implies ~25% win) |

**RDS_win: negative.** Market overvalued his win chance.

**For RDS_board:**

| Factor | Reading |
|---|---|
| `readiness` | Very high |
| `lifecycle_confirmation` | Very high (board_authority multi-confirmed) |
| `novelty` | Moderate (most consistent board profile in the field) |
| `crowding` | Low (few horses share his specific multi-board-hit profile) |
| `market_expectation` | Moderate (place pool gave him action but not as heavily as win pool) |

**RDS_board: strongly positive.**

### §3.3 Action shape

- **$8 PLACE** at 3-1 (his structural strength)
- **$4 EXACTA-BOTTOM** with Renegade top, Wallabee bottom
- **$2 SHOW** (extra board insurance)
- **NOT** a $10 win bet

My v0.1 read of this bet: I made the error of converting `board_authority` lifecycle into a win bet. The v0.2 framework would have separated win_authority from board_authority and the action mapping would have refused the win bet structurally.

---

## §4 Growth Equity (#6, 12-1)

### §4.1 L2 belief snapshot

| Belief | Reading | Recency | Momentum |
|---|---|---|---|
| `form_trajectory` | Improving (4 starts, never out of exacta) | 0 races | 1.0 (all 4 strengthened) |
| `freshness` | Strong (Peter Pan→Belmont 3-week prep) | n/a | n/a |
| `trainer_intent` | Strong (Brown's deliberate spot, Arcangelo parallel) | 0 races | n/a |
| `class_trajectory` | Moving up sharply | 0 races | 0.5 |
| `closing_authority` | Unproven at this class | n/a | 0.0 |

**Sample-size warning:** only 4 lifetime starts. Even with high momentum (1.0), the shrinkage(n) factor in v0.2 should substantially pull back any lifecycle-derived edge.

### §4.2 Multi-dimensional RDS decomposition

| Factor | Reading | Notes |
|---|---|---|
| `readiness` (for win) | Moderate (improving but unproven at this class) |
| `lifecycle_confirmation` | High in momentum, low in absolute sample (4 starts) |
| `novelty` | High ("Arcangelo parallel" is a distinctive profile in this field) |
| `crowding` | Low |
| `market_expectation` | Low (12-1 implies ~7% win) |

**RDS_win: modestly positive,** shrunk hard by sample size. Net: small positive, fits "small probe."

**RDS_longshot_upside: moderately positive.** Price compensates for variance.

### §4.3 Action shape

- $2 WIN (small probe at 12-1)
- $2 PLACE
- $2 in an exacta box
- **Capped exposure ~$6 of $20** — never primary

Both Context-B users (myself + Codex) included Growth Equity but tended to size him too aggressively for a thin-sample lifecycle thesis. The v0.2 framework's explicit shrinkage on small samples would have constrained the sizing.

---

## §5 Commandment (#7, 6-1)

### §5.1 L2 belief snapshot

| Belief | Reading | Recency | Momentum |
|---|---|---|---|
| `win_authority` | Strong (Florida Derby winner) | 1 race (Derby fade) | 0.4 |
| `board_authority` | Moderate | 1 race | 0.4 |
| `class_trajectory` | Recent setback (Derby 7th vs elite crop) | 1 race | 0.2 |
| `pedigree_distance_match` | **Weak** (DI 3.44, CD 1.00 — most speed-leaning dosage in field) | n/a | n/a |
| `closing_authority` | Absent | n/a | n/a |

The `pedigree_distance_match` lifecycle:

- Born negative (dosage analysis said weak for 10F)
- **Weakened** (Derby fade at the distance) — distance weakness was confirmed in the Derby

### §5.2 Multi-dimensional RDS decomposition

| Factor | Reading |
|---|---|
| `readiness` (for win) | Mixed (class is strong but pedigree weakness lifecycle is confirmed for the distance) |
| `lifecycle_confirmation` | Mixed — class trajectory weakened, pedigree weakness re-confirmed |
| `novelty` | Low |
| `crowding` | Low |
| `market_expectation` | Moderate (6-1, ~14% win) |

**RDS_win: negative.** Pedigree-distance lifecycle says lower realized win probability than market.

### §5.3 On Commandment "contradicting" the pedigree-weakness thesis

If Commandment performed better than the pedigree-weakness lifecycle predicted, that's a single `weakened` event for the family-level thesis ON THIS HORSE. The framework's discipline (per RDS spec v0.2 §6):

- Single contradictory race ≠ retired thesis
- Multiple horses + multiple races contradicting the thesis = weakened or retired at the family level
- A single horse outperforming a multi-warrant lifecycle prediction is small-sample noise

The pedigree-weakness lifecycle survives at the family level; the individual prediction on Commandment was wrong. That's a calibration event for L4 (the Market Mispricing Study should track this), not a refutation of the L2 belief family.

---

## §6 Vitruvian Man (#1, 30-1)

### §6.1 L2 belief snapshot

| Belief | Reading | Recency | Momentum |
|---|---|---|---|
| `surface_affinity_for_slop` | **Single confirmation** (maiden win on sloppy) | Many races ago | 0.0 |
| `class_trajectory` | Weak (distant 3rd in Santa Anita Derby) | 1 race | 0.0 |
| `win_authority` | Weak | n/a | 0.0 |
| `board_authority` | Weak | n/a | 0.0 |

### §6.2 Environment_state dependency

`surface_affinity_for_slop` is a **conditional belief**, operative only when `environment_state.track_condition` is sloppy at post. Per RDS spec v0.2 §9, the realized track condition is the gate, not the forecast.

### §6.3 Multi-dimensional RDS decomposition

**On a fast track (most likely realized condition):**

| Factor | Reading |
|---|---|
| `readiness` (for win) | Very weak |
| `lifecycle_confirmation` | Weak everywhere |
| `novelty` | Low |
| `crowding` | None (no one in field shares his profile) |
| `market_expectation` | Very low (30-1, ~3% implied) |

**RDS_win on fast: strongly negative.** He's not even a 3% horse on a fast track.

**On a sloppy track (low-probability conditional):**

| Factor | Reading |
|---|---|
| `surface_affinity_for_slop` × `environment_state` multiplier | Activates the conditional belief |
| Other factors | Largely unchanged |

**RDS_weather_hedge on sloppy: moderately positive but with very wide confidence_band** (single L3 confirmation; relevance only conditional on environment).

### §6.4 Action shape

- $0 if `environment_state.track_condition` not realized as sloppy
- $1 WIN as tiny asymmetric flyer ONLY if track is confirmed sloppy at scratch time
- Per integration-pattern §7 "Option" category: candidate action, not truth

I included a $1 hedge in my Belmont bets. The structural logic was right (tiny asymmetric flyer); the actual outcome depended on realized track. The v0.2 framework formalizes this conditional dependency.

---

## §7 Realized environment_state for Belmont 2026

Per RDS spec v0.2 §9: the environment_state at post (realized, not forecast) is what should have updated the operative-beliefs set.

From the actual race (Golden Tempo won):

| Variable | Value (realized) |
|---|---|
| `track_condition` | (need confirmation — but Golden Tempo's win suggests it was raceable for closers) |
| `track_bias` | Closer-favoring or neutral (Golden Tempo won from off the pace) |
| `pace_realization` | Soft enough to allow Golden Tempo to close (consistent with v0.2 spec's pre-race light-early-speed expectation) |
| `weather_realized` | (need confirmation) |
| `field_scratches` | None known to me |
| `late_odds_movement` | (need confirmation) |

**The environmental overlay's role in the result:**

- Closer-friendly conditions were realized. This MAGNIFIED Golden Tempo's lifecycle edge (`closing_authority` confirmed in supporting conditions).
- Vitruvian Man's `surface_affinity_for_slop` was either not operative (track stayed fast/good) or operative but insufficient.
- Wallabee's `board_authority` should have been operative regardless — closer-favoring conditions don't normally hurt stalkers — so his apparent failure to hit the board (per Sue's note that her exacta box #3/#9 lost) suggests EITHER the track was specifically punishing for stalkers OR he just didn't run his race. Single-race noise either way.

---

## §8 The v0.2 takeaway

The Belmont 2026 result, viewed through the v0.2 RDS framework:

| Horse | Strongest factor | Right action shape | What models did | Lesson |
|---|---|---|---|---|
| Golden Tempo | lifecycle_confirmation (4× closing_authority, momentum 0.8) | Place + exacta-bottom + small win | Most passed entirely | The 4× reconfirmed lifecycle was the loudest signal; models read L2 snapshot but missed L3 momentum |
| Renegade | market_expectation (already-priced) | Exacta-top under board-hitter | Mostly correct as anchor | Market priced fairly; no edge to exploit |
| Chief Wallabee | readiness for board (board_authority high, win_authority zero) | Place / show / exacta-bottom — NOT win | I (Claude) bet $10 win | win_authority vs board_authority split would have prevented the error |
| Growth Equity | lifecycle_confirmation high momentum but small sample | Capped probe (~$6 of $20) | Models sized too large | Shrinkage(n) on small lifecycle sample not honored |
| Commandment | pedigree_distance weakness lifecycle | Avoid as primary | Models followed lifecycle | Single outperformance ≠ retired family thesis |
| Vitruvian Man | surface_affinity_for_slop (conditional on env) | Tiny flyer only if env confirms | I included $1 hedge | Conditional belief operative only on realized environment_state |

**Dominant lessons reinforced in v0.2:**

1. **Multi-dimensional decomposition makes the WHY of a divergence legible** — Golden Tempo's edge was specifically the lifecycle_confirmation factor, not just "good horse"
2. **win_authority vs board_authority is a structural separation** that prevents the Belmont 2026 Wallabee category error
3. **belief_recency and belief_momentum** distinguish a fresh-confirmed thesis from a stale one
4. **Realized environment_state** is the gate on conditional beliefs; forecasts don't qualify
5. **Single contradictory races are weakening events, not retiring events** for family-level lifecycle theses

---

## §9 What this post-mortem does NOT claim

Unchanged from v0.1.

- The framework, applied pre-race, would have correctly identified Golden Tempo as the winner. (Qualitative readings ≠ predictions.)
- The bet shapes proposed here are uniquely right answers. (Internally consistent with v0.2; v0.2 may be wrong about specific factor weights.)
- v0.2 will outperform humans or markets in backtest. (See `BACKTEST_PLAN_v0.2.md` falsifiability gates.)

---

*v0.2 qualitative application of the v0.2 framework. The multi-dimensional decomposition makes the "why" of each divergence visible, which is the closest analog to TopicSpace's narrative-factor decomposition. The Travers 2026 application (per `project_travers_2026_experiment_design.md`) is the next live test; the backtest (per `BACKTEST_PLAN_v0.2.md`) is where the architectural questions get falsified.*
