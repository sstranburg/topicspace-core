# Belief Stack v0.4c2 — Substrate Admission Criteria

**Date locked:** 2026-06-05 (initial); amended to v0.1.1 same day after the Codex rollout JSONL schema was investigated.
**Predecessor:** [`belief_stack_v0_4c1/BELIEF_STACK_REPORT_v0.4c1.md`](../belief_stack_v0_4c1/BELIEF_STACK_REPORT_v0.4c1.md)
**Status:** LOCKED at v0.1.1 — gates whether a Codex project corpus is eligible to become the v0.4c2 substrate.

**v0.1 → v0.1.1 amendment (2026-06-05):** §1 required-fields list updated to include `event_idx`. The Codex rollout JSONL (resolved as the trace source by TKOS write-path scope §10 Q2) contains multiple events per conversational turn; canonical event identity becomes `(session_id, turn_idx, event_idx)`. This affects only §1; the gate structure (§2–§5) is unchanged.

---

## Purpose

v0.4c2 is the cross-substrate replication that, with v0.4c1 already complete, would close the publication gate for the *Maintained State as a Planning Primitive* paper. Per [`project_v04c2_substrate_plan.md`](../../.claude/projects/-Users-sue-Documents-git-storm/memory/project_v04c2_substrate_plan.md), the second substrate will be a fresh real-project Codex corpus.

This document is **not** the v0.4c2 pre-registration. It is the set of conditions a Codex project must satisfy for its traces to be **admissible** as the v0.4c2 substrate. Locked *before* the project starts because some failure modes (incomplete trace capture, post-hoc question padding) are unfixable once they happen.

Three admission gates. One hard disqualification rule.

---

## §1 Trace capture from day 1

All Codex sessions must be captured persistently from the first work session. No retroactive reconstruction.

Each trace must preserve:

- `session_id`
- `turn_idx` (monotonically increasing within a session)
- `event_idx` (monotonically increasing within a turn; required because Codex's rollout JSONL emits multiple events per conversational turn — reasoning, tool calls, tool results, assistant messages all carry distinct event_idx within the same turn_idx)
- timestamp
- event_type (user_message / assistant_message / tool_call / tool_result / reasoning / task_start / task_completion / ...)
- `call_id` (when applicable — correlates tool_call with tool_result per the rollout schema)
- user instruction (when event_type = user_message)
- assistant response (when event_type = assistant_message)
- tool call, if any (when event_type = tool_call)
- tool output, if any (when event_type = tool_result)
- file paths touched, if available
- terminal output, if available

The trace format must be convertible to the same conceptual schema as the Claude Code corpus, now at triple-component event identity: `(session_id, turn_idx, event_idx)` plus event content. The Claude Code corpus can be retro-augmented with `event_idx = 0` for every existing row (non-breaking — it was one event per conceptual turn already). The deterministic oracle and the rule-engine extractor both anchor on this schema; without it, no per-question scoring is possible.

**Decide before starting:** where traces are saved, in what format, and what tooling exports them after each session. If trace capture is added at session N, only sessions ≥ N are admissible; earlier sessions are useful software work but not admissible substrate.

---

## §2 Post-hoc fixtured belief extraction

The Codex corpus must be **closed at a defined cutoff** before evaluation. Live extraction is out of scope for v0.4c2.

After cutoff:

1. freeze the trace corpus
2. run belief extraction (v0.1 rule engine, unchanged)
3. fixture the belief substrate
4. generate evaluation questions
5. construct A / A' / B / C contexts
6. run generation
7. score

The reason for fixturing: v0.4c2 is testing **substrate transfer**, not live extractor robustness. Live extraction would introduce a second variable (rule-engine portability) on top of the substrate variable, and reviewers will conflate them. The cross-substrate claim earns its weight when only the substrate varies.

---

## §3 Minimum corpus size (pre-registered)

The threshold below must be locked before any data flows. Pad-after-the-fact is disqualifying (see §4).

**Minimum threshold (admissible):**

- ≥ 30 sessions
- ≥ 3,000–5,000 turns / events
- ≥ 40 paired planning questions
- coverage across ≥ 4 of the 5 original task categories (`approval_status`, `validation_check`, `completion_check`, `readiness_check`, `repeated_failure`)
- ≥ 5 questions per covered category

**Preferred threshold (matches v0.3 / v0.4a / v0.4c1 statistical resolution):**

- ≥ 50 sessions
- ≥ 7,500 turns / events
- ≥ 75 paired planning questions
- coverage across all 5 categories
- ≥ 15 questions per category (matches v0.4a per-metric n)

If the project does not generate enough naturally-occurring examples to clear the minimum, the options are: (a) extend the collection window, or (b) report v0.4c2 as a pilot substrate study with reduced statistical claim. **Padding with artificial tasks after seeing the traces is disqualifying.**

---

## §4 Hard disqualification rule

> *If traces are not captured from the first session, the project can still be useful software, but it cannot be used as the v0.4c2 substrate.*

This sounds harsh; it saves the paper later. A partial trace corpus introduces a selection bias that no analysis can fully repair: the rule-engine sees only the turns that survived capture, and the per-question oracle scores against an incomplete event stream. The v0.4c2 thesis test fails before it starts.

Same rule applies to any of §1–§3 violated mid-project. The decision is binary at admission time: corpus is admissible, or it isn't. There is no "fix it up" path.

If the chosen Codex project fails admission, start another project. Do not weaken the criteria to fit the corpus that exists.

---

## §5 Project choice

The Belief Stack SDK is the most attractive Codex project: it is real, useful, and dogfoods the architecture. It is also the most exposed to one specific reviewer concern, addressed below.

### Benefit
- real operational work, not a benchmark
- traceable coding-agent substrate
- directly relevant to the research program
- the project itself is something the program needs anyway

### Risk
- reviewers may see the substrate as too entangled with the hypothesis being tested
- specifically: the SDK is *about* belief-stack semantics, so the operational planning questions Codex asks during development may be unusually well-aligned with the belief-extraction categories

### Mitigation
Evaluation questions and the deterministic oracle anchor on **session events**, not on whether the SDK's code is correct or whether the SDK semantically implements Belief Stack. The oracle scores from observed event patterns (validation completed, action blocked, etc.); it does not score whether the agent built the right product. As long as that boundary is held, the operational substrate is just *another coding-agent operational workflow corpus*.

### Framing for the paper
Frame the Codex corpus as:

> *a second coding-agent operational workflow corpus generated by Codex*

Not as:

> *proof that Belief Stack works because Codex built Belief Stack*

The substrate matters because it is *a different coding-agent harness on real work*, not because of the specific work product.

---

## §6 What this document does not commit to

- The full v0.4c2 pre-registration (arms, success criteria, classifier, action commitments). That will be locked in a separate `BELIEF_STACK_PRE_REGISTRATION_v0.4c2.md` after the Codex project has produced an admissible corpus.
- The specific Codex project. §5 discusses the SDK option; the actual project decision is separate.
- The model field. Likely the same four-model field as v0.4c1, but the cross-model question is already answered; v0.4c2 may sensibly run on a subset (e.g., gpt-4o for parity with v0.4a, plus one additional model from a different provider) to control cost.

---

## §7 What happens next

1. Pick the Codex project (see §5).
2. Set up trace capture (see §1) — *before* the first work session.
3. Decide on the minimum / preferred threshold (see §3) and lock it.
4. Start the project. Build real software. Let the substrate accumulate naturally.
5. At cutoff, run admission checks (§1–§4). If admissible, proceed to the v0.4c2 pre-registration.

The publication gate after v0.4c2: only the manuscript remains.

---

*Locked 2026-06-05. The discipline that produced v0.3, v0.4a, v0.4a.2, and v0.4c1 applies unchanged to v0.4c2: lock before run, amendments are explicit re-locks, classifier outputs are honored as written, surprises are signals.*
