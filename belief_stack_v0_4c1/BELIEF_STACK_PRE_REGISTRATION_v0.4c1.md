# Belief Stack v0.4c1 — Cross-Model Replication Pre-Registration

**Date:** 2026-06-04
**Status:** **DRAFT — NOT YET LOCKED.** Six decisions need resolution before lock. See §1 Decisions table.
**Lineage:** OB-001 (v0.1) → OB-002 (v0.2.2) → Belief Stack v0.3 → v0.4a.1 → v0.4a.2 → **v0.4c1 (cross-model replication, this document)** → v0.4c2 (cross-substrate replication)

---

## §0 The question

**Does v0.4a's finding — *maintained state beats reconstruction* — replicate across LLM model families?**

v0.3 and v0.4a held the generator fixed at `gpt-4o-2024-08-06` (T=0, seed 20260601). The first reviewer question for any single-model result is: *how do we know this is not a model-specific artifact?* v0.4c1 holds the substrate and the experimental design constant and varies the generator across multiple models. Per the locked paper-scope-discipline memory, cross-model replication is one of two required experiments before the empirical claim earns its full generality in publication.

**Specifically, v0.4c1 tests the thesis (maintained state beats reconstruction), not the mechanism (which rendering of maintained state wins).** The mechanism question from v0.4a.1 is held as substrate-and-model-specific; this experiment focuses on the thesis. The pre-registered arm set is `A / A' / B / C` — sufficient to test the thesis across models without re-running the full mechanism ablation per model.

---

## §1 Decisions

| # | Topic | Status | Resolution |
|---|---|---|---|
| **D1** | Substrate | **RESOLVED** | Reuse v0.1 / v0.2.2 / v0.3 / v0.4a substrate unchanged. 75 paired single-next-action planning questions, derived from 164 Claude Code session logs (~20,190 evaluation turns). Same 5 categories. Maximizes cross-experiment comparability. |
| **D2** | Number of arms | **RESOLVED** | 4 (A / A' / B / C). Drops D and E from v0.4a's ladder because their result (E ≈ B; D ≈ C, both slightly below) was substrate-and-budget-specific; re-running them across models is mechanism-question scope, not thesis scope. v0.4c1 tests the thesis. |
| **D3** | **Models** | **LEANING — needs lock** | Four models proposed: <br/>1. `gpt-4o-2024-08-06` (original — parity check; same as v0.3 / v0.4a) <br/>2. `claude-opus-4-7` (frontier-class, different family) <br/>3. `gemini-2.5-pro` (frontier-class, different family) <br/>4. `claude-haiku-4-5-20251001` (smaller, model-scale variance) <br/><br/>**Rationale:** four models give us original-parity + two frontier-class-from-different-families + one smaller-model. Three is the minimum defensible (drop #4); four is the version that also addresses *"does this hold on cheaper models?"* If cost or wall-clock pressure motivates a cut, drop Haiku (#4) and accept the scale-variance question as v0.5+ scope. *Alternative if Sue prefers different smaller model:* substitute `gemini-2.5-flash` for Haiku. |
| **D4** | Per-model generator configurations | **LEANING — needs lock** | Match v0.4a's protocol where the model supports it: temperature 0, top_p 1.0, max output 1500 tokens, seed 20260601. Some models (Anthropic family) do not natively support deterministic seed — for those, use `temperature=0` and accept that residual non-determinism may slightly inflate variance. Each model's locked config recorded in §3 of this pre-reg before any data flows. |
| **D5** | Context budgets | **RESOLVED** | Match v0.4a's locked budget cap of ~285 tokens for B and C. Arm A's raw K=20 log unchanged. Arm A''s LLM summary cap matched to B at ~285 tokens. The §3.5a dedup-ranking machinery from v0.4a is the canonical projection pipeline; same code, same parameters across all models. |
| **D6** | Scoring | **RESOLVED** | **Hold the judge constant; only the generator varies.** Reuse v0.4a's deterministic oracle (`score_operational_label.Scorer`) + LLM judge (`gpt-5-mini-2025-08-07`, reasoning_effort=medium, seed 20260601). Same `combine_oracle_and_judge` policy (oracle wins on disagreement). Holding the judge constant isolates the generator question from any judge-variance confound. |
| **D7** | Primary outcome metric | **RESOLVED** | Per-model paired planning correctness. n = 75 paired observations per (model, arm pair). Pre-registered minimum effect size for "advancement" between arms: **3 percentage points**. |
| **D8** | Interpretation rules | **DRAFTED — needs lock** | See §7 below. Lock interpretation BEFORE results. |

**Five decisions need explicit Sue review before lock:** D3 (which models), D4 (per-model configs, particularly the seed handling), D8 (interpretation rules). D1, D2, D5, D6, D7 are essentially resolved at the v0.4a inheritance level.

---

## §2 The four arms (per model)

For each model in §3, the same four arms are run:

| Arm | Context shape | What it tests |
|---|---|---|
| **A** | Raw K=20 log + strong-baseline reconstruction prompt | The pre-maintained-state baseline (v0.3 Arm A unchanged) |
| **A'** | LLM prose summary of raw K=20 log at ~285-token cap, same protocol as Arm B | Compression-control: rules out "compression alone explains the lift" (v0.4a.2 Arm A' unchanged) |
| **B** | LLM prose summary of substrate-clustered active beliefs at ~285-token cap | The v0.4a Arm B (substrate-derived prose projection) |
| **C** | Bare `belief_type :: claim` per active cluster, dedup-ranked, ~285-token budget cap | The v0.4a Pareto-winner (sparse structured names) |

The **summarizer model** for arms B and A' is the same as the per-model generator under test (i.e., each model summarizes its own input). This holds the *full pipeline* constant per model and tests whether a given model can both (a) summarize the substrate to produce Arm B's context AND (b) plan from it correctly.

---

## §3 Models and locked configurations

**Each model's full configuration must be locked here before any data flows.** This section is filled at lock time per D3 + D4 resolution.

```
Model 1: gpt-4o-2024-08-06
  temperature:      0
  top_p:            1.0
  max_tokens:       1500
  seed:             20260601
  (matches v0.4a exactly)

Model 2: claude-opus-4-7
  temperature:      0
  top_p:            1.0 (or equivalent — Anthropic API default)
  max_tokens:       1500
  seed:             [TBD — Anthropic API does not support deterministic seed as of pre-reg date;
                     verify at lock time]
  notes:            residual non-determinism accepted if seed unsupported

Model 3: gemini-2.5-pro
  temperature:      0
  top_p:            1.0
  max_tokens:       1500
  seed:             [TBD — Gemini API seed support to verify at lock time]

Model 4: claude-haiku-4-5-20251001
  temperature:      0
  top_p:            1.0
  max_tokens:       1500
  seed:             [TBD per Anthropic]
```

Total expected API calls (if 4 models locked): 75 questions × 4 arms × 4 models = **1,200 generation calls** + **1,200 judge calls** (judge held constant). Estimated wall-clock: 6-12 hours depending on rate limits. Estimated cost: ~$30-80 across all model APIs.

---

## §4 Context construction

Per-model context construction reuses the v0.4a code paths with the per-model summarizer for arms A' and B.

**Anti-curation discipline:** all contexts for all (model, arm, question) cells are constructed BEFORE any answer-generation calls flow. This means:

1. Generate A contexts (75 questions × 4 models = 300; identical text across models since A is raw log — but generated per-model to preserve audit trail of the per-model summarizer being unused for A).
2. Generate A' contexts (75 questions × 4 models = 300; each model summarizes its own raw log).
3. Generate B contexts (75 questions × 4 models = 300; each model summarizes its own substrate input).
4. Generate C contexts (75 questions × 4 models = 300; deterministic — substrate-side §3.5a rendering, same across models, generated once and copied; or per-model for symmetric audit).

Total contexts: 1,200 (or 900 if C is generated once and shared across models). Audit JSON records per-arm token statistics and per-model summarizer telemetry.

---

## §5 Scoring

Per D6:

- **Primary metric:** paired planning correctness — per-(model, question) oracle agreement from `score_operational_label.Scorer`.
- **Judge:** `gpt-5-mini-2025-08-07`, reasoning_effort=medium, seed 20260601, same prompt hash as v0.3 / v0.4a / v0.4a.1 / v0.4a.2.
- **Policy:** oracle wins on disagreement (`combine_oracle_and_judge` unchanged from v0.3).
- **Sample:** n = 75 paired observations per (model, arm-pair) comparison.
- **Cross-model comparison:** *per-model* correctness rates are the primary unit; cross-model differences in absolute correctness are a secondary observation, not a primary outcome.

---

## §6 Pre-registered predictions

**Per-model prediction (committed):**

For each model `m`, the planning-correctness rates satisfy:

> **B(m) > A(m)** by ≥ 3 percentage points
> **C(m) > A(m)** by ≥ 3 percentage points
> **B(m) > A'(m)** by ≥ 3 percentage points
> **C(m) > A'(m)** by ≥ 3 percentage points

That is: on each model independently, both substrate-derived projections (B and C) beat both reconstruction baselines (A and A') by a meaningful margin.

**Reference predictions (per-model):**

- For `gpt-4o-2024-08-06` (the parity-check model), the results should reproduce v0.4a closely. Drift from v0.4a's reported rates beyond ~2 pp is unexpected and would prompt a sanity audit (substrate, scoring, or API behavior change).
- Per-model absolute rates are not pre-registered. The prediction is on the *shape* (B > A, C > A on each model), not the *level*.

---

## §7 Pre-registered interpretation rules (DRAFTED — needs lock)

**Per-model outcome classes** — each model's pattern of arm comparisons is classified independently. The cross-model conclusion is a function of the per-model classifications.

For each model `m`, the per-model class is one of:

1. **Full replication (m):** B(m) > A(m) AND C(m) > A(m) AND B(m) > A'(m) AND C(m) > A'(m), each ≥ 3 pp.
2. **Partial replication (m):** B *or* C beats A *and* A' by ≥ 3 pp, but not both.
3. **Compression-equivalent (m):** B and/or C tie A' (within 2 pp); A' ≥ A by ≥ 3 pp. This model exhibits the v0.4a.2 compression-confound that v0.4a.2 ruled out on gpt-4o.
4. **No effect (m):** B and C tie A within the 2 pp noise floor.
5. **Reversal (m):** A or A' beats B and/or C by ≥ 3 pp.

**Cross-model outcome classes** (locked):

| Cross-model result | Architectural reading | Action |
|---|---|---|
| **All N models in class 1** (Full replication) | Cross-model claim defended at full strength. Thesis generalizes across the model field. | Paper goes to v0.3 with cross-model section reporting all N models as supporting evidence. |
| **N-1 of N in class 1, 1 in class 2** (Mostly full; one partial) | Cross-model claim mostly defended; one model shows a weaker effect. Report honestly; thesis still defensible. | Paper goes to v0.3 with cross-model section reporting the partial-replication model as a noted caveat. |
| **≥ 1 model in class 3** (Compression-equivalent) | v0.4a.2's compression-control finding does not generalize across models on this substrate. This is informative; the thesis weakens for that model class. | Paper goes to v0.3 with explicit per-model caveat. Cross-model claim becomes "the maintained-state lift over raw context holds across models, but compression-vs-substrate isolation depends on model behavior." |
| **≥ 1 model in class 4** (No effect) | The thesis fails to replicate on at least one model. Cross-model claim substantially weakens. | Paper amendment required; report the failure honestly. Empirical claim becomes scoped to "models on which the effect replicates." |
| **≥ 1 model in class 5** (Reversal) | Paper claim does not hold on that model. Investigate root cause (API behavior, substrate-model mismatch, etc.) before drawing conclusions. | Halt and audit. May indicate methodological issue rather than model-variance finding. |

**The actions above lock now.** They are not amended after seeing results.

---

## §8 Anti-curation discipline

Same as v0.4a:

- All contexts for all (model, arm, question) cells generated before any answer-generation calls flow. No iterative tuning.
- **No prompt tuning after seeing outputs.** System prompts for each arm are locked at this pre-reg's lock time. Per-model summarizer prompts (for arms A' and B) are locked here.
- All seeds, model IDs, and configuration values are in source control before the first API call.
- **No silent truncation.** Budget cap enforced by §3.5a dedup-ranking with explicit `omitted: N` counter.
- **Failures reported honestly.** If a TPM cap drops a (model, question) pair for an arm, that cell is excluded from paired comparison for that arm pair on that model (n < 75 reported with explicit count).
- **Per-model parity check:** the `gpt-4o-2024-08-06` results should reproduce v0.4a closely; drift > 2 pp on any arm prompts a sanity audit before proceeding to cross-model interpretation.

---

## §9 What this experiment does NOT test

- **Not mechanism across models.** D and E are not run. Whether projection-side discipline (warrants, lifecycle markers) gains value on other models is unmeasured. v0.5+ scope.
- **Not cross-substrate.** Still single substrate (Claude Code session logs). v0.4c2 scope.
- **Not budget variance.** Still ~285-token cap. Higher budgets unmeasured.
- **Not extraction-mechanism variance.** Beliefs are fixtured from v0.1 substrate; live extraction is v0.4c.3 scope.
- **Not end-to-end economics.** Planning-side only.
- **Not single-step vs multi-step planning.** Single-next-action task only.
- **Not the contribution of the specific implementation choices.** v0.4c1 tests the thesis (maintained state vs reconstruction) using the same implementation as v0.4a; alternative implementations of maintained state are not tested.

---

## §10 Lock signature

This pre-registration is **NOT YET LOCKED.** It requires:

- [ ] D3 — confirm model set (4 models proposed; could cut to 3 by dropping Haiku)
- [ ] D4 — confirm per-model configurations (especially seed handling for non-OpenAI models)
- [ ] D8 — confirm interpretation rules
- [ ] §3 — fill per-model locked configs after D3/D4 resolved
- [ ] Lock signature line below filled in

**Locked by:** _______________________
**Locked on:** _______________________
**Lock hash (commit SHA of this file at lock time):** _______________________

After lock: no amendments without a re-lock and re-version (v0.4c1.1, etc.).

---

*Drafted 2026-06-04 as part of the paper-publication-gate experimental program. Cross-references: [`project_paper_scope_discipline.md`](../../.claude/projects/-Users-sue-Documents-git-storm/memory/project_paper_scope_discipline.md), [`project_belief_stack_cost_frontier.md`](../../.claude/projects/-Users-sue-Documents-git-storm/memory/project_belief_stack_cost_frontier.md), [`paper/MAINTAINED_STATE_AS_PLANNING_PRIMITIVE_v0.2.md`](../paper/MAINTAINED_STATE_AS_PLANNING_PRIMITIVE_v0.2.md).*
