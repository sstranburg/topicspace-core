# Backlog

The canonical backlog for TopicSpace Research. *Work that isn't here isn't queued — it's an idea in someone's head.*

Status: **partial — consolidated from two prior backlog files on 2026-06-03.** Items not yet adjudicated live in the Review Queue at the bottom of this file.

---

## Active priorities

| # | Item | Status | Next step |
|---|------|--------|-----------|
| **OPS-001** | Formalize the operating model | in progress — Session A shipped 2026-06-03 (`/ops/operating_principles.md`, this backlog) | Session B: write `CLAUDE.md` at storm root |
| **OPS-001 / Session B** | CLAUDE.md / AGENTS.md entry-point artifact | queued | Single-file project orientation, readable cold in <10 min |
| **OPS-001 / Session C** | `/write-work-order` Claude Skill | queued | Reusable ritual for structured work delegation |
| **PAPER-001** | *Maintained State as a Planning Primitive* — paper | in progress | Working draft v0.1 written 2026-06-04 (`paper/MAINTAINED_STATE_AS_PLANNING_PRIMITIVE_v0.1.md`). Covers v0.3 + v0.4a.1 + v0.4a.2. Iterate as cross-substrate, model-variance, and end-to-end-economics results land. |
| **v0.4** | Belief Stack v0.4 — replication across 4 axes | scoping | End-to-end cost + model variance + domain transfer + extraction-mechanism robustness (see `project_belief_stack_cost_frontier.md`). Post-v0.4a, **cross-substrate replication is highest priority** — the single-substrate caveat is the largest live risk to the v0.4a interpretation. |
| **TKOS write-path** | Live event ingestion → rule engine → derived `belief_instances` / `belief_events` | not started | Required to move v0.4 off fixtured beliefs onto a live substrate |
| **`tkos timeline`** | Belief-events stream CLI surface | not started | TKOS-002 §5.1 Q2/Q4/Q7 — quality-of-life for the human surface |
| **`tkos explain <belief_id>`** | Single-belief drill-down CLI | not started | TKOS-002 §5.1 Q3/Q5/Q8 — quality-of-life for the human surface |

---

## Recurring maintenance

Items that recur indefinitely and live here as a reminder, not as one-off work.

| # | Item | Cadence |
|---|------|---------|
| **MAINT-API-keys** | Monitor NewsAPI / X-API auth status; rotate when 403/402 returns | as-needed |
| **MAINT-daily-date** | Daily date propagation on signals + report — verify after each `/evening` | daily |
| **MAINT-shadow** | Maintain shadow-tracking baselines; review weekly drift | weekly |
| **MAINT-actors** | Add tracked actors when narrative warrants; backfill on add | as-needed |

---

## Review queue

Items inherited from prior backlog files. Status uncertain post–Belief-Stack pivot. **Not adjudicated; needs human triage.** See archived files for full text per item.

### From `ops/archive/BACKLOG_BELIEF_OBSERVABILITY_JUNE_2026.md`

All P0–P6 shipped (essay distributed, TKOS-002 read+overlay slices, OB-002 v0.2.2 locked + run, TopicSpace maintenance audit, Belief Stack v0.3 done). **OPS-001 is the live item from this backlog** and has been promoted to Active above. **P5** (Runtime sidecar / SDK) was deferred — likely subsumed by v0.4 + TKOS write-path; verify before re-queuing.

### From `ops/archive/BACKLOG_pre_OPS-001.md`

| Cohort | Count | Likely status | Reason |
|--------|-------|---------------|--------|
| **P-001 → P-009** (product / UX) | 9 items | **REVIEW STALE** | Most surfaces (intel, board, briefing UI) were archived or de-emphasized in the Batch 1 / Batch 2 site rewrite. P-007/P-008/P-009 already marked DONE. |
| **R-001 → R-011** (research questions) | 11 items | **REVIEW** | Research focus shifted from narrative-intelligence/market work to Belief Stack. Some R-### items may have become v0.4 inputs; most are likely de-prioritized. |
| **C-001 → C-006** (communication / writeups) | 6 items | **MIXED** | C-001 and C-004 marked DONE. C-003 (daily social posts) likely stale given new positioning; C-004 (formal research writeup), C-005 (replay format), C-006 (shadow tracking honesty piece) may have ongoing value. |
| **I-001 → I-010** (infrastructure) | 10 items | **MIXED** | I-008 and I-009 marked DONE. I-005 (daily date propagation) and I-006/I-007 (API auth) moved to Recurring Maintenance above. I-001 → I-004 are intel-surface specific; likely STALE. I-010 (add actors) moved to Recurring. |
| **Q-001 → Q-007** (question-graph quality) | 7 items | **REVIEW STALE** | The question-graph system is from the prior product focus. Almost certainly de-prioritized now; verify and bulk-archive. |

**Triage recommendation:** schedule one focused session to walk these in order (Product → Quality → Research → Communication → Infrastructure). Each item gets one of: **PROMOTE** (to Active), **MAINTAIN** (to Recurring), **ARCHIVE** (intentionally done), or **DROP** (no longer relevant). Cap at 30 minutes; default verdict for anything ambiguous is **DROP** — items can come back if they prove themselves.

---

## Archived

Prior backlog files preserved for reference, not for active use:

- [`archive/BACKLOG_pre_OPS-001.md`](archive/BACKLOG_pre_OPS-001.md) — the original product/research backlog before the Belief Stack pivot
- [`archive/BACKLOG_BELIEF_OBSERVABILITY_JUNE_2026.md`](archive/BACKLOG_BELIEF_OBSERVABILITY_JUNE_2026.md) — the interim P0–P6 backlog that produced the v0.3 result

---

*Living document. Items move between sections as state changes. The Review Queue should be drained, not allowed to grow.*

*Last revision: 2026-06-03 (Session A of OPS-001).*
