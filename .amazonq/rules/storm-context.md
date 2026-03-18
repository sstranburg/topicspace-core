# Storm Detection System — Project Context

This file is automatically loaded by Amazon Q on every chat. It describes the full system so you can continue development without re-explaining.

## What This System Does

Storm is a **narrative intelligence system** for the tech ecosystem. It ingests news events, embeds them semantically, clusters them into "storms" (narrative clusters), tracks their lifecycle, detects propagation between actors, and produces a print-ready HTML briefing.

Think of it as **weather radar for tech industry narratives** — detecting formation, growth, convergence, and decay of stories across companies.

## Environment

- Python 3.14, venv at `./venv`
- Always activate before running: `source venv/bin/activate && python scripts/...`
- Dependencies: `pydantic`, `python-dotenv`, `requests`, `sentence-transformers`, `numpy`, `scikit-learn`, `matplotlib`
- API keys in `.env` (OpenAI for embeddings and LLM naming)
- Run scripts directly via `/Users/sue/Documents/git/storm/venv/bin/python3.14 scripts/...`

## Architecture Layers (Bottom to Top)

### Layer 1: Ingest & Normalize
- `src/ingest_finnhub.py`, `src/ingest_newsapi.py`, `src/ingest_sec.py` — fetch from sources
- `src/normalize.py` — unified event schema
- `scripts/fetch_all.py`, `scripts/fetch_today.py` — orchestration
- Output: `data/normalized/tech_ecosystem.jsonl` → filtered to `tech_ecosystem_filtered.jsonl`
- **2503 events** across SEC, Finnhub, NewsAPI for Feb-Mar 2026 window

### Layer 2: Embed
- `src/embed_events.py` — OpenAI `text-embedding-3-large` (3072 dims), API at `https://api.openai.com`
- `scripts/embed_filtered.py` — batch embedding
- Output: `data/derived/tech_ecosystem_embeddings.npz` (embeddings + event_ids)

### Layer 3: Storm Detection
- `src/storm_tracking.py` — time-aware semantic clustering into actor storms
- `src/ecosystem_grouping.py` — cross-actor ecosystem storms
- `src/storm_topic_clustering.py` — sub-topic clustering within storms
- `scripts/detect_actor_storms.py`, `scripts/detect_ecosystem_storms.py`
- Output: `data/derived/actor_storms.jsonl` (32 storms), `ecosystem_storms.jsonl` (6 storms)
- Each storm has: `storm_id`, `actor`, `event_ids`, `centroid`, `event_count`, `state`, `created_at`

### Layer 4: Trajectories & Lifecycle
- `src/storm_tracking.py` — windowed trajectory tracking
- States: emerging, growing, peaking, stable, fading, volatile
- `scripts/track_storms.py`
- Output: `data/derived/storm_trajectories.jsonl` (11 trajectories)
- Each trajectory has: `momentum`, `acceleration`, `drift`, `peak_ratio`, `state`

### Layer 5: Summaries & Naming
- `src/storm_summaries.py` — statistical summaries (coherence, domain phrases, representative events)
- `src/llm_naming.py` — GPT-4o-mini generates headlines and one-liners
- Output: `data/derived/actor_storm_summaries.jsonl`, `ecosystem_storm_summaries.jsonl`

### Layer 6: Propagation & Convergence
- `src/storm_propagation.py` — detects narrative flow between actors via semantic + temporal similarity
- `scripts/detect_storm_propagation.py`
- Output: `storm_propagation.jsonl` (48 edges), `propagation_chains.json` (153 chains), `merge_candidates.jsonl`

### Layer 7: Narrative Evolution
- `src/narrative_evolution.py` — phase-based drift analysis, shift type classification
- Shift types: `thematic_shift`, `market_noise_shift`, `mixed_shift`, `stable`, `unclear`
- `scripts/compute_narrative_evolution.py`
- Output: `data/derived/narrative_evolution.jsonl` (19 storms, 6 with evolution data)

### Layer 8: Coherence (Separate from Drift)
- Computed in `generate_master_report.py`, not a standalone module
- Case A: `used_topic_clustering` → `cluster_dominance_ratio`
- Case B: no clustering, ≥5 events → fallback capped at 0.75 using `summary_confidence`
- Case C: sparse <5 events → `None` / N/A

### Layer 9: Narrative Leadership
- `src/narrative_leadership.py` — roles from propagation chain positions + edge directions
- Roles: leader, amplifier, bridge, receiver, insufficient_data (chains < 3)
- Output: `data/derived/narrative_leadership.json`, `theme_leadership.json`
- Current: AMD=Leader, AMZN/ASML/GOOGL=Amplifiers, MSFT/NVDA=Bridges, TSM=Receiver

### Layer 10: Narrative Pressure
- `src/narrative_pressure.py` — weighted combination of momentum, acceleration, actor spread, pre-peak ratio
- State modifier: growing/emerging +0.10, fading -0.15, stable -0.05, volatile +0.05
- Small-storm cap: event_count < 4 → max 0.49
- Thresholds: HIGH=0.75, BUILDING=0.35
- `scripts/detect_narrative_pressure.py`
- Output: `data/derived/narrative_pressure.jsonl` (38 entries)

### Layer 11: Strategic Watchlist
- `src/strategic_watchlist.py` — joins pressure + leadership into strategic scores
- Formula: `0.70 * pressure + 0.20 * role_weight + 0.10 * ecosystem_bonus + shift_bonus`
- Categories: priority_watch, monitor_closely, lower_priority
- Dedupe: same-actor storms with identical pressure scores get merged
- Filtering: removes market_noise at non-high pressure, removes insufficient_data actors
- `scripts/generate_strategic_watchlist.py`
- Output: `data/derived/strategic_watchlist.jsonl` (14 after dedupe)
- Current: 1 priority (GOOGL), 1 monitor closely

### Layer 12: Community Overlay
- `src/community_overlay.py` — maps Reddit/community posts onto institutional storms WITHOUT mixing into storm detection
- Attaches via cosine similarity ≥0.78 to storm centroids + time lag ≤10 days
- Computes alignment (aligned/mixed/divergent), divergent themes, precursors
- `scripts/build_community_overlay.py`
- Output: `community_overlay.jsonl`, `community_precursors.jsonl`
- Currently uses synthetic test data (`scripts/generate_synthetic_community.py`). Real Reddit fetch not yet built.
- `tech_ecosystem_filtered.jsonl` was a one-off manual filter of `tech_ecosystem.jsonl` — no filter script exists. New events from `fetch_today.py` go into `tech_ecosystem.jsonl` only and are NOT automatically added to the filtered file.

### Layer 13: Visualization
- `src/visualize_field.py` — 2D UMAP projections with storm regions, trajectories, density
- `scripts/plot_storm_field_with_state.py` — ecosystem field view
- `scripts/plot_per_actor.py` — per-actor field views
- `scripts/plot_watchlist_matrix.py` — pressure × leadership matrix (bubble chart)
- Colors: leader=red, amplifier=blue, bridge=purple, receiver=gray

### Layer 14: Report Generation
- `scripts/generate_master_report.py` — main HTML report from all layers
- `topicspace_master_report_template.html` — template with `{{ var_name }}` simple string replacement (no Jinja)
- Output: `master_report.html`
- 7 sections: Exec Overview, Strategic Watchlist, Narrative Leadership, Ecosystem View, Actor Snapshots (5 actors), Convergence & Propagation, Method & Caveats, plus Appendix (Storm Index)
- Also: `scripts/generate_ecosystem_report.py`, `scripts/generate_community_overlay_report.py`, `scripts/generate_strategic_watchlist.py`

## Key Data Facts

- **8 actors**: AMD, AMZN, ASML, AVGO, GOOGL, MSFT, NVDA, TSM
- **32 actor storms** (AMD:1, AMZN:9, ASML:3, AVGO:1, GOOGL:5, MSFT:3, NVDA:3, TSM:7)
- **6 ecosystem storms**
- **11 trajectories**, **48 propagation edges**, **153 chains**
- **19 of 32 actor storms have fading state** — heavily skews pressure toward low
- All storms for the same actor share the same trajectory values (best trajectory by total_events)
- Pressure deduplication needed in reports because of shared trajectory scores

## Critical Design Decisions

1. **Coherence ≠ drift**. Coherence uses clustering metrics. Drift uses trajectory embeddings. They were incorrectly coupled as `coherence = 1 - drift` before being separated.

2. **Community overlay is NOT mixed into storm detection**. Reddit enriches institutional storms but does not redefine boundaries. The `signal_layer: "community"` field preserves this separation.

3. **Template uses simple string replacement**, not Jinja. `{{ key }}` → value. No conditionals in the template — all HTML logic is pre-built in Python.

4. **Watchlist deduplication** is essential. Same-actor storms sharing identical pressure scores (from same trajectory) get merged into one entry with combined event count.

5. **Shift type classification** has two paths: evolution-level (from `narrative_evolution.py` phase-term analysis) and title-level fallback (from `generate_master_report.py` using `MARKET_NOISE_TERMS`). Noise thresholds: evolution 0.25/0.15, title 0.06/0.03.

## Featured Actors in Report

The master report features 5 actors (set in `generate_master_report.py`):
```python
priority_actors = ['AMZN', 'TSM', 'GOOGL', 'AVGO', 'ASML']
```

## Running the Full Pipeline

```bash
source venv/bin/activate

# Fetch and normalize (needs API keys in .env)
python scripts/fetch_all.py

# Embed
python scripts/embed_filtered.py

# Detect storms
python scripts/detect_actor_storms.py
python scripts/detect_ecosystem_storms.py

# Track trajectories
python scripts/track_storms.py
python scripts/track_ecosystem_storms_windowed.py

# Generate summaries (needs OpenAI key)
python scripts/generate_storm_summaries.py
python scripts/generate_ecosystem_summaries.py
python scripts/generate_llm_storm_names.py

# Propagation
python scripts/detect_storm_propagation.py

# Narrative evolution
python scripts/compute_narrative_evolution.py

# Pressure detection
python scripts/detect_narrative_pressure.py

# Strategic watchlist
python scripts/generate_strategic_watchlist.py

# Community overlay (currently synthetic data)
python scripts/generate_synthetic_community.py
python scripts/build_community_overlay.py

# Visualizations
python scripts/plot_storm_field_with_state.py
python scripts/plot_per_actor.py
python scripts/plot_watchlist_matrix.py

# Reports
python scripts/generate_master_report.py
python scripts/generate_ecosystem_report.py
python scripts/generate_community_overlay_report.py
python scripts/generate_strategic_watchlist.py
```

## What Was Being Worked On

The most recent work was the **community overlay layer** (community-overlay.md). The architecture is complete and tested with synthetic data. The next step is building `scripts/fetch_reddit.py` to get real Reddit data. Needs decision on:
1. Reddit API key vs public JSON endpoints
2. Which subreddits to target first
3. Time window to match

Other potential next steps from the spec backlog:
- **Pressure × Leadership matrix visualization** is done (`plot_watchlist_matrix.py`)
- **Real Reddit data ingestion** — fetch script not yet built
- Tighter ecosystem storm boundaries
- Trajectory-level reporting improvements

## Style Notes

- Minimal code, no verbose implementations
- No auto-generated tests unless explicitly requested
- Prefer modifying existing files over creating new ones when possible
- All scripts must work with `source venv/bin/activate && python scripts/...`
- Diagnostics printed at end of every script run
