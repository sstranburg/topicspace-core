#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
import numpy as np
from src.storm_merge_split import detect_merge_candidates, detect_split_candidates

print("="*70)
print("STORM MERGE/SPLIT ANALYSIS")
print("="*70)

# Load trajectories
print("\nLoading trajectories...")
trajectories = []
with open("data/derived/storm_trajectories.jsonl", 'r') as f:
    for line in f:
        trajectories.append(json.loads(line))

print(f"Loaded {len(trajectories)} trajectories")

# Load embeddings
print("Loading embeddings...")
data = np.load("data/derived/tech_ecosystem_embeddings.npz")
embeddings = data['embeddings']
event_ids = data['event_ids']

embedding_lookup = {
    str(event_id): embeddings[i]
    for i, event_id in enumerate(event_ids)
}

print(f"Loaded {len(embeddings)} embeddings")

# Detect merge candidates
print("\n" + "="*70)
print("DETECTING MERGE CANDIDATES")
print("="*70)

merge_candidates = detect_merge_candidates(trajectories, embedding_lookup)

print(f"\nMerge candidates detected: {len(merge_candidates)}")

if merge_candidates:
    print(f"\nTop 5 merge candidates:")
    for i, candidate in enumerate(merge_candidates[:5], 1):
        print(f"\n{i}. {candidate['trajectory_a']} + {candidate['trajectory_b']}")
        print(f"   Score: {candidate['merge_score']:.3f}")
        print(f"   Semantic similarity: {candidate['semantic_similarity']:.3f}")
        print(f"   Time overlap: {candidate['time_overlap']:.3f}")
        print(f"   Densities: {candidate['density_a']} + {candidate['density_b']}")

# Detect split candidates
print("\n" + "="*70)
print("DETECTING SPLIT CANDIDATES")
print("="*70)

split_candidates = detect_split_candidates(trajectories, embedding_lookup)

print(f"\nSplit candidates detected: {len(split_candidates)}")

if split_candidates:
    print(f"\nTop 5 split candidates:")
    for i, candidate in enumerate(split_candidates[:5], 1):
        print(f"\n{i}. Parent: {candidate['parent_trajectory']}")
        print(f"   Children: {', '.join(candidate['child_trajectories'])}")
        print(f"   Score: {candidate['split_score']:.3f}")
        print(f"   Parent peak density: {candidate['parent_peak_density']}")
        print(f"   Number of children: {candidate['num_children']}")

# Save artifacts
print("\n" + "="*70)
print("SAVING ARTIFACTS")
print("="*70)

with open("data/derived/merge_candidates.jsonl", 'w') as f:
    for candidate in merge_candidates:
        f.write(json.dumps(candidate) + '\n')

print(f"✅ Saved {len(merge_candidates)} merge candidates to merge_candidates.jsonl")

with open("data/derived/split_candidates.jsonl", 'w') as f:
    for candidate in split_candidates:
        f.write(json.dumps(candidate) + '\n')

print(f"✅ Saved {len(split_candidates)} split candidates to split_candidates.jsonl")

# Generate report
print("\nGenerating MERGE_SPLIT_REPORT.md...")

with open("MERGE_SPLIT_REPORT.md", 'w') as f:
    f.write("# Storm Merge/Split Analysis Report\n\n")
    f.write(f"Generated from {len(trajectories)} trajectories\n\n")
    
    f.write("## Summary\n\n")
    f.write(f"- **Merge candidates**: {len(merge_candidates)}\n")
    f.write(f"- **Split candidates**: {len(split_candidates)}\n\n")
    
    f.write("## Merge Candidates\n\n")
    if merge_candidates:
        f.write("Trajectories that may be converging into shared situations:\n\n")
        for i, candidate in enumerate(merge_candidates[:10], 1):
            f.write(f"### {i}. {candidate['trajectory_a']} + {candidate['trajectory_b']}\n\n")
            f.write(f"- **Merge score**: {candidate['merge_score']:.3f}\n")
            f.write(f"- **Semantic similarity**: {candidate['semantic_similarity']:.3f}\n")
            f.write(f"- **Time overlap**: {candidate['time_overlap']:.3f}\n")
            f.write(f"- **Actors**: {', '.join(candidate['actors_a'])} + {', '.join(candidate['actors_b'])}\n")
            f.write(f"- **Densities**: {candidate['density_a']} + {candidate['density_b']}\n\n")
    else:
        f.write("No merge candidates detected.\n\n")
    
    f.write("## Split Candidates\n\n")
    if split_candidates:
        f.write("Trajectories that may be branching into multiple descendants:\n\n")
        for i, candidate in enumerate(split_candidates[:10], 1):
            f.write(f"### {i}. {candidate['parent_trajectory']}\n\n")
            f.write(f"- **Split score**: {candidate['split_score']:.3f}\n")
            f.write(f"- **Parent peak density**: {candidate['parent_peak_density']}\n")
            f.write(f"- **Number of children**: {candidate['num_children']}\n")
            f.write(f"- **Children**: {', '.join(candidate['child_trajectories'])}\n\n")
            
            f.write("**Child details:**\n\n")
            for child in candidate['child_details']:
                f.write(f"- {child['trajectory_id']}: ")
                f.write(f"similarity={child['semantic_similarity']:.3f}, ")
                f.write(f"offset={child['time_offset_days']} days\n")
            f.write("\n")
    else:
        f.write("No split candidates detected.\n\n")
    
    f.write("## Interpretation\n\n")
    f.write("### Merge Candidates\n\n")
    if merge_candidates:
        f.write("High merge scores indicate trajectories that:\n")
        f.write("- Are semantically similar (discussing related topics)\n")
        f.write("- Overlap significantly in time\n")
        f.write("- Involve different actors (cross-actor convergence)\n\n")
        f.write("These may represent situations where multiple actors are responding to the same underlying event or trend.\n\n")
    
    f.write("### Split Candidates\n\n")
    if split_candidates:
        f.write("High split scores indicate trajectories that:\n")
        f.write("- Had high peak density (major narrative)\n")
        f.write("- Spawned multiple semantically-related child trajectories\n")
        f.write("- May represent narrative branching or fragmentation\n\n")

print("✅ Report written to MERGE_SPLIT_REPORT.md")

print("\n" + "="*70)
print("ANALYSIS COMPLETE")
print("="*70)

print(f"\nMerge candidates: {len(merge_candidates)}")
print(f"Split candidates: {len(split_candidates)}")

print(f"\nArtifacts written:")
print(f"  data/derived/merge_candidates.jsonl")
print(f"  data/derived/split_candidates.jsonl")
print(f"  MERGE_SPLIT_REPORT.md")
