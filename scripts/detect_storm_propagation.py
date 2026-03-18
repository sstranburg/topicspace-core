#!/usr/bin/env python3
"""
Detect storm propagation across actors.
"""
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from storm_propagation import (
    detect_propagation_edges,
    build_actor_propagation_graph,
    detect_propagation_chains,
    compute_actor_roles,
    interpret_propagation,
    detect_semantic_pathways,
    aggregate_lane_transitions,
    compute_actor_lead_lag
)


def load_storms(path: Path) -> list:
    """Load storms from JSONL file."""
    storms = []
    with open(path, 'r') as f:
        for line in f:
            if line.strip():
                storms.append(json.loads(line))
    return storms


def main():
    # Paths
    base_dir = Path(__file__).parent.parent
    storms_path = base_dir / 'data' / 'derived' / 'actor_storms.jsonl'
    summaries_path = base_dir / 'data' / 'derived' / 'actor_storm_summaries.jsonl'
    output_dir = base_dir / 'data' / 'derived'
    
    trajectories_path = base_dir / 'data' / 'derived' / 'storm_trajectories.jsonl'

    # Load storms and summaries
    print("Storm Propagation Detection")
    print("---------------------------")
    storms = load_storms(storms_path)
    summaries = load_storms(summaries_path)

    # Build actor → dominant state from trajectories (highest total_events wins)
    actor_state_map: dict = {}
    if trajectories_path.exists():
        trajs = load_storms(trajectories_path)
        for t in trajs:
            actor = t.get('actor')
            if not actor:
                continue
            existing = actor_state_map.get(actor)
            if existing is None or t.get('total_events', 0) > existing[1]:
                actor_state_map[actor] = (t['state'], t.get('total_events', 0))
        actor_state_map = {a: state for a, (state, _) in actor_state_map.items()}

    # Create lookup for summaries
    summary_map = {s['storm_id']: s for s in summaries}

    # Merge themes from summaries and state from trajectories into storms
    for storm in storms:
        storm.setdefault('state', actor_state_map.get(storm.get('actor'), 'unknown'))
        if storm['storm_id'] in summary_map:
            summary = summary_map[storm['storm_id']]
            storm['themes'] = summary.get('themes', [])
            storm['bigrams'] = summary.get('bigrams', [])
            storm['domain_phrases'] = summary.get('domain_phrases', [])
            storm['entity_actions'] = summary.get('entity_actions', [])
    
    print(f"Storms loaded: {len(storms)}")
    
    # Detect propagation edges
    edges = detect_propagation_edges(storms)
    print(f"Accepted propagation edges: {len(edges)}")
    
    # Build actor-level graph
    actor_graph = build_actor_propagation_graph(edges)
    print(f"Actor-level edges: {len(actor_graph)}")
    
    # Detect chains
    chains = detect_propagation_chains(edges)
    print(f"Propagation chains: {len(chains)}")
    
    # Detect semantic pathways
    pathways = detect_semantic_pathways(edges)
    print(f"Semantic pathways: {len(pathways)}")
    
    # Save storm-level propagation
    propagation_path = output_dir / 'storm_propagation.jsonl'
    with open(propagation_path, 'w') as f:
        for edge in edges:
            f.write(json.dumps(edge) + '\n')
    
    # Save actor-level graph
    graph_path = output_dir / 'actor_propagation_graph.json'
    with open(graph_path, 'w') as f:
        json.dump(actor_graph, f, indent=2)
    
    # Save chains
    chains_path = output_dir / 'propagation_chains.json'
    with open(chains_path, 'w') as f:
        json.dump(chains, f, indent=2)
    
    # Save semantic pathways
    pathways_path = output_dir / 'semantic_pathways.json'
    with open(pathways_path, 'w') as f:
        json.dump(pathways, f, indent=2)

    # Aggregate lane transitions
    lane_transitions = aggregate_lane_transitions(edges)
    transitions_path = output_dir / 'lane_transitions.json'
    with open(transitions_path, 'w') as f:
        json.dump(lane_transitions, f, indent=2)

    # Compute actor lead-lag
    actor_lead_lag = compute_actor_lead_lag(edges)
    lead_lag_path = output_dir / 'actor_lead_lag.json'
    with open(lead_lag_path, 'w') as f:
        json.dump(actor_lead_lag, f, indent=2)

    # Print top edges
    print("\nTop propagation edges:")
    sorted_edges = sorted(edges, key=lambda x: x['propagation_score'], reverse=True)
    for i, edge in enumerate(sorted_edges[:3], 1):
        themes_str = ', '.join(edge['shared_themes'][:2]) if edge['shared_themes'] else 'mixed'
        print(f"{i}. {edge['source_actor']} -> {edge['target_actor']} | "
              f"score {edge['propagation_score']:.2f} | "
              f"lag {edge['lag_days']}d | "
              f"themes: {themes_str}")

    # Print lane transition table
    print("\n=== LANE TRANSITIONS ===")
    if lane_transitions:
        print(f"  {'transition':<25} {'count':>5}  {'avg_lag_h':>9}  top actors")
        print(f"  {'-'*25} {'-'*5}  {'-'*9}  {'-'*30}")
        for t in lane_transitions:
            transition_label = f"{t['source_lane']} → {t['target_lane']}"
            actors_str = ', '.join(t['top_actors'])
            print(f"  {transition_label:<25} {t['count']:>5}  {t['avg_lag_hours']:>9.1f}  {actors_str}")
    else:
        print("  (no transitions detected)")

    # Print actor lead-lag table
    print("\n=== ACTOR LEAD-LAG ===")
    if actor_lead_lag:
        print(f"  {'source → target':<20} {'count':>5}  {'avg_lag_h':>9}  {'med_lag_h':>9}  lanes")
        print(f"  {'-'*20} {'-'*5}  {'-'*9}  {'-'*9}  {'-'*20}")
        for r in actor_lead_lag[:15]:
            pair = f"{r['source_actor']} → {r['target_actor']}"
            lanes = f"{r['source_lane']}→{r['target_lane']}"
            print(f"  {pair:<20} {r['count']:>5}  {r['mean_lag_hours']:>9.1f}  {r['median_lag_hours']:>9.1f}  {lanes}")
    else:
        print("  (no pairs with ≥5 edges)")

    print(f"\nArtifacts written to {output_dir}")


if __name__ == '__main__':
    main()
