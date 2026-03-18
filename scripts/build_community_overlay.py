#!/usr/bin/env python3
"""Build community overlay: attach posts to storms, compute alignment, detect precursors."""

import json
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from community_overlay import (
    load_community_posts, filter_posts, attach_posts_to_storms,
    compute_community_alignment, compute_community_divergence,
    detect_community_precursors, build_community_perspective,
)


def load_jsonl(path):
    items = []
    if not path.exists():
        return items
    with open(path) as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def main():
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data' / 'derived'
    community_path = base_dir / 'data' / 'normalized' / 'community_posts.jsonl'

    if not community_path.exists():
        print("No community_posts.jsonl found. Skipping overlay.")
        return

    # Load community posts
    raw_posts = load_community_posts(community_path)
    filtered = filter_posts(raw_posts)

    # Load storms
    actor_storms = load_jsonl(data_dir / 'actor_storms.jsonl')
    eco_storms = load_jsonl(data_dir / 'ecosystem_storms.jsonl')
    all_storms = actor_storms + eco_storms

    # Merge summaries
    actor_summaries = load_jsonl(data_dir / 'actor_storm_summaries.jsonl')
    eco_summaries = load_jsonl(data_dir / 'ecosystem_storm_summaries.jsonl')
    summary_map = {s['storm_id']: s for s in actor_summaries + eco_summaries}
    for storm in all_storms:
        sm = summary_map.get(storm['storm_id'])
        if sm:
            storm.update(sm)

    # Build storm centroids from embeddings
    emb_path = data_dir / 'tech_ecosystem_embeddings.npz'
    storm_centroids = {}
    if emb_path.exists():
        emb_data = np.load(emb_path, allow_pickle=True)
        embeddings = emb_data['embeddings']
        event_ids = list(emb_data['event_ids'])
        emb_map = {eid: embeddings[i] for i, eid in enumerate(event_ids)}

        for storm in all_storms:
            eids = storm.get('event_ids', [])
            vecs = [emb_map[eid] for eid in eids if eid in emb_map]
            if vecs:
                storm_centroids[storm['storm_id']] = np.mean(vecs, axis=0)

    # Attach posts to storms
    attached, unmatched = attach_posts_to_storms(filtered, all_storms, storm_centroids)

    # Build overlay for each storm with enough posts
    storm_map = {s['storm_id']: s for s in all_storms}
    overlay_records = []
    alignment_counts = {'aligned': 0, 'mixed': 0, 'divergent': 0}

    for storm_id, posts in attached.items():
        storm = storm_map.get(storm_id, {})
        if len(posts) < 3:
            continue
        alignment = compute_community_alignment(storm, posts)
        divergent = compute_community_divergence(storm, posts)
        perspective = build_community_perspective(storm, posts, alignment, divergent)
        perspective['storm_id'] = storm_id
        perspective['label'] = storm.get('display_headline', storm.get('headline', storm_id))
        perspective['actor'] = storm.get('actor', '')
        overlay_records.append(perspective)
        alignment_counts[alignment['community_alignment_label']] += 1

    # Detect precursors
    precursors = detect_community_precursors(unmatched)

    # Save artifacts
    overlay_path = data_dir / 'community_overlay.jsonl'
    with open(overlay_path, 'w') as f:
        for r in overlay_records:
            f.write(json.dumps(r) + '\n')

    precursor_path = data_dir / 'community_precursors.jsonl'
    with open(precursor_path, 'w') as f:
        for r in precursors:
            f.write(json.dumps(r) + '\n')

    # Diagnostics
    print("Community Overlay Diagnostics")
    print("-----------------------------")
    print(f"Community posts loaded: {len(raw_posts)}")
    print(f"Posts after filtering: {len(filtered)}")
    print(f"Posts attached to storms: {sum(len(v) for v in attached.values())}")
    print(f"Posts unmatched: {len(unmatched)}")
    print(f"Storms with community overlay: {len(overlay_records)}")
    print(f"Community precursor clusters: {len(precursors)}")
    print()
    print("Alignment breakdown:")
    for label in ['aligned', 'mixed', 'divergent']:
        print(f"  {label}: {alignment_counts[label]}")
    print()
    if overlay_records:
        print("Storms with overlay:")
        for r in overlay_records:
            print(f"  {r['label'][:50]} ({r['actor']}) - {r['community_alignment_label']} ({r['community_post_count']} posts)")
            if r['community_divergent_themes']:
                print(f"    divergent themes: {', '.join(r['community_divergent_themes'][:4])}")
    print()
    if precursors:
        print("Precursor topics:")
        for p in precursors:
            print(f"  {p['label']} ({p['post_count']} posts, avg score {p['avg_score']})")
    print()
    print(f"Artifact: {overlay_path}")
    print(f"Artifact: {precursor_path}")


if __name__ == '__main__':
    main()
