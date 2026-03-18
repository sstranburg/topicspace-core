"""
Strategic watchlist: joins narrative pressure with leadership roles
to identify the most important narratives to monitor.
"""

ROLE_WEIGHT = {
    'leader': 1.00,
    'amplifier': 0.85,
    'bridge': 0.90,
    'receiver': 0.70,
    'insufficient_data': 0.40,
    'unknown': 0.40,
}

SHIFT_BONUS = {
    'thematic_shift': 0.10,
    'mixed_shift': 0.05,
    'market_noise_shift': -0.10,
    'stable': 0.00,
    'unclear': 0.00,
}


def build_pressure_leadership_records(pressure_records, leadership_map):
    """Join pressure records with leadership roles and compute strategic scores.

    Args:
        pressure_records: list of dicts from narrative_pressure.jsonl
        leadership_map: dict of actor -> leadership record

    Returns:
        list of enriched watchlist records
    """
    records = []
    for pr in pressure_records:
        actor = pr.get('actor', '')
        lead = leadership_map.get(actor, {})
        role = lead.get('role', 'unknown')
        shift_type = pr.get('shift_type', 'unclear')
        num_actors = pr.get('num_unique_actors', 1) or 1
        pressure_score = pr.get('pressure_score', 0)
        event_count = pr.get('event_count', 0)

        # Strategic score
        ecosystem_bonus = min(num_actors / 5.0, 1.0) * 0.10
        shift_mod = SHIFT_BONUS.get(shift_type, 0.0)
        raw = (
            0.70 * pressure_score +
            0.20 * ROLE_WEIGHT.get(role, 0.40) +
            0.10 * ecosystem_bonus
        ) + shift_mod
        strategic_score = min(max(raw, 0.0), 1.0)

        # Watch category
        pressure_level = pr.get('pressure_level', 'low')
        if pressure_level == 'high' and role in ('leader', 'bridge', 'amplifier'):
            watch_category = 'priority_watch'
        elif pressure_level in ('high', 'building') and strategic_score >= 0.55:
            watch_category = 'monitor_closely'
        else:
            watch_category = 'lower_priority'

        records.append({
            'storm_id': pr.get('storm_id', ''),
            'label': pr.get('label', ''),
            'actor': actor,
            'state': pr.get('state', 'unknown'),
            'pressure_score': pressure_score,
            'pressure_level': pressure_level,
            'role': role,
            'shift_type': shift_type,
            'event_count': event_count,
            'num_unique_actors': num_actors,
            'domain_phrases': pr.get('domain_phrases', []),
            'strategic_score': round(strategic_score, 3),
            'watch_category': watch_category,
            'watch_interpretation': interpret_watchlist_record({
                'pressure_level': pressure_level,
                'role': role,
                'shift_type': shift_type,
                'state': pr.get('state', 'unknown'),
            }),
        })

    return records


def interpret_watchlist_record(rec):
    """Generate concise human-readable interpretation."""
    level = rec.get('pressure_level', 'low')
    role = rec.get('role', 'unknown')
    shift = rec.get('shift_type', 'unclear')
    state = rec.get('state', 'unknown')

    role_label = role.replace('_', ' ')
    article = 'an' if role_label[0] in 'aeiou' else 'a'

    if level == 'high':
        base = f"High-pressure narrative led by {article} {role_label} actor"
        if role in ('amplifier', 'bridge'):
            base += "; may broaden into a larger ecosystem discussion."
        elif role == 'leader':
            base += "; likely originating new narrative flows."
        elif role == 'receiver':
            base += "; downstream absorption of upstream momentum."
        else:
            base += "."
    elif level == 'building':
        base = f"Building narrative associated with {article} {role_label} actor"
        if role == 'bridge':
            base += "; worth monitoring for cross-actor spread."
        elif role == 'leader':
            base += "; early-stage narrative that may gain traction."
        else:
            base += "; watch for acceleration."
    else:
        if state == 'fading':
            return "Low-pressure narrative with declining attention."
        return f"Low-pressure narrative; {role_label} actor with limited current momentum."

    if shift == 'thematic_shift':
        base = base.rstrip('.') + " with genuine thematic evolution."
    elif shift == 'market_noise_shift':
        base = base.rstrip('.') + ", though driven primarily by market noise."

    return base


def filter_watchlist(records):
    """Remove noise and low-quality entries from the watchlist."""
    filtered = []
    for r in records:
        # Skip market noise unless high pressure
        if r['shift_type'] == 'market_noise_shift' and r['pressure_level'] != 'high':
            continue
        # Skip insufficient data actors
        if r['role'] == 'insufficient_data':
            continue
        filtered.append(r)
    return filtered


def dedupe_watchlist(records):
    """Merge same-actor storms that share identical pressure scores.

    Thin narrative fragments from the same trajectory get collapsed into
    the single best entry (highest event count, then strategic score).
    """
    from collections import defaultdict
    groups = defaultdict(list)
    for r in records:
        key = (r['actor'], round(r['pressure_score'], 3))
        groups[key].append(r)

    deduped = []
    for key, group in groups.items():
        best = max(group, key=lambda r: (r['event_count'], r['strategic_score']))
        if len(group) > 1:
            best = dict(best)
            total_events = sum(r['event_count'] for r in group)
            best['event_count'] = total_events
            best['merged_count'] = len(group)
        deduped.append(best)
    return deduped
