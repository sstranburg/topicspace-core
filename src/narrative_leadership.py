"""
Narrative leadership analysis.
Classifies actors as leaders, amplifiers, bridges, or receivers
based on propagation chain positions and edge directions.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path


ROLES = ['leader', 'amplifier', 'bridge', 'receiver']


def compute_leadership(edges, chains):
    """Compute narrative leadership scores for all actors.
    
    Args:
        edges: list of propagation edge dicts (source_actor, target_actor, shared_themes)
        chains: list of chain dicts (actors, shared_theme_hint)
    
    Returns:
        list of actor leadership dicts
    """
    # Count chain positions
    early = Counter()
    middle = Counter()
    late = Counter()
    participated = Counter()

    for chain in chains:
        actors = chain['actors']
        for i, actor in enumerate(actors):
            participated[actor] += 1
            if i == 0:
                early[actor] += 1
            elif i == len(actors) - 1:
                late[actor] += 1
            else:
                middle[actor] += 1

    # Count edge directions
    outgoing = Counter()
    incoming = Counter()
    for edge in edges:
        outgoing[edge['source_actor']] += 1
        incoming[edge['target_actor']] += 1

    all_actors = set(participated.keys())
    if not all_actors:
        return []

    max_chains = max(participated.values())
    total_chains = sum(participated.values()) or 1

    results = []
    for actor in sorted(all_actors):
        cp = participated[actor]
        if cp == 0:
            continue

        early_ratio = early[actor] / cp
        middle_ratio = middle[actor] / cp
        late_ratio = late[actor] / cp
        chains_norm = cp / max_chains

        total_edges = outgoing[actor] + incoming[actor]
        out_ratio = outgoing[actor] / total_edges if total_edges else 0.5
        in_ratio = incoming[actor] / total_edges if total_edges else 0.5

        leader_score = 0.5 * early_ratio + 0.3 * out_ratio + 0.2 * chains_norm
        amplifier_score = 0.6 * middle_ratio + 0.4 * chains_norm
        bridge_score = 1.0 - abs(in_ratio - out_ratio)
        receiver_score = 0.6 * late_ratio + 0.4 * in_ratio

        scores = {
            'leader': round(leader_score, 3),
            'amplifier': round(amplifier_score, 3),
            'bridge': round(bridge_score, 3),
            'receiver': round(receiver_score, 3),
        }

        if cp < 3:
            role = 'insufficient_data'
        else:
            role = max(scores, key=scores.get)

        centrality = (outgoing[actor] + incoming[actor]) / total_chains

        results.append({
            'actor': actor,
            'role': role,
            **{f'{k}_score': v for k, v in scores.items()},
            'chains_participated': cp,
            'outgoing_edges': outgoing[actor],
            'incoming_edges': incoming[actor],
            'centrality_score': round(centrality, 4),
        })

    return results


def compute_theme_leadership(edges, chains):
    """Compute leadership roles per theme.
    
    Returns list of dicts with theme and role assignments.
    """
    # Group chains by theme
    theme_chains = defaultdict(list)
    for chain in chains:
        theme = chain.get('shared_theme_hint', 'mixed')
        if theme and theme != 'mixed':
            theme_chains[theme].append(chain)

    # Group edges by shared themes
    theme_edges = defaultdict(list)
    for edge in edges:
        for theme in edge.get('shared_themes', []):
            theme_edges[theme].append(edge)

    results = []
    for theme in sorted(set(list(theme_chains.keys()) + list(theme_edges.keys()))):
        t_chains = theme_chains.get(theme, [])
        t_edges = theme_edges.get(theme, [])
        if not t_chains and not t_edges:
            continue

        actors = compute_leadership(t_edges, t_chains)
        if not actors:
            continue

        role_map = {}
        for a in actors:
            role_map[a['role']] = role_map.get(a['role']) or a['actor']

        results.append({
            'theme': theme,
            'leader': role_map.get('leader', 'N/A'),
            'amplifier': role_map.get('amplifier', 'N/A'),
            'bridge': role_map.get('bridge', 'N/A'),
            'receiver': role_map.get('receiver', 'N/A'),
            'actors_analyzed': len(actors),
        })

    return results


def generate_role_description(actor, role, scores):
    """Generate a one-line description for an actor's role."""
    descs = {
        'leader': f"{actor} frequently originates narrative flows across the ecosystem.",
        'amplifier': f"{actor} tends to expand narratives into broader discussions.",
        'bridge': f"{actor} connects different narrative streams, balancing incoming and outgoing flows.",
        'receiver': f"{actor} typically appears downstream as narratives propagate through the ecosystem.",
    }
    return descs.get(role, f"{actor} participates in narrative propagation.")
