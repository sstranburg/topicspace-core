#!/usr/bin/env python3
"""Generate ecosystem storm summaries."""

import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
from src.ecosystem_summaries import generate_ecosystem_storm_summary
from src.storm_topic_clustering import load_embeddings
from src.config import USE_LLM_NAMING

print("="*70)
print("ECOSYSTEM STORM SUMMARY GENERATION")
print("="*70)

# Load embeddings
print("\nLoading title embeddings...")
title_embeddings_map = load_embeddings()
print(f"Loaded embeddings for {len(title_embeddings_map)} titles")

# Load ecosystem storms
print("Loading ecosystem storms...")
storms = []
with open("data/derived/ecosystem_storms.jsonl", 'r') as f:
    for line in f:
        storms.append(json.loads(line))

print(f"Loaded {len(storms)} ecosystem storms")

# Load trajectories
print("Loading trajectories...")
trajectories = []
with open("data/derived/ecosystem_trajectories.jsonl", 'r') as f:
    for line in f:
        trajectories.append(json.loads(line))

print(f"Loaded {len(trajectories)} trajectories")

# Build trajectory lookup
traj_by_storm = {}
for traj in trajectories:
    # New windowed format: storms reference trajectory_id
    traj_by_storm[traj['trajectory_id']] = traj
    # Old format: trajectory has storm_ids list
    for storm_id in traj.get('storm_ids', []):
        traj_by_storm[storm_id] = traj

# Generate summaries
print("\n" + "="*70)
print("GENERATING SUMMARIES")
print("="*70)

summaries = []
llm_stats = {
    'total': 0,
    'eligible': 0,
    'attempted': 0,
    'succeeded': 0,
    'accepted': 0,
    'rejected': 0,
    'fallback': 0
}

for storm in storms:
    # Match by trajectory_id (new windowed format)
    traj = traj_by_storm.get(storm.get('trajectory_id')) or traj_by_storm.get(storm['storm_id'])
    
    summary = generate_ecosystem_storm_summary(
        storm,
        trajectory=traj,
        title_embeddings_map=title_embeddings_map,
        use_clustering=True,
        use_llm_naming=USE_LLM_NAMING
    )
    
    summaries.append(summary)
    
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
    if summary.get('display_source') == 'heuristic':
        llm_stats['fallback'] += 1

print(f"\nGenerated {len(summaries)} ecosystem storm summaries")

# Statistics
avg_confidence = sum(s['summary_confidence'] for s in summaries) / len(summaries) if summaries else 0
used_clustering = sum(1 for s in summaries if s.get('used_topic_clustering'))

print(f"Average confidence: {avg_confidence:.2f}")
print(f"Used clustering: {used_clustering}")

if USE_LLM_NAMING:
    print(f"\nLLM Naming Statistics:")
    print(f"  Total: {llm_stats['total']}")
    print(f"  Eligible: {llm_stats['eligible']}")
    print(f"  Attempted: {llm_stats['attempted']}")
    print(f"  Succeeded: {llm_stats['succeeded']}")
    print(f"  Accepted: {llm_stats['accepted']}")
    print(f"  Rejected: {llm_stats['rejected']}")
    print(f"  Fallback: {llm_stats['fallback']}")

# Show top examples
print("\n" + "="*70)
print("TOP 5 ECOSYSTEM SUMMARIES")
print("="*70)

sorted_summaries = sorted(summaries, key=lambda x: x['event_count'], reverse=True)
for i, summary in enumerate(sorted_summaries[:5], 1):
    print(f"\n{i}. {summary['storm_id']}")
    print(f"   Headline: {summary['display_headline']}")
    print(f"   One-liner: {summary['display_one_liner']}")
    print(f"   Actors: {', '.join(summary['actors'])} ({summary['num_unique_actors']} total)")
    print(f"   Events: {summary['event_count']}")
    print(f"   State: {summary['state']}")
    print(f"   Confidence: {summary['summary_confidence']:.2f}")

# Save summaries
print("\n" + "="*70)
print("SAVING SUMMARIES")
print("="*70)

output_path = "data/derived/ecosystem_storm_summaries.jsonl"
with open(output_path, 'w') as f:
    for summary in summaries:
        f.write(json.dumps(summary) + '\n')

print(f"✅ Saved {len(summaries)} summaries to {output_path}")

print("\n" + "="*70)
print("ECOSYSTEM SUMMARY GENERATION COMPLETE")
print("="*70)
