# RDS Backtest Plan — v0.2

**Date:** 2026-06-07
**Status:** v0.2 scope draft. Supersedes v0.1.
**Predecessors:**
- [`BACKTEST_PLAN_v0.1.md`](./BACKTEST_PLAN_v0.1.md) (retained as audit trail)
- [`HORSE_RACING_RDS_SPEC_v0.2.md`](./HORSE_RACING_RDS_SPEC_v0.2.md)

**v0.1 → v0.2 amendments (per Sue 2026-06-07):**

- **The strategy comparison is now the architectural test, not a 5-variant strategy mix.** Three strategies: L2-only, L2+L3, L2+L3+L4-feedback. This is the cleanest analog to the Belief Stack research program's central question.
- **The primary research question shifts.** From "does the framework make money?" to "does lifecycle matter?" and "does calibration of lifecycle matter?"
- **L4 Market Mispricing Study** is now a primary outcome (per RDS spec v0.2 §7), not just a sidebar.
- **Bet-shape integrity** remains the load-bearing metric (unchanged from v0.1).

---

## §0 The research question (v0.2 — restructured)

The original framing (v0.1) was:
> *Does lifecycle-aware, action-specific divergence improve bet construction versus static handicapping notes?*

That's still important. But v0.2 puts the architectural question first:

> *Does the L1 → L2 → L3 → L4 layer structure carry useful information across layers? Specifically:*
>
> 1. *Does L3 lifecycle add signal beyond static L2 belief snapshots?*
> 2. *Does L4 calibration of L3 lifecycle add signal beyond raw L3 lifecycle?*
> 3. *Does the resulting typed-action RDS reduce bet-shape errors?*

These three questions correspond to three strategy contrasts.

---

## §1 Population

Unchanged from v0.1.

- 100-300 NYRA graded stakes ≥1⅛ miles, 2018-2025.
- 70/30 training/backtest split.
- 2026+ races are held-out test (Belmont 2026 already qualifies as one data point).
- Per-horse requirement: ≥3 prior starts in the data window for RDS-based strategies.

---

## §2 Strategies (v0.2 — three, not five)

The strategy comparison is the architectural test. Each strategy generates per-race bet recommendations against the same odds and pool data. ROI, calibration, and bet-shape integrity are compared across all three.

| Strategy | Inputs | Bet construction |
|---|---|---|
| **A. L2-only** | Today's belief snapshot per horse (form, freshness, class, distance, pedigree, win_authority, board_authority). No lifecycle, no L4 calibration. | Pick top-rated L2 horses for each outcome type per the v0.2 integration-pattern §7 mapping (win_authority → win bet; board_authority → place bet). Static handicapping. |
| **B. L2 + L3** | A + lifecycle of each belief across prior races, with recency and momentum. NO L4 calibration — just raw lifecycle as L2 boost. | Same bet-construction rules as A, but lifecycle-strengthened beliefs get larger sizing; lifecycle-weakened beliefs get reduced sizing. No empirical edge claims. |
| **C. L2 + L3 + L4 feedback** | B + L4 calibration of which lifecycle patterns the market historically misprices. RDS computed per the v0.2 multi-dimensional decomposition. | Bet only where RDS_type > confidence_band(type), in the action shape the type permits. Hold cash when no positive-RDS bets exist. |

**The contrasts that matter:**

- **B vs A** isolates the **lifecycle contribution.** Does L3 help, given L2?
- **C vs B** isolates the **calibration contribution.** Does L4 calibration of L3 help, given L3?
- **C vs A** is the total architectural lift.

These three contrasts answer the three architectural questions in §0.

### §2.1 What v0.2 dropped from v0.1

The v0.1 "market baseline" strategy (S1) and "RDS + environmental overlay" strategy (S5) are removed from the primary comparison to keep the architectural test clean. They re-enter as **secondary controls**:

- **A0. Market baseline** — bet the favorite to win at $2. Useful as a sanity check (the strategies should beat random; they may or may not beat the market).
- **C+. C + environmental overlay** — C with `environment_state` realized values applied. Tests whether the overlay carries signal beyond L4 calibration alone.

But the headline test is A vs B vs C.

---

## §3 Backtest mechanics

Unchanged from v0.1: per-race procedure, training/calibration split, no-future-leakage rules. See `BACKTEST_PLAN_v0.1.md` §3 for details.

---

## §4 Evaluation metrics (v0.2 — three tiers)

### §4.1 Architectural-question metrics (primary, v0.2)

These directly answer the three questions in §0.

1. **B−A lift on bet-shape integrity** — does adding lifecycle improve the rate of "right shape for the horse" bets? Pre-registered threshold: ≥ +10 pp.
2. **C−B lift on calibration accuracy** — does adding L4 calibration improve the alignment of stated confidence with realized outcomes? Pre-registered threshold: mean absolute calibration deviation reduced by ≥ 3 pp.
3. **C−A total lift on combined ROI + bet-shape integrity** — does the full stack outperform the snapshot baseline meaningfully? Pre-registered threshold: ≥ +5 pp ROI AND ≥ +15 pp bet-shape integrity.

### §4.2 Outcome metrics (secondary)

Unchanged from v0.1:

- Win accuracy
- Board-hit rate
- Place/show ROI
- Exacta-anchor usefulness
- Longshot ROI
- Aggregate ROI
- Calibration analysis (bucketed by confidence)

### §4.3 L4 Market Mispricing Study output (v0.2 addition, per RDS spec v0.2 §7)

A separate report produced from the training subset:

> *For each candidate lifecycle pattern (e.g., "closing_authority confirmed ≥3 times, recency ≤2, momentum ≥0.5"), what is the realized vs market-implied edge per outcome type?*

The output is a table of lifecycle patterns ranked by mispricing magnitude (positive = market underprices; negative = market overprices). This is the closest analog to TopicSpace's NDS-discovery work: not "did we predict winners" but "which patterns repeatedly carry information the market doesn't price in."

The Market Mispricing Study has value EVEN IF the strategies A, B, C all underperform on ROI. It tells you what's happening at the substrate level, separate from whether the betting layer was disciplined.

---

## §5 Falsifiability gates (v0.2 — restructured)

Pre-registered before the backtest runs.

| Architectural question | Gate | Threshold |
|---|---|---|
| Does L3 lifecycle add signal? | B − A on bet-shape integrity | ≥ +10 pp |
| Does L4 calibration of L3 add signal? | C − B on calibration accuracy | MAD ≥ −3 pp |
| Does the typed-action discipline reduce bet-shape errors? | C bet-shape integrity vs A bet-shape integrity | ≥ +15 pp |
| Does the framework return positive ROI lift? | C − A aggregate ROI | ≥ +5 pp over backtest set |
| Does the Market Mispricing Study identify replicable patterns? | At least 2 lifecycle patterns show edge ≥ +5 pp in training AND backtest | Pattern survives held-out test |

**Strongest possible outcome:** all five gates clear. The architectural pattern transfers; lifecycle matters; calibration of lifecycle matters; the typed-action discipline pays off in bet shape AND ROI.

**Most-likely-interesting outcome:** B−A clears (lifecycle matters), C−B partially clears (calibration helps some but not dramatically), ROI is noisy. The framework adds structure but not edge. This is fine.

**Null result:** none of the gates clear. The architectural pattern didn't transfer to this domain. Document honestly; do not torture data; treat as evidence the geometry is narrower than hypothesized.

---

## §6 What the v0.2 backtest does NOT test

Unchanged from v0.1 plus:

- Specific factor weights (w_R, w_L, w_N, w_C, w_M from RDS spec v0.2 §10.1). v0.2 backtest uses initial values; sensitivity analysis on weight tuning is v0.3 work.
- Cross-domain transfer beyond horse racing. v0.2 tests whether the pattern works HERE; cross-substrate is a separate research question (see `project_nds_is_cross_substrate_pattern.md`).
- Live deployment edge. The 2026+ held-out test is the closest proxy; real prospective edge requires real money over more races.

---

## §7 What the v0.2 backtest WOULD demonstrate, if it passes

A small, contained, falsifiable demonstration that:

1. **The Belief Stack layer model (L1→L2→L3→L4 with L4→L2 feedback) carries useful information in a noisy real-world prediction domain** — not just on operational planning where v0.4c1 measured it.
2. **Lifecycle-aware divergence (multi-dimensional RDS) reduces bet-shape errors** — the Belmont 2026 failure mode is structurally fixable by typed-action discipline.
3. **The Market Mispricing Study identifies lifecycle patterns that systematically carry information the market doesn't price** — the TopicSpace NDS-discovery question, instantiated in racing.

That's the result space. It's small, contained, and the null is genuinely informative.

---

## §8 Sequencing

Unchanged from v0.1.

1. Lock this plan (v0.2). Pre-register strategies, metrics, gates.
2. Gather data. See §9.
3. Build L1 → L2 → L3 pipeline.
4. Train L4 calibration on training subset.
5. Run A, B, C on backtest subset.
6. Compute the L4 Market Mispricing Study report.
7. Score against §5 gates.
8. Write `BACKTEST_RESULT_v0.1.md` honestly. Null result valid.
9. Decide v0.3 iteration or framework-decline.

---

## §9 Data sources needed

Unchanged from v0.1. See `BACKTEST_PLAN_v0.1.md` §9.

---

*v0.2. The strategy structure is now the architectural test. The Market Mispricing Study makes the L4 layer load-bearing. The bet-shape integrity metric remains the load-bearing outcome. Null result is valid; the pattern may not transfer, and that's still useful evidence.*
