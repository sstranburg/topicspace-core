# Backlog — Belief Observability / TKOS

**Date:** 2026-06-02
**Status:** Reprioritized.

---

## Strategic frame

Belief Stack is moving toward **belief observability for AI systems**.

Core framing:

- One belief-state substrate.
- Two peer query surfaces:
  - **AI-facing:** `overlay()` — compact, ranked, budgeted attention compressor.
  - **Human-facing:** `state()` / `timeline()` / `explain()` — browsable, time-traveled epistemic debugger.
- Same `state()` truth layer underneath.
- Same data model.
- **Do not fork the substrate for different consumers.**

This framing is now reflected in the canonical [Belief Stack spec](../topicspace-site/app/research/belief-stack/page.tsx) (the "Where this sits" framing paragraph + the "Two surfaces over one substrate" section). It is also the framing for the TKOS docs ([TKOS-001](tkos_sidecar/TKOS_SIDECAR_SKETCH_v0.1.md), [TKOS-002](tkos_sidecar/TKOS-002_HUMAN_OBSERVABILITY_SURFACE_v0.1.md), [TKOS-002 implementation slice](tkos_sidecar/TKOS-002_IMPLEMENTATION_SLICE_v0.1.md)).

---

## Priority order

| # | Item | Status | Why this slot |
|---|------|--------|---------------|
| **P0** | Publish / distribute the essay | shipped 2026-06-01; low response | external legibility of the v0.1 result |
| **P1** | TKOS-002 read-path slice — `tkos state` | ✅ done 2026-06-02 | human surface validated against same substrate |
| **P1b** | TKOS-002 overlay slice — `tkos overlay` | ✅ done 2026-06-02 | AI surface validated against same substrate — dual-consumer claim now demonstrated |
| **P2** | OB-002 v0.2 pre-reg cleanup | ✅ locked 2026-06-02 | pre-registration complete; eligible for execution |
| **P3** | OB-002 v0.2 execution | ✅ done 2026-06-02 | inspection-side result locked at v0.2.2 — smallest overlay wins |
| **P4** | TopicSpace maintenance audit | shipped (Batch 1 + 2) 2026-06-02 | site identity shifted to research org |
| **P5** | Runtime sidecar / SDK | deferred | do not start until P6 is clearer |
| **P6** | Belief Stack v0.3 — planning-side experiment | ✅ done 2026-06-03 | Arm B (overlay only, 14% of Arm A tokens) beats raw context by 8 pts on planning correctness; "maintained state is a planning primitive" is now evidence-backed |
| **OPS-001** | Formalize the human / AI operating discipline | parked (traceable, not active) | enabling infrastructure; pick up after P6 lands |

---

## P0 — Publish / distribute the essay

**Status:** essay is ready ([`writing/the-recent-log-is-not-the-same-as-state`](../topicspace-site/app/writing/the-recent-log-is-not-the-same-as-state/page.tsx)).

**Goal:** make the operational-belief result legible to a broader technical audience.

**Deliverables:**

- LinkedIn post.
- Link to the essay.
- Optional targeted shares to collaborators / reviewers.

**Discipline:** do not over-edit endlessly. The essay is locked; the post wraps it for distribution.

---

## P1 / P1b — TKOS-002 read-path slice ✅ shipped 2026-06-02

**Status:** done. Both the human-facing surface (`tkos state`) and the AI-facing surface (`tkos overlay`) are built, read from the same SQLite-backed belief-state substrate, and pass all six acceptance tests against the hand-written demo session fixture.

**Code:** [`tkos_sidecar/tkos.py`](tkos_sidecar/tkos.py), [`tkos_sidecar/test_tkos.py`](tkos_sidecar/test_tkos.py).
**Implementation note:** [`tkos_sidecar/TKOS-002_IMPLEMENTATION_NOTE_v0.1.md`](tkos_sidecar/TKOS-002_IMPLEMENTATION_NOTE_v0.1.md).
**Deliverable spec:** [`tkos_sidecar/TKOS-002_IMPLEMENTATION_SLICE_v0.1.md`](tkos_sidecar/TKOS-002_IMPLEMENTATION_SLICE_v0.1.md).

**Original goal:** prove that the shared belief-state substrate supports human-facing time-travel state inspection — *before* building ingestion, rule engine, overlay ranking, or sidecar integration. P1b extended the goal to demonstrate the AI-facing surface against the same substrate.

**Scope:**

- SQLite DDL for the shared substrate tables (`events`, `belief_instances`, `belief_events`, `active_beliefs` view, `action_checks` stub).
- One hand-written fixture representing a ~12-turn coding-assistant session.
- Around 6 belief instances exercising:
  - `fix_attempted`
  - `validation_pending`
  - `pipeline_running` or `pipeline_failed`
  - `action_blocked`
  - `validation_complete`
  - `report_ready`
- One CLI command:
  - `tkos state <session_id> --turn T`

**Acceptance tests:**

- Before validation succeeds (turn 8): `validation_pending` and `action_blocked` are both active.
- After validation succeeds (turn 10): `validation_pending` is retired and `validation_complete` is active.
- State reconstruction MUST replay `belief_events` — do not use a hand-written active-state file.
- The human-facing state view MUST read from the same substrate that later powers `overlay()`.

**Non-goals:**

- No rule engine.
- No event ingestion.
- No overlay ranking.
- No dashboard.
- No TUI.
- No agent integration.
- No governance checks.

**Reason this is P1, not P3+:** it is the cheapest way to validate "one substrate, two surfaces" against implementation. With both `tkos state` and `tkos overlay` now passing acceptance tests against the same store, the substrate shape is validated and the dual-consumer claim is demonstrated. Remaining slices (`timeline`, `explain`, real event ingestion, rule engine) are quality-of-life or write-path additions — none of them is an architectural blocker.

**What's still on paper (not yet built):**

- `tkos timeline` — belief-events stream (Q2, Q4, Q7 from TKOS-002 §5.1).
- `tkos explain <belief_id>` — single-belief drill-down (Q3, Q5, Q8).
- Event ingestion + rule engine — the write path; would replace the hand-written fixture with derived beliefs.
- Real event adapter (Claude Code logs, etc.).
- Optional local HTML trace viewer.

---

## P2 — OB-002 v0.2 pre-reg cleanup

**Goal:** prepare Operational Belief v0.2 for lock, but do not run it yet.

**Current draft:** [`operational_belief_v2/OPERATIONAL_BELIEF_PRE_REGISTRATION_v0.2.md`](operational_belief_v2/OPERATIONAL_BELIEF_PRE_REGISTRATION_v0.2.md) (revised 2026-06-02).

**Required changes before lock — STATUS:**

| Change | Status |
|--------|--------|
| Non-remembered-state priority — overlays prioritize active beliefs whose evidence is outside the K=20 recent-log window | ✅ added as §3.0 meta-rule (2026-06-02) |
| Compressed serialization contract — one line per belief; minimal fields; evidence trails belong to human surface | ✅ added as §3.5 (2026-06-02) |
| Keep global deterministic ranking (no category-aware, no LLM scoring) | ✅ locked in §3.3 (2026-06-02) |
| Keep lexicographic tiers; no continuous scoring in v0.2 | ✅ retained in §3.1 (2026-06-02) |
| Add tie-breaks: out-of-window before in-window, last_updated desc, authority, deterministic hash | ✅ added as §3.4 (2026-06-02) |
| Add small human-audit anchor — stratified review of YES labels + judge-oracle conflicts; audit support, not a third metric | ✅ added as §6.3 (2026-06-02) |
| Preserve previous lock items: regenerate A, keep q047/q061, omitted-belief counts summary, strict budgets, frozen scorer/judge configs, budget header in overlay | ✅ preserved in §4 / §5 / §7 |

**Lock complete (2026-06-02):** all §5 decisions resolved (D8 → single seed), all §7 open questions closed (Q2 → skip B0). The pre-registration is now eligible for execution.

---

## P3 — OB-002 v0.2 execution

**Blocker:** P2 lock.

**Goal:** test whether budgeted/ranked overlays preserve most of the v0.1 benefit while eliminating the v0.1 feasibility failures.

**Candidate arms:**

- **A:** raw log only (regenerated under v0.2 controls for parity).
- **B500 / B1000 / B2000:** ranked, budgeted overlays at 500 / 1000 / 2000 tokens.
- **B0:** unbounded overlay, reference only where feasible (v0.1 reference condition).

**Primary comparison:** B1000 vs A on aggregate operational error.

**Secondary:**

- Budget sensitivity curve (B500 / B1000 / B2000).
- False-completion preservation (the v0.1 dominant signal).
- Overlay token utilization per arm.
- Omitted belief counts per arm.
- Human-audit anchor (per §6.3 of the pre-reg).

---

## P4 — TopicSpace maintenance audit

**Status:** queued separately. Audit document: [`TOPICSPACE_MAINTENANCE_AUDIT.md`](TOPICSPACE_MAINTENANCE_AUDIT.md) (2026-06-01).

**Goal:** reduce TopicSpace from daily operating burden into a maintained research artifact.

**Decisions per surface:** keep live / weekly update / freeze as archive / remove from nav / deprecate.

**Filter:** does this support Belief Stack, belief observability, TKOS, or the sensemaking case study?

**Headline finding from the audit:** the strategic site needs none of the current 30-step daily pipeline; a skinny 8-step pipeline is enough, and most daily-commentary surfaces can be frozen with an as-of banner.

---

## P5 — Runtime sidecar / SDK

**Discipline:** do not start until P1 and P2 are clearer.

**Goal:** thin runtime sidecar, not a platform.

**Possible API (sketched in [TKOS-001](tkos_sidecar/TKOS_SIDECAR_SKETCH_v0.1.md)):**

- `observe(event)`
- `state(session_id, turn=None)`
- `overlay(session_id, budget_tokens=1000)`
- `risk(session_id, action)`

**Position:** advisory / observable state first. **No hard governance.** The line between sidecar and governance system is the line `risk()` does not cross in v0.1.

---

## P6 — Belief Stack v0.3 (planning-side experiment)

**Status:** Draft pre-registration in progress. [`belief_stack_v0_3/BELIEF_STACK_PRE_REGISTRATION_v0.3.md`](belief_stack_v0_3/BELIEF_STACK_PRE_REGISTRATION_v0.3.md).

**Why this slot.** v0.1 and v0.2.2 demonstrated the *inspection-side* case: a maintained belief overlay reduces workflow-state errors when injected alongside raw context. v0.3 tests the *planning-side* case: can a maintained belief state support agent planning with materially less raw context? This is positioned as a **new planning-side track** rather than a continuation of v0.2.2's inspection-side line, because the task surface, evaluation methodology, and outcome metrics are different even though the substrate may be shared.

**Core claim under test (bounded).**

> Not: agents can plan from belief state alone.
>
> But: maintained belief state can support planning with less raw context, while preserving provenance and lifecycle signals that generic summaries lack.

**The conceptual frame.** Every agentic system today pays the **reconstruct-world-model-every-step tax** — re-reading prompt history, retrieved documents, memory stores, tool outputs, and prior plans at each step to re-infer "what do I currently believe?" v0.3 is the first direct test of whether maintained belief state reduces that tax.

**Three arms.** A (raw context large, strong baseline with explicit reconstruction prompt); B (compact belief overlay only); C (compact belief overlay + minimal targeted evidence). Arm C may be the realistic production architecture — registered as a secondary hypothesis.

**Fair-comparison constraint (load-bearing).** Arm A must receive the same underlying evidence used to derive the belief state. Otherwise the comparison measures substrate-builder effort, not the belief-state architecture.

**Outcomes:** planning quality (primary) + operational telemetry (tokens, latency — quantifies the tax) + failure-mode catalog (v0.2.2 metrics + new *grounding bankruptcy*: correct high-level state but missing scratchpad detail).

**Status of §12 lock decisions.** D5 (single-next-action), D6 (programmatic gate primary; LLM judge secondary), D7 (≥50% token reduction), D8 (within ~2 pts or beats Arm A) have user leanings. D2 (substrate — reuse v0.1 corpus if planning-capable, else build small new fixture set) is the next blocker; D1, D3, D4, D9 fall out from D2 + D5.

**Not for execution yet.** Pre-reg must be fully locked before any data flows.

---

## OPS-001 — Formalize the human / AI operating discipline

**Status:** **Parked. Traceable, not active.** Pick up after P6 lands. Enabling infrastructure rather than the next research claim.

**Status:** queued. Not for execution this week.

**Motivation.** Across June 2026 a repeatable rhythm emerged: *experiment → evidence → decision → backlog → implementation → trace*. That rhythm is what made it possible to lock OB-002 v0.2.2 in a day, ship the TKOS-002 read-path slice, restructure the site without breaking anything, and keep every step auditable. The pattern generalizes beyond this project — to professional work, to TKOS, and to future contributor collaboration. Worth formalizing as a small operating system rather than leaving as project habit.

**The bigger insight.** TopicSpace is building belief infrastructure for AI agents. The same architecture works for human + AI teams — decision logs, experiment ledgers, and contributor onboarding are *belief infrastructure for people and their AI collaborators*. Same substrate idea, different consumer.

**Goal.** A small folder of operating documents + Claude Skills that make the rhythm reproducible across projects and collaborators. Not automation magic — reusable rituals.

**Proposed structure (`/ops/` directory):**

```
/ops/
  operating_principles.md         # the rhythm, the rules, the discipline
  experiment_ledger.md            # hypothesis / setup / result / decision per experiment
  decision_log.md                 # decisions + reason + reversibility
  backlog.md                      # work orders, acceptance criteria, status, owner
  coding_assistant_protocol.md    # how to brief Claude, when to test, when to stop
  contributor_onboarding.md       # architecture, glossary, roadmap, "how we work here"
  skills/
    write_work_order.md
    review_experiment.md
    daily_research_closeout.md
    prepare_coding_assistant_brief.md
    update_decision_log.md
    contributor_onboarding.md
```

**Five categories the operating discipline covers:**

1. **Project memory** — decisions made, open questions, current thesis, known constraints, active risks.
2. **Experiment ledger** — hypothesis, setup, expected vs observed result, decision, evidence link.
3. **Backlog discipline** — work orders with acceptance criteria, status, owner, next action.
4. **Coding assistant protocol** — how to brief Claude, how to review output, when to stop coding, when to test, when to summarize.
5. **Contributor onboarding** — architecture overview, glossary, current roadmap, "how we work here," quality bars.

**Claude Skills as the surface:**

- **Write Work Order** — produces a structured work-order document
- **Review Experiment** — walks through an experiment audit
- **Daily Research Closeout** — end-of-day summary + memory update
- **Prepare Coding Assistant Brief** — generates a structured prompt
- **Update Decision Log** — appends a new decision with reason + reversibility
- **Contributor Onboarding** — generates a first-day brief

**The one rule that makes the whole thing work:**

> **Nothing important lives only in chat.**

That's the discipline that lets the system become real and lets other people eventually join.

**First concrete deliverable when this is picked up:** `/ops/operating_principles.md` capturing the *experiment → evidence → decision → backlog → implementation → trace* rhythm + the "Write Work Order" Claude Skill as the first reusable ritual.

*Origin: morning strategy conversation 2026-06-03 (with GPT).*

---

## Cross-cutting discipline

- One substrate. Two peer surfaces. Do not fork.
- AI surface is the attention compressor. Human surface is the epistemic debugger. Both read through `state()`.
- Locked v0.1 results are not revisitable. v0.2 builds on top, does not replace.
- Pre-registration discipline carries: no prompt tuning after seeing outputs, no silent truncation, no answer_guidance, all seeds + model IDs locked before any data flows.

---

*End of backlog. Re-prioritize this doc when an item ships or a constraint changes.*
