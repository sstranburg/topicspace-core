# topicspace backlog

A lightweight working backlog. Edit by hand. One card per item. Priority is forced — most things are not P1.

## legend

- **priority** — `P0` (urgent + critical) · `P1` (important) · `P2` (worthwhile) · `P3` (someday)
- **status** — `Inbox` · `Ready` · `In Progress` · `Blocked` · `Done` · `Deferred`
- **effort** — `S` (<1 day) · `M` (1–3 days) · `L` (>3 days)

When marking `Done`, leave the card in place for ~2 weeks then archive to `BACKLOG_ARCHIVE.md` (not yet created).

---

## Next 5

In priority order, the five items to work on next:

1. **R-001 — Test hardware / infra vs software / platform bifurcation hypothesis.** Most distinctive structural finding in current data. Informs product positioning, intel framing, and a future writing piece. Now that storm cohesion is a field (R-002), it can be a partition variable in the analysis.
2. **C-002 — Publish intel case-study Writing.** Reinforces the intel announcement with a real worked example (e.g., the ZETA "BI pivot" thesis). Shows the analytical sharpness, not just the feature. Worth running fresh once we have a few days of cohesion-enriched briefs to compare against.
3. **I-001 — Real durable log store for intel briefs.** Current JSONL is ephemeral on Vercel serverless. Gates public launch and broader QA; needed before intel sees external traffic.
4. **R-005 — Re-validate eligibility matrix against recent 90 days.** Live shadow underperforming the backtest baseline. Need to know if cells are decaying or it's noise.
5. **P-001 — Improve intel explain-mode quality.** Field layer is now stronger (I-002 done). Next pass is QA: 10 sample briefs scored for sharpness; tighten prompt frame again if needed.

> **Principle**: field/product improvements come before content cadence. Publish and explain, but protect the time for the underlying improvements. The backlog ordering is a guardrail, not a suggestion — if content starts crowding out research, drop a content slot, not a research one.

---

## Product

### P-001 — Improve intel explain-mode quality
- **category**: Product
- **priority**: P1
- **status**: Ready
- **effort**: M
- **owner**: Sue
- **dependencies**: I-002 (field layer needs to feed it)
- **why_it_matters**: Explain mode is the most-used contextual entry (actor page button) and currently risks producing generic paraphrase. Quality here gates whether intel becomes load-bearing in the product.
- **success_condition**: Briefs cite specific recent headlines for the explained ticker; bottom line distinguishes absent vs. not-supported vs. contradicted; no generic-filler retries on average inputs.
- **notes**: We've tightened the prompt; next step is field-layer depth.

### P-002 — Improve structures page usability
- **category**: Product
- **priority**: P2
- **status**: In Progress
- **effort**: M
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Structures still has the strongest analyst utility but the most internal-feeling UI. Low-confidence sections, lineage internals, and grouping methodology language are still partially exposed.
- **success_condition**: First-time analyst loads `/threads` and immediately understands which themes are organizing/intensifying, who's involved, and why it matters — without needing to know the engine.
- **notes**: Already ran one major pass (dominant-formation hero, why-it-matters lines). Next pass: better summary lines for low-coherence threads.

### P-003 — Improve Board / actor-page validity explanation
- **category**: Product
- **priority**: P2
- **status**: In Progress
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: "Valid here / weak here / conditional" is the highest-information label in the product. Mobile users still get only the dotted-underline tooltip, no popover.
- **success_condition**: A first-time user on mobile or desktop understands the validity tag in <5 seconds without leaving the page.
- **notes**: Tooltips landed; popover for mobile is the next iteration.

### P-004 — Add "Compare watchlist" intel entry (phase 3 rollout)
- **category**: Product
- **priority**: P2
- **status**: Ready
- **effort**: S
- **owner**: Sue
- **dependencies**: none — code path already exists (`/intel?mode=basket&tickers=...`)
- **why_it_matters**: Watchlist is now reachable only as a chip on the Board. Adding a "Compare watchlist with intel" button on `/watchlist` makes intel useful for personal portfolio review.
- **success_condition**: One-click goes from `/watchlist` → pre-filled basket request → grounded brief with the user's tracked names.
- **notes**: Same pattern as actor-page button.

### P-005 — Decide and ship a coverage-pill or coverage-line UI on intel briefs (post-launch polish)
- **category**: Product
- **priority**: P3
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Coverage banner now shows when `partial: true`; consider promoting to a small permanent pill regardless. Could improve trust.
- **success_condition**: Users glance at a brief and know coverage breadth without reading the wrinkle.

### P-006 — Mobile QA pass on intel + briefing
- **category**: Product
- **priority**: P3
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Hamburger nav landed but full mobile test is overdue. Brief layouts haven't been stressed at small widths.
- **success_condition**: All current pages render legibly on a 375px viewport with no horizontal scroll, no clipped text.

### P-007 — Refine homepage "How topicspace works" block (DONE — recent)
- **category**: Product
- **priority**: —
- **status**: Done
- **effort**: S
- **owner**: Sue
- **notes**: Shipped May 8 — block now reflects user workflow with intel as card 4.

### P-008 — Simplify nav (DONE — recent)
- **category**: Product
- **priority**: —
- **status**: Done
- **effort**: S
- **owner**: Sue
- **notes**: Shipped May 8 — Watchlist + Report removed from primary nav. Watchlist relocated to Board chip; Report relocated to Briefing CTA. Intel later promoted into nav.

### P-009 — Promote intel into primary nav (DONE — recent)
- **category**: Product
- **priority**: —
- **status**: Done
- **effort**: S
- **owner**: Sue
- **notes**: Shipped May 8 after evaluating placement. Currently between Board and Alerts.

---

## Research

### R-001 — Test hardware / infra vs software / platform bifurcation hypothesis
- **category**: Research
- **priority**: P1
- **status**: Ready
- **effort**: M
- **owner**: Sue
- **dependencies**: none — uses existing backtest data
- **why_it_matters**: The most distinctive structural pattern in the current data. Hardware/infra names print confirmations / price-led moves while software/platform names print divergence. If structural, this should change how the validity matrix is constructed and how intel briefs are framed by sector.
- **success_condition**: A clean numerical statement: over the backtest window, hardware-cluster and software-cluster realized 10D excess returns differ by N pp with statistical confidence; OR the bifurcation is a recent 2026 phenomenon (last 90 days) and hasn't held historically.
- **notes**: Two clusters to test: {NVDA, MU, SNDK, AMD, AVGO, TSM, ANET, SMCI, NBIS, VRT, DELL, VST, CEG} vs {MSFT, META, GOOGL, PLTR, NFLX, ADBE, CRM, SNOW, DDOG, ZETA, TTD}.

### R-002 — Operationalize storm cohesion as a per-actor field
- **category**: Research
- **priority**: —
- **status**: Done
- **effort**: S
- **owner**: Sue
- **notes**: Shipped May 9. New `scripts/compute_storm_cohesion.py`; writes `data/derived/storm_cohesion.json` with per-actor fields (n_storms, by_state, dominant_direction, agreement_pct, cohesion_strength). Wired into `run_pipeline.py` and copied to `topicspace-site/public/storm_cohesion.json`. Initial run shows striking signals: AMZN 100% stable across 92 storms; PLTR 100% growing across 19 storms. Forward-return partition analysis still TODO — opening as new card R-008.

### R-003 — Investigate "zero lineages" as a setup type
- **category**: Research
- **priority**: P2
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: R-002 useful but not required
- **why_it_matters**: ZETA, USAR, ODC have zero cleaned lineages despite distinct fundamentals. Hypothesis: 0-lineage names with strong fundamentals are systematically under-narrated and over-discounted. Reverse direction (heavy lineage but weak fundamentals) is the opposite.
- **success_condition**: Forward-return comparison shows (0-lineage, narr<50, rel<0) outperforms (3+-lineage, narr>70, rel<0) by N pp over 5–10D. Or doesn't, and we drop the hypothesis.

### R-004 — Investigate negative-story-rejection anomaly before splitting subtypes
- **category**: Research
- **priority**: P2
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: INTC repeatedly shows read="price confirming negative story" with extreme NDS+rel divergence. Currently labeled DISAGREEMENT. The contrarian premium on this pattern may be larger than the standard DISAGREEMENT cohort.
- **success_condition**: Numeric comparison of forward-return distributions for the standard DISAGREEMENT cohort vs. the "price confirming negative story" sub-cohort. If meaningfully different, split as a new setup type in benchmarks.json.

### R-005 — Re-validate eligibility matrix against recent 90 days
- **category**: Research
- **priority**: P2
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Matrix is frozen at 2026-04-29. Live shadow tracking is currently underperforming the backtest baseline. Need to know if eligibility cells are decaying (structural drift) or it's just n=6 noise.
- **success_condition**: Per-cell win-rate / excess-return comparison: full backtest period vs. last 90 days. Cells that have decayed materially flagged for review.

### R-006 — Earnings reaction gap-closure dynamics
- **category**: Research
- **priority**: P3
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: DDOG: earnings → +28% → 5d rel +37% → NDS −192. Narrative needs days/weeks to catch up. The narrative-volume ramp post-print may itself be tradable.
- **success_condition**: For 20+ post-earnings episodes in our data, characterize how many days for narr to catch rel within X pp; identify whether faster-catching names produce different forward returns.

### R-008 — Cohesion vs. forward-return analysis
- **category**: Research
- **priority**: P2
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: R-002 (Done — cohesion field now exists); historical data accumulating
- **why_it_matters**: R-002 created the field; this validates whether it predicts anything. If HIGH-cohesion-growing names systematically outperform HIGH-cohesion-fading names by N pp over 5–10 days, cohesion graduates from a useful narrative descriptor into a tradable signal. Could inform intel framing AND eligibility-matrix updates.
- **success_condition**: Forward-return distributions of (HIGH growing, HIGH fading, LOW/mixed) partitioned cohorts; statistical comparison with confidence interval. If meaningful: new setup type or eligibility refinement. If not: cohesion stays an interpretive cue, not a filter.
- **notes**: Needs ~2–3 weeks of cohesion data history before the comparison is meaningful. Set a calendar reminder for late May / early June.

### R-007 — AI compass override mechanics — does it fire too often?
- **category**: Research
- **priority**: P2
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: The system_state override has fired on most evening runs lately. If it's firing >70% of the time, it's no longer an override — it's the default. Either weak-compass detection thresholds are too sensitive, or the underlying compass is genuinely struggling.
- **success_condition**: Compass run logs over 30 days analyzed; override-fire rate quantified; if >70%, threshold review.

---

## Content

### C-002 — Publish case-study Writing(s) — intel applied to a real claim
- **category**: Content
- **priority**: P1
- **status**: Ready
- **effort**: M
- **owner**: Sue
- **dependencies**: P-001 (better explain-mode briefs make better case studies)
- **why_it_matters**: The intel announcement piece tells what intel is. A case study shows what it does — pick a real claim from X (e.g. the ZETA "BI pivot" thesis or the semis-to-software rotation thesis), show the brief, walk through the wrinkle and bottom line. Far more convincing than the feature post.
- **success_condition**: One published Writing showing a thesis → intel brief → analyst commentary → what would change the read. Reader walks away knowing how to use intel.
- **notes**: ZETA thesis is the clearest candidate — already ran intel on it manually with strong output.

### C-003 — Continue daily / periodic social posts grounded in Briefing / Board reads
- **category**: Content
- **priority**: P2
- **status**: In Progress
- **effort**: S (recurring)
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Distribution. Daily posts compound; a thread of grounded posts is the closest thing topicspace has to traffic acquisition.
- **success_condition**: 2–4 posts per week. Each grounded in a board state, an alert, a clear divergence — not opinion.

### C-004 — Plan paper / formal research writeup
- **category**: Content
- **priority**: P2
- **status**: Inbox
- **effort**: L
- **owner**: Sue
- **dependencies**: R-001, R-005 (need stronger findings to anchor it)
- **why_it_matters**: Builds research credibility. The eligibility-matrix work is the most defensible academic contribution. A writeup makes it citable.
- **success_condition**: Outline + two figures + abstract drafted. Doesn't need to be published; needs to exist as a serious document.

### C-005 — Build a reusable "historical setup replay" format
- **category**: Content
- **priority**: P2
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Pulling a past actor-day and showing how the system read it then vs. what happened next is high-quality content the system can self-generate. A template would make this a weekly content engine.
- **success_condition**: One worked example + a template the pipeline can fill in.

### C-006 — Shadow tracking honesty piece (eventually)
- **category**: Content
- **priority**: P3
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: 30+ days of shadow tracking data
- **why_it_matters**: Live shadow is currently underperforming the backtest. A "what we got wrong" piece is rare in this space and builds trust.
- **success_condition**: Honest writeup of S4/B4 vs. realized; what surprised us; what the data is doing now that backtest didn't predict.

### C-001 — Publish intel Writing (DONE — recent)
- **category**: Content
- **priority**: —
- **status**: Done
- **effort**: M
- **owner**: Sue
- **notes**: Shipped May 8: `/writing/introducing-topicspace-intel`.

---

## Infrastructure / Data

### I-001 — Real durable log store for intel briefs (replace JSONL on Vercel)
- **category**: Infrastructure / Data
- **priority**: P1
- **status**: Ready
- **effort**: M
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Current `data/intel-log.jsonl` is ephemeral on Vercel serverless. Logs are only persisted in local dev. Gates broader QA, public launch, and any analytics on intel quality over time.
- **success_condition**: Briefs and feedback persist in a durable store (Vercel Postgres / Neon / Supabase / object store) writable from the API route. GET /api/intel/[request_id] reads from the same. Logs survive deploy.
- **notes**: Vercel Postgres is the simplest first option — already in their ecosystem, low setup.

### I-002 — Strengthen intel field layer (especially explain mode)
- **category**: Infrastructure / Data
- **priority**: —
- **status**: Done
- **effort**: M
- **owner**: Sue
- **notes**: Shipped May 9. Explain mode event budget bumped from 25 → 35 per ticker; theme-scan window 60 → 80 events. Added storm cohesion (R-002) into the context bundle for all modes with new `cohesion:TICKER` citation format. Prompt frame updated with cohesion guidance. Validator accepts the new source prefix. Quality scoring of resulting briefs lives under P-001.

### I-003 — Add request_id / recent-brief retrieval QA workflow
- **category**: Infrastructure / Data
- **priority**: P3
- **status**: Done (basic version)
- **effort**: —
- **owner**: Sue
- **notes**: Basic version live: GET /api/intel/[request_id] + localStorage recent list. Future: a `/intel/qa` page with diff view between two briefs by request_id, drift checks, weekly QA samples surfaced.

### I-004 — Maintain shadow tracking; monitor forward behavior
- **category**: Infrastructure / Data
- **priority**: P2
- **status**: In Progress (recurring)
- **effort**: S (per evening)
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: 6 days of live data so far. Need 30+ days before the gap-vs-backtest comparison is meaningful. Just keep running it daily and don't lose continuity.
- **success_condition**: 60 unbroken days of shadow returns + portfolios. Then re-evaluate.

### I-005 — Daily date propagation / deploy checks
- **category**: Infrastructure / Data
- **priority**: P3
- **status**: In Progress (manual)
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Briefing/board/AI/crypto/geo/reportDate dates can drift apart. Recent fix for briefing.json bug exposed this. Currently caught manually during /evening.
- **success_condition**: An automated check (script or pipeline step) that fails the deploy if any of the 6 surfaces (briefing, actors, ai/crypto/geo signals, reportDate.ts) disagree on date.

### I-006 — NewsAPI 403 — recurring auth issue
- **category**: Infrastructure / Data
- **priority**: P2
- **status**: Blocked
- **effort**: S (likely just an account/key issue)
- **owner**: Sue
- **dependencies**: external (subscription / API key)
- **why_it_matters**: Every evening fetch logs dozens of NewsAPI 403s. Reddit + Finnhub + amplification still produce enough events that the pipeline works, but NewsAPI was historically the broadest source. Long-term fix needed before this becomes a coverage gap.
- **success_condition**: 0 NewsAPI errors per fetch_today.py run, OR a documented alternative source.

### I-007 — X API 402 — payment required
- **category**: Infrastructure / Data
- **priority**: P3
- **status**: Deferred
- **effort**: S (subscription)
- **owner**: Sue
- **dependencies**: external (paid X tier)
- **why_it_matters**: All X fetches return 402. We get social signal from Reddit instead, which is acceptable for now.
- **success_condition**: Either upgraded tier OR formally remove X queries from the pipeline to stop the noise in fetch logs.

### I-010 — Add more tracked actors as needed (recurring)
- **category**: Infrastructure / Data
- **priority**: P3
- **status**: In Progress (recurring)
- **effort**: S (per actor)
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Untracked rate is high in intel basket queries (e.g. recent rotation thesis: 5 of 17 names tracked). Each new actor takes ~10 min via the `add-actor` skill.
- **success_condition**: Quarterly review of which untracked names are getting referenced most in intel queries; add the top 3.
- **notes**: SNDK was the most recent addition (May 8).

### I-008 — Improve prompt / validator rules (DONE — recent)
- **category**: Infrastructure / Data
- **priority**: —
- **status**: Done
- **effort**: M
- **notes**: Shipped May 8: 5 new discipline rules, GENERIC_FILLER regex set, mixed-must-be-partitioned check, next-signal specificity check. Validator now retries on filler.

### I-009 — events_by_actor pipeline copy step (DONE — recent)
- **category**: Infrastructure / Data
- **priority**: —
- **status**: Done
- **notes**: Shipped May 8: run_pipeline.py now copies events_by_actor.json to topicspace-site/public/ at the end of each run.

---

## How to use this file

- Edit cards by hand. Status is the most important field to keep current.
- When something changes status to `In Progress`, update `Next 5` if it falls off.
- New items go into `Inbox`; promote to `Ready` when ready to start.
- Don't be afraid to mark `Deferred` — saying "not now" is the highest-leverage backlog action.
- Quarterly: prune `Done` items older than ~2 weeks into `BACKLOG_ARCHIVE.md`.
