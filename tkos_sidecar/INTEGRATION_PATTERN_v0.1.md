# Belief Stack Integration Pattern v0.1

**Date:** 2026-06-06
**Status:** v0.1 working draft — harness-focused, not product copy. Iterates as integrations land.
**Audience:** anyone wiring Belief Stack (via the TKOS sidecar or any compatible implementation) into an agent harness (Claude Code, Codex, custom).

This document is **not** about why Belief Stack matters. It is about how to slot it into a real agent's context-construction pipeline. For positioning copy, see [`topicspace.ai/research/belief-stack`](https://topicspace.ai/research/belief-stack).

---

## §1 Where Belief Stack sits in the token-cost toolkit

The current industry token-saving toolkit has four widely-discussed families. Belief Stack is a fifth. It does **not** compete with the four.

| Family | What it solves | Belief Stack relationship |
|---|---|---|
| **Prompt caching** (K/V, prefix, semantic) | Stable-prefix cost — system prompts, tool schemas, examples charged repeatedly | Complementary. Cache the stable prefix; project Belief Stack into the variable part. |
| **Lazy-load dormant tokens** (Anthropic Tool Search, layered memory) | Bloated tool/capability lists in context | Peer abstraction at the same layer of the stack. Both keep a compact handle in context with rich content fetched elsewhere; just different content types — capabilities vs world-state. |
| **Routing / cheap models** (RouteLLM, cascades, subagents) | Paying frontier prices for easy tasks | Orthogonal. Belief Stack lifts any model. Pairing with cheaper models is defensible (substrate compensates for reconstruction the cheaper model can't do internally). |
| **Compaction** (autonomous compression, summary buffers) | History bloat once it has already happened | **Upstream alternative, not competitor.** Compaction says: *history got too big; summarize it.* Belief Stack says: *don't make history carry state in the first place.* |

The right mental model for an implementer: **five complementary techniques attacking five different cost axes.** Pick the ones that fit your harness and compose them.

---

## §2 The layer-cake context shape

The recommended prompt/context construction for a harness using Belief Stack:

```
┌─────────────────────────────────────────────────────────┐
│ [ stable system prompt          ]  ← prompt caching     │
│ [ tool definitions / tool search]  ← lazy-loading       │
│ [ layered memory index          ]  ← project memory     │
│ [ BELIEF STACK PROJECTION       ]  ← current state      │
│ [ K=3 recent turns              ]  ← execution detail   │
│ [ current user message          ]                       │
└─────────────────────────────────────────────────────────┘
```

Per-turn changeability (top is most stable, bottom is most variable):

| Layer | Changes per turn? | Cacheable? |
|---|---|---|
| Stable system prompt | No | Yes (frontier providers' prompt-cache API) |
| Tool definitions / search index | No | Yes |
| Layered memory index | Rarely (once per session) | Yes within a session |
| **Belief Stack projection** | **Yes** | No (changes by design); kept small to bound cost |
| K=3 recent turns | Yes | No (changes by design) |
| Current user message | Yes | No |

The Belief Stack projection is the new layer this document introduces. Everything above and below it is what most production agent harnesses already do.

---

## §3 Sidecar integration architecture

Belief Stack runs as a sidecar. It is not part of the agent harness's main process. The interface is four operations.

### §3.1 Diagram

```
                    agent harness
                       │   ▲
                events │   │ projection
                       ▼   │
                 ┌─────────────────┐
                 │  TKOS sidecar    │
                 │  (Belief Stack)  │
                 └─────────────────┘
                          │
                  audit ▼ │
                 ┌─────────────────┐
                 │  human inspection │
                 │  (CLI, future UI) │
                 └─────────────────┘
```

### §3.2 Operations

| Operation | Direction | Purpose |
|---|---|---|
| `observe(event)` | harness → sidecar | Stream session events to the substrate. One event per call. |
| `overlay(session_id, budget_tokens, ...)` | harness → sidecar → harness | Get a sparse, ranked, budget-bounded projection of current belief state for injection into the planner's context. |
| `state(session_id, turn=None)` | human / audit → sidecar | Return the full belief state with warrants and lifecycle — for human inspection, not for the agent. |
| `risk(session_id, action)` | harness → sidecar → harness | Optional advisory check: any blockers for a proposed action? Information only; sidecar never blocks the agent. |

### §3.3 The two consumer surfaces

- **Agent surface:** `overlay()` returns bare `belief_type :: claim` per active belief, ranked and budget-bounded (per v0.4a/v0.4c1 results: ~241 mean tokens). This is what goes in context.
- **Human surface:** `state()` returns the same beliefs with full warrant chains, lifecycle audit trail, and authority signals. This is what a developer/auditor reads via CLI or trace viewer.

Same substrate. Different projections. The substrate-vs-projection split is the architectural commitment.

---

## §4 Pull strategies

How often does the harness call `overlay()`? Three viable patterns, in priority order.

### §4.1 Per-plan (recommended default)

Call `overlay()` immediately before each planning step. Highest precision: the projection reflects every event up to the moment of the decision.

- **When to use:** the harness can intercept the "about to plan" moment cleanly.
- **Cost:** one sidecar call per planning step; with v0.4c1 budgets (~241 tokens) the per-call ingest cost is small.
- **Trade-off:** none for correctness; adds a single sidecar round-trip to the planning latency budget.

### §4.2 On state-change signal

Call `overlay()` when the sidecar emits a state-change webhook (a belief was minted, refreshed, contradicted, or retired). The harness caches the most recent overlay and reuses it until the next signal.

- **When to use:** the harness has a long-running session loop and wants to minimize round-trips.
- **Cost:** fewer sidecar calls; requires a webhook channel (HTTP callback, file watcher, or similar).
- **Trade-off:** the cached overlay may be stale between signals; requires the harness to trust the signal.

### §4.3 TTL refresh

Call `overlay()` every N seconds or every M turns, whichever comes first.

- **When to use:** the harness cannot hook into planning moments and cannot accept webhooks.
- **Cost:** lower than per-plan if N/M is generous; higher than state-change if traffic is bursty.
- **Trade-off:** stale projections between refreshes — a belief contradicted at turn T may not appear in the projection until turn T+M.

**Recommendation:** default to per-plan. Fall back to TTL only if per-plan integration is impossible.

---

## §5 Placement strategies

Where in the prompt does the overlay land?

| Placement | Mechanism | Trade-off |
|---|---|---|
| **Tool result / observation (LOCKED default)** | Inject as the result of a virtual tool call named e.g. `get_current_state()` | Treated by the model as an observation, not an instruction. No authority confusion. |
| User-message inline tag | Wrap in a tag like `<current_state>...</current_state>` inside the user message | Mixes user intent with system observation; some models privilege earlier system content over later user content. |
| System prefix | Concatenate to the system prompt | Authority confusion: the system prompt says *how to behave*; the projection says *what current state is*. These are different categories; mixing them muddles the model's frame. |

**The default placement is tool-result observation.** Other placements are not forbidden but require evidence to choose. The reason for the default:

- System prompt = how to behave (authority).
- Belief Stack projection = what current state is (observation).

Don't confuse the two. The tool-result framing keeps the categories clean: the agent has a tool that returns current state, and the result is treated as ground truth observation, not as an instruction.

---

## §6 Plan/execute split

The v0.3 / v0.4a / v0.4c1 experiments measured at **planning resolution** — single-next-action decisions. Execution-time may not need the overlay at all.

A natural two-mode harness:

```
plan(belief_overlay)  → returns a next action
execute(action, scratchpad) → carries out the action with K=3 raw turns for execution detail
```

The overlay is what `plan()` consumes. The scratchpad is what `execute()` consumes. They are not the same surface.

**Practical implication for integration:**
- Inject the overlay only at planning moments. Don't include it in execution-time tool calls.
- The K=3 scratchpad (recent raw turns) lives separately and persists across both modes — but it's small and bounded.
- This is the architecture v0.3 measured and v0.4c1 replicated across four models.

If the harness doesn't separate plan from execute (single-call architecture), inject the overlay once per turn and accept the small cost of including it in execution-time calls. The data does not say this is harmful.

---

## §7 Minimal viable integration

The smallest set of changes to turn an existing agent harness into a Belief-Stack-using harness:

### §7.1 Pre-integration assumptions

- The harness already has a notion of "session" (each user-task interaction).
- The harness emits identifiable events: user messages, assistant messages, tool calls, tool results, file edits.
- The harness can intercept context construction before sending to the model.

### §7.2 What to add

1. **Sidecar:** run `tkos serve` in a separate process. Local HTTP. SQLite-backed. No auth required for v0.1.
2. **Event emitter:** in the harness's main event loop, POST each event to the sidecar as it happens. Don't wait for batches.
3. **Overlay fetch:** at planning time, GET `/overlay?session_id={id}&budget=300` from the sidecar.
4. **Context injection:** inject the returned overlay text as a tool result for a virtual tool call named `get_current_state`.

That's the minimum. Four touchpoints. No streaming, no native integration, no harness rewrite.

### §7.3 What does NOT need to change

- The harness's existing prompt caching strategy.
- The harness's existing tool definitions or tool-search integration.
- The harness's existing memory layering.
- The harness's existing routing or subagent setup.
- The model the harness uses for planning.

Belief Stack adds a layer; it doesn't replace what's already there.

### §7.4 Reference integrations

- **Codex via TKOS write-path sidecar (v0.2):** the reference integration. See [`TKOS_WRITE_PATH_SCOPE_v0.2.md`](./TKOS_WRITE_PATH_SCOPE_v0.2.md). The Codex trace adapter reads `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` and POSTs events to the sidecar. Overlay is injected at planning moments.
- **Claude Code (planned):** would use the same sidecar with a different trace adapter reading Claude Code's session logs. Architecturally identical; differs only in the input adapter.

---

## §8 Non-goals (what Belief Stack integration is NOT)

To prevent scope drift:

- **Not a replacement for prompt caching.** Use prompt caching alongside.
- **Not a replacement for lazy-loaded tools.** Use Tool Search or equivalent alongside.
- **Not a replacement for model routing.** Use routing alongside; Belief Stack helps the routed-to model plan correctly.
- **Not a replacement for aggressive compaction.** It is the upstream alternative to compaction-as-state-management; if history still bloats for other reasons (long raw responses, voluminous tool outputs), compact separately.
- **Not an LLM-driven extractor.** v0.1 uses deterministic rules. LLM-driven extraction is a future research direction.
- **Not a memory store.** Beliefs are session-local in v0.1. Cross-session reasoning is a different system.
- **Not a governance / safety / blocking layer.** `risk()` is advisory only. The sidecar never reaches into the host or stops actions.
- **Not a runtime intervention system.** The sidecar observes; the harness decides.

---

## §9 What's missing from v0.1 of this spec

Honest gaps to be filled in v0.2:

- **Overlay format normalization.** Today the overlay is a string. A structured format (JSON with type/claim/authority fields) may be preferable for harnesses that want to render or parse it.
- **Streaming overlay updates.** Some harnesses may want a streaming connection so the overlay can update mid-call. Not in v0.1.
- **Multi-session overlays.** "Show me all currently-pending approvals across all my sessions" is a cross-session query. Not in v0.1.
- **Cross-implementation compatibility tests.** This spec describes the integration pattern; a conformance test suite for "is this a real Belief Stack?" is future work.

---

*This integration pattern reflects what the v0.3 / v0.4a / v0.4c1 experimental program measured: a sparse maintained-state projection injected at planning resolution, against a substrate that preserves warrants and lifecycle for separate human inspection. The architecture composes with the rest of the agent-cost-management toolkit. The locked default placement (tool-result observation) and pull strategy (per-plan) are the minimum-friction integration. Both are revisable when evidence justifies.*
