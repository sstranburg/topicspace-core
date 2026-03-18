"""
Narrative Registry — persistent narrative tracking across report runs.

Matches lineages to existing narratives using:
    0.55 * cosine(lineage_centroid, narrative_centroid)
  + 0.25 * theme_anchor_overlap
  + 0.20 * actor_overlap

Threshold: >= 0.68  → attach to existing narrative
           <  0.68  → create new narrative

Constraints:
  - Only consider narratives last seen within 45 days (recency window)
  - Never match if actor_overlap == 0 AND theme_anchor_overlap == 0

Persists to: data/narrative_registry.jsonl
"""

import json
import math
import uuid
from pathlib import Path
from datetime import datetime, timezone

MATCH_THRESHOLD   = 0.68
RECENCY_DAYS      = 45
REGISTRY_PATH     = Path(__file__).parent.parent / 'data' / 'narrative_registry.jsonl'


# ── similarity helpers ────────────────────────────────────────────────────────

def _cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    ma  = math.sqrt(sum(x * x for x in a))
    mb  = math.sqrt(sum(x * x for x in b))
    return dot / (ma * mb) if ma and mb else 0.0


def _jaccard_sets(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _theme_overlap(lineage_themes, narrative_themes):
    return _jaccard_sets(lineage_themes, narrative_themes)


def _actor_overlap(lineage_actors, narrative_actors):
    return _jaccard_sets(lineage_actors, narrative_actors)


def narrative_similarity(lineage_centroid, lineage_themes, lineage_actors,
                         narrative_centroid, narrative_themes, narrative_actors):
    cos   = _cosine(lineage_centroid, narrative_centroid)
    theme = _theme_overlap(lineage_themes, narrative_themes)
    actor = _actor_overlap(lineage_actors, narrative_actors)
    return round(0.55 * cos + 0.25 * theme + 0.20 * actor, 4)


# ── centroid helpers ──────────────────────────────────────────────────────────

def _mean_centroid(centroids):
    """Element-wise mean of a list of equal-length vectors."""
    if not centroids:
        return []
    n = len(centroids)
    return [sum(c[i] for c in centroids) / n for i in range(len(centroids[0]))]


def lineage_centroid(storms_in_lineage):
    """Average centroid of all storms in a lineage."""
    centroids = [s['centroid'] for s in storms_in_lineage if s.get('centroid')]
    return _mean_centroid(centroids)


def lineage_theme_anchors(storms_in_lineage):
    """Union of themes + domain_phrases across all storms in a lineage."""
    themes = set()
    for s in storms_in_lineage:
        themes.update(s.get('themes', []))
        themes.update(s.get('domain_phrases', []))
    return sorted(themes)


# ── registry I/O ─────────────────────────────────────────────────────────────

def _compress_centroid(vec):
    """Round centroid floats to 4 decimal places to reduce storage size."""
    return [round(x, 4) for x in vec] if vec else []


def load_registry(path=None):
    """
    Load existing narratives from JSONL.
    Reconstructs _centroid from persisted 'centroid' field.
    Marks entries missing centroid with centroid_missing=True.
    Returns (narratives, load_stats).
    """
    p = Path(path) if path else REGISTRY_PATH
    if not p.exists():
        return [], {'loaded': 0, 'with_centroid': 0, 'missing_centroid': 0}
    narratives = []
    n_with, n_missing = 0, 0
    with open(p) as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            persisted = record.get('centroid')
            if persisted:
                record['_centroid'] = [float(x) for x in persisted]
                record['centroid_missing'] = False
                n_with += 1
            else:
                record['_centroid'] = []  # cosine will be 0; theme/actor carry the match
                record['centroid_missing'] = True
                n_missing += 1
            narratives.append(record)
    stats = {'loaded': len(narratives), 'with_centroid': n_with, 'missing_centroid': n_missing}
    return narratives, stats


def save_registry(narratives, path=None):
    """Persist narratives to JSONL. Saves centroid as rounded floats."""
    p = Path(path) if path else REGISTRY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w') as f:
        for n in narratives:
            record = {k: v for k, v in n.items()
                      if k not in ('_centroid', 'centroid_missing')}
            record['centroid'] = _compress_centroid(n.get('_centroid', []))
            f.write(json.dumps(record) + '\n')


# ── core registry update ──────────────────────────────────────────────────────

def update_registry(lineage_summaries, all_storms, path=None):
    """
    Match each lineage to an existing narrative or create a new one.

    Parameters
    ----------
    lineage_summaries : list of lineage summary dicts (from group_into_lineages)
    all_storms        : list of all storm dicts (with centroid, themes, etc.)
    path              : optional override for registry file path

    Returns
    -------
    narratives        : updated list of narrative dicts
    match_log         : list of dicts describing each lineage → narrative decision
    """
    narratives, load_stats = load_registry(path)
    now = datetime.now(timezone.utc).isoformat()

    # Build storm lookup
    storm_by_id = {s['storm_id']: s for s in all_storms}

    match_log = []

    for lin in lineage_summaries:
        lin_id      = lin['lineage_id']
        lin_storms  = [storm_by_id[sid] for sid in lin['storm_ids'] if sid in storm_by_id]
        lin_centroid = lineage_centroid(lin_storms)
        lin_themes  = lineage_theme_anchors(lin_storms)
        lin_actors  = lin.get('lineage_actor_set', [])
        lin_gravity = lin.get('lineage_gravity_score', 0)
        lin_events  = lin.get('lineage_event_count', 0)
        lin_start   = lin.get('lineage_start_time', now)
        lin_latest  = lin.get('lineage_latest_time', now)

        # Max velocity across storms in this lineage
        lin_velocity = max(
            (storm_by_id[sid].get('velocity_score', 0) for sid in lin['storm_ids'] if sid in storm_by_id),
            default=0
        )

        # Find best-matching existing narrative within recency window
        best_score = 0.0
        best_idx   = None
        best_id    = None
        for idx, n in enumerate(narratives):
            # Recency filter: skip narratives not seen in the last RECENCY_DAYS days
            try:
                last_seen = datetime.fromisoformat(
                    n.get('latest_seen_timestamp', '').replace('Z', '+00:00')
                )
                age_days = (datetime.now(timezone.utc) - last_seen).days
                if age_days > RECENCY_DAYS:
                    continue
            except (ValueError, AttributeError):
                pass  # missing/malformed timestamp — allow through

            n_themes = n.get('theme_anchors', [])
            n_actors = n.get('actor_set', [])

            # Null-overlap guard: skip if nothing in common
            theme_ov = _theme_overlap(lin_themes, n_themes)
            actor_ov = _actor_overlap(lin_actors, n_actors)
            if theme_ov == 0.0 and actor_ov == 0.0:
                continue

            score = narrative_similarity(
                lin_centroid, lin_themes, lin_actors,
                n.get('_centroid', []), n_themes, n_actors
            )
            if score > best_score:
                best_score = score
                best_idx   = idx
                best_id    = n['narrative_id']

        if best_score >= MATCH_THRESHOLD and best_idx is not None:
            # Attach lineage to existing narrative
            n = narratives[best_idx]
            already_seen = lin_id in n.get('lineage_ids', [])
            if not already_seen:
                n.setdefault('lineage_ids', []).append(lin_id)
                # Only accumulate counts for lineages not previously recorded
                n['total_storm_count'] = n.get('total_storm_count', 0) + lin.get('lineage_storm_count', 0)
                n['total_event_count'] = n.get('total_event_count', 0) + lin_events
                # Update centroid as running mean only on new data
                if lin_centroid and n.get('_centroid'):
                    n['_centroid'] = _mean_centroid([n['_centroid'], lin_centroid])
                elif lin_centroid:
                    n['_centroid'] = lin_centroid
            n['latest_seen_timestamp'] = max(n.get('latest_seen_timestamp', lin_latest), lin_latest)
            n['actor_set']             = sorted(set(n.get('actor_set', [])) | set(lin_actors))
            n['theme_anchors']         = sorted(set(n.get('theme_anchors', [])) | set(lin_themes))[:30]
            n['max_gravity_score']     = max(n.get('max_gravity_score', 0), lin_gravity)
            n['max_velocity_score']    = max(n.get('max_velocity_score', 0), lin_velocity)
            # Inflection: previous run velocity negative, current positive
            prev_velocity = n.get('last_velocity_score')
            inflection = (
                prev_velocity is not None
                and prev_velocity < 0
                and lin_velocity > 0
            )
            if inflection:
                n['velocity_inflection']    = True
                n['inflection_timestamp']   = now
                n['velocity_before']        = round(prev_velocity, 4)
                n['velocity_after']         = round(lin_velocity, 4)
            elif not inflection and n.get('velocity_inflection'):
                # Clear stale inflection flag once velocity is no longer crossing zero
                n['velocity_inflection'] = False
            n['last_velocity_score'] = round(lin_velocity, 4)
            action = 'matched'
        else:
            # Create new narrative
            narrative_id = f"narrative_{uuid.uuid4().hex[:8]}"
            n = {
                'narrative_id':           narrative_id,
                'narrative_label':        _derive_label(lin_storms, lin_actors),
                'first_seen_timestamp':   lin_start,
                'latest_seen_timestamp':  lin_latest,
                'total_storm_count':      lin.get('lineage_storm_count', 0),
                'total_event_count':      lin_events,
                'actor_set':              sorted(lin_actors),
                'theme_anchors':          lin_themes[:30],
                'max_gravity_score':      round(lin_gravity, 4),
                'max_velocity_score':     round(lin_velocity, 4),
                'last_velocity_score':    round(lin_velocity, 4),
                'velocity_inflection':    False,
                'inflection_timestamp':   None,
                'velocity_before':        None,
                'velocity_after':         None,
                'lineage_ids':            [lin_id],
                '_centroid':              lin_centroid,
            }
            narratives.append(n)
            action = 'created'
            inflection = False

        match_log.append({
            'lineage_id':              lin_id,
            'action':                  action,
            'narrative_id':            n['narrative_id'],
            'best_match_narrative_id': best_id,
            'best_match_score':        round(best_score, 4),
            'matched_or_created':      action,
            'storm_count':             lin.get('lineage_storm_count', 0),
            'already_seen':            (action == 'matched' and already_seen) if action == 'matched' else False,
            'velocity_inflection':     inflection,
            'velocity_before':         round(prev_velocity, 4) if (action == 'matched' and prev_velocity is not None) else None,
            'velocity_after':          round(lin_velocity, 4),
        })

    save_registry(narratives, path)
    return narratives, match_log, load_stats


def _derive_label(storms, actors):
    """Best-effort label from storm headlines and actors."""
    for s in storms:
        headline = s.get('display_headline') or s.get('headline') or s.get('llm_headline', '')
        if headline:
            actor_str = ' & '.join(actors[:2]) if actors else ''
            suffix = f' [{actor_str}]' if actor_str else ''
            return headline[:60].rsplit(' ', 1)[0] + suffix
    return f"Narrative around {', '.join(actors[:3])}" if actors else 'Unnamed narrative'
