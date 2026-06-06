# TKOS Write-Path Sidecar — Scope v0.2

**Date:** 2026-06-05
**Status:** LOCKED — implementation-ready. Supersedes v0.1.1.
**Predecessors:**
- [`TKOS_WRITE_PATH_SCOPE_v0.1.md`](./TKOS_WRITE_PATH_SCOPE_v0.1.md) — v0.1 / v0.1.1; superseded by this document. v0.1.1 conflated software scope, v0.4c2 substrate admissibility, and streaming/batch correctness in ways that a build-time audit (Codex review, 2026-06-05) found contradictory before any code flowed.
- [`TKOS_SIDECAR_SKETCH_v0.1.md`](./TKOS_SIDECAR_SKETCH_v0.1.md) — architectural sketch from 2026-06-01. Still load-bearing for §2 API shape and the design principles.
- [`TKOS-002_IMPLEMENTATION_SLICE_v0.1.md`](./TKOS-002_IMPLEMENTATION_SLICE_v0.1.md) — the read-path slice (existing `tkos.py`).
- [`operational_belief_v1/build_operational_belief_substrate.py`](../operational_belief_v1/build_operational_belief_substrate.py) — the v0.1 batch rule engine.
- [`reference_codex_trace_storage.md`](../../.claude/projects/-Users-sue-Documents-git-storm/memory/reference_codex_trace_storage.md) — Codex rollout JSONL location and structure.
- [`project_v04c2_substrate_separation.md`](../../.claude/projects/-Users-sue-Documents-git-storm/memory/project_v04c2_substrate_separation.md) — the locked decision separating this software build from v0.4c2 substrate work.

---

## v0.1.1 → v0.2 amendment log

Nine substantive changes; the rest is restructuring around them.

1. **Software/substrate separation.** This scope is now software-only. It does not produce the v0.4c2 substrate. A fresh Codex project will start that work after this software's trace capture is verified.
2. **Canonical event identity changed.** `source_event_id` is now the primary identity; `(session_id, turn_idx, event_idx)` are derived fields.
3. **Normalized event schemas locked before rules.** Each event type has a typed schema fixed in §4 before any rule references it.
4. **Streaming/batch equivalence narrowed.** Test scope is the *shared canonical derivation spec over the v0.1 belief subset*, not full pipeline equality.
5. **Atomicity invariant added.** Event persistence + rule effects are wrapped in a single transaction.
6. **Capture completeness checks added.** Sequence validation + transcript hash, not "we tried to capture everything."
7. **Retro-minting uses `effective_turn` and `observed_at_turn`** as separate fields, not one timestamp doing double duty.
8. **Event identity is hash-derived if Codex lacks native IDs**, deterministic across replays.
9. **Acceptance tests = nine explicit.** The export-determinism test from v0.1.1 stays; renumbered against the new structure.

---

## §1 Purpose and scope

### §1.1 What this is

The TKOS read-path slice already implements substrate-to-projection queries. The write-path is the missing piece: a streaming engine that converts a live event stream into the substrate the read-path consumes.

This document scopes **v0.2 of the write-path as software-only**. The chosen input source is the Codex rollout JSONL. The deliverable is working software that ingests Codex events, mints and updates beliefs deterministically, and exposes the same SQLite schema the read-path queries.

### §1.2 What this is NOT

This software's captured traces are **not the v0.4c2 substrate**. The v0.4c2 substrate is a separate fresh Codex project that begins after this software is verified to capture traces correctly (see `project_v04c2_substrate_separation.md`).

The reason: any exploratory work, scaffolding, or pre-capture activity in this project necessarily violates the v0.4c2 admission §4 hard rule. Trying to do both at once was the v0.1.1 mistake.

### §1.3 In-scope (v0.2)

- HTTP ingestion endpoint accepting one event per POST.
- Persistent event storage in SQLite (same DB as the read-path).
- A streaming port of the v0.1 rule engine that fires per event and writes `belief_events` rows under transactional guarantees.
- A materialized `active_beliefs` view backed by `belief_instances` + `belief_events`.
- A Codex trace adapter that reads `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` line-by-line and POSTs one event per line.
- CLI: `tkos serve`, `tkos replay <trace.jsonl>`, `tkos verify <session_id>` (the new capture-completeness check), `tkos export <session_id>`.
- Nine acceptance tests (§7).

### §1.4 Out-of-scope (v0.2)

Unchanged from v0.1.1:

- LLM-driven belief extraction.
- Auth, multi-tenant, network protocols beyond local HTTP.
- Trace viewer UI; CLI only.
- IDE integration beyond Codex.
- Cross-session reasoning.
- Tool registration to the assistant.
- Overlay auto-injection.
- Performance optimization beyond single-user workloads.
- Postgres / replication / clustering.
- Production-grade observability of the sidecar itself.

---

## §2 Reference architecture

The existing TKOS read-path (`tkos_sidecar/tkos.py`) is unmodified. The write-path adds three new files:

```
tkos_sidecar/
├── tkos.py                    (existing, unchanged)
├── test_tkos.py               (existing, unchanged)
├── ingest.py                  (new — HTTP + atomic-write dispatcher)
├── rules.py                   (new — streaming rule engine)
├── trace_adapter_codex.py     (new — Codex rollout JSONL → ingest)
├── test_ingest.py             (new)
├── test_rules.py              (new)
├── test_trace_adapter.py      (new)
├── test_capture_completeness.py (new)
└── tkos.db                    (existing schema + additive write-path columns)
```

Read-path is read-only of the write-path's output: write-path adds rows to `events`, `belief_instances`, `belief_events`, and new operational tables; read-path queries these tables via existing functions.

---

## §3 Canonical event identity

This is the architectural primitive everything else relies on.

### §3.1 `source_event_id` is primary

Every ingested event has a stable, deterministic `source_event_id`. This is the primary key for idempotency, replay, deduplication, and audit.

**If Codex emits native event IDs in the rollout JSONL:** use those.

**Otherwise (the v0.2 default):**

```
source_event_id = sha256(
    source_rollout_path + "\n" +
    source_line_number  + "\n" +
    source_event_type   + "\n" +
    source_timestamp
)
```

The hash inputs are normalized strings: `source_rollout_path` is the absolute path to the rollout JSONL file; `source_line_number` is a 1-indexed integer; `source_event_type` is the normalized event type (§4); `source_timestamp` is the ISO 8601 value from the rollout line.

Same input → same hash → same `source_event_id`, every time, across machines.

### §3.2 Derived identity tuple

`(session_id, turn_idx, event_idx)` are **derived** fields, useful for reasoning, grouping, and queries, but they are not the primary key.

- `session_id`: stable within a rollout file (the Codex session UUID).
- `turn_idx`: monotonic per session; increments on each new user message OR each Codex task-start boundary. The exact rule is locked in §4.4.
- `event_idx`: monotonic within a turn; assigned by the adapter as it reads rollout lines.

If the adapter recomputes these from the same rollout, it gets the same values. They are deterministic but secondary; the hash is what enforces uniqueness.

### §3.3 Why this matters

Two reasons:

- **Idempotency at the rollout-line layer.** Replaying the same rollout produces the same `source_event_id`s. Inserting an already-present `source_event_id` is a no-op. No need to reason about turn boundaries to know if you've seen an event.
- **Cross-source compatibility.** When a future adapter (e.g., a Claude Code adapter, or any other agent harness) is built, it uses the same identity scheme. The substrate doesn't care where events came from; the read-path's queries work uniformly.

---

## §4 Normalized event schema (locked before rules)

The rule engine fires against this schema. Locking it first prevents the rules from drifting against undefined event shapes.

### §4.1 Event type taxonomy (v0.2)

| `event_type`        | Source in Codex rollout | Required fields beyond identity | Optional |
|---|---|---|---|
| `user_message`      | user role line | `content` (string) | — |
| `assistant_message` | assistant role line, content-only (no tool calls inside) | `content` (string) | — |
| `assistant_reasoning` | reasoning record | `content` (string) | — |
| `tool_call`         | assistant role line, tool_calls block | `tool_name`, `arguments_json`, `call_id` | — |
| `tool_result`       | tool role line | `call_id` (matches a prior tool_call), `output` (string), `exit_code` (int, when shell), `stderr_first_line` (string) | `file_paths_touched` (list), `terminal_output` (string) |
| `task_start`        | task start record | `task_name` | `task_id` |
| `task_completion`   | task completion record | `task_id` | `final_status` |

This is the complete v0.2 taxonomy. Any rollout line that doesn't match one of these is logged and ignored. The session is marked `admissibility-eligible=false` if any line is unmatched (capture completeness, §6).

### §4.2 Event record shape

Every persisted event row carries:

```
{
  source_event_id:      str,    # primary key, hash from §3.1
  session_id:           str,
  turn_idx:             int,    # derived
  event_idx:            int,    # derived, monotonic within turn
  event_type:           str,    # from §4.1 taxonomy
  timestamp:            str,    # ISO 8601, from rollout
  payload:              dict,   # event-type-specific fields per §4.1
  source_rollout_path:  str,    # for replay + audit
  source_line_number:   int,    # for replay + audit
  call_id:              str | null,  # for tool_call/tool_result correlation
}
```

### §4.3 Schema validation at ingest

The HTTP endpoint validates every incoming event against §4.1 before persistence. Validation failures are logged with the source line number; the offending event is rejected; the session is marked `admissibility-eligible=false`. Validation has no fuzzy paths — a missing required field is a hard reject.

### §4.4 Turn-boundary rule (locked)

A new `turn_idx` increments on either of these conditions, whichever comes first:

1. A `user_message` event is observed.
2. A `task_start` event is observed.

`event_idx` resets to 0 at each turn boundary. This rule is deterministic and replayable.

---

## §5 Streaming rule engine

### §5.1 Shared canonical derivation spec

The streaming engine and the v0.1 batch engine each implement a **derivation spec**: for each belief type in their supported subset, what events mint, refresh, weaken, contradict, confirm, or retire it.

The v0.2 streaming engine implements a strict subset of the v0.1 batch engine's belief types. For belief types in the streaming subset, **both engines must use the same derivation spec** — same predicates, same lifecycle transitions, same authority handling.

This shared spec is the load-bearing artifact for §7 acceptance test 6. It lives at:

```
tkos_sidecar/RULES_SPEC_v0.2.md
```

(A separate document to be written before rule code. The spec is the locked contract; the code is its implementation.)

### §5.2 v0.2 supported belief subset

The minimum set sufficient for end-to-end demonstration:

- `fix_attempted`
- `validation_pending`
- `validation_complete`
- `pipeline_running`
- `pipeline_failed`
- `action_blocked`
- `user_approval_pending`
- `report_ready`

These are the eight from the sketch §3, unchanged. The optional `failure_signature_active` is deferred to a later version.

### §5.3 Event-to-rule dispatch

Per event type, the engine evaluates a small fixed set of rules. Each rule has:

- A predicate over current `active_beliefs` plus the incoming event.
- A lifecycle action: `born` / `refreshed` / `weakened` / `contradicted` / `confirmed` / `retired`.
- A one-line `note` recorded in `belief_events.note` for audit.

The dispatch table is enumerated explicitly in `RULES_SPEC_v0.2.md`. Rules cannot reference event fields outside the §4.1 schema for their event type.

### §5.4 `effective_turn` and `observed_at_turn` for retro-minting

Some rules fire retroactively. The canonical example: minting `pipeline_running` after K=3 turns without a matching `tool_result`. The belief was effectively true at the original `tool_call` turn, but only observable as `pipeline_running` once enough subsequent turns have passed without resolution.

The audit trail records both:

- `effective_turn` — the turn at which the belief is asserted to be true.
- `observed_at_turn` — the turn at which the rule fired and the belief was minted.

For non-retro rules, the two values are equal. For retro-minted rules, `observed_at_turn > effective_turn`. The read-path's `reconstruct_state(turn=T)` should include retro-minted beliefs whose `effective_turn ≤ T`, even if `observed_at_turn > T`. (This is a read-path semantic decision; the read-path's existing `reconstruct_state` already supports it once the new column is present.)

### §5.5 What v0.2 does NOT do

- No LLM scoring inside rules.
- No probabilistic belief weights. Lifecycle states are categorical.
- No retroactive rule changes (rule code updates require a full replay from event 1 to take effect).
- No fuzzy belief matching across sessions. Beliefs are session-local.

### §5.6 Determinism guarantee

Given the same locked `RULES_SPEC_v0.2.md` and the same event stream (identified by `source_event_id`), the engine produces the same `belief_events` rows in the same order. This is what makes `tkos replay` reproducible and acceptance test 5 verifiable.

---

## §6 Atomicity and capture completeness

### §6.1 Atomicity invariant

Each `observe(event)` call wraps the following in a single SQLite transaction:

1. Insert the event row into `events`.
2. Run all applicable rules; insert their `belief_events` rows.
3. Update the materialized `active_beliefs` view.
4. Append an `ingest_log` row recording which rules fired.

If any step fails, the entire transaction rolls back. The DB is never in a half-applied state. There is no path where an event row exists without its corresponding `belief_events` rows (and vice versa).

If a rule throws an unhandled exception, the transaction rolls back, the rule failure is logged in a separate `rule_failures` table (outside the rolled-back transaction), and the HTTP endpoint returns a 500 with the rule name. The session is marked `admissibility-eligible=false`.

### §6.2 Capture completeness checks

A session is **capture-complete** if and only if all of the following pass after the rollout file has been ingested:

1. **Sequence validation.** Within each `turn_idx`, `event_idx` is `[0, 1, 2, ...]` with no gaps and no duplicates.
2. **Transcript hash.** A hash of the rollout JSONL file (taken at ingest time and stored in `session_status`) matches a hash recomputed from the persisted events (reconstructed in `source_line_number` order). Mismatch means truncation, corruption, or out-of-order ingestion.
3. **Schema completeness.** Every line of the rollout matched a §4.1 event type (no unmatched lines, no validation failures).
4. **No rule failures.** No rows in `rule_failures` for this session.

The CLI command `tkos verify <session_id>` runs all four checks and returns pass/fail with the specific failure mode if any fail. A session is `admissibility-eligible=true` only if all four pass.

### §6.3 What admissibility-eligibility means here

In v0.2, `admissibility-eligible=true` means "this session's traces meet all the technical conditions that would be required for v0.4c2 admission, *if* this project were the v0.4c2 substrate project, *which it is not*."

This software-side admissibility check is exercised against the sidecar's own traces during the build, validating that the capture mechanism works. The v0.4c2 substrate project, when it starts, will rely on the same checks against its own traces.

---

## §7 Acceptance tests (nine, locked)

Each test is concrete, runnable, and fails clearly when broken.

1. **Single-event ingest.** POST one valid `tool_call` event; verify it appears in `events` with all §4.2 fields populated; verify the transaction succeeded.
2. **End-to-end demo session.** Replay the sketch §7 demo scenario (18 turns) through `observe()`. Verify the final `active_beliefs` contains exactly the beliefs the demo specifies (post-deploy: `report_ready` active, others retired or confirmed).
3. **Lifecycle transitions.** Replay the same scenario and verify each `belief_events` row matches the expected lifecycle transition per `RULES_SPEC_v0.2.md`.
4. **Out-of-window beliefs survive.** Replay a 50-turn synthetic session in which a `user_approval_pending` belief is minted at turn 5 and not addressed until turn 48. Verify `state(session, turn=48)` returns it.
5. **Replay idempotency.** Run `tkos replay <trace.jsonl>` twice; verify the second run inserts zero new rows. Idempotency is keyed on `source_event_id`.
6. **Streaming/batch equivalence over the shared subset.** Take a real Claude Code session from the v0.1 corpus; run it through the streaming engine with `RULES_SPEC_v0.2.md`; run it through the batch engine restricted to the same belief subset and the same spec; verify `active_beliefs` matches for the supported belief types. Belief types outside the shared subset are excluded from the comparison.
7. **Codex adapter round-trip.** Capture a Codex session in live mode; replay the captured rollout JSONL through batch mode; verify identical resulting state.
8. **Read-path compatibility.** After write-path populates the DB from a Codex session, call the existing read-path's `reconstruct_state` and `build_overlay` against it. Verify both queries return well-formed results with no schema mismatches.
9. **Export determinism.** Capture a session and run `tkos export <session_id>` twice with no DB changes between runs. The two output files must be byte-identical. Requires stable ordering (sort by `source_event_id` lexicographically) and no non-deterministic fields.

Tests 5, 6, 8, and 9 are the load-bearing ones. They define what "correct" means.

---

## §8 Data model additions

The read-path's existing tables get one additive change (the new identity column); existing read-path queries continue to work unchanged.

### §8.1 `events` schema amendment

The existing `events` table gets `source_event_id TEXT PRIMARY KEY` as the new primary key, with `(session_id, turn_idx, event_idx)` indexed. Existing fixtured rows backfill `source_event_id` deterministically with a fixture-specific scheme (e.g., `sha256("fixture:" + session_id + ":" + turn_idx)`).

Additional new columns on `events`:
- `event_idx INTEGER NOT NULL DEFAULT 0`
- `source_rollout_path TEXT`
- `source_line_number INTEGER`
- `call_id TEXT`

### §8.2 `belief_events` schema amendment

Add `effective_turn INTEGER` (nullable, defaults to `at_turn`). The existing `at_turn` field is renamed semantically to `observed_at_turn` (column name unchanged for compatibility). For non-retro rules, `effective_turn = observed_at_turn` is enforced at write time.

### §8.3 `session_status` (new)

| Column | Type | Notes |
|---|---|---|
| session_id | TEXT PRIMARY KEY | |
| source_rollout_path | TEXT NOT NULL | |
| transcript_hash | TEXT NOT NULL | hash of the rollout JSONL at ingest time |
| capture_started_at | TEXT NOT NULL | ISO 8601 |
| capture_ended_at | TEXT | nullable until session closed |
| capture_started_at_turn | INTEGER NOT NULL | must be 0 for admissibility-eligible |
| admissibility_eligible | INTEGER NOT NULL DEFAULT 1 | flipped to 0 by any §6.2 failure |
| failure_reasons | TEXT | JSON list of reasons if admissibility_eligible = 0 |

### §8.4 `rule_failures` (new)

Append-only audit of rule-engine exceptions. Outside the atomic transaction so it survives rollbacks.

| Column | Type | Notes |
|---|---|---|
| failure_id | INTEGER PRIMARY KEY | |
| session_id | TEXT NOT NULL | |
| source_event_id | TEXT NOT NULL | the event being processed when the rule failed |
| rule_name | TEXT NOT NULL | |
| exception_class | TEXT NOT NULL | |
| exception_message | TEXT | |
| logged_at | TEXT NOT NULL | ISO 8601 |

### §8.5 `ingest_log` (new, retained from v0.1.1)

Append-only audit of every `observe()` call.

| Column | Type | Notes |
|---|---|---|
| ingest_id | INTEGER PRIMARY KEY | |
| source_event_id | TEXT NOT NULL | |
| session_id | TEXT NOT NULL | |
| received_at | TEXT NOT NULL | |
| rules_fired | TEXT | JSON list of rule names |
| transaction_status | TEXT NOT NULL | `committed` / `rolled_back` |

---

## §9 Build plan

Each step's traces remain non-admissible for v0.4c2 (the sidecar build is software-only per §1.2).

1. **Bootstrap.** Create the new files; lock `RULES_SPEC_v0.2.md`; add `session_status`, `rule_failures`, `ingest_log` tables to DDL; backfill `source_event_id` for existing fixtures.
2. **Trace capture, no rules.** Implement the HTTP endpoint with §4.3 schema validation and §6.1 atomicity. Get `tkos serve` and `tkos replay` working. Wire the Codex trace adapter (§3 hash-based identity; §4.4 turn-boundary rule). Pass acceptance test 1.
3. **Capture-completeness checks.** Implement `tkos verify`. Pass §6.2's four checks against a known-good captured session.
4. **First rule pair.** Implement `validation_pending` mint from `tool_call` and `validation_complete` mint from `tool_result`. Pass tests 2 and 3 for these two belief types.
5. **Remaining rules.** Implement the rest of §5.2's belief subset. Pass tests 2 and 3 fully.
6. **Long-session correctness.** Pass test 4.
7. **Idempotency.** Pass test 5.
8. **Streaming/batch equivalence over the shared subset.** Pass test 6. Hardest test; expect iteration. This is what validates `RULES_SPEC_v0.2.md`.
9. **Codex adapter polish + read-path compatibility.** Pass tests 7 and 8.
10. **Export.** Implement `tkos export` with stable ordering. Pass test 9.
11. **Software ships.** Verify `tkos verify` passes against multiple captured Codex sessions of varying lengths. Document the verified-working state.
12. **(Separate project) v0.4c2 substrate begins.** A fresh Codex project starts; trace capture is wired from session 1; the v0.4c2 admission criteria apply to that fresh project. This is not part of v0.2 of the sidecar.

---

## §10 Invariants

These hold across v0.2 and constrain refactors:

- **Read-path is read-only of the write-path's output.** No reach-back.
- **Every belief lifecycle transition has a `belief_events` row.** No silent state mutations.
- **`source_event_id` is unique.** Two rows with the same hash represent the same source event.
- **Atomicity.** Event persistence + rule effects commit or roll back together.
- **Streaming-equals-batch over the shared subset.** Acceptance test 6.
- **Capture completeness is binary.** A session passes all four §6.2 checks or it doesn't. No partial admissibility.
- **Software-only.** The sidecar's own captured traces are not the v0.4c2 substrate.

---

## §11 Failure modes (what should never happen silently)

- A rollout line doesn't match any §4.1 event type → log, drop, mark session `admissibility-eligible=false`. Do not invent a mapping.
- A rule throws an exception on an event → roll back the transaction, log to `rule_failures`, return 500, mark session `admissibility-eligible=false`.
- The DB schema diverges from what the read-path expects → fail loudly on startup.
- Two sessions interleaved on the same HTTP endpoint → supported (sessions are id-scoped) but log if interleaving rate exceeds a configurable threshold.
- A `source_event_id` collision (same hash, different content) → in practice impossible with sha256, but on detection: hard fail.
- A capture-completeness check fails → the session is admissibility-eligible=false and a `tkos verify` report explains why.

---

## §12 Locked decisions (carried from v0.1.1, refined)

- **Q1. HTTP framing:** one event per POST. Unchanged.
- **Q2. Codex transcript location:** `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. Resolved.
- **Q3. Long-running tool detection:** K=3 unmatched-result rule, with `effective_turn` = original `tool_call` turn, `observed_at_turn` = retro-mint turn. Refined per §5.4.
- **Q4. Failure signature:** simple `exit code + first stderr line` matcher.
- **Q5. Multi-process safety:** SQLite WAL + startup lock file.
- **Q6. Export format:** JSONL per session, one line per event, sorted by `source_event_id` lexicographically. Each line carries the event record (§4.2) plus the `active_beliefs` snapshot computed up-to-and-including that event. Stable ordering and deterministic content per acceptance test 9.

---

## §13 What this scope does NOT commit to

- The v0.4c2 pre-registration (written after the substrate exists).
- LLM-driven belief extraction (separate research direction).
- IDE integration beyond Codex (out of scope).
- Live integration with Claude Code (the Claude Code corpus is fixtured; the streaming engine can ingest a Claude Code rollout via a separate adapter, but that adapter is not in v0.2).
- `failure_signature_active` belief type (deferred).
- Production-grade hosting (single-user, local-process only).

---

## §14 Deliverables at v0.2 close

When all nine acceptance tests pass and the build plan steps 1–11 complete:

- A running `tkos serve` ingesting Codex events.
- A working `tkos replay` re-processing saved traces idempotently.
- A working `tkos verify` checking capture completeness.
- A working `tkos export` producing byte-identical artifacts.
- Existing read-path queries return correct results against write-path-populated DB.
- `RULES_SPEC_v0.2.md` locked and verified against the v0.1 batch engine over the shared subset.
- A verified-working trace-capture mechanism, ready for a separate v0.4c2 substrate project to begin against.

Expected timeline: 3–4 weeks of focused Codex-assisted work for a competent Python developer.

---

*This scope is implementation-ready. The decoupling from v0.4c2 substrate work, the `source_event_id` identity primitive, the locked event schemas before rules, the narrowed equivalence test, the atomicity invariant, and the capture-completeness checks each came from a build-time audit (Codex review of v0.1.1, 2026-06-05) that found contradictions before code flowed. The audit doing its job is what makes this version safer to build against.*
