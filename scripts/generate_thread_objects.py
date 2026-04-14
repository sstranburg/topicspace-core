#!/usr/bin/env python3
"""
generate_thread_objects.py — v3

Groups storm objects into narrative threads with:
  - Lineage-based grouping (primary, uses canonical names)
  - Per-actor fallback grouping (no lineage match)
  - Conservative title normalization (strips generic pipeline prefixes)
  - 5-value thread lifecycle vocabulary
  - 6-value thread price status vocabulary
  - Thread name refinement for over-generic lineage labels
  - Coherence scoring (simple, explainable heuristics)
  - dominant_actors / supporting_actors actor split

Grouping priority:
  1. Lineage / canonical narrative name (cleaned_lineages.json)
  2. Actor-level fallback (one thread per actor, no cross-actor merging)

Inputs: same as generate_storm_objects.py
Output: topicspace-site/public/threads.json

Usage:
  venv/bin/python scripts/generate_thread_objects.py
  venv/bin/python scripts/generate_thread_objects.py --min-events 3 --limit 80
"""

import argparse
import json
import re
import sys
from collections import defaultdict, Counter
from datetime import date
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))
from generate_storm_objects import (
    load_jsonl,
    load_json,
    build_pressure_by_storm,
    build_trajectory_by_actor,
    build_leadership_by_actor,
    build_lineage_index,
    build_actor_board_state,
    build_propagation_partners,
    build_storm_object,
    storm_sort_key,
    _SORT_ORDER,
    PHASE_SIGNAL_TO_LIFECYCLE,
)

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "derived"
SITE_DIR = ROOT.parent / "topicspace-site" / "public"

SUMMARIES_FILE    = DATA_DIR / "actor_storm_summaries.jsonl"
TRAJECTORIES_FILE = DATA_DIR / "storm_trajectories.jsonl"
PRESSURE_FILE     = DATA_DIR / "narrative_pressure.jsonl"
LINEAGES_FILE     = DATA_DIR / "cleaned_lineages.json"
LEADERSHIP_FILE   = DATA_DIR / "narrative_leadership.json"
PROP_FILE         = DATA_DIR / "propagation_chains.json"
ACTORS_JSON       = SITE_DIR / "actors.json"
OUTPUT_FILE       = SITE_DIR / "threads.json"


# ── Actor display names ────────────────────────────────────────────────────────
# Used for thread naming when actor-level context improves the label.

ACTOR_DISPLAY_NAMES: dict[str, str] = {
    "MSFT":    "Microsoft",
    "GOOGL":   "Google",
    "META":    "Meta",
    "NVDA":    "Nvidia",
    "AAPL":    "Apple",
    "AMZN":    "Amazon",
    "TSM":     "TSMC",
    "ASML":    "ASML",
    "PLTR":    "Palantir",
    "AMD":     "AMD",
    "ARM":     "Arm",
    "INTC":    "Intel",
    "AVGO":    "Broadcom",
    "CRM":     "Salesforce",
    "NOW":     "ServiceNow",
    "SNOW":    "Snowflake",
    "DDOG":    "Datadog",
    "CRWD":    "CrowdStrike",
    "ANET":    "Arista Networks",
    "VRT":     "Vertiv",
    "VST":     "Vistra",
    "CEG":     "Constellation Energy",
    "ZETA":    "Zeta Global",
    "SOFI":    "SoFi",
    "MP":      "MP Materials",
    "MU":      "Micron",
    "NBIS":    "Nebius",
    "SAMSNG":  "Samsung",
    "SKHX":    "SK Hynix",
    "DELL":    "Dell",
    "ORCL":    "Oracle",
    "SMCI":    "Super Micro",
    "TSLA":    "Tesla",
    "ADBE":    "Adobe",
}


# ── Title normalization ────────────────────────────────────────────────────────
#
# Strips generic heuristic pipeline prefixes from storm display names.
# Applied to all storms in the thread build step as a display post-process.
# LLM-named storms are not modified.
#
# Conservative principle: under-normalize rather than over-normalize.

def _cap_first(s: str) -> str:
    """Capitalize first character without downcasing the rest."""
    return s[0].upper() + s[1:] if s else s


# Single-word qualifiers that prefix "developments around X"
_SINGLE_WORD_DEV_QUALIFIERS: dict[str, str] = {
    "high":      "momentum",
    "growing":   "growth",
    "rising":    "rising",
    "falling":   "declining",
    "strong":    "momentum",
    "bullish":   "bullish activity",
    "bearish":   "bearish pressure",
}

# Source-brand words that make a storm name source-shaped rather than narrative-shaped
_SOURCE_BRAND_WORDS = frozenset({"motley fool", "barron's", "seeking alpha", "wsj", "cnbc", "bloomberg"})


def _normalize_dev_prefix(prefix: str, actor: str) -> str | None:
    """
    Clean the prefix from 'X developments around TICKER' patterns.

    Single-word qualifiers → "{actor} {qualifier_concept}"
    Multi-word meaningful prefix → the prefix itself (actor shown in pill)
    Source-brand prefix → "{actor} coverage" (deprioritize, don't expose brand)
    Generic/empty prefix → "{actor} activity"
    """
    prefix_stripped = prefix.strip()
    prefix_lower    = prefix_stripped.lower()
    actor_lower     = actor.lower()

    # Source-shaped content: replace with neutral coverage label
    if any(brand in prefix_lower for brand in _SOURCE_BRAND_WORDS):
        return f"{actor} coverage"

    # Empty or just the actor name
    if not prefix_lower or prefix_lower == actor_lower:
        return f"{actor} activity"

    # Single word: map qualifier to meaningful concept
    words = prefix_stripped.split()
    if len(words) == 1:
        concept = _SINGLE_WORD_DEV_QUALIFIERS.get(prefix_lower)
        if concept:
            return f"{actor} {concept}"
        # Unknown single word — use it with actor for legibility
        return f"{actor} {prefix_stripped.lower()}"

    # Multi-word: use the prefix as the concept; actor shown in adjacent pill
    return _cap_first(prefix_stripped)


def _build_patterns() -> list[tuple]:
    """Return ordered (compiled_regex, transform_fn) pairs for title normalization."""
    return [
        # "Expansion involving TICKER"
        (re.compile(r"^expansion involving \S+$", re.I),
         lambda m, a: f"{a} expansion"),

        # "Product Launch from TICKER"
        (re.compile(r"^product launch from \S+$", re.I),
         lambda m, a: f"{a} product launch"),

        # "investment developments around TICKER"
        (re.compile(r"^investment developments around .+$", re.I),
         lambda m, a: f"{a} investment interest"),

        # "coverage narrative around TICKER" — source-shaped
        (re.compile(r"^coverage narrative around .+$", re.I),
         lambda m, a: f"{a} coverage"),

        # "X developments around TICKER" — clean the prefix
        (re.compile(r"^(.+?)\s+developments around .+$", re.I),
         lambda m, a: _normalize_dev_prefix(m.group(1).strip(), a)),

        # "X narrative around TICKER"
        (re.compile(r"^(.+?)\s+narrative around .+$", re.I),
         lambda m, a: (
             _cap_first(m.group(1).strip())
             if m.group(1).strip().lower() not in (a.lower(), "")
             else f"{a} narrative"
         )),

        # "narrative around TICKER" (no prefix)
        (re.compile(r"^narrative around .+$", re.I),
         lambda m, a: f"{a} narrative"),
    ]


_PATTERNS = _build_patterns()


def normalize_storm_title(name: str, actor: str, display_source: str) -> str:
    """
    Return a cleaner display title for a storm.

    LLM-named storms are returned as-is (already editorially shaped).
    Heuristic names are cleaned by pattern matching.
    If a pattern matches but normalization returns None (rare), the original is kept.
    """
    if display_source == "llm":
        return name

    name_stripped = name.strip()
    for pattern, transform in _PATTERNS:
        m = pattern.match(name_stripped)
        if m:
            result = transform(m, actor)
            return name_stripped if result is None else result

    return name_stripped


# ── 5-value thread lifecycle vocabulary ───────────────────────────────────────

_STORM_TO_THREAD_STAGE: dict[str, str] = {
    "intensifying": "intensifying",
    "confirming":   "confirming",
    "organizing":   "organizing",
    "emerging":     "organizing",
    "splitting":    "unresolved",
    "dissipating":  "weakening",
    "unknown":      "unresolved",
}

THREAD_STAGE_PRIORITY: dict[str, int] = {
    "intensifying": 0,
    "confirming":   1,
    "organizing":   2,
    "weakening":    3,
    "unresolved":   4,
}


def derive_thread_lifecycle(storm_stages: list[str]) -> tuple[str, dict[str, int]]:
    """
    Derive thread lifecycle from member storm stages. Returns (stage, raw_counts).

    Uses majority vote (>50%); surfaces highest-signal stage if mixed.
    Under-claims rather than over-claims.

    Note: stages are actor-level proxies, not per-storm measurements.
    """
    if not storm_stages:
        return "unresolved", {}

    mapped = [_STORM_TO_THREAD_STAGE.get(s, "unresolved") for s in storm_stages]
    counts = Counter(mapped)
    total  = len(mapped)

    top, top_n = counts.most_common(1)[0]
    if top_n / total > 0.5:
        return top, dict(counts)

    for stage in ("intensifying", "confirming", "organizing"):
        if counts.get(stage, 0) > 0:
            return stage, dict(counts)

    return "unresolved", dict(counts)


# ── 6-value thread price status vocabulary ────────────────────────────────────

_STORM_PRICE_TO_THREAD: dict[str, str] = {
    "price_confirming":         "price_confirming",
    "early_follow_through":     "price_confirming",
    "price_lagging":            "price_lagging",
    "price_diverging":          "price_diverging",
    "rejected_by_price":        "rejected_by_price",
    "price_confirming_bearish": "rejected_by_price",
    "price_leading":            "price_leading",
    "macro_driven":             "unknown",
    "no_clear_signal":          "unknown",
}

THREAD_PRICE_LABELS: dict[str, str] = {
    "price_confirming":  "Price confirming",
    "price_lagging":     "Price lagging",
    "price_diverging":   "Price diverging",
    "rejected_by_price": "Rejected by price",
    "price_leading":     "Price leading",
    "mixed":             "Mixed price response",
    "unknown":           "No clear signal",
}


def derive_thread_price_status(storms: list[dict]) -> tuple[str, str]:
    """
    Dominant price status across thread's storms (6-value vocabulary).
    Returns (code, label). Requires >50% majority; falls back to "mixed"/"unknown".
    """
    raw = [s.get("price_confirmation_status") for s in storms if s.get("price_confirmation_status")]
    if not raw:
        return "unknown", THREAD_PRICE_LABELS["unknown"]

    mapped = [_STORM_PRICE_TO_THREAD.get(c, "unknown") for c in raw]
    known  = [m for m in mapped if m != "unknown"]

    if not known:
        return "unknown", THREAD_PRICE_LABELS["unknown"]

    counts = Counter(known)
    top, top_n = counts.most_common(1)[0]
    if top_n / len(known) > 0.5:
        return top, THREAD_PRICE_LABELS.get(top, top)

    return "mixed", THREAD_PRICE_LABELS["mixed"]


# ── Thread name refinement ────────────────────────────────────────────────────
#
# Lineage canonical names are LLM-generated from narrative data and are often
# reasonable, but some are too generic (end in "Dynamics", "Sector", etc.).
# When a name is too generic, we refine it using actor context.

# Generic endings that add no specificity — safe to strip
_GENERIC_ENDINGS: list[re.Pattern] = [
    re.compile(r"\s+dynamics\s*$",                      re.I),
    re.compile(r"\s+in\s+tech(?:nology)?\s+sector\s*$", re.I),
    re.compile(r"\s+in\s+the\s+tech(?:nology)?\s+sector\s*$", re.I),
    re.compile(r"\s+in\s+technology\s*$",               re.I),
    re.compile(r"\s+sector\s*$",                        re.I),
]

# Signals that indicate a lineage name is too generic to use as-is
_GENERIC_NAME_SIGNALS = frozenset({
    "dynamics", "in tech sector", "in technology", "sector",
    "strategic developments", "market developments",
})


def _is_too_generic(name: str) -> bool:
    """True if the lineage name should be refined with actor context."""
    name_lower = name.lower()
    return any(signal in name_lower for signal in _GENERIC_NAME_SIGNALS)


def _clean_lineage_name(name: str) -> str:
    """Strip known generic endings from a lineage canonical name."""
    result = name
    for pat in _GENERIC_ENDINGS:
        result = pat.sub("", result).strip()
    return result if result else name


def derive_thread_name(
    canonical_name: str | None,
    storms: list[dict],
) -> tuple[str, str]:
    """
    Derive a display name for a named lineage thread.
    Returns (name, name_source).

    name_source (naming_method):
      'lineage_based'   — canonical lineage name is specific enough; used as-is (or cleaned)
      'actor_fallback'  — one actor dominates or no lineage; name centers on that actor
      'title_cluster'   — multiple actors; name derived from cleaned concept + top actors
      'singleton'       — only one storm in group; name taken directly from that storm
      'fallback'        — no better option found

    Conservative: lineage names from LLM analysis are trusted unless clearly too generic.
    Never invents concepts not supported by the canonical name or storm content.
    """
    if not storms:
        return canonical_name or "Active thread", "fallback"

    # Singleton — only one storm; name it directly
    if len(storms) == 1:
        return storms[0].get("name") or canonical_name or "Active thread", "singleton"

    # Compute actor event shares
    actor_events: dict[str, int] = {}
    for s in storms:
        a = s.get("actor", "")
        actor_events[a] = actor_events.get(a, 0) + s.get("event_count", 0)

    total_events  = sum(actor_events.values())
    unique_actors = len(actor_events)
    top_actor     = max(actor_events, key=lambda a: actor_events[a]) if actor_events else None
    dominance     = (actor_events[top_actor] / total_events) if top_actor and total_events > 0 else 0.0

    top_label = ACTOR_DISPLAY_NAMES.get(top_actor, top_actor) if top_actor else None

    # 1. Canonical name is specific — use it
    if canonical_name and not _is_too_generic(canonical_name):
        return canonical_name, "lineage_based"

    # 2. Generic canonical name + single dominant actor → actor-centered fallback
    if dominance > 0.65 and top_label and canonical_name:
        concept = _clean_lineage_name(canonical_name)
        if concept and len(concept) > 3:
            return f"{top_label} — {concept}", "actor_fallback"
        return f"{top_label} narrative activity", "actor_fallback"

    # 3. Generic canonical name + multiple actors → title cluster (concept + actors)
    if canonical_name:
        cleaned = _clean_lineage_name(canonical_name)
        if unique_actors <= 4 and top_label:
            top_labels = [
                ACTOR_DISPLAY_NAMES.get(a, a)
                for a, _ in sorted(actor_events.items(), key=lambda x: -x[1])[:3]
            ]
            return f"{cleaned} — {', '.join(top_labels)}", "title_cluster"
        return cleaned if cleaned != canonical_name else canonical_name, "lineage_based"

    # 4. No canonical name (unexpected for lineage threads)
    if top_label:
        return f"{top_label} narrative activity", "actor_fallback"

    return "Active narrative thread", "fallback"


# ── Coherence scoring ─────────────────────────────────────────────────────────
#
# Simple, explainable heuristics.
# Does not use embeddings or similarity — legibility over sophistication.
#
# Coherence levels:
#   high    — named lineage, multiple active actors with storm evidence
#   medium  — named lineage but single actor dominates, OR actor fallback with 2+ storms
#   low     — no lineage, only 1 storm, or very weak group evidence

def compute_coherence(
    storms: list[dict],
    lineage_id: str | None,
    is_standalone: bool,
) -> tuple[str, str]:
    """
    Returns (coherence_level, grouping_reason).

    coherence_level: "high" | "medium" | "low"
    grouping_reason: short human-readable explanation of why these storms are grouped.
    """
    n = len(storms)

    if n == 0:
        return "low", "No active storms in group."

    actor_events: dict[str, int] = {}
    for s in storms:
        a = s.get("actor", "")
        actor_events[a] = actor_events.get(a, 0) + s.get("event_count", 0)

    unique_actors  = len(actor_events)
    total_events   = sum(actor_events.values())
    top_actor      = max(actor_events, key=lambda a: actor_events[a]) if actor_events else None
    dominance      = (actor_events[top_actor] / total_events) if top_actor and total_events > 0 else 0.0
    top_label      = ACTOR_DISPLAY_NAMES.get(top_actor, top_actor) if top_actor else "one actor"

    # ── Standalone thread (actor-level fallback) ─────────────────────────────
    if is_standalone:
        if n == 1:
            return "low", "Singleton — only one active storm. No lineage match."
        if n >= 2 and unique_actors == 1:
            return "medium", f"Actor-centered fallback grouping for {top_label}. No shared lineage detected."
        return "low", "Best-effort grouping; low coherence evidence."

    # ── Named lineage thread ──────────────────────────────────────────────────
    if lineage_id:
        if n >= 3 and unique_actors >= 2:
            return "high", "Grouped by shared lineage with multiple active actors."
        if n >= 2 and unique_actors >= 2:
            return "high", "Grouped by shared lineage; two or more actors active."
        if n >= 2 and dominance > 0.85:
            return "medium", (
                f"Grouped by shared lineage; {top_label} leads activity. "
                "Other lineage actors are not currently active."
            )
        if n == 1:
            return "low", "Named lineage with only one active storm; grouping is tentative."
        return "medium", "Grouped by shared lineage."

    return "low", "No lineage match; grouping is approximate."


# ── Actor split ───────────────────────────────────────────────────────────────

def compute_actor_split(storms: list[dict]) -> tuple[list[str], list[str]]:
    """
    Split actors by event-count contribution.
    Returns (dominant_actors, supporting_actors).

    dominant_actors:  top actors accounting for ~80% of events (up to 3)
    supporting_actors: remaining storm actors (up to 3)
    """
    actor_events: dict[str, int] = {}
    for s in storms:
        a = s.get("actor", "")
        actor_events[a] = actor_events.get(a, 0) + s.get("event_count", 0)

    ranked = sorted(actor_events, key=lambda a: actor_events[a], reverse=True)
    total  = sum(actor_events.values())

    dominant: list[str] = []
    cumulative = 0
    for a in ranked:
        dominant.append(a)
        cumulative += actor_events[a]
        if cumulative / total >= 0.80 or len(dominant) >= 3:
            break

    supporting = [a for a in ranked if a not in dominant][:3]
    return dominant, supporting


# ── Per-thread storm deduplication ────────────────────────────────────────────
#
# Collapses near-duplicate child storms within a single thread into one display
# object. Conservative: only merges when same actor AND concept similarity is
# unambiguous. Under-merges rather than over-merges.
#
# Directional qualifiers (fading, growing, volatile) are kept as concept words —
# they carry meaning and help distinguish bearish from bullish narratives.

_CONCEPT_STOPWORDS = frozenset({
    # Narrative structure words (no information content)
    "narrative", "around", "story", "developments", "sentiment",
    "attention", "headlines", "predictions", "coverage", "activity",
    "news", "signal", "update", "report",
    # Generic equity/market terms
    "shares", "stock", "market", "price", "trading", "interest",
    # Generic corporate suffixes often part of company names
    "company", "firm", "group", "corporation", "technologies", "holdings",
    # Prepositions, articles, conjunctions
    "in", "the", "a", "an", "for", "of", "on", "with", "and",
    "about", "from", "to", "at", "by", "its", "their",
    # Other generic filler
    "new", "recent", "latest", "updated", "involving",
})


def _concept_tokens(name: str, actor: str) -> frozenset[str]:
    """
    Extract meaningful concept tokens from a storm display name.

    Removes: actor name variants, concept stopwords, short tokens.
    Keeps: directional qualifiers (fading/growing/volatile), finance/domain terms.
    """
    actor_lower   = actor.lower()
    display_lower = ACTOR_DISPLAY_NAMES.get(actor, actor).lower()
    actor_words   = set(actor_lower.split()) | set(display_lower.split())

    tokens = re.sub(r"[^\w\s]", " ", name.lower()).split()
    return frozenset(
        t for t in tokens
        if t not in _CONCEPT_STOPWORDS
        and t not in actor_words
        and len(t) > 2
    )


def _token_similarity(tokens_a: frozenset, tokens_b: frozenset) -> float:
    """
    Jaccard similarity between two concept token sets.

    Edge cases:
    - Both empty → 1.0 (both are pure actor-only generic names; likely same story)
    - One empty, other non-empty → 0.0 (different specificity; keep separate)
    - Standard Jaccard otherwise (handles 1-token case: identical=1.0, different=0.0)
    """
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union        = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def _price_compatible(storm_a: dict, storm_b: dict) -> bool:
    """
    True when two storms' price confirmation statuses are compatible for merging.
    Blocks merge only when both have known but different statuses.
    """
    _UNKNOWN = {None, "unknown", "no_clear_signal", "macro_driven"}
    pa = storm_a.get("price_confirmation_status")
    pb = storm_b.get("price_confirmation_status")
    if pa in _UNKNOWN or pb in _UNKNOWN:
        return True
    return pa == pb


def _are_merge_candidates(
    storm_a: dict,
    storm_b: dict,
    threshold: float = 0.4,
) -> bool:
    """
    Conservative check: should two storms in the same thread be merged?

    All three conditions must pass:
    1. Same primary actor (non-negotiable)
    2. Exact name match OR concept token Jaccard similarity >= threshold
    3. Price confirmation statuses compatible (no conflicting known signals)
    """
    if storm_a.get("actor") != storm_b.get("actor"):
        return False

    name_a = (storm_a.get("name") or "").strip().lower()
    name_b = (storm_b.get("name") or "").strip().lower()
    actor  = storm_a.get("actor", "")

    if name_a == name_b:
        return True  # exact match — always merge

    tokens_a = _concept_tokens(storm_a.get("name", ""), actor)
    tokens_b = _concept_tokens(storm_b.get("name", ""), actor)
    sim      = _token_similarity(tokens_a, tokens_b)

    if sim < threshold:
        return False

    return _price_compatible(storm_a, storm_b)


# Known noise: pipeline-produced one- or two-word stubs with no narrative content
_NOISE_NAMES = frozenset({"ai chip", "ai chips", "data center", "rtx 3060", "ai"})


def _merged_display_name(storms: list[dict]) -> str:
    """
    Select the best display name from a group of merged storms.
    Prefers longer, more specific names. Skips known pipeline noise stubs.
    """
    candidates = [
        s for s in sorted(storms, key=lambda x: -x.get("event_count", 0))
        if len((s.get("name") or "").strip()) > 8
        and (s.get("name") or "").strip().lower() not in _NOISE_NAMES
    ]
    if candidates:
        return max(candidates, key=lambda s: len(s.get("name", ""))).get("name", "")
    # All names are noise stubs — fall back to highest event_count
    return max(storms, key=lambda s: s.get("event_count", 0)).get("name", "")


def _merge_storm_group(storms: list[dict]) -> dict:
    """
    Collapse a group of near-duplicate storms into one display object.

    Primary storm (highest event_count) provides base attributes.
    Event counts are summed. All actor references are unioned.
    Adds merge_count, merged_from, raw_titles for debugging and UI hints.
    """
    if len(storms) == 1:
        merged = dict(storms[0])
        merged["merge_count"] = 1
        merged["merged_from"] = [storms[0].get("id", "")]
        merged["raw_titles"]  = [storms[0].get("name", "")]
        return merged

    primary = max(storms, key=lambda s: s.get("event_count", 0))
    merged  = dict(primary)

    # Aggregate event count
    merged["event_count"] = sum(s.get("event_count", 0) for s in storms)

    # Best display name (longest non-noise candidate)
    merged["name"] = _merged_display_name(storms)

    # Best summary: longest non-noisy one, from highest event_count storm first
    summaries = [
        s.get("summary", "")
        for s in sorted(storms, key=lambda x: -x.get("event_count", 0))
        if s.get("summary") and "high semantic drift" not in s.get("summary", "")
    ]
    merged["summary"] = max(summaries, key=len) if summaries else primary.get("summary")

    # Union all actor references across merged storms
    merged["actors"] = sorted({a for s in storms for a in (s.get("actors") or [])})

    # Merge metadata
    n = len(storms)
    merged["id"]          = f"{primary.get('id', 'unknown')}_m{n}"
    merged["merge_count"] = n
    merged["merged_from"] = [s.get("id", "") for s in storms]
    merged["raw_titles"]  = [s.get("name", "") for s in storms]

    return merged


def dedupe_thread_storms(storms: list[dict], threshold: float = 0.4) -> list[dict]:
    """
    Deduplicate near-duplicate child storms within a single thread.

    Greedy grouping: processes storms in descending event_count order. Each storm
    anchors a group; later storms with the same actor and sufficient concept
    similarity are folded into it.

    Only merges within same actor. Never merges across actors.
    threshold=0.4 is conservative: Jaccard >= 0.4 required (or exact name match).
    """
    if len(storms) <= 1:
        result = []
        for s in storms:
            ms = dict(s)
            ms["merge_count"] = 1
            ms["merged_from"] = [s.get("id", "")]
            ms["raw_titles"]  = [s.get("name", "")]
            result.append(ms)
        return result

    ordered = sorted(storms, key=lambda s: -s.get("event_count", 0))
    groups: list[list[dict]] = []
    used:   set[int]         = set()

    for i, anchor in enumerate(ordered):
        if i in used:
            continue
        group = [anchor]
        for j in range(i + 1, len(ordered)):
            if j in used:
                continue
            if _are_merge_candidates(anchor, ordered[j], threshold):
                group.append(ordered[j])
                used.add(j)
        used.add(i)
        groups.append(group)

    result = [_merge_storm_group(g) for g in groups]
    result.sort(key=lambda s: -s.get("event_count", 0))
    return result


# ── Aggregate thread metrics ───────────────────────────────────────────────────

def compute_thread_metrics(storms: list[dict]) -> dict:
    intensities = [s["intensity"] for s in storms if s.get("intensity") is not None]
    pressures   = [s["pressure_score"] for s in storms if s.get("pressure_score") is not None]
    return {
        "total_event_count": sum(s.get("event_count", 0) for s in storms),
        "avg_recency":       round(sum(intensities) / len(intensities), 3) if intensities else None,
        "pressure_score":    round(max(pressures), 3) if pressures else None,
    }


# ── Phase normalization ────────────────────────────────────────────────────────

def build_thread_phases(lineage: dict) -> list[dict]:
    return [
        {
            "name":       p.get("name"),
            "lifecycle":  PHASE_SIGNAL_TO_LIFECYCLE.get(p.get("signal", ""), "unknown"),
            "signal_raw": p.get("signal"),
            "date_range": p.get("date_range"),
            "key_actors": p.get("key_actors", []),
        }
        for p in lineage.get("phases", [])
    ]


# ── Thread object assembler ────────────────────────────────────────────────────

def _assemble_thread(
    thread_id:        str,
    name:             str,
    name_source:      str,
    summary:          str | None,
    actors:           list[str],
    storm_actors:     list[str],
    dominant_actors:  list[str],
    supporting_actors:list[str],
    phases:           list[dict],
    storms:           list[dict],
    lineage_id:       str | None,
    narrative_type:   str | None,
    is_standalone:    bool,
    coherence:        str,
    grouping_reason:  str,
) -> dict:
    """Core thread assembler. All builders go through here."""
    lifecycle, lifecycle_raw   = derive_thread_lifecycle([s["lifecycle_stage"] for s in storms])
    price_status, price_label  = derive_thread_price_status(storms)
    metrics                    = compute_thread_metrics(storms)

    return {
        "id":              thread_id,
        "name":            name,
        "name_source":     name_source,    # how the name was derived
        "summary":         summary,
        "narrative_type":  narrative_type,
        "lineage_label":   lineage_id,
        "is_standalone":   is_standalone,
        # Coherence — simple heuristic (high/medium/low); see comments in compute_coherence
        "coherence":       coherence,
        "grouping_reason": grouping_reason,
        # Actors
        "actors":           actors,         # full lineage cast (may include untracked actors)
        "storm_actors":     storm_actors,   # actors with actual storm evidence
        "dominant_actors":  dominant_actors,   # top actors by event count
        "supporting_actors":supporting_actors, # remaining actors with storm evidence
        "phases":          phases,
        # Lifecycle — 5-value; derived from actor-level proxy stages (heuristic)
        "lifecycle_stage":     lifecycle,
        "lifecycle_stage_raw": lifecycle_raw,
        # Price status — 6-value; derived from leaderboard actor states (heuristic)
        "price_status":        price_status,
        "price_status_label":  price_label,
        # Aggregate metrics
        "total_event_count": metrics["total_event_count"],
        "avg_recency":       metrics["avg_recency"],
        "pressure_score":    metrics["pressure_score"],
        "storm_count":       len(storms),
        "storms":            storms,
    }


# ── Lineage thread builder ─────────────────────────────────────────────────────

def build_lineage_thread(lineage_id: str, lineage: dict, storms: list[dict]) -> dict:
    """Thread from a named lineage record."""
    storms_sorted  = sorted(storms, key=storm_sort_key)
    storms_deduped = dedupe_thread_storms(storms_sorted)

    canonical_name   = lineage.get("canonical_name") or lineage.get("original_label") or lineage_id
    name, name_src   = derive_thread_name(canonical_name, storms_deduped)

    storm_actors     = sorted({a for s in storms_deduped for a in s.get("actors", [])})
    dominant, supporting = compute_actor_split(storms_deduped)
    coherence, reason    = compute_coherence(storms_deduped, lineage_id, is_standalone=False)

    merged_count = sum(s.get("merge_count", 1) for s in storms_deduped if s.get("merge_count", 1) > 1)
    if merged_count:
        print(f"  [dedup] {lineage_id}: {len(storms_sorted)} → {len(storms_deduped)} storms ({merged_count} merged)")

    return _assemble_thread(
        thread_id         = lineage_id,
        name              = name,
        name_source       = name_src,
        summary           = lineage.get("summary"),
        actors            = lineage.get("actors", []),
        storm_actors      = storm_actors,
        dominant_actors   = dominant,
        supporting_actors = supporting,
        phases            = build_thread_phases(lineage),
        storms            = storms_deduped,
        lineage_id        = lineage_id,
        narrative_type    = lineage.get("narrative_type"),
        is_standalone     = False,
        coherence         = coherence,
        grouping_reason   = reason,
    )


# ── Standalone actor thread builder ───────────────────────────────────────────

def build_actor_thread(actor: str, storms: list[dict]) -> dict:
    """
    Fallback thread for a single actor with no lineage match.

    Conservative: does not merge across actors, does not invent concepts.
    Uses the most event-dense storm's (normalized) title as thread name.

    Honest limitations: no lineage_label, no phases, no lineage summary.
    """
    storms_sorted  = sorted(storms, key=storm_sort_key)
    storms_deduped = dedupe_thread_storms(storms_sorted)

    # Use representative storm (highest event count after dedup) for the thread title
    rep            = max(storms_deduped, key=lambda s: s.get("event_count", 0))
    rep_name       = rep.get("name", actor)  # storm name already normalized at this point
    actor_display  = ACTOR_DISPLAY_NAMES.get(actor, actor)

    # Avoid duplicating the ticker when the name already references the actor
    name_lower_check = rep_name.lower()
    mentions_actor   = (
        actor.lower() in name_lower_check
        or actor_display.lower() in name_lower_check
    )
    thread_name = rep_name if mentions_actor else f"{actor} — {rep_name}"

    coherence, reason    = compute_coherence(storms_deduped, lineage_id=None, is_standalone=True)
    dominant, supporting = compute_actor_split(storms_deduped)
    naming_method = "singleton" if len(storms_deduped) == 1 else "actor_fallback"

    return _assemble_thread(
        thread_id         = f"standalone_{actor}",
        name              = thread_name,
        name_source       = naming_method,
        summary           = None,
        actors            = [actor],
        storm_actors      = [actor],
        dominant_actors   = dominant,
        supporting_actors = supporting,
        phases            = [],
        storms            = storms_deduped,
        lineage_id        = None,
        narrative_type    = None,
        is_standalone     = True,
        coherence         = coherence,
        grouping_reason   = reason,
    )


# ── Thread sort key ────────────────────────────────────────────────────────────

def thread_sort_key(t: dict) -> tuple:
    """
    Named threads before standalone.
    Within each group: lifecycle priority → total event count desc → recency desc.
    """
    return (
        1 if t.get("is_standalone") else 0,
        THREAD_STAGE_PRIORITY.get(t["lifecycle_stage"], 4),
        -(t.get("total_event_count") or 0),
        -(t.get("avg_recency") or 0.0),
        -t.get("storm_count", 0),
    )


# ── System meta ────────────────────────────────────────────────────────────────

def compute_thread_meta(threads: list[dict]) -> dict:
    named      = [t for t in threads if not t.get("is_standalone")]
    standalone = [t for t in threads if t.get("is_standalone")]

    stage_counts = Counter(t["lifecycle_stage"] for t in named)
    price_counts = Counter(
        t["price_status"] for t in named
        if t["price_status"] not in ("mixed", "unknown", None)
    )
    dominant = max(named, key=lambda t: t.get("total_event_count", 0)) if named else None

    return {
        "named_thread_count":      len(named),
        "standalone_thread_count": len(standalone),
        "storm_count":             sum(t["storm_count"] for t in threads),
        "stage_counts":            dict(stage_counts),
        "price_counts":            dict(price_counts),
        "dominant_thread":         dominant["name"] if dominant else None,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main(min_events: int = 5, limit: int = 60) -> None:
    print("Loading source data...")

    summaries    = load_jsonl(SUMMARIES_FILE)
    trajectories = load_jsonl(TRAJECTORIES_FILE)
    pressure     = load_jsonl(PRESSURE_FILE)
    lineages     = load_json(LINEAGES_FILE) or {}
    leadership   = load_json(LEADERSHIP_FILE) or []
    prop_chains  = load_json(PROP_FILE) or []
    actors_raw   = load_json(ACTORS_JSON)

    print(f"  Summaries:   {len(summaries)}")
    print(f"  Trajectories:{len(trajectories)}")
    print(f"  Pressure:    {len(pressure)}")
    print(f"  Lineages:    {len(lineages)}")

    pressure_map   = build_pressure_by_storm(pressure)
    traj_map       = build_trajectory_by_actor(trajectories)
    leadership_map = build_leadership_by_actor(leadership)
    lineage_index  = build_lineage_index(lineages)
    board_state    = build_actor_board_state(actors_raw)
    prop_partners  = build_propagation_partners(prop_chains)

    # Deduplicate summaries by storm_id (keep highest event_count)
    seen_ids: dict[str, dict] = {}
    for s in summaries:
        sid = s.get("storm_id", "")
        if not sid:
            continue
        if sid not in seen_ids or s.get("event_count", 0) > seen_ids[sid].get("event_count", 0):
            seen_ids[sid] = s
    summaries = list(seen_ids.values())
    print(f"  After storm_id dedup: {len(summaries)}")

    usable = [
        s for s in summaries
        if s.get("event_count", 0) >= min_events
        and (s.get("actors") or s.get("actor"))
    ]
    print(f"\nUsable summaries (event_count >= {min_events}): {len(usable)}")

    # Build storm objects
    all_storms: list[dict] = []
    for summary in usable:
        try:
            obj = build_storm_object(
                summary, pressure_map, traj_map, leadership_map,
                lineages, lineage_index, board_state, prop_partners
            )
            all_storms.append(obj)
        except Exception as e:
            print(f"  [WARN] skipped {summary.get('storm_id', '?')}: {e}")

    # Sort globally and cap at 3 per actor
    all_storms.sort(key=storm_sort_key)
    actor_seen: dict[str, int] = defaultdict(int)
    capped: list[dict] = []
    for s in all_storms:
        if actor_seen[s["actor"]] < 3:
            capped.append(s)
            actor_seen[s["actor"]] += 1
    all_storms = capped[:limit]
    print(f"After per-actor cap (limit={limit}): {len(all_storms)} storms")

    # Post-process storm display names: normalize heuristic pipeline noise
    # LLM-named storms are unchanged by normalize_storm_title.
    # This runs after capping so only displayed storms are touched.
    for storm in all_storms:
        storm["name"] = normalize_storm_title(
            storm.get("name", ""),
            storm.get("actor", ""),
            storm.get("display_source", "heuristic"),
        )

    # Group: primary lineage → per-actor fallback
    thread_storms: dict[str, list[dict]] = defaultdict(list)
    actor_storms:  dict[str, list[dict]] = defaultdict(list)

    for storm in all_storms:
        actor       = storm["actor"]
        lineage_ids = lineage_index.get(actor, [])
        if lineage_ids:
            thread_storms[lineage_ids[0]].append(storm)
        else:
            actor_storms[actor].append(storm)

    # Build named threads
    named_threads: list[dict] = []
    for lineage_id, storms in thread_storms.items():
        if lineage_id not in lineages:
            for s in storms:
                actor_storms[s["actor"]].append(s)
            continue
        named_threads.append(build_lineage_thread(lineage_id, lineages[lineage_id], storms))

    # Build standalone actor threads
    standalone_threads: list[dict] = []
    for actor, storms in actor_storms.items():
        standalone_threads.append(build_actor_thread(actor, storms))

    named_threads.sort(key=thread_sort_key)
    standalone_threads.sort(key=thread_sort_key)
    threads = named_threads + standalone_threads

    meta   = compute_thread_meta(threads)
    output = {"date": str(date.today()), "meta": meta, "threads": threads}

    OUTPUT_FILE.write_text(json.dumps(output, indent=2))

    print(f"\nWrote {len(threads)} threads → {OUTPUT_FILE}")
    print(f"  Named: {meta['named_thread_count']}  |  Standalone: {meta['standalone_thread_count']}  |  Storms: {meta['storm_count']}")

    print("\nNamed threads:")
    for t in named_threads:
        p = f"{t['pressure_score']:.2f}" if t["pressure_score"] is not None else "n/a"
        print(
            f"  [{t['coherence']:6}] [{t['lifecycle_stage']:12s}] {t['name'][:50]:50s} | "
            f"p={p} | {t['storm_count']} storms"
        )
        print(f"           src={t['name_source']} | {t['grouping_reason'][:70]}")

    if standalone_threads:
        print(f"\nStandalone threads ({len(standalone_threads)}):")
        for t in standalone_threads[:8]:
            print(f"  [{t['coherence']:6}] [{t['lifecycle_stage']:12s}] {t['name'][:55]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-events", type=int, default=5)
    parser.add_argument("--limit",      type=int, default=60)
    args = parser.parse_args()
    main(min_events=args.min_events, limit=args.limit)
