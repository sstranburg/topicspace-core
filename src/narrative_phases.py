"""
Narrative Macro Phase Generator.

Groups contiguous storm windows within a lineage into 4-8 macro phases using:
  - Cosine similarity on storm centroids  (thematic continuity)
  - Time gap guardrail                    (inactivity breaks)

Keeps micro-phase windows intact for propagation/lead-lag analysis.
Only compresses for report presentation.
"""
import math
from datetime import datetime, timezone
from collections import Counter
from typing import List, Dict, Optional

PHASE_THEME_THRESHOLD = 0.62   # below this → new phase
PHASE_TIME_GAP_DAYS   = 5      # gap > N days → new phase regardless of similarity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if (na and nb) else 0.0


def _parse_ts(s: dict) -> Optional[datetime]:
    raw = s.get('created_at', '')
    if not raw:
        return None
    raw = raw.rstrip('Z').replace('+00:00Z', '+00:00')
    if not raw.endswith('+00:00'):
        raw += '+00:00'
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _actors(s: dict) -> set:
    a = s.get('actor')
    return {a} if a else set(s.get('actors', []))


def _keywords(s: dict) -> List[str]:
    return (s.get('themes') or []) + (s.get('domain_phrases') or [])


def _actor_entropy(actor_counter: Counter) -> float:
    total = sum(actor_counter.values())
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in actor_counter.values() if c > 0)


# ---------------------------------------------------------------------------
# Phase label generation
# ---------------------------------------------------------------------------

def _phase_label(top_keywords: List[str], dominant_actors: List[str]) -> str:
    """Generate ≤4-word label: top keyword(s) + primary actor."""
    words = []
    seen = set()
    for kw in top_keywords:
        kw_clean = kw.replace('_', ' ').title()
        if kw_clean.lower() not in seen:
            words.append(kw_clean)
            seen.add(kw_clean.lower())
        if len(words) >= 2:
            break

    actor_hint = dominant_actors[0] if dominant_actors else ''
    if words and actor_hint:
        return f"{' '.join(words[:2])} — {actor_hint}"
    if words:
        return ' '.join(words[:3])
    return actor_hint or 'Unnamed Phase'


# ---------------------------------------------------------------------------
# Trend direction
# ---------------------------------------------------------------------------

def _trend(storms: List[dict], actor_traj_map: Dict[str, dict]) -> str:
    """Derive trend from storm states and actor trajectory momentum."""
    states = [s.get('state', 'unknown') for s in storms]
    state_counts = Counter(states)

    # Use actor trajectory momentum if available
    momenta = []
    for s in storms:
        for actor in _actors(s):
            traj = actor_traj_map.get(actor)
            if traj:
                m = traj.get('latest_momentum', 0) or 0
                momenta.append(m)

    if momenta:
        avg_momentum = sum(momenta) / len(momenta)
        if avg_momentum > 10:
            return 'growing'
        if avg_momentum < -10:
            return 'fading'

    # Fall back to state counts
    growing = state_counts.get('growing', 0)
    fading  = state_counts.get('fading', 0)
    stable  = state_counts.get('stable', 0)
    if growing > fading and growing > stable:
        return 'growing'
    if fading > growing and fading > stable:
        return 'fading'
    if stable >= growing and stable >= fading:
        return 'stable'
    return 'mixed'


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------

def compute_macro_phases(
    storms: List[dict],
    actor_traj_map: Optional[Dict[str, dict]] = None,
) -> List[dict]:
    """
    Group consecutive storm windows into macro phases.

    Parameters
    ----------
    storms          : list of storm dicts (must have 'centroid', 'created_at')
    actor_traj_map  : actor → trajectory dict (for momentum-based trend)

    Returns
    -------
    list of phase dicts, each containing:
      label, phase_start, phase_end, storm_count, total_events,
      dominant_actors, top_keywords, trend, storms,
      phase_gravity, phase_velocity, actor_entropy
    """
    if not storms:
        return []

    actor_traj_map = actor_traj_map or {}

    sorted_storms = sorted(
        storms,
        key=lambda s: (_parse_ts(s) or datetime.min.replace(tzinfo=timezone.utc))
    )

    phases: List[List[dict]] = []
    current: List[dict] = [sorted_storms[0]]

    for s in sorted_storms[1:]:
        prev = current[-1]
        ts_prev = _parse_ts(prev)
        ts_curr = _parse_ts(s)

        # Time gap check
        gap_days = (ts_curr - ts_prev).days if (ts_prev and ts_curr) else 0
        if gap_days > PHASE_TIME_GAP_DAYS:
            phases.append(current)
            current = [s]
            continue

        # Thematic similarity check using centroids
        centroid_prev = prev.get('centroid') or []
        centroid_curr = s.get('centroid') or []
        sim = _cosine(centroid_prev, centroid_curr)

        if sim < PHASE_THEME_THRESHOLD:
            phases.append(current)
            current = [s]
        else:
            current.append(s)

    phases.append(current)

    # Build phase summary objects
    result = []
    for i, ph_storms in enumerate(phases, 1):
        dates = [s.get('created_at', '')[:10] for s in ph_storms if s.get('created_at')]
        phase_start = min(dates) if dates else 'N/A'
        phase_end   = max(dates) if dates else 'N/A'

        all_actor_counts: Counter = Counter()
        for s in ph_storms:
            for a in _actors(s):
                all_actor_counts[a] += 1
        dominant_actors = [a for a, _ in all_actor_counts.most_common(4)]

        kw_counts: Counter = Counter()
        for s in ph_storms:
            for kw in _keywords(s):
                kw_counts[kw] += 1
        top_keywords = [kw for kw, _ in kw_counts.most_common(6)]

        label = _phase_label(top_keywords, dominant_actors)
        trend = _trend(ph_storms, actor_traj_map)

        total_events   = sum(s.get('event_count', 0) for s in ph_storms)
        gravity_scores = [s.get('gravity_score', 0) or 0 for s in ph_storms]
        phase_gravity  = sum(gravity_scores) / len(gravity_scores) if gravity_scores else 0.0

        momenta = []
        for s in ph_storms:
            for actor in _actors(s):
                traj = actor_traj_map.get(actor)
                if traj:
                    m = traj.get('latest_momentum', 0) or 0
                    momenta.append(m)
        phase_velocity = sum(momenta) / len(momenta) if momenta else 0.0

        entropy = _actor_entropy(all_actor_counts)

        result.append({
            'label':           label,
            'phase_number':    i,
            'phase_start':     phase_start,
            'phase_end':       phase_end,
            'storm_count':     len(ph_storms),
            'total_events':    total_events,
            'dominant_actors': dominant_actors,
            'top_keywords':    top_keywords,
            'trend':           trend,
            'phase_gravity':   round(phase_gravity, 4),
            'phase_velocity':  round(phase_velocity, 1),
            'actor_entropy':   round(entropy, 3),
            'storms':          ph_storms,
        })

    return result
