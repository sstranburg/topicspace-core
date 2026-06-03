# CLAUDE.md

Cold-start orientation for any AI agent (Claude, GPT, or otherwise) joining this project. Read this first. Target: 10 minutes.

The human-facing companion to this file is [`ops/operating_principles.md`](ops/operating_principles.md). Same substrate, different surfaces — see [project_dual_consumer_pattern_recurs.md](../../.claude/projects/-Users-sue-Documents-git-storm/memory/project_dual_consumer_pattern_recurs.md) in memory for why this matters.

---

## What this project is

**TopicSpace Research** — a research project on **runtime belief observability for AI systems**.

The thesis: **Maintained state is a planning primitive.** Most agent harnesses today track *execution state* (what the system has done). Belief Stack maintains *belief state* (what the system currently holds to be true, with provenance, lifecycle, and a contradiction signal). v0.3 measured this directly: on a 75-question single-next-action planning task derived from 164 Claude Code session logs, a 285-token maintained belief overlay outperformed a 2,037-token raw log by 8 percentage points (98.7% vs 90.7%) at 3× lower latency and 14% of the input tokens.

Primary public artifact: [topicspace.ai](https://topicspace.ai). The Belief Stack spec lives at [topicspace.ai/research/belief-stack](https://topicspace.ai/research/belief-stack).

---

## When you arrive in a new session

A reproducible orientation sequence:

1. Read `MEMORY.md` (the auto-memory index) — gives you the active set of project facts, feedback disciplines, and references.
2. `git -C /Users/sue/Documents/git/storm status` and `git log --oneline -10` — see what's recent.
3. Skim [`ops/backlog.md`](ops/backlog.md) — see what's queued.
4. Ask Sue: *"What are we working on today?"* The plan rarely lives in the backlog yet on a given day; Sue carries it and will tell you.

---

## Working directories

| Path | What it is |
|---|---|
| `/Users/sue/Documents/git/storm` | Primary research repo. Experiments, pre-registrations, case studies, pipelines, ops. |
| `/Users/sue/Documents/git/topicspace-site` | Next.js 15 site — the public surface (essays, spec, case studies, homepage). |
| `~/.claude/projects/-Users-sue-Documents-git-storm/memory/` | Auto-memory system. Persistent context across sessions. ~30 files. |

---

## How to operate

The full discipline lives in [`ops/operating_principles.md`](ops/operating_principles.md). Eight rules in summary:

1. **Nothing important lives only in chat.** Durable artifact before context moves on.
2. **Experiment before conclusion.** Pre-registered claims; everything else is hypothesis.
3. **Lock before run.** Amendments explicit, never silent.
4. **Report failures.** Negative results are first-class.
5. **Evidence outranks intuition.** Measured result wins.
6. **Name the critique class** before responding (matter / generality / mechanism / cost).
7. **Backlog is canonical.** [`ops/backlog.md`](ops/backlog.md).
8. **Decisions require trace.** Reason + reversibility.

Read the constitution when in doubt.

---

## Vocabulary

The post-v0.3 hierarchy (locked 2026-06-03). Each layer plays a distinct role:

| Layer | Concept | Role |
|---|---|---|
| **Thesis** | Maintained state is a planning primitive | The claim |
| **Product** | Belief Stack | The named layer — *the spec* |
| **Architecture** | TKOS (Temporal Knowledge Operating System) | The runtime engineering |
| **Belief state** | Claims · warrants · lifecycle | The mechanism — what lives inside |
| **Result** | Reduced reconstruction tax | The measured outcome |

Other vocabulary:
- **OB-001 / OB-002 / OB-003 (a.k.a. v0.1 / v0.2.2 / v0.3)** — versions of the Operational Belief-State Grounding experiment line. v0.3 is the current locked result.
- **REPI** (Runtime Epistemic Infrastructure) — historical category framing. **Demoted post-v0.3.** Do not surface unless directly asked.
- **TopicSpace** (the original product) — narrative-intelligence work on AI-ecosystem markets. Archived but still hosted; not the active research focus.
- **Sensemaking v1.5** — Belief Stack applied to the markets substrate. Near-chance aggregate calibration with measurable regional heterogeneity. Different methodology, different success criteria than the operational line.

---

## Memory system

Persistent context for agents lives at `~/.claude/projects/-Users-sue-Documents-git-storm/memory/`. About 30 files organized by type:

- **`project_*`** — facts about state, decisions, architecture
- **`feedback_*`** — disciplines Sue has given (operating heuristics)
- **`reference_*`** — pointers to external resources or schemas

Index: `MEMORY.md`. Read it at the start of every session. The index entries are one-line hooks; click through to the file when relevant.

**Read these first when you join:**

- `project_belief_stack_claim_hierarchy.md` — four positioning claims at different abstraction layers; do **not** surface all four everywhere
- `project_belief_stack_lifecycle_is_novelty.md` — the core architectural defense (claims + warrants + lifecycle; do not collapse to "belief = summary")
- `project_belief_stack_open_questions_post_v03.md` — four explicitly-open questions + the matter/generality/mechanism/cost critique-class triage
- `project_dual_consumer_pattern_recurs.md` — the load-bearing design pattern that recurs across Belief Stack and the operating model itself
- `feedback_default_to_yes.md` — operating heuristic for long pipelines
- `feedback_l1_representation_contract.md` — what L1 actually owes (label + warrant + applicability bounds)

When you learn something durable, save it as memory and add a line to `MEMORY.md`. Don't duplicate facts derivable from repo state.

---

## Where to find current state

| Question | Where to look |
|---|---|
| What's queued? | [`ops/backlog.md`](ops/backlog.md) — canonical |
| What just shipped? | `git log --oneline -20` on storm + topicspace-site |
| What's the current research thesis? | [topicspace.ai/research/belief-stack](https://topicspace.ai/research/belief-stack) |
| What experiments exist? | `belief_stack_v0_3/`, `operational_belief_v1/`, `operational_belief_v2/` — each has PRE_REGISTRATION + REPORT |
| What decisions matter and why? | Commit messages on main + the `project_*` memories |
| What is being kept deliberately open? | `project_belief_stack_open_questions_post_v03.md` |

A formal experiment ledger (`ops/experiment_ledger.md`) is planned but not yet built. For now, treat the experiment directories as the ledger.

---

## How Sue likes to work

Condensed working agreement. Full forms live in the `feedback_*` memories.

- **Terse > verbose.** One-sentence status updates. No narration of what you're about to do; do it.
- **Default to yes** on long pipelines like `/evening`. Don't pause to confirm at every step; proceed and report after.
- **Build / audit / pause** rhythm for substantive work. Build → check → flag anomalies → pause for input → continue.
- **Lock before run.** When designing experiments, lock the spec before executing. Amendments are re-locks, not silent edits.
- **Match scope to ask.** Don't add features, refactors, or abstractions beyond what was requested.
- **Save successes too**, not only corrections — quiet validations of a non-obvious choice are worth remembering.
- **Never use `npx tsc --noEmit`.** npm/npx swallow the flag; tsc emits `.js` next to `.tsx`. Use `npx next build` to type-check.
- **Always `cd` explicitly** for repo operations — Bash cwd resets between calls. Use `cd /Users/sue/Documents/git/topicspace-site && ...` every time.
- **Clear `.next` before local builds** — stale cache causes false failures.
- **Stage everything in topicspace-site** before pushing for deploy, not just the changed file.

---

## Build & deploy (topicspace-site)

Local verification:

```bash
cd /Users/sue/Documents/git/topicspace-site
rm -rf .next
npx next build
```

Production deploy after commit + push to main:

```bash
cd /Users/sue/Documents/git/topicspace-site
npx vercel --prod --yes
```

Live site: [topicspace.ai](https://topicspace.ai). Custom domain auto-aliases to the latest production deployment.

---

## Repository structure

**storm** (research):
- `belief_stack_v0_3/`, `operational_belief_v1/`, `operational_belief_v2/` — experiment directories (each: PRE_REGISTRATION, REPORT, scripts, data)
- `tkos_sidecar/` — TKOS-002 read-path slice (Python, SQLite-backed; `tkos.py` + `test_tkos.py`)
- `scripts/` — pipeline scripts (fetch, embed, detect, summarize, propagation, pressure, watchlist, etc.)
- `src/` — Python modules (`config.py`, `ingest_x.py`, `actor_grouping.py`, `strategic_watchlist.py`, etc.)
- `ops/` — operating principles, backlog, archive
- `data/derived/` — pipeline outputs (parquet, JSON)
- `social/`, `public/charts/` — generated artifacts

**topicspace-site** (public surface):
- `app/page.tsx` — homepage
- `app/research/belief-stack/page.tsx` — the spec
- `app/research/case-studies/` — case study pages (sensemaking-v1, tkos-log-replay-v1, belief-stack-v0-3)
- `app/research/pre-registrations/` — pre-registration pages
- `app/writing/` — essays
- `app/components/`, `app/lib/` — shared UI

---

## What this document is *not*

- Not a manual for every tool. Use `--help` or read the script.
- Not a complete glossary. The spec at [topicspace.ai/research/belief-stack](https://topicspace.ai/research/belief-stack) is the canonical vocabulary source.
- Not a substitute for `MEMORY.md`. The memory system carries the working set of project facts; this file is the cold-start orientation.

If you discover the document is wrong, fix it. If you discover it's incomplete in a way that costs another agent time, expand it. Same rule applies as for the constitution: update the artifact when it drifts.

---

*Living document. AI-facing entry-point for the project. Human-facing companion: [`ops/operating_principles.md`](ops/operating_principles.md). Last revision: 2026-06-03 (Session B of OPS-001).*
