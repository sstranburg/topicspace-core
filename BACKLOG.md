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

1. **C-002 — Write up R-001 as the case-study Writing.** The bifurcation finding (+4.92pp HW vs SW gap, t=13.5, plus 3 counterintuitive sub-findings) is the strongest research result topicspace has produced. Publishing it is more compelling than another worked example. Research as content.
2. **F-007 V2 phase 2 — sign-flip rule (DONE 2026-05-21) + label-staleness fix (open).** Sign-flip ships in `region_calibration.json` as `effective_direction_sign` per region + a top-level `v2_phase2.sign_flip_rule` block. 10 inverted public regions flipped. Gating evidence: `scripts/test_compound_persistence_inversion.py` — contrarian (sign-flipped) hit_5d is 73–81% across all persistence levels on inverted regions (n=115). Persistence does NOT compound with sign-flip (persistent×inverted 73% vs emerging×inverted 81%) — the two rules ship independently rather than stacked. Operating-layer consumers should now prefer `effective_direction_sign` over `direction_sign`. **Open:** (a) UI surfacing of `effective_direction_sign` + `sign_flip` on /architecture L4 card and /actor/[ticker] (next session), (b) cluster-label-staleness fix for the Datadog-style mislabel (separate cleaner concern).
3. **F-006 V2 — per-expectation walk-forward + reconfirmed event type (DONE 2026-05-21).** Single-split #4 + reconfirmed #5 shipped. Rolling re-test (in same session as F-007 V2 phase 1) refined the verdict: persistence-as-prior-weight signal is real at 5d but sign-flips at 10d/20d — narrower than the single-split suggested. F-006 #6 build gated on the same bias investigation + corpus extension as F-007 V2 phase 2.
4. **I-001 — Real durable log store for intel briefs.** Current JSONL is ephemeral on Vercel. Has to land before intel sees real traffic; also starts building QA history.
5. **R-011 — Update eligibility matrix to incorporate R-001 magnitudes.** Software CONFIRMED is actually negative (−5pp); hardware NEG_CONFIRMATION is +11.6pp. Better to do this AFTER C-002 ships — reader feedback will inform weighting decisions.

> **Principle**: field/product improvements come before content cadence. Publish and explain, but protect the time for the underlying improvements. The backlog ordering is a guardrail, not a suggestion — if content starts crowding out research, drop a content slot, not a research one.
>
> **Validation standard (added 2026-05-17)**: rolling walk-forward only for headline performance. In-sample metrics are diagnostic, not claims. See `feedback_rolling_walkforward_standard.md` in `.claude` memory and `/methods §08b`.
>
> **V1/V2 discipline (added 2026-05-20)**: every new calibration / measurement layer ships in two phases. **V1 measures honestly without acting** — surface aggregate, surface heterogeneity, surface failure modes, do not act on findings. **V2 acts** only after V1's findings are validated. The architecture goes from analysis to operating system at V2, not V1. See `feedback_calibration_v1_success_criteria.md`.

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
- **priority**: —
- **status**: Done
- **effort**: M
- **owner**: Sue
- **notes**: Shipped May 9. New `scripts/analyze_hardware_vs_software.py`; report in `data/derived/r001_bifurcation_analysis.md`. Findings: full-backtest gap **+4.92pp** (HW +3.29pp vs SW −1.63pp) over 3,161 observations, **Welch t=13.5, p≈0**. Last 90 days widens to **+6.07pp**. Bifurcation is **structural and persistent**, not a 2026 emergence. The gap concentrates in NEG_CONFIRMATION (+12.6pp gap), DISAGREEMENT (+9.8pp), DIVERGENCE (+6.2pp), and CONFIRMED (+7.3pp; software CONFIRMED is actually −5pp — the worst software setup). Surprising sub-findings: CRWV behaves like hardware (mean +4.8pp) despite "Growth Software" classification; NVDA / SMCI / VST / CEG are the laggards within the hardware cluster, not the leaders. Multiple follow-ups opened: R-009, R-010, R-011.

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

### R-009 — Reclassify CRWV (and possibly GOOGL/AMZN) as hardware-cluster
- **category**: Research
- **priority**: P2
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: R-001 (Done)
- **why_it_matters**: R-001 surfaced that CRWV's mean 10D forward excess is +4.83pp — well inside the hardware distribution despite our "Growth Software" sector classification. CRWV is GPU cloud; it's literally selling AI hardware capacity. GOOGL (+1.11) and AMZN (+0.68) also straddle the line as hyperscalers. Reclassifying may sharpen the validity matrix and the eligibility cells.
- **success_condition**: Decision and implementation: either reclassify in `_SECTORS` (generate_leaderboard.py, run_shadow_tracking.py) and propagate; or document why the current classification is preferred despite the return signature.

### R-010 — Investigate why NVDA / SMCI / VST / CEG underperform their cluster
- **category**: Research
- **priority**: P2
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: R-001 (Done)
- **why_it_matters**: The "AI celebrity" hardware names (NVDA +0.20pp, SMCI −1.38pp, VST −1.87pp, CEG −1.82pp) are the LAGGARDS of the hardware cluster. The alpha lives in less-celebrated names (INTC +10.31pp, MU +8.96pp, MRVL +6.08pp, NBIS +5.88pp, VRT +5.69pp). Hypothesis: the most-narrated names are most-priced; the contested-narrative hardware names are where edge sits.
- **success_condition**: Per-ticker analysis comparing narrative-volume metrics (avg storm count, avg event count, narr distribution) against forward returns. If narrative density inversely correlates with forward returns within the hardware cluster, that becomes a tradable refinement.

### R-011 — Update eligibility matrix to incorporate R-001 magnitudes
- **category**: Research
- **priority**: P1
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: R-001 (Done); also R-009 (reclassification first)
- **why_it_matters**: R-001 found Software CONFIRMED at −5.07pp — actually the WORST software setup, not a positive one. Current matrix has Growth Software with zero eligible states, which is right but doesn't explicitly flag CONFIRMED as a negative-EV cell. NEG_CONFIRMATION + Semis is +11.59pp — already flagged constructively but the magnitude is bigger than current weight implies.
- **success_condition**: Updated eligibility cells with explicit negative cells for software CONFIRMED, and amplified positive weights for hardware NEG_CONFIRMATION / DISAGREEMENT / DIVERGENCE. Re-run shadow tracking config; document changes.

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

### C-002 — Publish case-study Writing — write up R-001 as the case study
- **category**: Content
- **priority**: P1
- **status**: Ready
- **effort**: M
- **owner**: Sue
- **dependencies**: R-001 (Done — provides the actual numbers + sub-findings)
- **why_it_matters**: Originally scoped as "intel applied to a real claim" (e.g. ZETA thesis). Reframed: the R-001 finding IS the case study. A piece titled something like "What topicspace measured: a +4.92pp gap between AI hardware and AI software" is more credible content than another worked-example explainer. The numbers are clean, methodology is reproducible, and the three sub-findings (Software CONFIRMED is the worst software setup; CRWV behaves like hardware; AI-celebrity names are the laggards) are individually quotable.
- **success_condition**: One published Writing covering: hypothesis, method, headline numbers (HW +3.29pp, SW −1.63pp, gap +4.92pp, t=13.5), per-state breakdown, three sub-findings, what it implies for how to read the AI/tech market, what the limits are.
- **notes**: Output from R-001 in `data/derived/r001_bifurcation_analysis.md` is the source material. Tone should match the existing Writings — calm, specific, restrained.

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

### C-004 — Write up "stacked fields" as a topicspace Writing (DONE — recent)
- **category**: Content
- **priority**: P1
- **status**: Done
- **effort**: M
- **owner**: Sue
- **completed**: 2026-05-14
- **notes**: Published at `/writing/stacked-fields`. Includes four-layer essay, matched three-figure set (information field at t=T, stacked architecture with feedback arrow, homepage card composition), L1-L4 unified labeling across diagrams + prose, §05 "How the stack drives the homepage" tying architecture to today's six featured actors, honest "what's not implemented yet" framing in §03 stack status + §10 limitations. Feedback arrow explicit so the stack reads as a learning system, not a pipeline. Subsequent honesty pass on /methods §10 captures the gap between essay rhetoric and implementation reality (now tracked by the F-series).

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
- **notes**: SNDK was the most recent addition (May 8). MELI added May 10. COHR, ALAB, CLS, WDC added May 11 — backfill + pipeline complete; AI signals + leaderboard regen + deploy still pending (paused mid-flight to pivot to new idea).

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

## Question Graph

The question graph PoC is shipped through Phase E: seed graph (A), refreshed briefs (B), narrow triggers (C), explicit field state (D), and queue operations (E). The items below are the next refinements that emerged from actually building and using it. P1 items map to the four discipline axes that matter most right now: queue quality, config correctness, freshness discipline, and learning from real use.

### Q-001 — Prevent trivially recursive derived questions
- **category**: Infrastructure / Data
- **priority**: P1
- **status**: Ready
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Phase D verification exposed it — Q-001-cs1-cs1 emerged from the freshly-promoted Q-001-cs1 and essentially restated the parent's split. Manual dismiss handled it, but the candidate shouldn't have reached the queue. Hard suppression at trigger time preserves queue discipline as the graph grows.
- **success_condition**: A trigger refuses to produce a candidate when its proposed sub-cohort has ≥66% overlap with the parent's sub-cohort AND the proposed title token-overlaps the parent's title above a threshold. Verified by the Q-001-cs1 → cs1-cs1 path producing nothing.
- **notes**: Related to Q-007 (softer overlap penalty in scoring). Q-001 is the hard "auto-suppress" case; Q-007 is the graduated case.

### Q-002 — Centralize topic labels in shared config
- **category**: Infrastructure / Data
- **priority**: P1
- **status**: Ready
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: `TOPIC_LABELS` lives identically in both `scripts/generate_derived_questions.py` and `scripts/build_question_field_states.py`. They will drift the moment a new actor is added in one place but not the other.
- **success_condition**: A single `config/topic_labels.yaml` (or equivalent) is imported by both scripts. No duplicated map. Adding a new ticker label is a one-file edit.

### Q-003 — Use last-brief timestamp for staleness instead of last_updated_at
- **category**: Product
- **priority**: P1
- **status**: Ready
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Phase E's stale marker uses `last_updated_at`, which bumps on every lifecycle transition, seed-YAML edit, and brief refresh. A question briefed daily looks "active" even with no real engagement. True staleness is days-since-the-brief-content-actually-changed.
- **success_condition**: `_is_stale()` in `questions_cli.py` reads `question_briefs.json` to compute days since the most recent brief's `generated_at`. Stale marker (`⏱`) and `health` warnings reflect brief freshness, not metadata churn.

### Q-004 — Review real-world use of the question graph
- **category**: Research
- **priority**: P1
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: 7–14 days of disciplined daily use (review candidates, promote / dismiss, read briefs)
- **why_it_matters**: The system is operable. The bottleneck is no longer modeling complexity but disciplined use. The most important learning is what gets promoted, revisited, ignored, or left to go stale — and whether the graph improved real workflow vs the existing briefing / board pattern. Feeds every other Q-### card.
- **success_condition**: A short internal review note (≤ 500 words) covering: which active questions were actually consulted, which candidates were promoted vs dismissed and why, which questions stayed dead, and what the graph improved vs raw briefing/board workflow. Honest negatives included.

### Q-005 — Detect parent drift when seed scope changes
- **category**: Infrastructure / Data
- **priority**: P2
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: A seed's `entities` / `cohort` / `themes` can change in YAML after derived children exist. Children retain their original `trigger_evidence` (cohort frozen at creation time) but don't surface that the parent has moved. Risk: silently-stale derived questions whose parent assumes a different scope.
- **success_condition**: `seed_questions.py` detects when a seed's cohort/themes changed AND that seed already has children. Flags the affected children in `validate` output OR as a discipline warning OR writes a `parent_drift` entry to each child's `lifecycle_history`. User picks which is least noisy.

### Q-006 — Refactor triggers to consume question field state directly
- **category**: Infrastructure / Data
- **priority**: P2
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: Q-002 (shared config makes refactor safer)
- **why_it_matters**: Phase D added `trigger_signals` shortcuts and skip-when-not-ready, but trigger functions themselves still recompute the `by_class` groupings. The structural facts (`split_patterns`, `fragmentation`, etc.) are already in `question_field_states.json`. Triggers should read them rather than re-derive. Less drift risk, smaller functions, single source of truth.
- **success_condition**: `trigger_cluster_split` and `trigger_too_broad` read `split_patterns` / `fragmentation` from `question_field_states.json`. The trigger module's `READ_CLASS` / `READ_CLASS_LABEL` maps are imported from one source. Same candidates produced for the same input data; less code; verified by parity test.

### Q-007 — Add parent-overlap / self-restatement penalty to candidate scoring
- **category**: Product
- **priority**: P2
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: Q-001 (handles the clean recursion case first)
- **why_it_matters**: Q-001 handles the cleanest "literal restatement" case. Softer cases — child proposes a sub-cohort that's ~50% the parent's with a slightly different framing — are harder. A graded scoring penalty catches these without hard suppression.
- **success_condition**: `score_candidate()` includes a `parent_overlap` component (0 to −10) or tightens `relevance` / `sharpening` to factor cohort-and-title overlap with the parent. Hand-test cases that should rank lower do.

### Q-008 — Build minimal internal review UI for questions
- **category**: Product
- **priority**: P2
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: Q-001 (queue should be clean before adding UI affordances)
- **why_it_matters**: CLI is fully sufficient today. A thin internal UI at `/questions` makes weekly review a 5-minute glance vs a CLI session. The model and JSON files don't change — UI is purely a renderer.
- **success_condition**: Internal-only `/questions` (list), `/questions/[id]` (detail with promote / dismiss / archive buttons), `/questions/review-log`. No schema changes. Behind an env flag.

### Q-009 — Support explicit reopen path for dismissed nodes
- **category**: Product
- **priority**: P3
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Phase E intentionally restricts `restore` to archived-only — recovering from a mistaken dismiss currently means hand-editing JSON. A deliberate `reopen` subcommand with extra friction preserves the "don't make undo too easy" design while giving an audit-trailed path.
- **success_condition**: New `reopen QID --reason "..."` subcommand. Flips dismissed → candidate (back to the queue, not straight to active). Refuses without `--reason`. Appends to `lifecycle_history`.

### Q-010 — Analyze review-log patterns as a research artifact
- **category**: Research
- **priority**: P3
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: Q-004 (need real use); ≥30 days of review-log data
- **why_it_matters**: Over time, the promote / dismiss decisions become a record of what topicspace's owner actually values in inquiry. Trends in which triggers get promoted, which parents reliably produce useful children, which dismissal reasons recur — these are the most honest description of the system's research taste.
- **success_condition**: A short internal note (or Writing draft) on what kinds of derived questions get promoted, dismissed, or archived. Quantified where possible: which trigger types have the highest promotion rate, which parents have the most active children, which dismissal reasons cluster.

---

## Field Architecture

Multi-phase plan to transition from stacked-data (today) to stacked-fields. See `/methods §10` (limitations) and the stacked-fields essay for the framing; this section tracks the engineering work to close the gap.

### F-001 — Build L1 validation backtest (the gate before any field promotion) (DONE — 2026-05-17)
- **category**: Field Architecture
- **priority**: P1
- **status**: Done
- **effort**: M
- **owner**: Sue
- **completed**: 2026-05-17
- **verdict**: **inconclusive — do NOT promote.** Field-derived variants do not materially beat event-count `narr` on the current corpus. `semantic_density_7d` edges narr by 1pp at 20d (54% vs 53%), within noise. Avg/median excess within ±0.15pp across all variants. State stability slightly improved by field variants (~3% fewer transitions/day) but the difference is small. Net: L1 stays in shadow mode.
- **what_to_do_next**: (a) re-run when corpus extends to 9-12 months; (b) consider variant-specific threshold sweeps (current state engine thresholds are tuned for narr); (c) fix data-quality issue: SNOW/VST events have effectively empty body text → near-zero embedding density (see disagreement report). Improving embed input could lift field variants. None of these is the highest-leverage next move — picking up F-002 (cluster lineage) or F-005 (L2 expectation clustering) is. L2 doesn't depend on L1 promotion; expectations get embedded into the same field regardless of which pressure feeds state.
- **artifacts**: `scripts/l1_validation_backtest.py` · `/methods §10` · `data/derived/l1_validation_{summary,per_window,stability,disagreements}.{csv,md}`
- **gate result**: blocks F-008 (production promotion) until materially better variant found. Does NOT block F-002/F-003/F-005/F-006/F-007 — those can proceed since they build on L1 infrastructure (embeddings + field metrics), not on the specific narrative-pressure variant chosen.

### F-002 — Cluster lineage table for stable theme IDs (DONE — 2026-05-17)
- **category**: Field Architecture
- **priority**: P1
- **status**: Done
- **effort**: M
- **owner**: Sue
- **completed**: 2026-05-17
- **what_landed**: `scripts/build_cluster_lineage.py` produces 5 artifacts in `data/derived/`:
  - `cluster_lineage.parquet` (2,950 rows · 715 unique stable_cluster_ids · 118 dates · lifecycle: persisted 1634, split_target 690, merge_target 540, drift 61, born 25)
  - `cluster_members.parquet` (5.9 MB · per (date, day_cluster, event_id))
  - `cluster_actor_membership.parquet` (120 KB · per (date, ticker, stable_cluster) with `is_primary` flag)
  - `cluster_events.parquet` (29 KB · 1947 lifecycle events: 690 retired, 690 split_target, 540 merge_target, 25 born, 2 large_drift)
  - `cluster_labels.json` (1.3 MB · 715 LLM-labeled stable clusters, gpt-4o-mini, cached, ~$2 total)
- **method**: KMeans on 30-day window per day (k = clip(n/50, 8, 25)) · cosine-similarity centroid matching against prior day · MATCH_PERSIST_SIM=0.85 (clean) · MATCH_DRIFT_SIM=0.50 (drift) · birth if no match · merge if multiple priors claim one today · split if one prior maps to multiple today · retired if prior gets no claim · LLM relabel only when member-set churn ≥40% or first sighting.
- **also_in_this_commit**: data-quality fix — switched field pipeline + embed_events.py to read from `tech_ecosystem_filtered.jsonl + tech_ecosystem_backfill.jsonl` (matching `build_backtest_history.py`'s corpus). Previously they only read `tech_ecosystem.jsonl` which missed ~37k backfill events, causing SNOW/VST etc to show narr=95 / density=0 in the disagreement report. Now SNOW Dec 2025 shows actual events and density. Added `degenerate_event_share` metric (events with combined title+text < 30 chars excluded from centroid/density).
- **next_dependencies_unlocked**: F-005 (L2 expectation clustering can now use stable theme IDs), F-006 (L3 fingerprints can use `actor + stable_cluster_id + direction_sign`).
- **artifacts**: `scripts/build_cluster_lineage.py` · `scripts/embed_events.py` (updated) · `scripts/build_field_instrumentation.py` (updated) · `scripts/build_backtest_history.py` (wired in evening pipeline)

### F-003 — LLM-labeled cluster names
- **category**: Field Architecture
- **priority**: P2
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: F-002 (need stable cluster IDs first, otherwise we label and re-label daily)
- **why_it_matters**: Current TFIDF labels ("marvell / micro / asml") are fine for debug but bad for any user-facing claim-space view. LLM labels using top 20-30 titles per cluster give readable theme names like "AI capex tailwind in semis."
- **success_condition**: One LLM call per *new* cluster per evening (~10-30/day → ~$0.10/day). Stored next to cluster_lineage; surfaced as `cluster_label` field everywhere it's used.

### F-004 — Field watchdog: narr vs semantic_density divergence detection
- **category**: Field Architecture
- **priority**: P2
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: While F-001 validates whether semantic_density is better, the validation period needs an early-warning system: when narr and semantic_density disagree dramatically for an actor on a day, that's interesting. Surfacing those divergences accelerates iteration on the field definitions.
- **success_condition**: Daily compute of `|z-score(narr) - z-score(semantic_density_7d)|` per actor; rows above threshold (e.g. 1.5σ) flagged in an internal report. Useful both as a validation tool and as a future signal candidate.

### F-005 — L2 expectation clustering + /claims page V1 (DONE — 2026-05-17)
- **category**: Field Architecture
- **priority**: P1
- **status**: Done
- **effort**: L
- **owner**: Sue
- **completed**: 2026-05-17
- **what_landed**:
  - `scripts/embed_expectations.py` — embeds headline + near_term_view for all live + historical expectations (~2,840 total, ~$0.05 one-time, idempotent by input_hash)
  - `scripts/build_claims.py` — attaches each expectation to nearest stable_cluster_id (by cosine sim against day-cluster centroids built from event embeddings + F-002 member lists). Outputs per-(date, theme) stats: n_members, member_tickers, direction_distribution, alignment_score (max bucket share), conflict_score (normalized entropy), dominant_direction, avg_conviction, crowding_score (n × avg_conviction × alignment), state_distribution, 3 representative headlines.
  - `topicspace-site/public/claims.json` — latest snapshot, ~11 themes on 2026-05-14.
  - `app/claims/page.tsx` — server-rendered theme list, sorted by crowding. Each card: label · dominant direction chip · clickable member tickers · scores row · state distribution chips · representative headlines (with ticker → actor page links). Honesty footer notes V1 assignment (nearest-only) + L1 OOS caveat.
  - Added to primary nav between Replay and intel.
  - Wired into evening pipeline at the tail of `generate_actor_expectations.py` (after source provenance scoring).
- **method**:
  - V1 attachment = each expectation to its single nearest day-cluster by cosine sim → that cluster's stable_cluster_id
  - alignment_score = max(direction bucket counts) / total
  - conflict_score = entropy(direction distribution) / log2(3), normalized to [0, 1]
  - crowding_score = n_members × avg_conviction × alignment_score
  - Direction normalization: bullish_continuation → +1, bearish_continuation → -1, mixed/inflection/neutral → 0
- **sample_today_themes** (2026-05-14, top 4):
  - "Tech stock volatility and investment strategies" — bearish, 5 members (AMZN, MP, NBIS, NFLX, TTD)
  - "AI infrastructure and semiconductor partnerships" — bearish, 4 members (AAPL, ANET, MRVL, VST)
  - "AI partnerships and market valuations" — mixed, 4 members (CEG, DDOG, SNOW, VRT)
  - "Semiconductor sector resilience amid AI demand" — bearish, 4 members (ARM, ASML, AVGO, SMCI)
- **next_dependencies_unlocked**: F-006 (L3 lifecycle IDs — the V1 fingerprint `actor + stable_cluster_id + direction_sign` now has all its pieces); F-007 (L4 region-level walk-forward — themes become a viable region dimension).
- **v2_shipped** (2026-05-17):
  - `scripts/qa_claims.py` — QA harness reporting on assignment quality (median sim 0.611), label quality (2/11 generic at V1), conflict sanity (3 high-conflict themes, legitimate), member coherence, direction sanity (0 mismatches). Writes `data/derived/qa_claims.md` + `qa_claims_assignments.csv`.
  - Claim-sentence generation in `build_claims.py` — GPT-4o-mini synthesizes a 12-25-word propositional sentence per theme (cached by `stable_id::member_hash` in `claim_sentences.json`). Surfaces direction + mechanism in active voice, no ticker enumeration.
  - `/claims` UI hierarchy refactor: topical label demoted to uppercase chip; claim sentence is now the bold proposition lead. Direction/member/score row unchanged.
- **followups_for_v3**:
  - Multi-cluster expectation membership (some expectations are semantically split across themes)
  - Historical theme drill-down (today's UI shows latest snapshot only; per-theme timeline view comes next)
  - Theme-level walk-forward in F-007

### F-006 — L3 expectation lifecycle IDs + thesis trails (V1 DONE — 2026-05-17)
- **category**: Field Architecture
- **priority**: P1
- **status**: V1 Done; V2 Inbox
- **effort**: L
- **owner**: Sue
- **completed_v1**: 2026-05-17
- **what_landed_v1**:
  - `scripts/build_expectation_lifecycle.py` — attaches every (date, ticker, embedding) to its nearest stable_cluster_id from F-002 (≥SIM_FLOOR=0.10) → fingerprints by `entity_id = sha1(ticker + stable_cluster_id + direction_sign)`. Emits three Parquets + a thesis trails JSON.
  - `data/derived/expectation_entities.parquet` (1,544 entities at run) — one row per (ticker, theme, direction) with first_seen, last_seen, n_versions, status (active/contradicted/retired), peak/mean/last conviction, last headline + direction.
  - `data/derived/expectation_versions.parquet` (2,798 rows) — per-(entity, date) snapshot: direction, conviction, headline, near_term_view, sim to assigned cluster, input_hash.
  - `data/derived/expectation_lifecycle_events.parquet` (3,262 events) — typed events `born / strengthened / weakened / contradicted / retired` with prior/new/delta conviction and detail. Thresholds: Δconviction > 0.10, retired after 7 days absent.
  - `data/derived/thesis_trails.json` + `topicspace-site/public/thesis_trails.json` — per-ticker payload of active_claims (≥3 versions) + most recent lifecycle events for the actor page.
  - `app/actor/[ticker]/page.tsx` — `Thesis Trail` section under the event timeline. Renders persistent active claims (with theme label, claim sentence from F-005, n_versions, conviction range) and a reverse-chrono event list with typed pills (BORN / STRENGTHENED / WEAKENED / CONTRADICTED / RETIRED).
  - Wired into evening pipeline tail of `generate_actor_expectations.py`, immediately after `build_claims.py` (shared inputs).
- **method_v1**:
  - V1 lifecycle fingerprint = `(ticker, stable_cluster_id, direction_sign)` — no LLM matching, just deterministic hash
  - Trail filter: only surface entities with ≥3 versions in UI, plus all strengthened/weakened/contradicted events regardless of entity persistence. Avoids exposing daily-attachment churn (single-day entities are noisy on this 118-day corpus).
  - Contradicted = different non-zero direction_sign appears in the same (ticker, cluster) within the active window; the prior-sign entity gets the event and is dropped from the active sign set.
- **observations_v1**:
  - 1,544 entities for 32 actors = ~48/actor; ~94% are retired single-day attachments — expected on a 118-day window with daily LLM expectations that drift in framing
  - 84 active entities + 8 contradicted across the cohort; 35 strengthened, 37 weakened, 194 contradicted events
  - Tickers with the most persistent claims today: SNOW (4), MU (4), CEG (4), MRVL (4), VRT (4) — all heavily AI-infra exposed and consistently in the bearish/mixed half of the claim space
  - MRVL has 39 entities but **zero with ≥3 versions** — the thesis trail correctly shows "no persistent claims; expectation drifts day-to-day." That's a real read worth keeping.
- **followups_for_v2**:
  - Lifecycle markers on `/replay/[ticker]` (alongside narrative + price)
  - Lifecycle aggregate page `/lifecycle` — system-wide event timeline
  - Split / merge classification (when an entity's cluster bifurcates or absorbs another) — needs F-002 cluster-lineage event-type integration
  - ~~Per-expectation walk-forward (F-007 input — does an active entity with strengthened events outperform one with weakened? more samples than per-actor)~~ **DONE 2026-05-21** — `scripts/run_lifecycle_walkforward.py`. Single-split finding: persistence bucket *spread* (persistent_bundle − emerging) is positive at all three horizons in both train and test (5d +1.22% / +0.22%, 10d +2.21% / +1.69%, 20d +5.73% / +2.79%) — suggestive but small-sample. Strengthened/weakened lifecycle-character bucket cells are still vapor (n ≤ 6). Recommendation: rolling walk-forward (subsumed by F-007 V2) before any L1 prior-weight build.
  - ~~Reconfirmed event type (e.g. when retired-then-reborn happens within N days)~~ **DONE 2026-05-21** — `build_expectation_lifecycle.py` now scans within-history attachment gaps ≥ `RETIRED_GAP_DAYS`, emits a `retired` event at gap-start and a `reconfirmed` event at gap-end. Also fixed `entity.status` to reflect the latest chronological event (was permanently "retired" if any retired event existed, even after resurrection). First run: 176 reconfirmed events surfaced; 16 entities reclassified from `retired` to `active`.
  - Use entity persistence as an L1 prior weight (high-persistence entities → trust the directional signal more) — gated on F-007 V2 rolling walk-forward confirming the single-split finding above.
- **gate**: V1 passes the "would I show this to a reader" test on actor pages with persistent claims (SNOW, MU, CEG, MRVL, VRT). Actors without persistent claims show an honest "no persistent claims" note rather than fake-confident timeline noise.
- **artifact_policy**: The four lifecycle artifacts under `data/derived/` are force-added despite `data/` being gitignored at storm root:
  ```
  data/derived/expectation_entities.parquet
  data/derived/expectation_versions.parquet
  data/derived/expectation_lifecycle_events.parquet
  data/derived/thesis_trails.json
  ```
  The evening pipeline regenerates all four on every run, so daily diffs will appear under `git status` whether or not the underlying field actually moved. **Manual refresh only.** Do NOT auto-commit on every pipeline run, and do NOT propose a cron / hook for this. Refresh them manually when the lifecycle methodology changes or when the published data state crosses a meaningful checkpoint (new actor onboarded, F-006 V2 matching rules shipped, publication snapshot). Until F-006 V2 stabilizes the (actor, cluster, direction-sign) matching, daily diffs may reflect implementation noise (cluster centroid drift, embedding re-shuffling, LLM expectation reframing) as much as real field movement. Auto-committing this churn would pollute the repo history and erode the signal value of any future `git log` for these files.

  The site-facing copy at `topicspace-site/public/thesis_trails.json` is the **production artifact** — `/architecture` and `/actor/[ticker]` both read from it via the site repo's normal build. The storm-side copies are reproducibility artifacts; no production reader touches them. If manual refreshing becomes painful, add `scripts/commit_lifecycle_artifacts.sh` — but keep it human-triggered, not cron'd. Re-evaluate this policy once F-006 V2 lands.

### F-007 — L4 region-level walk-forward (V1 DONE — 2026-05-18)
- **category**: Field Architecture
- **priority**: P1
- **status**: V1 Done; V2 Inbox
- **effort**: L
- **owner**: Sue
- **dependencies**: F-005 (themes), F-006 (signed expectation versions)
- **completed_v1**: 2026-05-18
- **what_landed_v1**:
  - `scripts/build_performance_regions.py` — joins `expectation_versions.parquet` (F-006) with per-ticker + QQQ prices; emits one observation row per (date, ticker, theme_id, direction_sign) with `rel_5d / 10d / 20d` (actor minus QQQ), direction-aligned `hit_5d / 10d / 20d` flags, and `region_id = "reg-" + sha1(theme_id::direction_sign)[:10]`. Output: `data/derived/performance_regions.parquet` (2,775 rows from 1,544 F-006 entities).
  - `scripts/build_region_calibration.py` — aggregates per region across all three horizons; emits `n_obs`, `hit_rate`, `avg_excess_return`, `std_excess`, and a tier label (`public` n≥10 / `limited` 5–9 / `insufficient` <5) per horizon. Also emits first-half / second-half splits (stability check). Output: `data/derived/region_calibration.json` + `topicspace-site/public/region_calibration.json` (417 regions; tier counts: 44 public / 59 limited / 314 insufficient).
  - Three baselines computed at every horizon and embedded in the artifact: `all_expectations` (pool across signed observations), `random` (50% by definition), `price_momentum` (predicts direction from sign of trailing N-day return). Aggregate run: all_expectations 49% / 50% / 51% at 5d / 10d / 20d; price_momentum 49% / 48% / 52% — i.e. the L2 layer is, on average, no better than trailing-return sign.
  - `/architecture` L4 card transitioned from `SCOPED / F-007` to `BUILT V1`. Shows system-wide stats (44 public regions, baseline hit rates, count of regions beating baseline by ≥10pp) plus an actor-specific table of every signed region the worked-example actor participates in, with 5d / 20d hit rates, deltas vs baseline (green ≥ +10pp / red ≤ −10pp), and tier badges.
  - `/actor/[ticker]` Thesis Trail — each persistent active claim now renders a region-calibration chip next to its conviction tag (e.g. `hit 5d 70% · 20d 80% · n=10`), color-coded vs baseline. Insufficient-history regions render as `history n/a · n=N`; sign=0 claims render no chip. 11 of 15 current active claims across the cohort attach to a region.
  - `/methods §08c` writeup documenting region schema, sample-size tiers, baselines, current state of the field, and the V1-vs-V2 split.
  - Wired into `scripts/build_backtest_history.py` shaper loop after `build_actor_trace.py --all`, so evening pipeline regenerates the F-007 artifacts on every run.
- **method_v1**:
  - Walk-forward discipline: every observation uses only information available on its observation date. Future returns are joined in but do NOT revise the L2 prediction — the prediction was the prediction.
  - Direction-aligned hit: `direction_sign = +1` hit when `rel_forward > 0`; `−1` hit when `rel_forward < 0`; `0` excluded from hit-rate (kept in observation table).
  - Region = `(theme_id, direction_sign)` only. State / conviction tier dimensions deferred to V2 — V1 would have shattered sample sizes below usefulness.
  - V1 hit rates are **in-sample at the region level** (no train/test split per region). Stability is checked via first-half / second-half splits embedded in the artifact, but not enforced as a publish gate.
- **observations_v1**:
  - The field is not uniform. 9 of 43 public regions beat the 5d baseline by ≥10pp; 12 of 43 are ≥10pp **worse**. Pays-as-predicted concentrations include `Salesforce AI dynamics +` (5d 90%, 20d 100%, n=10), `Critical minerals volatility +` (70/80%, n=10), `Oracle AI/multicloud +` (71/42%, n=14). Persistently inverted regions include `Intel AI strategy −` (9/9%, n=11), `MRVL sentiment −` (17/25%, n=12), `Micron AI expansion −` (23/31%, n=13) — the L2 direction extractor reads bearish on these themes and the market consistently does the opposite. Recoverable in V2 via a region sign-flip rule.
  - Aggregate baseline matching `random` and `price_momentum` is the honest version of "L2 is not a free predictor on average." The signal lives in regional heterogeneity, not the mean.
- **followups_for_v2**:
  - ~~Per-region walk-forward (rolling, not just first-half / second-half) once corpus extends past ~12 months — current windows are too small for stable folds.~~ **PHASE 1 DONE 2026-05-21.** `scripts/rolling_walkforward.py` (generic primitive) + `scripts/run_region_rolling_walkforward.py` (F-007 caller, public regions only, n≥10). Verdict on corpus as-is: public-region aggregate hit rate is STABLE across 3 expanding-window folds at all three horizons (5d 49.6 / 44.1 / 53.8, 10d 47.9 / 46.7 / 56.7, 20d 56.2 / 49.8 / 44.4 — all ranges within 12pp). Aggregate sits at baseline (~50%) which matches V1's "no aggregate edge" framing. Per-region per-fold cells remain too sparse (n=1-2 typical) for individual region stability to be authoritative; treat as diagnostic.
  - ~~Inverted-region detection + escalation rule (flag any public region with hit ≤ 30% for upstream review — mislabeled theme, sign-extractor bug, or genuine fade dynamic).~~ **PHASE 1 DONE 2026-05-21.** `flagged_inverted` field now lives on every region in `region_calibration.json`. First run: **10 public regions flagged**, 7 of 10 with `sign = -1`. Leaders: Intel AI Strategy − (hit_5d 7%, n=14), Taiwan semiconductor demand − (10%, n=10), Nvidia stock outlook − (15%, n=13), Oracle AI/momentum − (20%, n=37), AI growth driving tech valuations − (20%, n=15). Bias investigation completed same day (`scripts/investigate_inverted_regions.py` → `data/derived/inverted_regions_investigation.md`): 9 of 10 fit the **fade dynamic** hypothesis (L2 reads correctly bearish/bullish, market fades on hot themes at 5d). 1 of 10 is a cluster-label-staleness bug (Datadog "strong Q4" label attached to bearish content). **No extractor fix needed.** Phase 2 V2-acts step is sign-flip rule on inverted regions, not human escalation. Compound test with F-006 #6 at 5d worth running before either ships independently.
  - **F-006 #6 rolling re-test landed in same session.** `scripts/run_persistence_rolling_walkforward.py` (reuses the same primitive). Verdict: persistent_bundle minus emerging spread is positive in ALL 3 folds at 5d (+4.6 / +13.7 / +16.2pp) but sign-flips at 10d (-7.8 / +14.4 / +21.7) and 20d (+9.1 / +6.1 / -2.3). The single-split positive at longer horizons from F-006 V2 #4 was a regime artifact. F-006 #6 has a narrower scope than the single-split suggested — 5d only, with caveats on the entrenched bucket whose std is 17pp at 5d.
  - Re-weight L2 conviction by region calibration (conviction → region-conditioned probability). **Partial: sign-flip subset shipped 2026-05-21.** Inverted public regions now carry an `effective_direction_sign` field in `region_calibration.json` (per-region) + `v2_phase2.sign_flip_rule` summary at the payload root. Compound test `scripts/test_compound_persistence_inversion.py` showed the sign-flip earns its keep standalone (73–81% contrarian hit_5d on inverted regions, n=115) and does NOT compound with persistence — so ship as two independent rules. Conviction *re-weighting* (continuous, not just sign-flip) remains a follow-up; would need (a) enough fold-stable regions to fit reliable weights and (b) a downstream consumer (the operating layer) to actually use the weight.

    **Framing discipline (preserved here so it doesn't drift):** `effective_direction_sign` should be presented as *region-calibrated effective direction* — calibrated historical behavior on this region/horizon — **not** as a new raw L2 expectation. The L2 layer's read is unchanged; the sign-flip is a downstream operating-layer reinterpretation gated by rolling 5d evidence. UI surfaces (architecture L4 card, actor Thesis Trail) phrase the inverted badge as "historically inverted at 5d · contrarian X% (n=Y)" rather than "system says buy/sell," and consumers should never collapse the raw + effective signs into a single number. Continuous conviction weighting remains deferred until more samples accumulate AND a real consumer exists.
  - Add `state` and `conviction_tier` as region sub-dimensions once sample sizes support it.
  - Lifecycle-conditioned calibration (does a region show higher hit rate when its L3 entity has a `strengthened` event in the prior N days?).
- **gate**: V1 passes the "would I show this to a reader" test on actor pages — claims that attach to a populated region get an honest chip with caveats; claims that don't get an honest `history n/a`. The /architecture L4 card is no longer a placeholder; it shows real per-actor calibration with delta indicators. Aggregate hit rates are honestly reported as essentially baseline, with the heterogeneity-within-regions story carrying the V1 weight.
- **artifact_policy**: Same as F-006 — `region_calibration.json` is regenerated daily by the pipeline; the site-facing copy at `topicspace-site/public/region_calibration.json` is the production artifact, and `data/derived/region_calibration.json` is a reproducibility shadow. The parquet (`performance_regions.parquet`) is repo-resident but force-added (data/ is gitignored at storm root). Manual refresh only — auto-commits would pollute git history with daily centroid + LLM reframing noise. Re-evaluate after V2 stabilizes the (theme, direction) matching.

### F-008 — Promote semantic_density into production (deferred — F-001 verdict inconclusive)
- **category**: Field Architecture
- **priority**: P3
- **status**: Deferred
- **effort**: M
- **owner**: Sue
- **dependencies**: F-001 re-run with extended corpus (9-12 months), OR a variant-specific threshold sweep finding a clear winner
- **why_it_matters**: F-001 (2026-05-17) showed field variants do not materially beat narr on the current 6-month corpus. Re-evaluate after more history accumulates and after the data-quality fix (richer embed input for tickers like SNOW/VST whose events have near-empty bodies).
- **success_condition**: F-001 v2 shows a variant beating narr by ≥3pp hit rate at 20d AND meaningfully better state stability across multiple rolling folds.

### F-009 — Point-in-time leakage assertions in L1 code
- **category**: Field Architecture
- **priority**: P2
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Arch doc §13 specifies leakage rules. Current L1 code respects them but it's by convention, not enforcement. Adding explicit assertions (e.g. `assert all(events_df.date <= t)` in `build_field_instrumentation.py`) catches accidental future-data leaks during refactors.
- **success_condition**: Code-level checks fail loudly if a feature uses any event with `event.timestamp > t`.

### F-010 — Mark expectation provenance explicitly (live_archived vs retrospectively_reconstructed)
- **category**: Field Architecture
- **priority**: P2
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: Replay UI informally notes that historical expectations are reconstructed, not archived. Arch doc §10.3 + §15.3 are right that this should be data-model-level, not just a UI footnote. As archived expectations accumulate going forward (via the daily archival hook), the distinction will matter more.
- **success_condition**: Add `provenance: "live_archived" | "retrospectively_reconstructed"` to every entry in `expectations_history/*.json`. UI shows a discreet chip on retrospectively-reconstructed cards. Future archivals stamp as `live_archived`; backfill marked as `retrospectively_reconstructed`.

### F-011 — Lock canonical L0–L4 semantics + portability doc
- **category**: Field Architecture
- **priority**: P1
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: none
- **why_it_matters**: The L0–L4 abstraction has started drifting. On `/governance/example`, L2 means at different points "expectation," "next-action prediction," and "risk prior." That's defensible internally but it makes the architecture less portable across domains. A canonical lock would prevent that drift and make domain ports cleaner.
- **success_condition**: One doc that defines the canonical abstraction:
  - L0 — Evidence: what happened?
  - L1 — Regions: what kind of situation is this?
  - L2 — Hypotheses: what do we expect in this region?
  - L3 — Lifecycle: how is this hypothesis/region evolving?
  - L4 — Calibration: was the hypothesis right, and what should change?

  Plus explicit domain mappings: markets (events → narratives → forward expectations → thesis lifecycle → return calibration); governance (eval logs → risk regions → risk/control hypotheses → risk lifecycle → control calibration); future research-radar (signals → topic regions → impact hypotheses → thesis lifecycle → business-impact calibration). Lives at `/methods` or a new `/architecture/canonical` doc.
- **notes**: Don't add new layers — tighten the existing ones. Drift is the risk; portability is the payoff.

### F-012 — L1 region-quality metrics (first-class)
- **category**: Field Architecture
- **priority**: P1
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: F-002 (stable cluster lineage)
- **why_it_matters**: L1 is the quiet dependency everything else rests on. If regions are bad, L2 and L4 become noisy. Today we have implicit measures (n_obs, tier); the architecture would benefit from explicit region-quality metrics that surface bad regions before downstream calibration starts misbehaving.
- **success_condition**: Every L1 region (markets and governance) carries six metrics:
  - **cohesion** — mean intra-region embedding similarity (are events semantically close?)
  - **purity** — concentration of risk / action labels (does one label dominate?)
  - **stability** — region persists across time without major centroid drift
  - **coverage** — fraction of traffic / data the region explains
  - **bimodality** — does L4 calibration suggest the region should split?
  - **drift** — centroid movement velocity across rolling windows

  Surface on `/architecture` L1 card (per region) and as an aggregate health line. **L4 → L1 re-cluster signal becomes data-driven** (auto-flag low-cohesion + high-bimodality regions as re-cluster candidates) instead of intuition-driven.
- **notes**: Biggest architectural unlock since F-007. Promotes L1 from "the clustering step" to "a measured layer in its own right."

### F-013 — L4 produces decision classes (PROMOTE / MONITOR / INTERVENE / RECLUSTER / INVERT / RETIRE / ESCALATE)
- **category**: Field Architecture
- **priority**: P1
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: F-007 V1 (region calibration shipping)
- **why_it_matters**: L4 currently emits metrics. To go from analysis to operating system, every calibration result should end with a **recommendation class** — what to do about the finding. This is the missing actionability layer.
- **success_condition**: Every per-region L4 row carries one of seven decision classes:
  - **PROMOTE** — enough evidence + positive calibration; raise conviction / use in production
  - **MONITOR** — early signal, insufficient sample; keep watching
  - **INTERVENE** — active risk or poor performance; ship a fix
  - **RECLUSTER** — bimodal or unstable; flag for L1 re-clustering (the L4 → L1 edge made operational)
  - **INVERT** — prediction / control is consistently wrong; sign-flip candidate
  - **RETIRE** — stale or unsupported; remove from active surface
  - **ESCALATE** — high-severity or human review needed

  Rules: thresholds documented in `/methods`; surface as a column on `/architecture` L4 table and on the `/governance/example` per-region table. Decisions ship with provenance (which metrics triggered which decision).
- **notes**: This is what turns the architecture from "calibrated regions" into "this region is strengthening, this control is inverted, this risk reopened — and here's what to do." Marketing-wise: the difference between a dashboard and an operating system.

### F-014 — L3 lifecycle states action-mapped (workflow-driving)
- **category**: Field Architecture
- **priority**: P1
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: F-006 V1 (lifecycle events shipped)
- **why_it_matters**: Lifecycle states are currently descriptive — BORN, STRENGTHENED, WEAKENED, CONTRADICTED, RETIRED, REOPENED, INVERTED. They identify what's happening but don't say what to do. Adding the action layer turns lifecycle from decorative to operational.
- **success_condition**: Each state maps to a default operational action (and which surface it should appear on):
  - BORN → monitor; surface on watchlist
  - STRENGTHENED → promote / prioritize; surface as high-conviction
  - WEAKENED → reduce confidence; demote on UI
  - CONTRADICTED → review assumptions; flag for re-evaluation
  - RETIRED → remove from active surface
  - REOPENED → regression alert; escalate
  - INVERTED → flip / rewrite / redesign control; escalate to L1 re-cluster
  - SPLIT (new, from F-002 lineage) → re-cluster separate hypotheses
  - MERGED (new, from F-002 lineage) → consolidate

  Encode the mapping as data, not just doc — every lifecycle event in the artifacts ships with its recommended action and the workflow surface it routes to.
- **notes**: Connects to F-013 (L4 decisions). Lifecycle + calibration both produce actionable recommendations; the architecture stays consistent across both.

### F-015 — Formalize L2a / L2b split as canonical (not example-page hack)
- **category**: Field Architecture
- **priority**: P2
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: F-011 (canonical semantics)
- **why_it_matters**: `/governance/example` introduced L2a (behavior prediction) and L2b (risk/control prediction) as a one-page convention. The split is genuinely useful and should be canonical — L2 is the expectation layer; it can carry multiple prediction targets simultaneously without forcing a single-target schema.
- **success_condition**: Canonical schema documents two L2 tracks per domain:
  - **L2a — forward expectation** about what will happen (markets: actor expectation; governance: behavior prediction; research: topic trajectory)
  - **L2b — domain-specific expectation layered on top** (markets: theme/region expectation; governance: risk/control prediction; research: impact hypothesis)

  Lock as part of the F-011 canonical doc. Update `/governance/example` and `/architecture` to use the L2a/L2b labels consistently.
- **notes**: Removes the ambiguity that "L2 is the one prediction." L2 is the expectation layer; track multiplicity is a feature.

### F-016 — Human-feedback joins into L4 (the strongest truth signal)
- **category**: Field Architecture
- **priority**: P1
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: F-007 V1 (calibration framework)
- **why_it_matters**: Automated judges (LLM, regex, programmatic graders) are useful but biased and brittle. The strongest L4 truth label for governance + assistant-memory use cases is **human response** — accepted / corrected / rejected / asked-for-simpler / asked-for-more-depth / escalated / complained / approved / deployed / reused.
- **success_condition**: L4 calibration framework joins in:
  - User pushback events (already detected in `governance_poc_judge.py`)
  - Explicit corrections (user saved a new `feedback_*.md` rule referencing the prior turn)
  - Escalations / SME overrides (in enterprise eval contexts)
  - Production incident reports / customer complaints

  Each L4 region row reports both automated calibration (catch rate, Brier) and human-feedback calibration (acceptance rate, override rate). Where they diverge is itself a finding — the automated judge may be miscalibrated against human ground truth.
- **notes**: Caught the over-engineering pattern in the Claude-logs POC implicitly (user push-backs cluster in those regions). Making it explicit closes the most important gap in V1.

### F-017 — Universal Region Card UI component
- **category**: Field Architecture
- **priority**: P2
- **status**: Inbox
- **effort**: M
- **owner**: Sue
- **dependencies**: F-013 (decision classes), F-014 (action-mapped lifecycle)
- **why_it_matters**: Every domain ends up wanting the same per-region object surface. Markets has `/actor/[ticker]`; governance has the region rows on `/governance/example`. Building a canonical Region Card component would unify the UI across domains and make new domains cheap to ship.
- **success_condition**: A reusable `RegionCard` component with fixed fields:
  - Region name
  - What it contains (description + representative evidence)
  - Current L2a hypothesis (with conviction)
  - Current L2b hypothesis / risk prior (where applicable)
  - L3 lifecycle status (with action mapping from F-014)
  - L4 calibration result + decision class (from F-013)
  - Sample-size tier (extended per F-018)
  - Recommended action (one line, derived from decision class)

  Used identically across:
  - Markets: actor pages and architecture L3 swimlanes
  - Governance: region rows on `/governance/example`
  - Future research-radar: topic cards
- **notes**: Less novel architecturally but unifies the product surface. Worth doing once F-013 + F-014 are in.

### F-018 — Extended sample-size discipline (temporal coverage)
- **category**: Field Architecture
- **priority**: P2
- **status**: Inbox
- **effort**: S
- **owner**: Sue
- **dependencies**: F-007 V1 (tier system)
- **why_it_matters**: Current tier system (n ≥ 10 public, 5–9 limited, < 5 insufficient) is good but one-dimensional. A region with n=100 all from one day is not the same as n=100 across six weeks. Adding temporal coverage prevents over-trusting region calibration that's actually built on a single time slice.
- **success_condition**: Every region's tier becomes a compound: `{ n_obs, fold_count, time_span_days, recentness_days, human_label_count, automated_label_only_flag }`. A region only earns "public" tier if it satisfies all dimensions (e.g., n≥10 AND time_span ≥ 14 days AND not_automated_label_only). UI surfaces the constraint that gates a region's tier so the reader knows why a region is "limited" (small n? short time span? automated-only labels?).
- **notes**: Small, high-leverage refinement. Catches a real failure mode (concentrated sampling) that the current tier system misses.

### F-019 — Enterprise RAG governance POC (synthetic eval workflow end-to-end)
- **category**: Field Architecture
- **priority**: P2
- **status**: Inbox
- **effort**: L
- **owner**: Sue
- **dependencies**: F-013 (decision classes), F-016 (human-feedback joins)
- **why_it_matters**: `/governance/example` proves the architecture on real Claude logs. A complementary synthetic POC structured like a deployed enterprise RAG eval would land harder with non-technical buyers — clear risk classes (financial advice leakage, unprofessional tone, unsupported claim, over-refusal, confidentiality risk), 300 eval prompts/responses, learned regions, L2a/L2b predictions, lifecycle across model + prompt versions, human + LLM labels, guardrail misfire analysis.
- **success_condition**: End-to-end enterprise-style RAG eval workflow producing:
  - Which risk regions exist
  - Which controls over-fire
  - Which controls under-fire
  - Which regions need human review
  - Which risks reopened after a model / prompt change

  Honest framing: synthetic data, illustrative. The current Claude-logs POC is the real-data proof; this is the audience-translation artifact.
- **notes**: Lower priority than F-011–F-016. Build only after the canonical semantics + action layer are locked, so the POC inherits a stable architecture.

---

## How to use this file

- Edit cards by hand. Status is the most important field to keep current.
- When something changes status to `In Progress`, update `Next 5` if it falls off.
- New items go into `Inbox`; promote to `Ready` when ready to start.
- Don't be afraid to mark `Deferred` — saying "not now" is the highest-leverage backlog action.
- Quarterly: prune `Done` items older than ~2 weeks into `BACKLOG_ARCHIVE.md`.
