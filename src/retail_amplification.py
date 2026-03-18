"""
Retail Amplification Layer.

Detects retail investment advice events, embeds them, and attaches them to
lineages via a scored attachment rule:

    retail_attach_score = cosine_similarity + actor_overlap_boost

    actor_overlap_boost:
        0.20  if shared_actor_count >= 2
        0.10  if shared_actor_count == 1
        0.00  otherwise

Attachment requires:
    retail_attach_score >= ATTACH_THRESHOLD  AND  shared_actor_count >= 1

Retail events are NOT included in storm clustering or gravity calculations.
They are overlay/amplification signals only.
"""

import ast
import os
import re
from collections import defaultdict

import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

ATTACH_THRESHOLD  = 0.60
NEAR_MISS_LOW     = 0.55   # lower bound for near-miss logging
EMBEDDING_MODEL   = 'text-embedding-3-large'
EMBEDDING_API_URL = 'https://api.openai.com/v1/embeddings'

# Known retail/investment-advice publishers (lowercase substrings of URL or source_name)
RETAIL_PUBLISHERS = {
    'motley fool', 'fool.com', 'seekingalpha', 'seeking alpha',
    'investopedia', 'thestreet', 'marketbeat', 'zacks', 'benzinga',
    'stockanalysis', 'simply wall st', 'wisesheets', 'moneymorning',
    'kiplinger', 'barrons', 'marketwatch', 'yahoo finance',
}

RETAIL_TITLE_PATTERNS = re.compile(
    r'\b('
    r'stocks? to buy|should you buy|best stocks?|top stocks?|'
    r'buy (now|right now|today)|stocks? (to (own|hold|watch))|'
    r'(buy|sell) (the dip|signal)|set you up for life|'
    r'no.brainer (stock|buy)|unstoppable stock|'
    r'(under.the.radar|overlooked) stocks?|'
    r'(billionaire|warren buffett).*(bought?|sold?|owns?)|'
    r'(invest|investing) \$\d|'
    r'(1|2|3|top) (growth|dividend|ai|tech) stocks?|'
    r'prediction:.*stock|stock.*prediction|'
    r'(outperform|beat) the (market|s&p)|'
    r'(could|will|might) (double|triple|soar|skyrocket)'
    r')\b',
    re.IGNORECASE,
)


def is_retail_event(event: dict) -> bool:
    """Return True if event is retail investment advice content."""
    title = event.get('title', '') or ''
    url   = (event.get('url', '') or '').lower()
    try:
        meta = ast.literal_eval(event.get('metadata', '{}') or '{}')
        source_name = (meta.get('source_name', '') or '').lower()
    except Exception:
        source_name = ''

    for pub in RETAIL_PUBLISHERS:
        if pub in url or pub in source_name:
            return True
    return bool(RETAIL_TITLE_PATTERNS.search(title))


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _embed_texts(texts: list[str]) -> list[np.ndarray]:
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError('OPENAI_API_KEY not set in environment')
    results = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = requests.post(
            EMBEDDING_API_URL,
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': EMBEDDING_MODEL, 'input': batch},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()['data']
        data.sort(key=lambda x: x['index'])
        results.extend(np.array(d['embedding'], dtype=np.float32) for d in data)
        print(f'  Embedded {min(i + batch_size, len(texts))}/{len(texts)}')
    return results


def _lineage_centroid(rec: dict, emb_map: dict) -> np.ndarray | None:
    vecs = [emb_map[eid] for s in rec.get('storms', [])
            for eid in s.get('event_ids', []) if eid in emb_map]
    if not vecs:
        return None
    return np.mean(vecs, axis=0).astype(np.float32)


def _parse_event_actors(event: dict) -> set[str]:
    """Normalize actors from a raw event dict to a set of uppercase ticker strings."""
    raw = event.get('actors', [])
    if isinstance(raw, str):
        try:
            raw = ast.literal_eval(raw)
        except Exception:
            raw = []
    return {str(a).upper() for a in raw if a}


def _parse_lineage_actors(rec: dict) -> set[str]:
    """Collect all actor tickers referenced by storms in a lineage."""
    actors: set[str] = set()
    for storm in rec.get('storms', []):
        # actor storms: singular 'actor' field
        a = storm.get('actor', '')
        if a:
            actors.add(a.upper())
        # ecosystem storms: 'actors_involved' list
        for aa in (storm.get('actors_involved') or storm.get('actors') or []):
            actors.add(str(aa).upper())
    return actors


def _actor_overlap_boost(shared_count: int) -> float:
    if shared_count >= 2:
        return 0.20
    if shared_count == 1:
        return 0.10
    return 0.00


def _precision_diagnostics(
    records: list[dict],
    lineage_retail: dict,
    tie_break_log: list[dict],
    attached_total: int,
) -> dict:
    """Compute attachment precision diagnostics from per-lineage records."""
    all_attached = [e for rec in records for e in rec.get('retail_events', [])]

    # 1. Distribution by lineage
    by_lineage = []
    for rec in records:
        retail = rec.get('retail_events', [])
        if not retail:
            continue
        mean_score = round(sum(e['retail_attach_score'] for e in retail) / len(retail), 4)
        mean_actors = round(sum(e['shared_actor_count'] for e in retail) / len(retail), 4)
        by_lineage.append({
            'lineage_id':              rec['lineage_id'],
            'lineage_label':           rec.get('lineage_label', rec['lineage_id']),
            'retail_event_count':      len(retail),
            'mean_retail_attach_score': mean_score,
            'mean_shared_actor_count': mean_actors,
        })
    by_lineage.sort(key=lambda r: -r['retail_event_count'])

    # 2. Score histogram
    buckets = {'0.60-0.64': 0, '0.65-0.69': 0, '0.70-0.74': 0, '0.75+': 0}
    for e in all_attached:
        s = e['retail_attach_score']
        if s >= 0.75:   buckets['0.75+']     += 1
        elif s >= 0.70: buckets['0.70-0.74'] += 1
        elif s >= 0.65: buckets['0.65-0.69'] += 1
        else:           buckets['0.60-0.64'] += 1

    # 3. Actor overlap distribution
    actor_overlap = {
        'shared_1':      sum(1 for e in all_attached if e['shared_actor_count'] == 1),
        'shared_2_plus': sum(1 for e in all_attached if e['shared_actor_count'] >= 2),
    }

    # 4. Multi-candidate diagnostics (from tie_break_log)
    multi_candidate_count = len(tie_break_log)
    top_multi = []
    for t in sorted(tie_break_log, key=lambda x: -x['n_valid'])[:3]:
        cands = t['candidates']
        winner   = cands[0] if cands else {}
        runner_up = cands[1] if len(cands) > 1 else {}
        top_multi.append({
            'event_id':          t['event_id'],
            'title':             t['title'],
            'n_valid':           t['n_valid'],
            'winner_lineage':    winner.get('lineage_id'),
            'winner_score':      winner.get('retail_attach_score'),
            'runner_up_lineage': runner_up.get('lineage_id'),
            'runner_up_score':   runner_up.get('retail_attach_score'),
        })

    # 5. Concentration check
    if attached_total > 0:
        counts_sorted = sorted(
            (rec['retail_event_count'] for rec in records if rec['retail_event_count'] > 0),
            reverse=True,
        )
        top1_pct  = round(counts_sorted[0] / attached_total, 4) if counts_sorted else 0.0
        top3_pct  = round(sum(counts_sorted[:3]) / attached_total, 4) if counts_sorted else 0.0
    else:
        top1_pct = top3_pct = 0.0

    return {
        'by_lineage':           by_lineage,
        'score_histogram':      buckets,
        'actor_overlap':        actor_overlap,
        'multi_candidate_count': multi_candidate_count,
        'top_multi_candidates': top_multi,
        'concentration_top1':   top1_pct,
        'concentration_top3':   top3_pct,
    }


def build_retail_amplification(
    all_events: list[dict],
    filtered_ids: set[str],
    lineages: list[dict],
    emb_map: dict,
) -> tuple[list[dict], dict]:
    """
    Detect retail events, embed them, attach to lineages.

    Attachment rule:
        retail_attach_score = cosine_similarity + actor_overlap_boost
        attach if retail_attach_score >= ATTACH_THRESHOLD AND shared_actor_count >= 1

    Returns
    -------
    records : list of per-lineage amplification dicts
    stats   : validation stats dict (retail_total, attached, attachment_rate,
              top_attached, near_misses, by_lineage)
    """
    retail_events = [
        e for e in all_events
        if e['event_id'] not in filtered_ids
        and e.get('source') != 'anchor'
        and is_retail_event(e)
    ]

    if not retail_events:
        return [], {'retail_total': 0, 'attached': 0, 'attachment_rate': 0.0,
                    'top_attached': [], 'near_misses': [], 'by_lineage': {}}

    print(f'  Retail events detected: {len(retail_events)}')

    texts = [f"{e.get('title', '')} {e.get('text', '')[:200]}".strip() for e in retail_events]
    embeddings = _embed_texts(texts)

    lin_centroids = {rec['lineage_id']: _lineage_centroid(rec, emb_map)
                     for rec in lineages}
    lin_centroids = {k: v for k, v in lin_centroids.items() if v is not None}

    lin_actors  = {rec['lineage_id']: _parse_lineage_actors(rec) for rec in lineages}
    lin_gravity = {rec['lineage_id']: rec.get('lineage_max_gravity', 0.0) for rec in lineages}

    lineage_retail: dict[str, list] = defaultdict(list)
    all_candidates = []   # for validation log (attached + near-misses)
    tie_break_log:  list[dict] = []  # events with multiple valid candidates

    for event, emb in zip(retail_events, embeddings):
        event_actors = _parse_event_actors(event)

        valid:     list[dict] = []  # all candidates meeting threshold
        near_miss: list[dict] = []

        for lid, centroid in lin_centroids.items():
            cos_sim      = _cosine_sim(emb, centroid)
            shared       = event_actors & lin_actors.get(lid, set())
            shared_count = len(shared)
            boost        = _actor_overlap_boost(shared_count)
            attach_score = cos_sim + boost

            candidate = {
                'event_id':            event['event_id'],
                'title':               event.get('title', ''),
                'source':              event.get('source', ''),
                'timestamp':           event.get('timestamp', ''),
                'lineage_id':          lid,
                'cosine_similarity':   round(cos_sim, 4),
                'shared_actor_count':  shared_count,
                'actor_overlap_boost': round(boost, 2),
                'retail_attach_score': round(attach_score, 4),
                'lineage_gravity':     round(lin_gravity.get(lid, 0.0), 4),
            }

            if attach_score >= ATTACH_THRESHOLD and shared_count >= 1:
                valid.append(candidate)
            elif (NEAR_MISS_LOW <= attach_score < ATTACH_THRESHOLD
                    or (attach_score >= ATTACH_THRESHOLD and shared_count == 0)):
                near_miss.append(candidate)

        all_candidates.extend({**c, '_outcome': 'near_miss'} for c in near_miss)

        if not valid:
            continue

        # Tiebreaker: 1) shared_actor_count desc  2) retail_attach_score desc  3) lineage_gravity desc
        best = max(valid, key=lambda c: (
            c['shared_actor_count'],
            c['retail_attach_score'],
            c['lineage_gravity'],
        ))

        if len(valid) > 1:
            tie_break_log.append({
                'event_id':   event['event_id'],
                'title':      event.get('title', ''),
                'n_valid':    len(valid),
                'selected':   best['lineage_id'],
                'candidates': [
                    {'lineage_id':          c['lineage_id'],
                     'shared_actor_count':  c['shared_actor_count'],
                     'retail_attach_score': c['retail_attach_score'],
                     'lineage_gravity':     c['lineage_gravity']}
                    for c in sorted(valid, key=lambda c: (
                        -c['shared_actor_count'],
                        -c['retail_attach_score'],
                        -c['lineage_gravity'],
                    ))
                ],
            })

        lineage_retail[best['lineage_id']].append(best)
        all_candidates.append({**best, '_outcome': 'attached'})

    # Per-lineage summary records
    records = []
    for rec in lineages:
        lid    = rec['lineage_id']
        retail = lineage_retail.get(lid, [])
        inst   = rec.get('lineage_event_count', 0)
        total  = inst + len(retail)
        ratio  = round(len(retail) / total, 4) if total > 0 else 0.0
        sources = sorted({e['source'] for e in retail})
        mean_score = (round(sum(e['retail_attach_score'] for e in retail) / len(retail), 4)
                      if retail else None)
        records.append({
            'lineage_id':                  lid,
            'lineage_label':               rec.get('label', lid),
            'lineage_type':                rec.get('lineage_type', 'actor'),
            'retail_event_count':          len(retail),
            'institutional_event_count':   inst,
            'retail_amplification_ratio':  ratio,
            'retail_source_count':         len(sources),
            'retail_sources':              sources,
            'mean_retail_attach_score':    mean_score,
            'retail_events':               retail,
        })

    attached_total = sum(len(v) for v in lineage_retail.values())
    attachment_rate = round(attached_total / len(retail_events), 4) if retail_events else 0.0

    top_attached = sorted(
        [c for c in all_candidates if c['_outcome'] == 'attached'],
        key=lambda c: -c['retail_attach_score']
    )[:20]
    near_misses = sorted(
        [c for c in all_candidates if c['_outcome'] == 'near_miss'],
        key=lambda c: -c['retail_attach_score']
    )

    precision = _precision_diagnostics(records, lineage_retail, tie_break_log, attached_total)

    stats = {
        'retail_total':    len(retail_events),
        'attached':        attached_total,
        'attachment_rate': attachment_rate,
        'top_attached':    [{k: v for k, v in c.items() if k != '_outcome'} for c in top_attached],
        'near_misses':     [{k: v for k, v in c.items() if k != '_outcome'} for c in near_misses],
        'tie_break_log':   tie_break_log,
        'by_lineage':      {lid: len(v) for lid, v in lineage_retail.items()},
        'precision':       precision,
    }
    return records, stats
