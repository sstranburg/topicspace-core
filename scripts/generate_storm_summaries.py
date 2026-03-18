#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
from src.storm_summaries import generate_storm_summary, generate_trajectory_summary
from src.storm_topic_clustering import load_embeddings
from src.config import USE_LLM_NAMING

print("="*70)
print("STORM NARRATIVE SUMMARY GENERATION (WITH TOPIC CLUSTERING)")
print("="*70)

# Load embeddings for topic clustering
print("\nLoading title embeddings for topic clustering...")
title_embeddings_map = load_embeddings()
print(f"Loaded embeddings for {len(title_embeddings_map)} titles")

# Load actor storms
print("\nLoading actor storms...")
storms = []
with open("data/derived/actor_storms.jsonl", 'r') as f:
    for line in f:
        storm = json.loads(line)
        # Convert to expected format
        storms.append({
            'storm_id': storm['storm_id'],
            'actors': [storm['actor']],
            'event_count': storm['event_count'],
            'representative_titles': [e['title'] for e in storm.get('representative_events', [])],
            'cluster_titles_topN': storm.get('cluster_titles_topN', []),  # Add cluster titles
            'tags': storm.get('tags', [])
        })

print(f"Loaded {len(storms)} actor storms")

# Load trajectories
print("Loading trajectories...")
trajectories = []
trajectory_by_actor = {}

with open("data/derived/storm_trajectories.jsonl", 'r') as f:
    for line in f:
        traj = json.loads(line)
        trajectories.append(traj)
        trajectory_by_actor[traj['actor']] = traj

print(f"Loaded {len(trajectories)} trajectories")

# Generate storm summaries
print("\n" + "="*70)
print("GENERATING STORM SUMMARIES")
print("="*70)

storm_summaries = []
llm_stats = {
    'total': 0,
    'eligible': 0,
    'attempted': 0,
    'succeeded': 0,
    'accepted': 0,
    'rejected': 0,
    'fallback': 0,
    'rejected_forbidden_phrase': 0,
    'rejected_low_overlap': 0,
    'rejected_generic_phrase': 0,
    'rejected_speculative': 0,
    'rejected_length': 0,
    'rejected_introduced_entity': 0
}
llm_comparisons = []

for storm in storms:
    # Find matching trajectory
    actor = storm['actors'][0] if storm['actors'] else None
    trajectory = trajectory_by_actor.get(actor)
    
    # Generate summary with topic clustering and LLM naming
    summary = generate_storm_summary(
        storm, 
        trajectory, 
        title_embeddings_map=title_embeddings_map, 
        use_clustering=True,
        use_llm_naming=USE_LLM_NAMING
    )
    storm_summaries.append(summary)
    
    # Track LLM stats
    llm_stats['total'] += 1
    if summary.get('naming_evidence'):
        llm_stats['eligible'] += 1
    if summary.get('llm_used'):
        llm_stats['attempted'] += 1
        if summary.get('llm_headline'):
            llm_stats['succeeded'] += 1
            if summary.get('llm_validation_passed') and summary.get('llm_faithful'):
                llm_stats['accepted'] += 1
            else:
                llm_stats['rejected'] += 1
                # Track rejection reasons
                for reason in summary.get('llm_rejection_reasons', []):
                    if reason == 'forbidden_phrase':
                        llm_stats['rejected_forbidden_phrase'] += 1
                    elif reason == 'low_overlap':
                        llm_stats['rejected_low_overlap'] += 1
                    elif reason == 'generic_phrase':
                        llm_stats['rejected_generic_phrase'] += 1
                    elif reason == 'speculative':
                        llm_stats['rejected_speculative'] += 1
                    elif reason == 'length':
                        llm_stats['rejected_length'] += 1
                    elif reason == 'introduced_entity':
                        llm_stats['rejected_introduced_entity'] += 1
    if summary.get('display_source') == 'heuristic':
        llm_stats['fallback'] += 1
    
    # Build comparison if LLM was attempted
    if summary.get('llm_used'):
        llm_comparisons.append({
            'storm_id': summary['storm_id'],
            'actors': summary['actors'],
            'state': summary['state'],
            'event_count': summary['event_count'],
            'heuristic_headline': summary['headline'],
            'llm_headline': summary.get('llm_headline'),
            'display_headline': summary['display_headline'],
            'display_source': summary.get('display_source'),
            'llm_validation_passed': summary.get('llm_validation_passed'),
            'llm_faithful': summary.get('llm_faithful'),
            'llm_validation_reason': summary.get('llm_validation_reason'),
            'llm_rejection_reasons': summary.get('llm_rejection_reasons', []),
            'dominant_cluster_ratio': summary.get('cluster_dominance_ratio', 1.0),
            'dominant_cluster_terms': summary.get('dominant_cluster_terms', [])
        })

print(f"\nGenerated {len(storm_summaries)} storm summaries")

# Calculate statistics
avg_confidence = sum(s['summary_confidence'] for s in storm_summaries) / len(storm_summaries) if storm_summaries else 0
total_weak_terms = sum(s.get('weak_terms_removed', 0) for s in storm_summaries)
low_confidence_count = sum(1 for s in storm_summaries if s['summary_confidence'] < 0.5)

# Clustering statistics
used_clustering_count = sum(1 for s in storm_summaries if s.get('used_topic_clustering', False))
fallback_count = len(storm_summaries) - used_clustering_count
clustered_summaries = [s for s in storm_summaries if s.get('used_topic_clustering', False)]
avg_clusters = sum(s.get('num_title_clusters', 1) for s in clustered_summaries) / len(clustered_summaries) if clustered_summaries else 0
avg_dominance = sum(s.get('cluster_dominance_ratio', 1.0) for s in clustered_summaries) / len(clustered_summaries) if clustered_summaries else 0

print(f"Average summary confidence: {avg_confidence:.2f}")
print(f"Total weak terms removed: {total_weak_terms}")
print(f"Low confidence summaries (<0.5): {low_confidence_count}")
print(f"\nTopic Clustering Statistics:")
print(f"  Used clustering: {used_clustering_count}")
print(f"  Fallback (no clustering): {fallback_count}")
print(f"  Average clusters per storm: {avg_clusters:.1f}")
print(f"  Average cluster dominance ratio: {avg_dominance:.2f}")

if USE_LLM_NAMING:
    print(f"\nLLM Naming Statistics:")
    print(f"  Total storms: {llm_stats['total']}")
    print(f"  Eligible: {llm_stats['eligible']}")
    print(f"  Attempted: {llm_stats['attempted']}")
    print(f"  Succeeded: {llm_stats['succeeded']}")
    print(f"  Accepted: {llm_stats['accepted']}")
    print(f"  Rejected: {llm_stats['rejected']}")
    if llm_stats['rejected'] > 0:
        print(f"    - Forbidden phrase: {llm_stats['rejected_forbidden_phrase']}")
        print(f"    - Low overlap: {llm_stats['rejected_low_overlap']}")
        print(f"    - Generic phrase: {llm_stats['rejected_generic_phrase']}")
        print(f"    - Speculative: {llm_stats['rejected_speculative']}")
        print(f"    - Length: {llm_stats['rejected_length']}")
        print(f"    - Introduced entity: {llm_stats['rejected_introduced_entity']}")
    print(f"  Fallback: {llm_stats['fallback']}")

# Show top examples by confidence
print("\nTop 10 Summaries by Confidence:")
sorted_summaries = sorted(storm_summaries, key=lambda x: x['summary_confidence'], reverse=True)
for i, summary in enumerate(sorted_summaries[:10], 1):
    print(f"\n{i}. {summary['storm_id']}")
    print(f"   Heuristic: {summary['headline']}")
    if USE_LLM_NAMING and summary.get('llm_headline'):
        print(f"   LLM: {summary['llm_headline']}")
        print(f"   Display: {summary['display_headline']}")
        print(f"   Source: {summary.get('display_source')}")
        if not summary.get('llm_validation_passed'):
            print(f"   Rejection: {summary.get('llm_validation_reason')}")
            if summary.get('llm_rejection_reasons'):
                print(f"   Reasons: {', '.join(summary.get('llm_rejection_reasons', []))}")
    print(f"   One-liner: {summary['one_liner']}")
    if summary.get('used_topic_clustering'):
        print(f"   Clustering: {summary['num_title_clusters']} clusters, dominance {summary['cluster_dominance_ratio']:.2f}, size {summary['dominant_cluster_size']}")
    else:
        print(f"   Clustering: Not used (fallback)")
    print(f"   Themes: {', '.join(summary['themes'])}")
    if summary.get('domain_phrases'):
        print(f"   Domain phrases: {', '.join(summary['domain_phrases'])}")
    if summary.get('entity_actions'):
        print(f"   Entity actions: {', '.join(summary['entity_actions'])}")
    if summary['bigrams']:
        print(f"   Bigrams: {', '.join(summary['bigrams'])}")
    print(f"   State: {summary['state']}, Confidence: {summary['summary_confidence']}, Weak terms removed: {summary.get('weak_terms_removed', 0)}")

# Generate trajectory summaries
print("\n" + "="*70)
print("GENERATING TRAJECTORY SUMMARIES")
print("="*70)

trajectory_summaries = []

for traj in trajectories:
    summary = generate_trajectory_summary(traj)
    trajectory_summaries.append(summary)

print(f"\nGenerated {len(trajectory_summaries)} trajectory summaries")

# Show examples
print("\nExample trajectory summaries:")
for i, summary in enumerate(trajectory_summaries[:3], 1):
    print(f"\n{i}. {summary['trajectory_id']} ({summary['actor']})")  
    print(f"   Lifecycle: {summary['lifecycle']}")
    print(f"   Events: {summary['total_events']}, Max density: {summary['max_density']}")
    print(f"   Peak ratio: {summary['peak_ratio']}, Momentum: {summary['momentum']:+d}")
    print(f"   {summary['interpretation']}")

# Save artifacts
print("\n" + "="*70)
print("SAVING ARTIFACTS")
print("="*70)

with open("data/derived/actor_storm_summaries.jsonl", 'w') as f:
    for summary in storm_summaries:
        f.write(json.dumps(summary) + '\n')

print(f"✅ Saved {len(storm_summaries)} storm summaries to actor_storm_summaries.jsonl")

with open("data/derived/trajectory_summaries.jsonl", 'w') as f:
    for summary in trajectory_summaries:
        f.write(json.dumps(summary) + '\n')

print(f"✅ Saved {len(trajectory_summaries)} trajectory summaries to trajectory_summaries.jsonl")

print("\n" + "="*70)
print("SUMMARY GENERATION COMPLETE")
print("="*70)

print(f"\nStorm summaries: {len(storm_summaries)}")
print(f"Average confidence: {avg_confidence:.2f}")
print(f"Used clustering: {used_clustering_count}")
print(f"Fallback summaries: {fallback_count}")
print(f"Average clusters per storm: {avg_clusters:.1f}")
print(f"Total weak terms removed: {total_weak_terms}")
print(f"Low confidence summaries: {low_confidence_count}")
print(f"Trajectory summaries: {len(trajectory_summaries)}")

print(f"\nFiles modified:")
print(f"  src/storm_summaries.py (integrated topic clustering)")
print(f"  src/storm_topic_clustering.py (updated for embedding loading)")
print(f"  scripts/generate_storm_summaries.py (added clustering pipeline)")

print(f"\nArtifacts written:")
print(f"  data/derived/actor_storm_summaries.jsonl")
print(f"  data/derived/trajectory_summaries.jsonl")
