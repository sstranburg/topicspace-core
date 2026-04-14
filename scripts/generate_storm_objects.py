#!/usr/bin/env python3
"""
generate_storm_objects.py

Translates existing derived pipeline data into a frontend-friendly storms.json.
Fields are mapped conservatively — nulls over invented values.
Heuristic derivations are marked in comments.

Inputs (all already exist after run_pipeline.py):
  - data/derived/actor_storm_summaries.jsonl
  - data/derived/storm_trajectories.jsonl
  - data/derived/narrative_pressure.jsonl
  - data/derived/cleaned_lineages.json
  - data/derived/narrative_leadership.json
  - data/derived/propagation_chains.json
  - topicspace-site/public/actors.json  (for price confirmation status)

Output:
  - topicspace-site/public/storms.json

Usage:
  venv/bin/python scripts/generate_storm_objects.py
  venv/bin/python scripts/generate_storm_objects.py --min-events 3
  venv/bin/python scripts/generate_storm_objects.py --limit 40
"""

import argparse
import json
from collections import defaultdict, Counter
from datetime import date
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "derived"
SITE_DIR = ROOT.parent / "topicspace-site" / "public"

# ── Inputs ────────────────────────────────────────────────────────────────────

SUMMARIES_FILE    = DATA_DIR / "actor_storm_summaries.jsonl"
TRAJECTORIES_FILE = DATA_DIR / "storm_trajectories.jsonl"
PRESSURE_FILE     = DATA_DIR / "narrative_pressure.jsonl"
LINEAGES_FILE     = DATA_DIR / "cleaned_lineages.json"
LEADERSHIP_FILE   = DATA_DIR / "narrative_leadership.json"
PROP_FILE         = DATA_DIR / "propagation_chains.json"
ACTORS_JSON       = SITE_DIR / "actors.json"
ACTOR_STORMS_FILE = DATA_DIR / "actor_storms.jsonl"

OUTPUT_FILE = SITE_DIR / "storms.json"

# ── Lifecycle normalization ────────────────────────────────────────────────────
#
# Normalized vocabulary (7 values):
#   emerging      — narrative just forming; very few events, no established trajectory
#   organizing    — narrative present and consolidating; not yet accelerating
#   intensifying  — narrative accelerating; momentum or acceleration is positive
#   confirming    — narrative with price confirmation (requires board_state == CONFIRMED)
#   splitting     — narrative diverging into sub-threads (not yet observable from current data)
#   dissipating   — narrative winding down; trajectory is fading
#   unknown       — high semantic drift or missing data; direction cannot be determined
#
# Source: trajectory.state (actor-level, not storm-level — this is a heuristic)
# The pipeline tracks actor-level trajectories, not per-storm. The normalized
# lifecycle_stage is therefore an actor-level proxy, not a true storm lifecycle.

_EMERGING_MAX_EVENTS = 8  # heuristic: storms with fewer events than this may be "emerging"

def normalize_lifecycle(
    traj_state:    str | None,
    summary_state: str | None,
    momentum:      int,
    acceleration:  int,
    event_count:   int,
    board_state:   str | None,
) -> str:
    """
    Map pipeline states to normalized lifecycle vocabulary.

    Priority: trajectory.state > summary.state > event_count heuristic.
    board_state=CONFIRMED can promote organizing/intensifying → confirming.
    """
    # Confirmed by price: narrative + price aligned
    # Only promote if trajectory already suggests active narrative
    source_state = traj_state or summary_state

    if not source_state:
        # No trajectory or summary state — too new or too sparse
        return "emerging" if event_count < _EMERGING_MAX_EVENTS else "unknown"

    if source_state == "volatile":
        # High semantic drift: content shifting faster than it can cohere.
        # Cannot determine direction — do not guess.
        return "unknown"

    if source_state == "fading":
        return "dissipating"

    if source_state == "stable":
        # Present but not accelerating. Price confirmation can elevate it.
        if board_state == "CONFIRMED":
            return "confirming"
        return "organizing"

    if source_state in ("growing", "peaking"):
        # growing + meaningful forward momentum or acceleration → intensifying
        # growing + decelerating → organizing (growth is slowing)
        # [heuristic: momentum and acceleration thresholds are empirically chosen]
        if board_state == "CONFIRMED":
            return "confirming"
        if momentum > 3 or acceleration > 5:
            return "intensifying"
        return "organizing"

    # Fallback for any unlisted state values
    return "unknown"


# Phase signal → lifecycle stage (for lineage phase display)
# Maps cleaned_lineages phase signals to the normalized vocabulary.
PHASE_SIGNAL_TO_LIFECYCLE: dict[str, str] = {
    "emergence":     "emerging",
    "expansion":     "intensifying",
    "consolidation": "organizing",
    "contraction":   "dissipating",
    "peak":          "intensifying",
    "splitting":     "splitting",
}


# ── Price confirmation status ─────────────────────────────────────────────────
# Derived from actor state on the leaderboard. This is actor-level, not
# storm-level — a heuristic that approximates how price is responding to
# the narrative the storm represents.

STATE_TO_PRICE_STATUS: dict[str, str] = {
    "CONFIRMED":        "price_confirming",
    "EARLY":            "early_follow_through",
    "DIVERGENCE":       "price_diverging",
    "REPRICING":        "price_lagging",
    "DISAGREEMENT":     "rejected_by_price",
    "NEG_CONFIRMATION": "price_confirming_bearish",
    "PRICE-LED":        "price_leading",
    "MACRO":            "macro_driven",
    "UNCLEAR":          "no_clear_signal",
}

PRICE_STATUS_LABEL: dict[str, str] = {
    "price_confirming":         "Price confirming",
    "early_follow_through":     "Early follow-through",
    "price_diverging":          "Price diverging",
    "price_lagging":            "Price lagging",
    "rejected_by_price":        "Rejected by price",
    "price_confirming_bearish": "Price confirming (bearish)",
    "price_leading":            "Price leading",
    "macro_driven":             "Macro-driven",
    "no_clear_signal":          "No clear signal",
}


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  [WARN] missing: {path.name}")
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        print(f"  [WARN] missing: {path.name}")
        return None
    return json.loads(path.read_text())


# ── Lookup tables ─────────────────────────────────────────────────────────────

def build_pressure_by_storm(pressure_recs: list[dict]) -> dict[str, dict]:
    """Best (highest pressure_score) pressure record per storm_id."""
    by_storm: dict[str, dict] = {}
    for r in pressure_recs:
        sid = r.get("storm_id", "")
        if not sid:
            continue
        if sid not in by_storm or r.get("pressure_score", 0) > by_storm[sid].get("pressure_score", 0):
            by_storm[sid] = r
    return by_storm


def build_trajectory_by_actor(traj_recs: list[dict]) -> dict[str, dict]:
    """Best (highest total_events) trajectory record per actor.
    Trajectories are actor-level, not storm-level."""
    by_actor: dict[str, dict] = {}
    for r in traj_recs:
        actor = r.get("actor", "")
        if not actor:
            continue
        if actor not in by_actor or r.get("total_events", 0) > by_actor[actor].get("total_events", 0):
            by_actor[actor] = r
    return by_actor


def build_leadership_by_actor(leadership: list[dict]) -> dict[str, dict]:
    return {r["actor"]: r for r in leadership if "actor" in r}


def build_lineage_index(lineages: dict) -> dict[str, list[str]]:
    """actor → list of lineage_ids that include that actor (sorted by actor count desc).
    This join is ambiguous — an actor may belong to multiple lineages.
    We use the first match (most populated lineage first) as a best-effort approximation."""
    index: dict[str, list[str]] = defaultdict(list)
    # Sort lineages by actor count so the best-fit comes first
    sorted_lineages = sorted(
        lineages.items(),
        key=lambda kv: len(kv[1].get("actors", [])),
        reverse=True,
    )
    for lid, lin in sorted_lineages:
        for actor in lin.get("actors", []):
            index[actor.upper()].append(lid)
    return index


def build_actor_board_state(actors_json: dict | None) -> dict[str, dict]:
    """actor ticker → {state, read, narr, rel, nds}. Returns {} if actors.json missing."""
    if not actors_json:
        return {}
    return {
        a["t"]: {
            "state": a.get("state", "UNCLEAR"),
            "read":  a.get("read", "") or "",
            "narr":  a.get("narr", 35),
            "rel":   a.get("rel", 0.0),
            "nds":   a.get("nds", 0.0),
        }
        for a in actors_json.get("actors", [])
    }


def build_propagation_partners(prop_chains: list[dict]) -> dict[str, set[str]]:
    """actor → set of actors it co-appears with in propagation chains."""
    partners: dict[str, set[str]] = defaultdict(set)
    for chain in prop_chains:
        actors = [a.upper() for a in chain.get("actors", [])]
        for a in actors:
            for b in actors:
                if a != b:
                    partners[a].add(b)
    return partners


# ── Roles derivation ──────────────────────────────────────────────────────────

def derive_roles(actor: str, lead: dict) -> dict:
    """
    Derive roles block from narrative_leadership record.

    Source: narrative_leadership.json, which assigns one role per actor
    across ALL propagation chains — this is actor-level, not storm-level.
    Roles within a single storm are not distinguishable from current data.

    Role values: leader, amplifier, receiver, bridge (from pipeline).
    Mapped to: originators (leader), amplifiers (amplifier),
               bridges (bridge), receivers (receiver).
    """
    role = lead.get("role")  # may be None if actor not in leadership file
    if not role:
        return {
            "originators": [],
            "amplifiers":  [],
            "bridges":     [],
            "receivers":   [],
        }
    return {
        "originators": [actor] if role == "leader"    else [],
        "amplifiers":  [actor] if role == "amplifier" else [],
        "bridges":     [actor] if role == "bridge"    else [],
        "receivers":   [actor] if role == "receiver"  else [],
    }


# ── Storm object builder ───────────────────────────────────────────────────────

def build_storm_object(
    summary:          dict,
    pressure_map:     dict[str, dict],
    traj_map:         dict[str, dict],
    leadership_map:   dict[str, dict],
    lineage_map:      dict,
    lineage_index:    dict[str, list[str]],
    board_state:      dict[str, dict],
    prop_partners:    dict[str, set[str]],
    actor_storms_map: dict[str, list[str]] | None = None,
) -> dict:
    storm_id = summary.get("storm_id", "")

    # Primary actor: first element of actors list, or fallback to actor field
    actors_raw = summary.get("actors") or []
    actor = actors_raw[0].upper() if actors_raw else (summary.get("actor") or "")
    actors = [a.upper() for a in actors_raw] if actors_raw else ([actor] if actor else [])

    # Name and summary
    # Prefer LLM-generated display fields; fall back to heuristic headline.
    # storm_id is last resort (not human-readable but never null).
    name     = summary.get("display_headline") or summary.get("headline") or storm_id
    one_line = summary.get("display_one_liner") or summary.get("one_liner") or None

    event_count = summary.get("event_count", 0)

    # ── Pressure (storm-level join) ───────────────────────────────────────────
    # Joined by storm_id from narrative_pressure.jsonl.
    # If no match: all pressure fields are null (not zero — absence of data ≠ zero pressure).
    pressure       = pressure_map.get(storm_id)
    pressure_score = round(pressure["pressure_score"], 3)      if pressure else None
    pressure_level = pressure.get("pressure_level")            if pressure else None
    velocity_state = pressure.get("velocity_state")            if pressure else None
    events_last_48h= pressure.get("events_last_48h")          if pressure else None
    events_prev_48h= pressure.get("events_prev_48h")          if pressure else None

    # intensity: fraction of this storm's activity happening in the last 48h.
    # [heuristic: recency score — higher = more active right now vs historically]
    # Null if pressure record missing or event_count is zero.
    if pressure and events_last_48h is not None and event_count > 0:
        intensity = round(min(1.0, events_last_48h / event_count), 3)
    else:
        intensity = None

    # ── Trajectory (actor-level proxy) ───────────────────────────────────────
    # Storm trajectories.jsonl tracks actors, not individual storms.
    # All storms for the same actor share the same trajectory metrics.
    # This is a known limitation — treat these fields as actor-level context,
    # not per-storm measurements.
    traj         = traj_map.get(actor, {})
    traj_state   = traj.get("state")            # volatile | growing | stable | fading | peaking
    summary_state= summary.get("state")         # volatile | growing | stable | fading
    momentum     = traj.get("latest_momentum")  # int, events/window delta; null if no trajectory
    acceleration = traj.get("latest_acceleration")  # int, momentum delta; null if no trajectory
    # density: current events-per-window from trajectory; null if no trajectory
    density      = traj.get("latest_density")

    # Lifecycle normalization
    actor_board  = board_state.get(actor, {})
    board_state_str = actor_board.get("state")
    lifecycle_stage = normalize_lifecycle(
        traj_state   = traj_state,
        summary_state= summary_state,
        momentum     = momentum or 0,
        acceleration = acceleration or 0,
        event_count  = event_count,
        board_state  = board_state_str,
    )

    # ── Price confirmation status ─────────────────────────────────────────────
    # Derived from actor's leaderboard state.
    # Null if actor not on leaderboard (e.g. private companies).
    if actor_board:
        price_status       = STATE_TO_PRICE_STATUS.get(board_state_str or "", "no_clear_signal")
        price_status_label = PRICE_STATUS_LABEL.get(price_status, price_status)
        board_read         = actor_board.get("read") or None
        board_nds          = actor_board.get("nds")
        board_rel          = actor_board.get("rel")
    else:
        price_status       = None
        price_status_label = None
        board_read         = None
        board_nds          = None
        board_rel          = None

    # ── Leadership / roles ────────────────────────────────────────────────────
    lead         = leadership_map.get(actor, {})
    dominant_role= lead.get("role")   # leader | amplifier | receiver | bridge | None
    roles        = derive_roles(actor, lead)

    # ── Lineage (best-effort join) ────────────────────────────────────────────
    # actor → lineage_id mapping is ambiguous: one actor can appear in multiple lineages.
    # We use the first match from the sorted index (largest lineage first).
    # This should be treated as a suggested narrative context, not a definitive link.
    actor_lineages = lineage_index.get(actor, [])
    lineage_id     = actor_lineages[0] if actor_lineages else None
    lineage_name   = None
    lineage_phases = []
    if lineage_id and lineage_id in lineage_map:
        lin            = lineage_map[lineage_id]
        lineage_name   = lin.get("canonical_name")
        lineage_phases = [
            {
                "name":          p.get("name"),
                "lifecycle":     PHASE_SIGNAL_TO_LIFECYCLE.get(p.get("signal", ""), "unknown"),
                "signal_raw":    p.get("signal"),
                "date_range":    p.get("date_range"),
                "key_actors":    p.get("key_actors", []),
            }
            for p in lin.get("phases", [])
        ]

    # ── Propagation partners ─────────────────────────────────────────────────
    # Co-occurrence in propagation chains — not directional.
    # Limited to top 5 by alphabetical sort (no frequency data at this level).
    partners = sorted(prop_partners.get(actor, set()) - {actor})[:5]

    # ── Top sources (representative headlines) ────────────────────────────────
    # cluster_titles_topN from actor_storms.jsonl — top 3 headlines for this storm.
    top_sources: list[str] = actor_storms_map.get(storm_id, []) if actor_storms_map else []

    # ── Fields not yet derivable from current data ────────────────────────────
    # These are included in the schema spec but have no backing data source yet.
    # Setting to empty arrays rather than omitting so the frontend type is stable.
    strengthening_triggers: list = []   # no backing data
    weakening_triggers:     list = []   # no backing data
    related_signals:        list = []   # could link to ai/latest.json signals in future

    return {
        "id":      storm_id,
        "name":    name,
        "summary": one_line,
        "actor":   actor,
        "actors":  actors,
        # ── Lifecycle ──
        # lifecycle_stage derived from actor-level trajectory + board state (heuristic)
        "lifecycle_stage":    lifecycle_stage,
        "momentum":           momentum,       # null if actor has no trajectory
        "acceleration":       acceleration,   # null if actor has no trajectory
        "density":            density,        # null if actor has no trajectory
        # intensity: recency score (events_last_48h / total event_count), null if missing
        "intensity":          intensity,
        # ── Pressure ──
        # All null if no pressure record matched this storm_id
        "pressure_score":     pressure_score,
        "pressure_level":     pressure_level,
        "velocity_state":     velocity_state,
        "events_last_48h":    events_last_48h,
        "event_count":        event_count,
        # ── Price behavior ──
        # All null if actor not on leaderboard
        "price_confirmation_status":       price_status,
        "price_confirmation_status_label": price_status_label,
        "board_state":   board_state_str,
        "board_read":    board_read,
        "board_nds":     board_nds,
        "board_rel":     board_rel,
        # ── Roles ──
        # dominant_role: actor-level across all propagation (not storm-specific)
        "dominant_role": dominant_role,
        "roles":         roles,
        # ── Lineage ──
        # best-effort: first lineage match for actor (may not be the best fit)
        "lineage_id":    lineage_id,
        "lineage_name":  lineage_name,
        "lineage_phases":lineage_phases,
        # ── Propagation ──
        "propagation_partners": partners,
        # ── Signals (not yet populated) ──
        "strengthening_triggers": strengthening_triggers,
        "weakening_triggers":     weakening_triggers,
        "related_signals":        related_signals,
        # ── Top sources ──
        # Top 3 representative headlines from cluster_titles_topN (actor_storms.jsonl)
        "top_sources": top_sources,
        # ── Source quality ──
        "llm_named":      summary.get("llm_used", False),
        "display_source": summary.get("display_source", "heuristic"),
    }


# ── System meta ───────────────────────────────────────────────────────────────

def compute_system_meta(storms: list[dict], lineage_map: dict | None) -> dict:
    if not storms:
        return {
            "system_state":        "unknown",
            "system_condition":    "no active storms",
            "dominant_constraint": None,
            "summary":             "No significant narrative storms detected.",
            "stage_counts":        {},
            "price_status_counts": {},
        }

    stage_counts = Counter(s["lifecycle_stage"] for s in storms)
    dominant_stage = stage_counts.most_common(1)[0][0]

    # Price confirmation distribution (exclude nulls)
    price_counts = Counter(
        s["price_confirmation_status"]
        for s in storms
        if s["price_confirmation_status"] is not None
    )

    # Dominant narrative constraint: lineage with most actors in the dataset
    lineage_actor_counts: Counter = Counter()
    if lineage_map:
        for lid, lin in lineage_map.items():
            lineage_actor_counts[lin.get("canonical_name", lid)] = len(lin.get("actors", []))
    dominant_constraint = lineage_actor_counts.most_common(1)[0][0] if lineage_actor_counts else None

    # System condition: dominant price response
    total = len(storms)
    confirming = price_counts.get("price_confirming", 0) + price_counts.get("price_confirming_bearish", 0)
    diverging  = price_counts.get("price_diverging", 0)
    leading    = price_counts.get("price_leading", 0)
    lagging    = price_counts.get("price_lagging", 0)

    if confirming / total > 0.4:
        condition = "price confirming across multiple actors"
    elif diverging / total > 0.3:
        condition = "narratives building but price not following"
    elif leading / total > 0.3:
        condition = "price ahead of narrative in multiple names"
    elif lagging / total > 0.3:
        condition = "narrative intact but price compressing"
    else:
        condition = "mixed — no dominant price behavior"

    # Summary sentence using normalized stage names
    parts = []
    for stage in ("intensifying", "organizing", "dissipating", "unknown", "confirming", "emerging"):
        n = stage_counts.get(stage, 0)
        if n:
            parts.append(f"{n} {stage}")
    storm_dist = ", ".join(parts) if parts else f"{total} active"

    summary = (
        f"{total} active narrative storms ({storm_dist}). "
        f"System condition: {condition}."
    )

    return {
        "system_state":        dominant_stage,
        "system_condition":    condition,
        "dominant_constraint": dominant_constraint,
        "summary":             summary,
        "stage_counts":        dict(stage_counts),
        "price_status_counts": dict(price_counts),
    }


# ── Sort key ──────────────────────────────────────────────────────────────────

_SORT_ORDER = {
    "intensifying": 0,
    "confirming":   1,
    "organizing":   2,
    "emerging":     3,
    "unknown":      4,
    "dissipating":  5,
    "splitting":    6,
}

def storm_sort_key(s: dict) -> tuple:
    """Sort by lifecycle stage priority, then pressure_score descending (nulls last)."""
    stage_rank    = _SORT_ORDER.get(s["lifecycle_stage"], 99)
    pressure_rank = -(s["pressure_score"] or 0.0)
    return (stage_rank, pressure_rank)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(min_events: int = 5, limit: int = 60) -> None:
    print("Loading source data...")

    summaries    = load_jsonl(SUMMARIES_FILE)
    trajectories = load_jsonl(TRAJECTORIES_FILE)
    pressure     = load_jsonl(PRESSURE_FILE)
    lineages     = load_json(LINEAGES_FILE) or {}
    leadership   = load_json(LEADERSHIP_FILE) or []
    prop_chains  = load_json(PROP_FILE) or []
    actors_raw   = load_json(ACTORS_JSON)
    actor_storms = load_jsonl(ACTOR_STORMS_FILE)

    # Build storm_id → top-3 representative headlines lookup
    actor_storms_map: dict[str, list[str]] = {
        rec["storm_id"]: (rec.get("cluster_titles_topN") or [])[:3]
        for rec in actor_storms
        if rec.get("storm_id")
    }

    print(f"  Summaries:   {len(summaries)}")
    print(f"  Trajectories:{len(trajectories)}")
    print(f"  Pressure:    {len(pressure)}")
    print(f"  Lineages:    {len(lineages)}")
    print(f"  Leadership:  {len(leadership)}")
    print(f"  Prop chains: {len(prop_chains)}")
    print(f"  Actor storms:{len(actor_storms)} (top_sources map: {len(actor_storms_map)} entries)")

    pressure_map   = build_pressure_by_storm(pressure)
    traj_map       = build_trajectory_by_actor(trajectories)
    leadership_map = build_leadership_by_actor(leadership)
    lineage_index  = build_lineage_index(lineages)
    board_state    = build_actor_board_state(actors_raw)
    prop_partners  = build_propagation_partners(prop_chains)

    # Deduplicate by storm_id — source file contains duplicates when the pipeline
    # re-runs clustering on overlapping windows. Keep the record with the highest
    # event_count; ties broken by first occurrence.
    seen_ids: dict[str, dict] = {}
    for s in summaries:
        sid = s.get("storm_id", "")
        if not sid:
            continue
        if sid not in seen_ids or s.get("event_count", 0) > seen_ids[sid].get("event_count", 0):
            seen_ids[sid] = s
    summaries = list(seen_ids.values())
    print(f"  After storm_id dedup: {len(summaries)}")

    # Filter: minimum event count, must have at least one actor
    usable = [
        s for s in summaries
        if s.get("event_count", 0) >= min_events
        and (s.get("actors") or s.get("actor"))
    ]
    print(f"\nUsable summaries (event_count ≥ {min_events}): {len(usable)}")

    # Build storm objects
    storms = []
    for summary in usable:
        try:
            obj = build_storm_object(
                summary, pressure_map, traj_map, leadership_map,
                lineages, lineage_index, board_state, prop_partners,
                actor_storms_map,
            )
            storms.append(obj)
        except Exception as e:
            print(f"  [WARN] skipped {summary.get('storm_id', '?')}: {e}")

    # Sort by lifecycle priority + pressure, then cap at 3 per actor
    storms.sort(key=storm_sort_key)
    actor_seen: dict[str, int] = defaultdict(int)
    capped: list[dict] = []
    for s in storms:
        if actor_seen[s["actor"]] < 3:
            capped.append(s)
            actor_seen[s["actor"]] += 1
    storms = capped[:limit]

    meta   = compute_system_meta(storms, lineages)
    output = {"date": str(date.today()), "meta": meta, "storms": storms}

    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {len(storms)} storms → {OUTPUT_FILE}")
    print(f"System state: {meta['system_state']}")
    print(f"Condition: {meta['system_condition']}")
    print(f"Stage distribution: {meta['stage_counts']}")

    print("\nTop 5 storms:")
    for s in storms[:5]:
        p = f"{s['pressure_score']:.2f}" if s["pressure_score"] is not None else "n/a"
        print(
            f"  [{s['lifecycle_stage']:12s}] {s['actor']:6s} | "
            f"p={p} | "
            f"{str(s['price_confirmation_status'] or 'null'):25s} | "
            f"{s['name'][:50]}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-events", type=int, default=5)
    parser.add_argument("--limit",      type=int, default=60)
    args = parser.parse_args()
    main(min_events=args.min_events, limit=args.limit)
