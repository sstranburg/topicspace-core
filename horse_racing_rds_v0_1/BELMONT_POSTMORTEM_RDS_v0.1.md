# Belmont 2026 Post-Mortem through the RDS Lens — v0.1

**Date:** 2026-06-07
**Status:** v0.1 qualitative application of the RDS framework to the Belmont 2026 field.
**Predecessors:**
- [`HORSE_RACING_RDS_SPEC_v0.1.md`](./HORSE_RACING_RDS_SPEC_v0.1.md)
- `project_action_policy_is_separate_layer.md` (the Belmont lesson)
- `/tmp/belmont_2026/` (the original betting experiment artifacts)

This is a **qualitative** application. No L4 calibration has been done yet (that requires the backtest from `BACKTEST_PLAN_v0.1.md`). The lifecycle readings and divergence estimates here are illustrative; numerical RDS values would require the calibration layer.

---

## §0 The single sentence

Golden Tempo's `closing_authority` belief was reconfirmed across the Risen Star, the Louisiana Derby, the Kentucky Derby (under traffic and soft pace), and the Belmont (under different pace conditions) — a **four-times-confirmed** L3 lifecycle that the market priced at 9-2 and the models mapped to "deep closer needs pace" instead of "creates his own closing opportunity."

That is the lifecycle-aware reading, and it was the right reading.

---

## §1 Golden Tempo (#9, 9-2)

**Active L2 beliefs (pre-race):**
- `closing_authority` — strong, four-times-confirmed
- `freshness` — strong, five-week prep
- `pedigree_distance_match` — strong (Curlin × Bernardini, classic dosage)
- `pace_independence` — emerging, supported by Derby trip

**L3 lifecycle of `closing_authority` (the load-bearing one):**
- Born — Risen Star (won from off the pace)
- Strengthened — Louisiana Derby (decisive late move)
- Strengthened — Kentucky Derby (forced through traffic, produced same kick under soft pace)
- Strengthened (post-race, now visible) — Belmont (different pace setup, same late authority)

**Estimated RDS readings (pre-race, qualitative):**
- `RDS_board` — **positive** (~+20 to +25 pp lifecycle vs market). Four-times-confirmed closing authority + freshness + pedigree should imply a board-hit probability well above the 9-2 implied ~18%.
- `RDS_win` — **moderately positive** (~+5 to +10 pp). Market gave him a real win chance at 9-2 (~18%); the lifecycle thesis adds some edge but doesn't dominate.
- `RDS_exacta_anchor` — **strong positive** especially as the *bottom* of an exacta (board-hit anchor under faster types).
- `RDS_longshot_upside` — negative. He's not a longshot.

**What the models missed:**

The models read his L2 beliefs correctly. Both contexts named him as having the strongest pedigree-for-distance profile. The failure was at L4 → action: they treated `closing_authority` as conditional-on-pace ("deep closer NEEDS pace") rather than as a confirmed lifecycle belief that has SURVIVED different pace setups.

**The replay matters.** Golden Tempo did not merely inherit the Belmont. The replay shows him forcing through traffic and producing the same late move he produced in the Derby under quite different fractions. That's L3 reconfirmation, not L2 snapshot — and it's exactly what the `closing_authority` belief family is designed to capture (per RDS spec §5 update).

**Bet shape the typed mapping would have produced:**
- $5-10 place (capturing `RDS_board`)
- $5 exacta with Golden Tempo *bottom* over likely speed types
- Optional small $2 win at 9-2 (covering `RDS_win`)
- NOT a single-horse win-against-the-chalk

Sue's $2 place on him was structurally right. Most of the model bets converted the same belief into the wrong shape.

---

## §2 Renegade (#4, 2-1)

**Active L2 beliefs:**
- `class_trajectory` — strong (G1 Arkansas Derby winner, narrow Derby second)
- `form_trajectory` — improving
- `trainer_intent` — Pletcher chasing fifth Belmont
- `pedigree_distance_match` — good (Into Mischief × Curlin mare)

**L3 lifecycle:**
- Class trajectory: improving — born (Remsen 2nd) → strengthened (Sam F. Davis win) → strengthened (Arkansas Derby win) → strengthened (Derby 2nd by a neck)
- Note the "Derby trip-compromise" framing: this is a *single-race excuse*. It hasn't been reconfirmed.

**Estimated RDS readings:**
- `RDS_win` — **near zero or slightly negative** at 2-1. The market correctly priced his improvement curve. A 2-1 favorite needs to win ~33% of the time to be a flat investment; his lifecycle is supportive but doesn't suggest meaningful divergence above that.
- `RDS_board` — neutral. Market priced him heavily; not much divergence to claim.
- `RDS_exacta_anchor` — moderately positive as the *top* (over a board-hitter or improving longshot).

**What the models did:**

Most models treated him as the chalk anchor in exotics, which was structurally reasonable. The failure mode (if any) wasn't on Renegade — it was on misallocating bets *against* him without enough lifecycle support for the alternative.

**Bet shape the typed mapping would suggest:**
- Use him as exacta-top over Golden Tempo or Chief Wallabee
- Don't bet him to win (no positive RDS_win)
- Don't bet against him purely on price — value-against-the-chalk requires the alternative to have positive RDS_win, not just lower implied probability

---

## §3 Chief Wallabee (#3, 3-1)

**Active L2 beliefs:**
- `board_resilience` — strong, multi-confirmed
- `form_trajectory` — consistent (no fade pattern, no big jumps)
- `pedigree_distance_match` — strong (Constitution × Medaglia d'Oro; grade-A dosage)
- `closing_authority` — **absent**. He's a grinder, not a burst-closer.

**L3 lifecycle:**
- Board resilience: born early → strengthened repeatedly (2nd Fountain of Youth, 3rd Florida Derby, 4th Derby — all in-money or close)
- Form trajectory: steady, no contradictions, no strong strengthenings either

**Estimated RDS readings:**
- `RDS_board` — **positive** at 3-1. The market gave him decent place/show pool action but a multi-confirmed board hitter at this price has structural edge.
- `RDS_win` — **near zero or negative**. Mott's stalkers win Belmonts when the pace falls apart; absent that, Wallabee's L3 doesn't say "winner" — it says "in the money."
- `RDS_exacta_anchor` — **strong positive** as the *bottom* of an exacta (under Renegade or Golden Tempo).

**What I (Claude) did and why it was wrong:**

I bet $10 win on Chief Wallabee. That was a bet-shape error. My handicapping read was correct: Mott + Saratoga + stalker + dosage. But the L3 lifecycle for `board_resilience` doesn't translate to `RDS_win` positive — it translates to `RDS_board` positive. I should have bet him to place or as an exotic bottom, not to win.

This is exactly the integration-pattern §7 mapping in action:

> reliable board-hitter → place/show/underneath, NOT win

I (and the other models) overtrusted Wallabee as a primary anchor. The lifecycle says he's a board-hitter; the action-policy mapping says board-hitters get board-exposure bets, not win bets.

**Bet shape the typed mapping would have produced:**
- $8 place at 3-1 (his structural strength)
- $4 exacta with Renegade top, Wallabee bottom
- $2 show
- NOT a $10 win bet

---

## §4 Growth Equity (#6, 12-1)

**Active L2 beliefs:**
- `form_trajectory` — improving (4 starts, never out of exacta)
- `freshness` — strong (Peter Pan→Belmont is a 3-week prep, well-timed)
- `trainer_intent` — Chad Brown's deliberate spot, Arcangelo (2023 Belmont) parallel
- `class_trajectory` — moving up
- `closing_authority` — unproven at this class

**L3 lifecycle:**
- Form trajectory: born early → strengthened repeatedly (4 starts, all close)
- BUT: only 4 lifetime starts, all at lower class. The L3 sample is thin — `shrinkage(n)` in the RDS formula would substantially deflate any lifecycle-derived edge.

**Estimated RDS readings:**
- `RDS_win` — **modestly positive** at 12-1, shrunk hard by sample size. The thesis is good (Arcangelo parallel, Brown's spot) but the L3 sample doesn't strongly confirm it.
- `RDS_longshot_upside` — **moderately positive** because the price compensates for the variance.
- `RDS_board` — modest positive.

**Why he was a value-dislocation thesis but high-variance:**

The thesis ("Brown's improver going Peter Pan→Belmont, like Arcangelo") is a meaningful pattern, but it's a *single* L3 confirmation from a small sample, not a multi-race lifecycle. The RDS spec §10.2's `shrinkage(n)` factor exists exactly for this case: small-sample patterns get pulled back toward zero divergence.

The right way to express this thesis: **small win bet + small place bet, not a primary anchor.**

**What the models did:**

Both context-B users included Growth Equity, but tended to size him too large for a thin-sample thesis. Codex's $8 place + $4 win + $8 in exactas was structurally too aggressive for what the L3 evidence actually warranted.

**Bet shape the typed mapping would have produced:**
- $2 win (small probe at 12-1)
- $2 place
- Possibly $2 included in an exacta box
- Capped exposure ~$6 of $20

---

## §5 Commandment (#7, 6-1)

**Active L2 beliefs:**
- `class_trajectory` — strong (Florida Derby winner)
- `pedigree_distance_match` — **weak** (DI 3.44, CD 1.00 — most speed-leaning dosage in field; Into Mischief × Orb)
- `form_trajectory` — declined into Derby (7th vs elite crop)

**L3 lifecycle of `pedigree_distance_match`:**
- Born negative (dosage analysis said weak for 10F)
- Weakened (Derby fade at the distance) → the weakness was *confirmed* in the Derby
- Going into Belmont: lifecycle says the distance is the open problem

**Estimated RDS readings:**
- `RDS_win` — **negative**. Market priced him at 6-1 (~14% implied); pedigree weakness lifecycle suggests realized win probability lower.
- `RDS_board` — **negative or neutral**. He can hit the board on tactical speed but the late part of 10F is the weak link.

**Whether Commandment contradicted or confirmed the pedigree-weakness thesis:**

This depends on his actual finish, which I don't have confirmed in my context — but Sue's framing ("why Commandment contradicted the pedigree weakness thesis") suggests he performed *better* than the lifecycle would have predicted. If so, two interpretations:

1. **The thesis was wrong.** Dosage analysis is a crude L1 input for a complex L2 belief; relying on it without other confirmation is the kind of "single-warrant" thinking that the framework should resist.
2. **Single-race noise.** One race outperforming a multi-warrant lifecycle thesis is not enough to contradict the lifecycle — small-sample drift around the predicted distribution. The dosage thesis would need to be contradicted multiple times before being weakened or retired.

The framework's discipline: don't update a lifecycle thesis on a single contradictory race unless the contradiction is decisive. One Commandment over-performance does not retire the pedigree-distance-match family's predictive utility. Multiple such over-performances across multiple horses across multiple races would.

**If Commandment indeed hit the board:** mark it as a `weakened` event for the pedigree-weakness thesis on this specific horse. The lifecycle theory survives at the family level; this individual prediction was wrong.

---

## §6 Vitruvian Man (#1, 30-1)

**Active L2 beliefs:**
- `surface_affinity_for_slop` — **only horse in field** with documented sloppy-track form
- `class_trajectory` — weak (distant third in Santa Anita Derby)
- `form_trajectory` — limited (broke maiden, then distant 3rd)
- `pedigree_distance_match` — mixed

**L3 lifecycle:**
- Surface affinity for slop: born in the maiden win — but a single confirmation, never tested again
- Class trajectory: contradicted at Santa Anita Derby

**Estimated RDS readings (HEAVILY dependent on environmental overlay):**
- `RDS_weather_hedge` — **conditional**. If actual track is sloppy, lifecycle says he becomes live (modest positive); if track is fast or good, lifecycle says he's at or below market (negative).
- `RDS_win` on a fast track — **strongly negative**. Market priced 30-1 (~3%); he's not a 3% horse on a fast track.
- `RDS_win` on a sloppy track — **moderately positive** but with wide confidence band (single L3 confirmation).

**The environmental-overlay lesson:**

The Belmont weather wildcard (storms forecast 4-8pm ET) was the single most important environmental overlay variable. The actual realized track condition determined whether Vitruvian Man had any value at all.

Per RDS spec §9: weather is NOT part of horse lifecycle. It's a current-state overlay that modifies which L2 beliefs are *operative*. Models who treated Vitruvian Man's `surface_affinity_for_slop` as part of his core profile were making a category error — that belief is only operative under realized slop, and the realized track must be observed (not forecast).

**Bet shape the typed mapping would have produced:**
- $1 win as a tiny asymmetric flyer **only if** track was confirmed sloppy at scratch time
- $0 if track was fast or good
- Per the integration-pattern §7 Option category: "candidate action, not truth"

I put $1 on him as a weather hedge. The structural logic was right (tiny asymmetric flyer); the actual outcome depended on realized track. If the track stayed fast or only got muddy late, that bet was guaranteed lost regardless of his lifecycle profile — and that's the structural reality the framework should make explicit.

---

## §7 What the realized environmental overlay should have done

Per the spec, the environmental overlay updates which beliefs are operative, not which beliefs exist:

- **If track stayed fast/good:** environmental modifier ≈ 1.0 for closing_authority, board_resilience, pedigree_distance_match. Standard handicapping. Most operative beliefs are the ones we discussed above.
- **If track turned sloppy:** environmental modifier > 1.0 for `surface_affinity_for_slop` (Vitruvian Man becomes live); environmental modifier < 1.0 for closers without slop form (Golden Tempo's closing thesis weakens because the surface punishes late kickers).
- **If pace setup changed (no scratches, but slower-than-expected fractions):** environmental modifier > 1.0 for `closing_authority` (closers get more room); < 1.0 for pure speed types like Commandment.

**The Belmont's realized environment:** Golden Tempo won. That implies (in retrospect):
- Track favored closers OR pace was honest enough for closing_authority to express. The environmental overlay did NOT punish closers.
- Even if rain hit, it didn't render the surface a closer-killer.
- Vitruvian Man's slop-form belief was either not operative (track stayed fast/good) or operative but insufficient (he wasn't competitive even in slop).

The environmental overlay narrative for the Belmont 2026: **closer-friendly conditions confirmed by the result**, regardless of the surface specifics.

---

## §8 The takeaway

The Belmont 2026 result, viewed through the RDS framework:

| Horse | Lifecycle thesis | Action shape (typed mapping) | Models' actual shape | Lesson |
|---|---|---|---|---|
| Golden Tempo | 4× confirmed `closing_authority` + freshness + pedigree | Board exposure + exacta-bottom + small win | Most models passed entirely | The four-times-confirmed lifecycle was the loudest signal in the race; models read the L2 snapshot but missed the L3 reconfirmation |
| Renegade | Strong overall profile but priced fairly | Exacta-top over board-hitter | Mostly correct | Reasonable use of the chalk |
| Chief Wallabee | Multi-confirmed `board_resilience`, no `closing_authority` | Place / show / exacta-bottom — NOT win | I (Claude) bet him to win | Bet-shape error — board-hitter mapped to wrong action |
| Growth Equity | Thin-sample improver thesis | Small win + small place — capped | Models sized too aggressively | Shrinkage(n) on small lifecycle samples not honored |
| Commandment | Pedigree-distance weakness lifecycle | Avoid as primary; underneath at best | Models followed the lifecycle here | Single race outperformance doesn't retire the family thesis |
| Vitruvian Man | Single `surface_affinity_for_slop` confirmation | Tiny asymmetric flyer ONLY under realized slop | I included a $1 hedge | Weather is overlay, not lifecycle — track must be realized |

The dominant lesson: **the L3 lifecycle for Golden Tempo's `closing_authority` was the strongest signal in the race, and it was underweighted because models confused the L2 snapshot ("deep closer needs pace") with the L3 history ("creates his own closing opportunity, has done it under multiple pace setups").**

The new L2 belief family `closing_authority` (per RDS spec §5) is the framework's response to that lesson. The next race that surfaces a similar reconfirmation pattern (Travers 2026 candidate) is the test.

---

## §9 What this post-mortem does NOT claim

- That the RDS framework, applied pre-race, would have correctly identified Golden Tempo as the winner. (Qualitative readings are not predictions.)
- That the bet shapes proposed here are the only right answers. (They're internally consistent with the framework, but the framework is v0.1.)
- That the framework will outperform humans or the market generally. (See `BACKTEST_PLAN_v0.1.md` falsifiability gates.)
- That `closing_authority` is now a locked, permanent belief family. (v0.2 may refactor based on backtest evidence; could be merged into a broader `late_authority` category, or split into `closing_authority_pace_dependent` and `closing_authority_pace_independent`.)

What this post-mortem DOES claim:

- The Belmont 2026 result is internally consistent with a lifecycle-aware reading that the four models did not produce. Sue's place bet on Golden Tempo was structurally what the framework would have recommended.
- The bet-shape errors (Wallabee bet to win, Growth Equity sized too large, Vitruvian Man hedge not gated on realized track) were *exactly* the failure modes the typed-action discipline is designed to prevent.
- The post-mortem is qualitative; the backtest is where the framework gets falsified or supported.

---

*Qualitative application of a v0.1 framework to a single race. Useful for sharpening intuition; not useful as a betting system. The Travers 2026 application (per `project_travers_2026_experiment_design.md`) will test whether explicit belief→action mapping in the prompt fixes the bet-shape failure modes documented here.*
