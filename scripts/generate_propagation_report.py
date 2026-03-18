#!/usr/bin/env python3
"""
Generate storm propagation report.
"""
import json
from pathlib import Path
from collections import defaultdict


def load_jsonl(path: Path) -> list:
    """Load JSONL file."""
    items = []
    with open(path, 'r') as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def main():
    # Paths
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data' / 'derived'
    
    edges_path = data_dir / 'storm_propagation.jsonl'
    graph_path = data_dir / 'actor_propagation_graph.json'
    chains_path = data_dir / 'propagation_chains.json'
    pathways_path = data_dir / 'semantic_pathways.json'
    report_path = base_dir / 'STORM_PROPAGATION_REPORT.md'
    
    # Load data
    edges = load_jsonl(edges_path)
    actor_graph = load_json(graph_path)
    chains = load_json(chains_path)
    pathways = load_json(pathways_path) if pathways_path.exists() else []
    
    # Compute actor roles
    actor_roles = defaultdict(lambda: {'outgoing': 0, 'incoming': 0, 'out_scores': [], 'in_scores': []})
    for edge in edges:
        actor_roles[edge['source_actor']]['outgoing'] += 1
        actor_roles[edge['source_actor']]['out_scores'].append(edge['propagation_score'])
        actor_roles[edge['target_actor']]['incoming'] += 1
        actor_roles[edge['target_actor']]['in_scores'].append(edge['propagation_score'])
    
    # Classify roles
    classified_roles = {}
    for actor, data in actor_roles.items():
        out = data['outgoing']
        inc = data['incoming']
        
        if out > inc * 1.5:
            role = 'originator'
        elif inc > out * 1.5:
            role = 'receiver'
        elif out > 0 and inc > 0:
            role = 'bridge'
        else:
            role = 'isolated'
        
        classified_roles[actor] = {
            'role': role,
            'outgoing': out,
            'incoming': inc,
            'mean_out': sum(data['out_scores']) / len(data['out_scores']) if data['out_scores'] else 0,
            'mean_in': sum(data['in_scores']) / len(data['in_scores']) if data['in_scores'] else 0
        }
    
    # Collect theme corridors
    theme_counts = defaultdict(int)
    for edge in edges:
        for theme in edge['shared_themes']:
            theme_counts[theme] += 1
    
    # Generate report
    with open(report_path, 'w') as f:
        f.write("# Storm Propagation Report\n\n")
        
        # Summary
        f.write("## Summary\n\n")
        f.write(f"- Total propagation edges: {len(edges)}\n")
        f.write(f"- Actor-level connections: {len(actor_graph)}\n")
        f.write(f"- Propagation chains (3+ actors): {len(chains)}\n")
        f.write(f"- Semantic pathways: {len(pathways)}\n")
        f.write(f"- Actors involved: {len(actor_roles)}\n\n")
        
        # Top propagation edges
        f.write("## Top Propagation Edges\n\n")
        sorted_edges = sorted(edges, key=lambda x: x['propagation_score'], reverse=True)
        for i, edge in enumerate(sorted_edges[:10], 1):
            themes_str = ', '.join(edge['shared_themes'][:3]) if edge['shared_themes'] else 'mixed'
            f.write(f"### {i}. {edge['source_actor']} → {edge['target_actor']}\n\n")
            f.write(f"- **Score**: {edge['propagation_score']:.2f}\n")
            f.write(f"- **Lag**: {edge['lag_days']} days\n")
            f.write(f"- **Semantic similarity**: {edge['semantic_similarity']:.2f}\n")
            f.write(f"- **Theme overlap**: {edge['theme_overlap']:.2f}\n")
            f.write(f"- **Shared themes**: {themes_str}\n")
            f.write(f"- **Source**: {edge['source_headline'][:100]}...\n")
            f.write(f"- **Target**: {edge['target_headline'][:100]}...\n\n")
        
        # Actor propagation map
        f.write("## Actor Propagation Map\n\n")
        sorted_graph = sorted(actor_graph.items(), key=lambda x: x[1]['mean_score'], reverse=True)
        for pair, data in sorted_graph[:10]:
            themes_str = ', '.join(data['shared_themes'])
            f.write(f"### {pair}\n\n")
            f.write(f"- **Edge count**: {data['edge_count']}\n")
            f.write(f"- **Mean score**: {data['mean_score']:.2f}\n")
            f.write(f"- **Avg lag**: {data['avg_lag_days']:.1f} days\n")
            f.write(f"- **Shared themes**: {themes_str}\n\n")
        
        # Propagation chains
        f.write("## Propagation Chains\n\n")
        sorted_chains = sorted(chains, key=lambda x: x['mean_score'], reverse=True)
        for i, chain in enumerate(sorted_chains[:10], 1):
            path = ' → '.join(chain['actors'])
            f.write(f"### {i}. {path}\n\n")
            f.write(f"- **Mean score**: {chain['mean_score']:.2f}\n")
            f.write(f"- **Theme hint**: {chain['shared_theme_hint']}\n")
            f.write(f"- **Edge scores**: {', '.join(f'{s:.2f}' for s in chain['edge_scores'])}\n\n")
        
        # Semantic pathways
        f.write("## Semantic Pathways (Narrative Corridors)\n\n")
        if pathways:
            for i, pathway in enumerate(pathways[:10], 1):
                path = ' → '.join(pathway['actors'])
                f.write(f"### {i}. {path}\n\n")
                f.write(f"- **Mean score**: {pathway['mean_score']:.2f}\n")
                f.write(f"- **Edge count**: {pathway['edge_count']}\n")
                f.write(f"- **Persistent themes**: {', '.join(pathway['persistent_themes']) if pathway['persistent_themes'] else 'none'}\n")
                f.write(f"- **Corridor themes**: {', '.join(pathway['corridor_themes'][:5])}\n")
                f.write(f"- **Plausible actor flow**: {'Yes' if pathway['has_plausible_flow'] else 'No'}\n\n")
        else:
            f.write("No semantic pathways detected.\n\n")
        
        # Shared theme corridors
        f.write("## Shared Theme Corridors\n\n")
        sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)
        for theme, count in sorted_themes[:10]:
            f.write(f"- **{theme}**: {count} propagation edges\n")
        f.write("\n")
        
        # Source vs recipient actors
        f.write("## Source vs Recipient Actors\n\n")
        
        f.write("### Originators\n\n")
        originators = [(a, d) for a, d in classified_roles.items() if d['role'] == 'originator']
        originators.sort(key=lambda x: x[1]['outgoing'], reverse=True)
        for actor, data in originators[:5]:
            f.write(f"- **{actor}**: {data['outgoing']} outgoing, {data['incoming']} incoming "
                   f"(mean out score: {data['mean_out']:.2f})\n")
        f.write("\n")
        
        f.write("### Receivers\n\n")
        receivers = [(a, d) for a, d in classified_roles.items() if d['role'] == 'receiver']
        receivers.sort(key=lambda x: x[1]['incoming'], reverse=True)
        for actor, data in receivers[:5]:
            f.write(f"- **{actor}**: {data['incoming']} incoming, {data['outgoing']} outgoing "
                   f"(mean in score: {data['mean_in']:.2f})\n")
        f.write("\n")
        
        f.write("### Bridges\n\n")
        bridges = [(a, d) for a, d in classified_roles.items() if d['role'] == 'bridge']
        bridges.sort(key=lambda x: x[1]['outgoing'] + x[1]['incoming'], reverse=True)
        for actor, data in bridges[:5]:
            f.write(f"- **{actor}**: {data['outgoing']} outgoing, {data['incoming']} incoming\n")
        f.write("\n")
    
    print(f"Report generated: {report_path}")


if __name__ == '__main__':
    main()
