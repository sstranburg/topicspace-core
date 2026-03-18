"""
Narrative lineage grouping.

Groups storms that share strong semantic and thematic similarity across time
into lineages without merging their individual event windows.

Actor lineage similarity:
    0.60 * cosine_similarity + 0.25 * theme_overlap + 0.15 * actor_overlap
    Threshold: >= 0.62 (pass 1) | >= 0.64 (pass 2)

Ecosystem lineage similarity:
    0.55 * cosine_similarity + 0.30 * theme_overlap + 0.15 * actor_overlap
    + time_boost (0.05 if gap<=2d, 0.03 if gap<=5d, 0 otherwise)
    Threshold: >= 0.50 (pass 1) | >= 0.64 (pass 2)
    Gate: actor_overlap=0 allowed if centroid_cosine >= 0.65 AND theme_overlap > 0

Time constraint: storms must be within 30 days of each other.
Each storm belongs to at most one lineage (greedy, largest-first).

Two separate tracks:
  actor_lineage_### — built only from actor storms
  eco_lineage_###   — built only from ecosystem storms
"""

import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import numpy as np

LINEAGE_THRESHOLD       = 0.62
LINEAGE_THRESHOLD_ECO   = 0.46   # lower than actor threshold: eco storms lack theme data
LINEAGE_THRESHOLD_P2    = 0.64
LINEAGE_MAX_DAYS        = 30
LINEAGE_ECO_HIGH_COS    = 0.65   # waives actor_overlap gate when theme_overlap > 0


def _parse_ts(ts):
    ts = ts.rstrip('Z').replace('+00:00Z', '+00:00')
    if not ts.endswith('+00:00'):
        ts += '+00:00'
    return datetime.fromisoformat(ts)


def _cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    ma  = math.sqrt(sum(x * x for x in a))
    mb  = math.sqrt(sum(x * x for x in b))
    return dot / (ma * mb) if ma and mb else 0.0


def _theme_anchor_overlap(a, b):
    """Weighted Jaccard over themes + domain_phrases."""
    def _collect(storm):
        terms = {}
        for t in storm.get('themes', []):
            terms[t] = max(terms.get(t, 0), 2)
        for t in storm.get('domain_phrases', []):
            terms[t] = max(terms.get(t, 0), 2)
        for t in storm.get('bigrams', []):
            terms[t] = max(terms.get(t, 0), 1)
        return terms

    ta, tb = _collect(a), _collect(b)
    if not ta or not tb:
        return 0.0
    keys  = set(ta) | set(tb)
    inter = sum(min(ta.get(k, 0), tb.get(k, 0)) for k in keys)
    union = sum(max(ta.get(k, 0), tb.get(k, 0)) for k in keys)
    return inter / union if union else 0.0


def _actor_overlap(a, b):
    """Jaccard over actor sets."""
    actors_a = set(a.get('actors', []) or ([a['actor']] if a.get('actor') else []))
    actors_b = set(b.get('actors', []) or ([b['actor']] if b.get('actor') else []))
    if not actors_a or not actors_b:
        return 0.0
    return len(actors_a & actors_b) / len(actors_a | actors_b)


def _time_gap_days(a, b):
    try:
        ta = _parse_ts(a.get('created_at', ''))
        tb = _parse_ts(b.get('created_at', ''))
        return abs((tb - ta).days)
    except (ValueError, AttributeError):
        return 9999


def _lineage_centroid(member_storms):
    vecs = [s['centroid'] for s in member_storms if s.get('centroid')]
    if not vecs:
        return []
    dim = len(vecs[0])
    return [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]


def _lineage_representative(member_storms):
    actors = set()
    themes, domain_phrases, bigrams = {}, {}, {}
    for s in member_storms:
        actors.update(s.get('actors', []) or ([s['actor']] if s.get('actor') else []))
        for t in s.get('themes', []):         themes[t]         = themes.get(t, 0) + 2
        for t in s.get('domain_phrases', []): domain_phrases[t] = domain_phrases.get(t, 0) + 2
        for t in s.get('bigrams', []):        bigrams[t]        = bigrams.get(t, 0) + 1
    return {
        'centroid':       _lineage_centroid(member_storms),
        'actors':         sorted(actors),
        'themes':         list(themes.keys()),
        'domain_phrases': list(domain_phrases.keys()),
        'bigrams':        list(bigrams.keys()),
        'created_at':     max((s.get('created_at', '') for s in member_storms), default=''),
    }


ECO_TIME_BOOST_NEAR = 0.05   # gap <= 2 days
ECO_TIME_BOOST_MID  = 0.03   # gap <= 5 days


def _eco_time_boost(gap_days):
    if gap_days <= 2:
        return ECO_TIME_BOOST_NEAR
    if gap_days <= 5:
        return ECO_TIME_BOOST_MID
    return 0.0


def lineage_similarity(a, b, lineage_type='actor', gap_days=None):
    cos   = _cosine(a.get('centroid', []), b.get('centroid', []))
    theme = _theme_anchor_overlap(a, b)
    actor = _actor_overlap(a, b)
    if lineage_type == 'ecosystem':
        base  = 0.55 * cos + 0.30 * theme + 0.15 * actor
        boost = _eco_time_boost(gap_days) if gap_days is not None else 0.0
        return round(base + boost, 4)
    return round(0.60 * cos + 0.25 * theme + 0.15 * actor, 4)


def _attach_centroids_from_embeddings(storms):
    """
    Compute mean centroid for each storm from its event_ids and the shared
    embeddings NPZ.  Mutates storms in-place.  Skips storms that already have
    a centroid or whose event_ids have no embedding hits.
    Returns (attached_count, missing_count).
    """
    needs = [s for s in storms if not s.get('centroid')]
    if not needs:
        return 0, 0

    npz_path = Path(__file__).parent.parent / 'data' / 'derived' / 'tech_ecosystem_embeddings.npz'
    if not npz_path.exists():
        return 0, len(needs)

    npz    = np.load(npz_path)
    emb    = npz['embeddings']
    id_idx = {str(eid): i for i, eid in enumerate(npz['event_ids'])}

    attached, missing = 0, 0
    for s in needs:
        idxs = [id_idx[eid] for eid in s.get('event_ids', []) if eid in id_idx]
        if not idxs:
            missing += 1
            continue
        s['centroid'] = emb[idxs].mean(axis=0).tolist()
        attached += 1
    return attached, missing


def _enrich_eco_storm_themes(storms):
    """
    Extract themes and domain_phrases for ecosystem storms that lack them.
    Uses the same pipeline as actor storm summaries: TF-IDF key terms,
    domain phrase matching, and bigrams over cluster_titles_topN.
    Mutates storms in-place.  Returns (enriched_count, empty_count).
    """
    from storm_summaries import (
        extract_key_terms, extract_domain_phrases, extract_bigrams,
        WEAK_DESCRIPTOR_WORDS,
    )

    enriched, empty = 0, 0
    for s in storms:
        if s.get('themes') and s.get('domain_phrases'):
            continue  # already populated

        titles = (
            s.get('cluster_titles_topN') or
            [e['title'] for e in s.get('representative_events', []) if e.get('title')]
        )
        actors = s.get('actors_involved') or s.get('actors') or []

        if not titles:
            s.setdefault('themes', [])
            s.setdefault('domain_phrases', [])
            s.setdefault('bigrams', [])
            empty += 1
            continue

        raw_terms    = extract_key_terms(titles, top_n=8, actors=actors)
        themes       = [t for t in raw_terms if t not in WEAK_DESCRIPTOR_WORDS][:5]
        domain_phr   = extract_domain_phrases(titles)[:3]
        bigrams      = extract_bigrams(titles, min_freq=1)[:3]  # min_freq=1: eco storms are small

        s['themes']         = themes
        s['domain_phrases'] = domain_phr
        s['bigrams']        = bigrams
        enriched += 1

    return enriched, empty


_ACTOR_NAMES = {'NVDA': 'Nvidia', 'AMD': 'AMD', 'AMZN': 'Amazon', 'GOOGL': 'Google',
                'MSFT': 'Microsoft', 'TSM': 'TSMC', 'ASML': 'ASML', 'AVGO': 'Broadcom'}

_LABEL_SKIP = {
    'market', 'news', 'update', 'activity', 'data', 'report', 'results', 'quarter',
    'company', 'stock', 'shares', 'deal', 'firm', 'group', 'new', 'top', 'gets',
    'raises', 'launch', 'planning', 'open', 'source', 'billion', 'valuation', 'funding',
}


def _title_case_phrase(p):
    return p.title().replace('Ai ', 'AI ').replace(' Ai ', ' AI ').replace('Ai\n', 'AI\n')


def _derive_eco_lineage_label(member_storms, actor_set):
    """Theme-first label for ecosystem lineages. Returns (label, evidence_dict)."""
    from collections import Counter

    dp_counts     = Counter()
    theme_counts  = Counter()
    bigram_counts = Counter()
    actor_counts  = Counter()

    for s in member_storms:
        for p in s.get('domain_phrases', []):
            dp_counts[p.lower()] += 1
        for t in s.get('themes', []):
            theme_counts[t.lower()] += 1
        for b in s.get('bigrams', []):
            bigram_counts[b.lower()] += 1
        for a in (s.get('actors') or ([s['actor']] if s.get('actor') else [])):
            actor_counts[a] += 1

    # Multi-word domain phrases shared by ≥1 storm (prefer shared, fall back to any)
    shared_dp = [p for p, c in dp_counts.most_common() if c >= 2 and len(p.split()) >= 2]
    any_dp    = [p for p, _ in dp_counts.most_common() if len(p.split()) >= 2]
    top_dp    = (shared_dp or any_dp)[:2]

    # Single-word themes not in skip list
    top_themes = [
        t for t, _ in theme_counts.most_common()
        if t not in _LABEL_SKIP and len(t) > 3
    ][:3]

    # Bigrams not dominated by skip words
    top_bigrams = [
        b for b, _ in bigram_counts.most_common()
        if not all(w in _LABEL_SKIP for w in b.split())
    ][:2]

    top_actors = [a for a, _ in actor_counts.most_common(2)]

    evidence = {
        'domain_phrases': top_dp,
        'themes':         top_themes,
        'bigrams':        top_bigrams,
        'actors':         top_actors,
    }

    # ── Label construction ────────────────────────────────────────────────────
    # Priority 1: two domain phrases → combine
    if len(top_dp) >= 2:
        base = f"{_title_case_phrase(top_dp[0])} {_title_case_phrase(top_dp[1])}"
    # Priority 2: one domain phrase + one strong theme
    elif top_dp and top_themes:
        base = f"{_title_case_phrase(top_dp[0])} {top_themes[0].title()}"
    # Priority 3: one domain phrase alone
    elif top_dp:
        base = _title_case_phrase(top_dp[0])
    # Priority 4: bigram + theme
    elif top_bigrams and top_themes:
        base = f"{_title_case_phrase(top_bigrams[0])} {top_themes[0].title()}"
    # Priority 5: themes only (2–3 words)
    elif len(top_themes) >= 2:
        base = ' '.join(t.title() for t in top_themes[:3])
    # Fallback: top actor(s) + best available theme/bigram
    else:
        actor_str = ' & '.join(_ACTOR_NAMES.get(a, a) for a in top_actors[:2])
        theme_str = (top_themes[0].title() if top_themes
                     else _title_case_phrase(top_bigrams[0]) if top_bigrams
                     else 'Ecosystem')
        base = f"{actor_str} {theme_str}" if actor_str else theme_str

    # Trim to ≤6 words, append 'Narrative'
    words = base.split()
    if len(words) > 6:
        base = ' '.join(words[:6])
    label = base + ' Narrative' if 'narrative' not in base.lower() else base
    return label, evidence


def _derive_lineage_label(member_storms, actor_set):
    from collections import Counter

    phrase_counts = Counter()
    for s in member_storms:
        for p in s.get('domain_phrases', []):
            phrase_counts[p.lower()] += 1
        for t in s.get('themes', []):
            phrase_counts[t.lower()] += 1

    _SKIP = {'market', 'news', 'update', 'activity', 'data', 'report', 'results', 'quarter'}
    top_phrases = [
        p for p, _ in phrase_counts.most_common(10)
        if p not in _SKIP and len(p.split()) >= 2
    ][:2]

    actor_counts = Counter()
    for s in member_storms:
        for a in (s.get('actors') or ([s['actor']] if s.get('actor') else [])):
            actor_counts[a] += 1
    top_actors = [a for a, _ in actor_counts.most_common(2)]

    try:
        import os
        if os.getenv('OPENAI_API_KEY'):
            from src.llm_naming import generate_llm_name, validate_llm_label
            rep_titles = [
                s.get('display_headline') or s.get('headline') or s.get('llm_headline', '')
                for s in member_storms
                if s.get('display_headline') or s.get('headline') or s.get('llm_headline')
            ][:3]
            evidence = {
                'actors':         top_actors,
                'domain_phrases': [p for p, _ in phrase_counts.most_common(8)],
                'themes':         list({t for s in member_storms for t in s.get('themes', [])})[:8],
                'bigrams':        list({b for s in member_storms for b in s.get('bigrams', [])})[:6],
                'representative_titles': rep_titles,
                'state':          member_storms[-1].get('state', 'stable'),
                'dominant_cluster_ratio': 0.7,
            }
            result = generate_llm_name(evidence)
            if result.get('llm_used') and result.get('llm_headline'):
                headline = result['llm_headline']
                valid, _, _ = validate_llm_label(headline, None, None)
                if valid:
                    label = headline if 'narrative' in headline.lower() else headline + ' Narrative'
                    return label
    except Exception:
        pass

    parts = []
    if top_actors:
        parts.append(' & '.join(_ACTOR_NAMES.get(a, a) for a in top_actors[:2]))
    if top_phrases:
        parts.append(top_phrases[0].title().replace('Ai ', 'AI ').replace(' Ai ', ' AI '))
    elif not parts:
        for s in member_storms:
            h = s.get('display_headline') or s.get('headline') or s.get('llm_headline', '')
            if h:
                parts.append(h[:40].rsplit(' ', 1)[0])
                break

    base = ' '.join(parts) if parts else f"Lineage {', '.join(list(actor_set)[:2])}"
    return base + ' Narrative' if 'narrative' not in base.lower() else base


def _second_pass_assignment(storms, lineage_groups, assigned, lineage_type='actor'):
    p2_threshold = LINEAGE_THRESHOLD_ECO if lineage_type == 'ecosystem' else LINEAGE_THRESHOLD_P2
    lineage_reps = {
        lid: _lineage_representative([storms[i] for i in group])
        for lid, group in enumerate(lineage_groups)
    }
    newly_assigned = {}
    for i in range(len(storms)):
        if i in assigned:
            continue
        storm = storms[i]
        best_score, best_lid = 0.0, None
        for lid, rep in lineage_reps.items():
            gap = _time_gap_days(storm, rep)
            if gap > LINEAGE_MAX_DAYS:
                continue
            if _theme_anchor_overlap(storm, rep) == 0.0 and _actor_overlap(storm, rep) == 0.0:
                continue
            score = lineage_similarity(storm, rep, lineage_type,
                                       gap_days=gap if lineage_type == 'ecosystem' else None)
            if score >= p2_threshold and score > best_score:
                best_score, best_lid = score, lid
        if best_lid is not None:
            lid_name = f"{'eco' if lineage_type == 'ecosystem' else 'actor'}_lineage_{best_lid:03d}"
            actor_ov = _actor_overlap(storm, lineage_reps[best_lid])
            theme_ov = _theme_anchor_overlap(storm, lineage_reps[best_lid])
            if lineage_type == 'ecosystem':
                print(f"[eco:p2_assign] {storm.get('storm_id','?')} → {lid_name}  "
                      f"score={best_score:.4f}  actor={actor_ov:.3f}  theme={theme_ov:.3f}")
            newly_assigned[i] = best_lid
            lineage_groups[best_lid].append(i)
            lineage_reps[best_lid] = _lineage_representative(
                [storms[j] for j in lineage_groups[best_lid]]
            )
    return newly_assigned


def _build_lineages(storms, id_prefix, lineage_type):
    """
    Core lineage grouping for a homogeneous list of storms (all actor OR all ecosystem).
    Returns (storms, lineage_summaries, stats).
    """
    n = len(storms)
    if n == 0:
        return storms, [], {'p1_assigned': 0, 'p2_assigned': 0, 'unassigned': 0, 'size_dist': {}}

    # Pass 1 — similarity matrix + BFS connected components
    sim = {}
    for i in range(n):
        for j in range(i + 1, n):
            if _time_gap_days(storms[i], storms[j]) > LINEAGE_MAX_DAYS:
                continue
            if lineage_type == 'ecosystem':
                cos_ij   = _cosine(storms[i].get('centroid', []), storms[j].get('centroid', []))
                theme_ij = _theme_anchor_overlap(storms[i], storms[j])
                actor_ij = _actor_overlap(storms[i], storms[j])
                # Gate: need actor OR theme overlap, unless cosine is high AND theme > 0
                high_cos_waiver = cos_ij >= LINEAGE_ECO_HIGH_COS and theme_ij > 0
                if not high_cos_waiver and theme_ij == 0.0 and actor_ij == 0.0:
                    continue
            threshold = LINEAGE_THRESHOLD_ECO if lineage_type == 'ecosystem' else LINEAGE_THRESHOLD
            gap_ij = _time_gap_days(storms[i], storms[j])
            s = lineage_similarity(storms[i], storms[j], lineage_type,
                                   gap_days=gap_ij if lineage_type == 'ecosystem' else None)
            if s >= threshold:
                sim[(i, j)] = s

    adj = defaultdict(set)
    for (i, j) in sim:
        adj[i].add(j)
        adj[j].add(i)

    assigned    = set()
    lin_groups  = []
    visited_any = set()
    for seed in sorted(range(n), key=lambda i: -len(adj[i])):
        if seed in visited_any:
            continue
        group, queue, bfs_visited = [], [seed], {seed}
        while queue:
            node = queue.pop()
            if node in assigned:
                continue
            group.append(node)
            bfs_visited.add(node)
            for nb in adj[node]:
                if nb not in bfs_visited and nb not in assigned:
                    bfs_visited.add(nb)
                    queue.append(nb)
        visited_any.update(bfs_visited)
        if len(group) >= 2:
            lin_groups.append(group)
            assigned.update(group)

    n_unassigned_p1 = n - len(assigned)
    lineage_summaries = []

    def _write_storm_fields(idx, lineage_id, label, pos, storm_count,
                            event_count, actor_set, start, latest, max_grav, p2):
        storms[idx].update({
            'lineage_id':            lineage_id,
            'lineage_label':         label,
            'lineage_position':      pos,
            'lineage_storm_count':   storm_count,
            'lineage_event_count':   event_count,
            'lineage_actor_set':     actor_set,
            'lineage_start_time':    start,
            'lineage_latest_time':   latest,
            'lineage_max_gravity':   round(max_grav, 4),
            'lineage_pass2_assigned': p2,
            'lineage_type':          lineage_type,
        })

    def _compute_meta(member_storms):
        actor_set = set()
        for s in member_storms:
            actor_set.update(s.get('actors', []) or ([s['actor']] if s.get('actor') else []))
        tss = []
        for s in member_storms:
            try:
                tss.append(_parse_ts(s.get('created_at', '')))
            except (ValueError, AttributeError):
                pass
        return (
            sorted(actor_set),
            sum(s.get('event_count', 0) for s in member_storms),
            max((s.get('gravity_score', 0) for s in member_storms), default=0),
            min(tss).isoformat() if tss else '',
            max(tss).isoformat() if tss else '',
        )

    for lid, group in enumerate(lin_groups):
        lineage_id    = f"{id_prefix}_{lid:03d}"
        members       = sorted(group, key=lambda i: storms[i].get('created_at', ''))
        member_storms = [storms[i] for i in members]
        actor_set, event_count, max_grav, start, latest = _compute_meta(member_storms)
        if lineage_type == 'ecosystem':
            label, _label_ev = _derive_eco_lineage_label(member_storms, actor_set)
        else:
            label = _derive_lineage_label(member_storms, actor_set)
        storm_count   = len(members)

        for pos, idx in enumerate(members):
            _write_storm_fields(idx, lineage_id, label, pos, storm_count,
                                event_count, actor_set, start, latest, max_grav, False)

        lineage_summaries.append({
            'lineage_id':            lineage_id,
            'lineage_type':          lineage_type,
            'lineage_label':         label,
            'lineage_storm_count':   storm_count,
            'lineage_event_count':   event_count,
            'lineage_actor_set':     actor_set,
            'lineage_start_time':    start,
            'lineage_latest_time':   latest,
            'lineage_gravity_score': round(max_grav, 4),
            'storm_ids':             [storms[i]['storm_id'] for i in members],
        })

    # Pass 2 — relaxed assignment of remaining singletons
    p2_assignments = _second_pass_assignment(storms, lin_groups, assigned, lineage_type)
    p2_by_lineage  = defaultdict(list)
    for storm_idx, lid in p2_assignments.items():
        p2_by_lineage[lid].append(storm_idx)
        assigned.add(storm_idx)

    for lid, extra_indices in p2_by_lineage.items():
        lineage_id    = f"{id_prefix}_{lid:03d}"
        all_members   = [storms[i] for i in lin_groups[lid]]
        actor_set, event_count, max_grav, start, latest = _compute_meta(all_members)
        if lineage_type == 'ecosystem':
            label, _label_ev = _derive_eco_lineage_label(all_members, actor_set)
        else:
            label = _derive_lineage_label(all_members, actor_set)
        storm_count   = len(lin_groups[lid])

        for pos, idx in enumerate(extra_indices):
            _write_storm_fields(idx, lineage_id, label,
                                storm_count - len(extra_indices) + pos,
                                storm_count, event_count, actor_set,
                                start, latest, max_grav, True)

        for summary in lineage_summaries:
            if summary['lineage_id'] == lineage_id:
                summary.update({
                    'lineage_label':         label,
                    'lineage_storm_count':   storm_count,
                    'lineage_event_count':   event_count,
                    'lineage_actor_set':     actor_set,
                    'lineage_start_time':    start,
                    'lineage_latest_time':   latest,
                    'lineage_gravity_score': round(max_grav, 4),
                    'storm_ids':             [storms[i]['storm_id'] for i in lin_groups[lid]],
                })
                break

    # Default all lineage fields to None for unassigned storms
    _FIELDS = [
        'lineage_id', 'lineage_label', 'lineage_position',
        'lineage_storm_count', 'lineage_event_count', 'lineage_actor_set',
        'lineage_start_time', 'lineage_latest_time', 'lineage_max_gravity',
        'lineage_pass2_assigned', 'lineage_type',
    ]
    for storm in storms:
        for f in _FIELDS:
            storm.setdefault(f, None)

    from collections import Counter as _Ctr
    stats = {
        'p1_assigned': len(assigned) - len(p2_assignments),
        'p2_assigned': len(p2_assignments),
        'unassigned':  sum(1 for s in storms if s.get('lineage_id') is None),
        'size_dist':   dict(sorted(_Ctr(len(g) for g in lin_groups).items())),
    }
    return storms, lineage_summaries, stats


def _eco_lineage_validation(eco_storms, eco_summaries):
    """
    Print ecosystem lineage validation diagnostics:
    - Per-lineage coherence metrics (mean pairwise cos, actor, theme overlap)
    - Assignment rate summary
    - Top-10 near-miss unassigned storms vs existing lineages
    """
    total   = len(eco_storms)
    assigned_storms = [s for s in eco_storms if s.get('lineage_id')]
    unassigned      = [s for s in eco_storms if not s.get('lineage_id')]
    rate = len(assigned_storms) / total * 100 if total else 0

    # Compute pairwise metrics across all ecosystem storms
    all_cos, all_actor, all_theme = [], [], []
    for i in range(total):
        for j in range(i + 1, total):
            all_cos.append(_cosine(eco_storms[i].get('centroid', []), eco_storms[j].get('centroid', [])))
            all_actor.append(_actor_overlap(eco_storms[i], eco_storms[j]))
            all_theme.append(_theme_anchor_overlap(eco_storms[i], eco_storms[j]))

    def _mean(vals):
        return sum(vals) / len(vals) if vals else 0.0

    NEAR_MISS_LOW_DIAG = LINEAGE_THRESHOLD_ECO - 0.06

    print(f"\n=== ECOSYSTEM LINEAGE FORMATION ===")
    print(f"  storms evaluated  : {total}")
    print(f"  lineages formed   : {len(eco_summaries)}")
    print(f"  mean cosine       : {_mean(all_cos):.3f}")
    print(f"  mean actor overlap: {_mean(all_actor):.3f}")
    print(f"  mean theme sim    : {_mean(all_theme):.3f}")

    print(f"[eco:validation] total={total}  assigned={len(assigned_storms)}  "
          f"unassigned={len(unassigned)}  rate={rate:.0f}%")

    # ── Per-lineage coherence block ───────────────────────────────────────────
    for summary in eco_summaries:
        lid     = summary['lineage_id']
        members = [s for s in eco_storms if s.get('lineage_id') == lid]

        # Log label derivation: old (title-based) vs new (theme-based)
        old_label = summary.get('lineage_label', '(none)')
        new_label, label_ev = _derive_eco_lineage_label(members, summary['lineage_actor_set'])
        label = new_label
        print(f"[eco:label] {lid}")
        print(f"  old label : {old_label}")
        print(f"  new label : {new_label}")
        print(f"  domain_phrases: {label_ev['domain_phrases']}")
        print(f"  themes        : {label_ev['themes']}")
        print(f"  bigrams       : {label_ev['bigrams']}")
        print(f"  actors        : {label_ev['actors']}")
        summary['lineage_label'] = new_label

        # Date range from created_at (normalised earlier)
        dates = sorted(
            s.get('created_at', '')[:10] for s in members if s.get('created_at')
        )
        date_range = f"{dates[0]} → {dates[-1]}" if dates else 'N/A'

        # Dominant theme anchors (union of themes + domain_phrases)
        from collections import Counter
        term_counts = Counter()
        for s in members:
            for t in s.get('themes', []) + s.get('domain_phrases', []):
                term_counts[t] += 1
        top_terms = [t for t, _ in term_counts.most_common(5)]

        # Mean pairwise metrics across member storms
        cos_vals, actor_vals, theme_vals = [], [], []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                cos_vals.append(_cosine(members[i].get('centroid', []), members[j].get('centroid', [])))
                actor_vals.append(_actor_overlap(members[i], members[j]))
                theme_vals.append(_theme_anchor_overlap(members[i], members[j]))

        def _mean(vals):
            return sum(vals) / len(vals) if vals else 0.0

        actor_set = summary['lineage_actor_set']
        print(f"\n[eco:lineage] {lid}")
        print(f"  label        : {label}")
        print(f"  storms       : {summary['lineage_storm_count']}")
        print(f"  events       : {summary['lineage_event_count']}")
        print(f"  actors ({len(actor_set)})   : {actor_set}")
        print(f"  date range   : {date_range}")
        print(f"  theme anchors: {top_terms if top_terms else '(none)'}")
        print(f"  mean cos     : {_mean(cos_vals):.3f}")
        print(f"  mean actor   : {_mean(actor_vals):.3f}")
        print(f"  mean theme   : {_mean(theme_vals):.3f}")

    # ── Unassigned near-miss table ────────────────────────────────────────────
    if not unassigned or not eco_summaries:
        return

    NEAR_MISS_LOW  = LINEAGE_THRESHOLD_ECO - 0.06   # flag range bottom (just below threshold)
    NEAR_MISS_HIGH = LINEAGE_THRESHOLD_ECO           # flag range top

    # Build lineage representatives from assigned members
    lin_reps = {}
    for summary in eco_summaries:
        lid     = summary['lineage_id']
        members = [s for s in eco_storms if s.get('lineage_id') == lid]
        lin_reps[lid] = _lineage_representative(members)

    candidates = []
    for storm in unassigned:
        for lid, rep in lin_reps.items():
            gap = _time_gap_days(storm, rep)
            cos   = _cosine(storm.get('centroid', []), rep.get('centroid', []))
            actor = _actor_overlap(storm, rep)
            theme = _theme_anchor_overlap(storm, rep)
            score = lineage_similarity(storm, rep, 'ecosystem', gap_days=gap)
            near_miss = NEAR_MISS_LOW <= score < NEAR_MISS_HIGH
            candidates.append({
                'storm_id':   storm['storm_id'],
                'lineage_id': lid,
                'cos':        cos,
                'actor':      actor,
                'theme':      theme,
                'score':      score,
                'gap':        gap,
                'near_miss':  near_miss,
            })

    candidates.sort(key=lambda c: -c['score'])
    top = candidates[:10]

    near_miss_count = sum(1 for c in candidates if c['near_miss'])
    print(f"  near misses detected: {near_miss_count}")

    print(f"\n[eco:unassigned] top candidates vs existing lineages "
          f"(threshold={LINEAGE_THRESHOLD_ECO}):")
    print(f"  {'storm_id':<22} {'lineage':<18} {'cos':>6} {'actor':>6} "
          f"{'theme':>6} {'score':>7} {'gap':>4}  flag")
    for c in top:
        flag = ' ◀ near-miss' if c['near_miss'] else ''
        print(f"  {c['storm_id']:<22} {c['lineage_id']:<18} {c['cos']:>6.3f} "
              f"{c['actor']:>6.3f} {c['theme']:>6.3f} {c['score']:>7.4f} "
              f"{c['gap']:>3}d{flag}")


def group_into_lineages(storms):
    """
    Split storms into actor and ecosystem tracks, build lineages independently,
    then return the combined storm list and lineage summaries.

    Ecosystem storms have centroids computed from embeddings before grouping
    if they are missing (common when loaded directly from ecosystem_storms.jsonl).

    Lineage ID namespaces:
      actor_lineage_### — actor storms only
      eco_lineage_###   — ecosystem storms only
    """
    actor_storms = [s for s in storms if not s.get('storm_id', '').startswith('eco_')]
    eco_storms   = [s for s in storms if s.get('storm_id', '').startswith('eco_')]

    # Attach centroids to eco storms from embeddings before grouping
    if eco_storms:
        attached, missing = _attach_centroids_from_embeddings(eco_storms)
        print(f"[lineage:ecosystem] centroid_attach: attached={attached}  missing={missing}")
        # Extract themes/domain_phrases so theme_overlap is non-zero during grouping
        enriched, empty = _enrich_eco_storm_themes(eco_storms)
        with_themes = sum(1 for s in eco_storms if s.get('themes'))
        pct = with_themes / len(eco_storms) * 100 if eco_storms else 0
        print(f"[lineage:ecosystem] theme_enrich:  enriched={enriched}  empty={empty}  "
              f"with_themes={with_themes}/{len(eco_storms)} ({pct:.0f}%)")
        for s in eco_storms[:10]:
            print(f"  {s['storm_id']:<25}  themes={s.get('themes',[])}  "
                  f"dp={s.get('domain_phrases',[])}")
        # Normalise field names so _build_lineages can use the same logic as actor storms
        for s in eco_storms:
            if not s.get('created_at') and s.get('start_time'):
                s['created_at'] = s['start_time']
            if not s.get('actors') and s.get('actors_involved'):
                s['actors'] = s['actors_involved']

    actor_storms, actor_summaries, actor_stats = _build_lineages(
        actor_storms, 'actor_lineage', 'actor'
    )
    eco_storms, eco_summaries, eco_stats = _build_lineages(
        eco_storms, 'eco_lineage', 'ecosystem'
    )

    # Validation log
    print(f"[lineage:actor]     lineages={len(actor_summaries)}  "
          f"p1={actor_stats['p1_assigned']}  p2={actor_stats['p2_assigned']}  "
          f"unassigned={actor_stats['unassigned']}")
    print(f"[lineage:ecosystem] lineages={len(eco_summaries)}  "
          f"p1={eco_stats['p1_assigned']}  p2={eco_stats['p2_assigned']}  "
          f"unassigned={eco_stats['unassigned']}")
    _eco_lineage_validation(eco_storms, eco_summaries)

    # Merge back into original order
    actor_map = {s['storm_id']: s for s in actor_storms}
    eco_map   = {s['storm_id']: s for s in eco_storms}
    for s in storms:
        sid = s['storm_id']
        if sid in actor_map:
            s.update(actor_map[sid])
        elif sid in eco_map:
            s.update(eco_map[sid])

    return storms, actor_summaries + eco_summaries
