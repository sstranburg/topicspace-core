"""
Narrative Lead-Lag Alpha.

Measures which actors tend to appear early in important propagating narratives.

Positional weights by hop order: 1st=1.0, 2nd=0.7, 3rd=0.4, 4th+=0.2

Per-chain contribution for each actor occurrence:
    positional_weight * chain_score_normalized * storm_gravity_score

chain_score_normalized = chain mean_score normalized 0-1 across all chains
storm_gravity_score    = max gravity score across the actor's storms
"""

from collections import defaultdict

POSITIONAL_WEIGHTS = [1.0, 0.7, 0.4, 0.2]


def _pos_weight(position):
    """0-indexed position → weight."""
    return POSITIONAL_WEIGHTS[min(position, len(POSITIONAL_WEIGHTS) - 1)]


def _interpret(lead_count, early_count, late_count, total, mean_pos):
    """Assign interpretation label from positional statistics."""
    if total == 0:
        return 'downstream_receiver'
    lead_rate  = lead_count / total
    early_rate = early_count / total
    late_rate  = late_count / total
    if lead_rate >= 0.40:
        return 'alpha_leader'
    if early_rate >= 0.50:
        return 'early_amplifier'
    if late_rate >= 0.50:
        return 'downstream_receiver'
    return 'mid_chain_distributor'


def compute_lead_lag_alpha(propagation_chains, actor_gravity_map):
    """
    Compute lead-lag alpha scores for each actor.

    Parameters
    ----------
    propagation_chains : list of chain dicts with 'actors', 'mean_score'
    actor_gravity_map  : dict mapping actor → max gravity score across their storms

    Returns
    -------
    list of per-actor result dicts, sorted by lead_lag_alpha_normalized descending
    """
    if not propagation_chains:
        return []

    # Normalize chain scores to 0-1
    scores = [c.get('mean_score', 0) for c in propagation_chains]
    min_s, max_s = min(scores), max(scores)
    score_range = max_s - min_s if max_s > min_s else 1.0

    def norm_score(s):
        return (s - min_s) / score_range

    # Accumulate per-actor stats
    raw_alpha   = defaultdict(float)
    lead_count  = defaultdict(int)
    early_count = defaultdict(int)
    late_count  = defaultdict(int)
    positions   = defaultdict(list)
    chain_count = defaultdict(int)

    for chain in propagation_chains:
        actors = chain.get('actors', [])
        if not actors:
            continue
        cs_norm = norm_score(chain.get('mean_score', 0))
        last_pos = len(actors) - 1

        for pos, actor in enumerate(actors):
            gravity = actor_gravity_map.get(actor, 0.0)
            pw = _pos_weight(pos)
            raw_alpha[actor]  += pw * cs_norm * gravity
            positions[actor].append(pos)
            chain_count[actor] += 1
            if pos == 0:
                lead_count[actor]  += 1
            if pos <= 1:
                early_count[actor] += 1
            if pos == last_pos:
                late_count[actor]  += 1

    # Collect all actors seen in chains
    all_actors = set(raw_alpha) | set(lead_count) | set(early_count)

    # Normalize alpha 0-1 across actors
    max_raw = max(raw_alpha.values(), default=1.0) or 1.0

    results = []
    for actor in all_actors:
        total  = chain_count[actor]
        pos_list = positions[actor]
        mean_pos = sum(pos_list) / len(pos_list) if pos_list else 0.0
        raw    = raw_alpha[actor]
        norm   = round(raw / max_raw, 4)
        lc     = lead_count[actor]
        ec     = early_count[actor]
        ltc    = late_count[actor]
        label  = _interpret(lc, ec, ltc, total, mean_pos)
        results.append({
            'actor':                      actor,
            'lead_lag_alpha_raw':         round(raw, 6),
            'lead_lag_alpha_normalized':  norm,
            'lead_count':                 lc,
            'early_count':                ec,
            'late_count':                 ltc,
            'chains_appeared':            total,
            'mean_chain_position':        round(mean_pos, 3),
            'interpretation':             label,
        })

    results.sort(key=lambda r: -r['lead_lag_alpha_normalized'])
    return results
