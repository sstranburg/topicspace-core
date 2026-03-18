#!/usr/bin/env python3
"""Generate storm summaries with optional LLM naming."""

import json
from pathlib import Path
from src.storm_summaries import generate_storm_summary
from src.config import USE_LLM_NAMING

def load_jsonl(path):
    """Load JSONL file."""
    with open(path) as f:
        return [json.loads(line) for line in f]

def save_jsonl(data, path):
    """Save JSONL file."""
    with open(path, 'w') as f:
        for item in data:
            f.write(json.dumps(item) + '\n')

def load_embeddings(path):
    """Load title embeddings."""
    embeddings = {}
    with open(path) as f:
        for line in f:
            obj = json.loads(line)
            embeddings[obj['title']] = obj['embedding']
    return embeddings

def main():
    # Load data
    storms = load_jsonl('data/derived/actor_storms.jsonl')
    trajectories = load_jsonl('data/derived/storm_trajectories.jsonl')
    embeddings = load_embeddings('data/derived/title_embeddings.jsonl')
    
    # Build trajectory lookup
    traj_map = {t['trajectory_id']: t for t in trajectories}
    
    # Generate summaries
    summaries = []
    stats = {
        'total': len(storms),
        'eligible': 0,
        'attempted': 0,
        'succeeded': 0,
        'accepted': 0,
        'rejected': 0,
        'fallback': 0
    }
    
    comparisons = []
    
    for storm in storms:
        # Find trajectory
        traj = None
        for t in trajectories:
            if storm['storm_id'] in t.get('storm_ids', []):
                traj = t
                break
        
        # Generate summary
        summary = generate_storm_summary(
            storm,
            trajectory=traj,
            title_embeddings_map=embeddings,
            use_clustering=True,
            use_llm_naming=USE_LLM_NAMING
        )
        
        summaries.append(summary)
        
        # Track stats
        if summary.get('llm_used'):
            stats['attempted'] += 1
            if summary.get('llm_headline'):
                stats['succeeded'] += 1
                if summary.get('llm_validation_passed'):
                    stats['accepted'] += 1
                else:
                    stats['rejected'] += 1
        
        if summary.get('naming_evidence'):
            stats['eligible'] += 1
        
        if not summary.get('llm_validation_passed'):
            stats['fallback'] += 1
        
        # Build comparison
        if summary.get('llm_used'):
            comparisons.append({
                'storm_id': summary['storm_id'],
                'actors': summary['actors'],
                'state': summary['state'],
                'event_count': summary['event_count'],
                'heuristic_headline': summary['headline'],
                'heuristic_one_liner': summary['one_liner'],
                'llm_headline': summary.get('llm_headline'),
                'llm_one_liner': summary.get('llm_one_liner'),
                'display_headline': summary['display_headline'],
                'llm_validation_passed': summary.get('llm_validation_passed'),
                'llm_validation_reason': summary.get('llm_validation_reason'),
                'cluster_dominance_ratio': summary.get('cluster_dominance_ratio', 1.0),
                'representative_title': summary.get('representative_title')
            })
    
    # Save summaries
    save_jsonl(summaries, 'data/derived/actor_storm_summaries.jsonl')
    
    # Print stats
    print("\n=== LLM Naming Statistics ===")
    print(f"Total storms: {stats['total']}")
    print(f"Eligible: {stats['eligible']}")
    print(f"Attempted: {stats['attempted']}")
    print(f"Succeeded: {stats['succeeded']}")
    print(f"Accepted: {stats['accepted']}")
    print(f"Rejected: {stats['rejected']}")
    print(f"Fallback: {stats['fallback']}")
    
    # Print comparisons
    if comparisons:
        print("\n=== Top 10 Comparisons ===")
        for i, comp in enumerate(comparisons[:10], 1):
            print(f"\n{i}. Storm: {comp['storm_id']}")
            print(f"   Actors: {', '.join(comp['actors'])}")
            print(f"   State: {comp['state']}")
            print(f"   Events: {comp['event_count']}")
            print(f"   Heuristic: {comp['heuristic_headline']}")
            print(f"   LLM: {comp['llm_headline']}")
            print(f"   Used LLM: {'yes' if comp['llm_validation_passed'] else 'no'}")
            if not comp['llm_validation_passed'] and comp['llm_validation_reason']:
                print(f"   Rejection: {comp['llm_validation_reason']}")
    
    # Generate comparison report
    if comparisons:
        with open('LLM_NAMING_COMPARISON_REPORT.md', 'w') as f:
            f.write("# LLM Naming Comparison Report\n\n")
            f.write(f"Generated for {len(comparisons)} storms with LLM naming attempts.\n\n")
            
            f.write("## Statistics\n\n")
            f.write(f"- Total storms: {stats['total']}\n")
            f.write(f"- Eligible for LLM naming: {stats['eligible']}\n")
            f.write(f"- LLM calls attempted: {stats['attempted']}\n")
            f.write(f"- LLM calls succeeded: {stats['succeeded']}\n")
            f.write(f"- LLM names accepted: {stats['accepted']}\n")
            f.write(f"- LLM names rejected: {stats['rejected']}\n")
            f.write(f"- Fallback to heuristic: {stats['fallback']}\n\n")
            
            f.write("## Detailed Comparisons\n\n")
            for comp in comparisons:
                f.write(f"### {comp['storm_id']}\n\n")
                f.write(f"**Actors:** {', '.join(comp['actors'])}  \n")
                f.write(f"**State:** {comp['state']}  \n")
                f.write(f"**Event Count:** {comp['event_count']}  \n")
                f.write(f"**Cluster Dominance:** {comp['cluster_dominance_ratio']:.2f}  \n\n")
                
                f.write(f"**Heuristic Headline:** {comp['heuristic_headline']}  \n")
                f.write(f"**Heuristic One-liner:** {comp['heuristic_one_liner']}  \n\n")
                
                f.write(f"**LLM Headline:** {comp['llm_headline']}  \n")
                f.write(f"**LLM One-liner:** {comp['llm_one_liner']}  \n\n")
                
                f.write(f"**Display Headline:** {comp['display_headline']}  \n")
                f.write(f"**LLM Validation:** {'✓ Passed' if comp['llm_validation_passed'] else '✗ Failed'}  \n")
                if comp['llm_validation_reason']:
                    f.write(f"**Rejection Reason:** {comp['llm_validation_reason']}  \n")
                
                f.write(f"\n**Representative Title:** {comp['representative_title']}  \n\n")
                f.write("---\n\n")
        
        print(f"\n✓ Comparison report saved to LLM_NAMING_COMPARISON_REPORT.md")
    
    print(f"\n✓ Summaries saved to data/derived/actor_storm_summaries.jsonl")

if __name__ == '__main__':
    main()
