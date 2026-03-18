#!/usr/bin/env python3
"""
Build retail amplification layer.
Detects retail advice events, embeds them, attaches to lineages.
Output: data/derived/retail_amplification.jsonl
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.narrative_lineage import group_into_lineages
from src.retail_amplification import build_retail_amplification

data_dir  = Path(__file__).parent.parent / 'data' / 'derived'
norm_dir  = Path(__file__).parent.parent / 'data' / 'normalized'
out_path  = data_dir / 'retail_amplification.jsonl'


def load_jsonl(p):
    return [json.loads(l) for l in open(p) if l.strip()] if Path(p).exists() else []


def main():
    print('=== Retail Amplification Layer ===\n')

    all_events   = load_jsonl(norm_dir / 'tech_ecosystem.jsonl')
    filtered_ids = {e['event_id'] for e in load_jsonl(norm_dir / 'tech_ecosystem_filtered.jsonl')}

    # Load embeddings
    d       = np.load(data_dir / 'tech_ecosystem_embeddings.npz', allow_pickle=True)
    emb_map = {str(k): v for k, v in zip(d['event_ids'], d['embeddings'])}

    # Build lineages (need storms with centroids)
    actor_storms = load_jsonl(data_dir / 'actor_storms.jsonl')
    eco_storms   = load_jsonl(data_dir / 'ecosystem_storms.jsonl')
    all_storms   = actor_storms + eco_storms
    for s in all_storms:
        vecs = [emb_map[e] for e in s.get('event_ids', []) if e in emb_map]
        if vecs:
            s['_centroid'] = np.mean(vecs, axis=0)

    all_storms, lineage_summaries = group_into_lineages(all_storms)

    # Aggregate into lineage records (mirrors generate_master_report aggregation)
    lineages: dict = {}
    for storm in all_storms:
        lid = storm.get('lineage_id')
        if not lid:
            continue
        if lid not in lineages:
            lineages[lid] = {
                'lineage_id':        lid,
                'label':             storm.get('lineage_label', lid),
                'lineage_type':      storm.get('lineage_type', 'actor'),
                'storms':            [],
                'event_count':       0,
                'max_gravity':       0.0,
            }
        lineages[lid]['storms'].append(storm)
        lineages[lid]['event_count'] += storm.get('event_count', 0)
        lineages[lid]['max_gravity']  = max(
            lineages[lid]['max_gravity'], storm.get('gravity_score', 0.0)
        )

    for rec in lineages.values():
        rec['lineage_event_count'] = rec.pop('event_count')
        rec['lineage_max_gravity'] = round(rec.pop('max_gravity'), 4)

    lineages_list = list(lineages.values())

    records, stats = build_retail_amplification(
        all_events, filtered_ids, lineages_list, emb_map
    )

    with open(out_path, 'w') as f:
        for r in records:
            r_out = {k: v for k, v in r.items() if k != 'retail_events_emb'}
            f.write(json.dumps(r_out) + '\n')

    precision_path = data_dir / 'retail_amplification_precision.json'
    with open(precision_path, 'w') as f:
        json.dump(stats['precision'], f, indent=2)

    print(f'\nRetail amplification stats:')
    print(f'  Retail events evaluated : {stats["retail_total"]}')
    print(f'  Attached to lineages    : {stats["attached"]}')
    print(f'  Attachment rate         : {stats["attachment_rate"]:.1%}')
    print(f'  By lineage:')
    for lid, cnt in sorted(stats['by_lineage'].items()):
        label = lineages.get(lid, {}).get('label', lid)
        print(f'    {lid:<20} {cnt:>3}  {label}')

    if stats['top_attached']:
        print(f'\n  Top {len(stats["top_attached"])} attached retail events:')
        print(f'  {"event_id":<30} {"lineage_id":<20} {"cos_sim":>7} {"actors":>6} {"boost":>5} {"score":>6}')
        for c in stats['top_attached']:
            print(f'  {c["event_id"]:<30} {c["lineage_id"]:<20} '
                  f'{c["cosine_similarity"]:>7.4f} {c["shared_actor_count"]:>6} '
                  f'{c["actor_overlap_boost"]:>5.2f} {c["retail_attach_score"]:>6.4f}')
            print(f'    {c["title"][:80]}')

    if stats['tie_break_log']:
        print(f'\n  Tie-break decisions ({len(stats["tie_break_log"])} events had multiple valid candidates):')
        for t in stats['tie_break_log']:
            print(f'  [{t["event_id"]}] {t["title"][:70]}')
            print(f'    {t["n_valid"]} candidates → selected: {t["selected"]}')
            for c in t['candidates']:
                marker = '✓' if c['lineage_id'] == t['selected'] else ' '
                print(f'    {marker} {c["lineage_id"]:<20} '
                      f'actors={c["shared_actor_count"]} '
                      f'score={c["retail_attach_score"]:.4f} '
                      f'gravity={c["lineage_gravity"]:.4f}')

    if stats['near_misses']:
        print(f'\n  Near misses (score {0.55:.2f}–{0.60:.2f}):')
        print(f'  {"event_id":<30} {"lineage_id":<20} {"cos_sim":>7} {"actors":>6} {"boost":>5} {"score":>6}')
        for c in stats['near_misses']:
            print(f'  {c["event_id"]:<30} {c["lineage_id"]:<20} '
                  f'{c["cosine_similarity"]:>7.4f} {c["shared_actor_count"]:>6} '
                  f'{c["actor_overlap_boost"]:>5.2f} {c["retail_attach_score"]:>6.4f}')
            print(f'    {c["title"][:80]}')

    print(f'\nArtifacts: {out_path}')
    print(f'           {precision_path}')
    _print_precision(stats['precision'])


def _print_precision(p: dict) -> None:
    print(f'\n  --- Attachment Precision Diagnostics ---')

    print(f'  Distribution by lineage:')
    print(f'  {"lineage_id":<20} {"label":<35} {"count":>5} {"mean_score":>10} {"mean_actors":>11}')
    for r in p['by_lineage']:
        print(f'  {r["lineage_id"]:<20} {r["lineage_label"][:35]:<35} '
              f'{r["retail_event_count"]:>5} {r["mean_retail_attach_score"]:>10.4f} '
              f'{r["mean_shared_actor_count"]:>11.2f}')

    print(f'\n  Score histogram:')
    for bucket, cnt in p['score_histogram'].items():
        bar = '█' * cnt
        print(f'    {bucket}  {cnt:>3}  {bar}')

    print(f'\n  Actor overlap distribution:')
    print(f'    shared_actor_count == 1  : {p["actor_overlap"]["shared_1"]}')
    print(f'    shared_actor_count >= 2  : {p["actor_overlap"]["shared_2_plus"]}')

    print(f'\n  Multi-candidate events: {p["multi_candidate_count"]}')
    for t in p['top_multi_candidates']:
        print(f'    [{t["event_id"]}] {t["title"][:60]}')
        print(f'      {t["n_valid"]} candidates  '
              f'winner={t["winner_lineage"]} ({t["winner_score"]:.4f})  '
              f'runner-up={t["runner_up_lineage"]} ({t["runner_up_score"]:.4f})')

    print(f'\n  Concentration:')
    print(f'    Top 1 lineage accounts for {p["concentration_top1"]:.0%} of attached events')
    print(f'    Top 3 lineages account for {p["concentration_top3"]:.0%} of attached events')


if __name__ == '__main__':
    main()
