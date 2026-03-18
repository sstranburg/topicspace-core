"""
Community overlay layer.
Maps community/Reddit posts onto existing institutional storms
without mixing them into core storm detection.
"""

import json
import numpy as np
from collections import defaultdict
from datetime import datetime, timedelta

# Defaults
MIN_POST_SCORE = 20
MIN_POST_COMMENTS = 10
SIMILARITY_THRESHOLD = 0.78
MAX_TIME_LAG_DAYS = 10
MIN_COMMUNITY_POSTS_FOR_OVERLAY = 3
MIN_POSTS_FOR_PRECURSOR_CLUSTER = 3

ALLOWED_SUBREDDITS = {
    'machinelearning', 'artificialintelligence', 'nvidia', 'amd',
    'hardware', 'semiconductors', 'cloudcomputing', 'investing',
    'stocks', 'datacenter', 'selfdrivingcars',
}


def load_community_posts(path):
    """Load community posts from JSONL."""
    posts = []
    with open(path) as f:
        for line in f:
            if line.strip():
                posts.append(json.loads(line))
    return posts


def filter_posts(posts):
    """Keep only reasonably strong community posts."""
    filtered = []
    for p in posts:
        score = p.get('score', 0) or 0
        comments = p.get('num_comments', 0) or 0
        sub = (p.get('subreddit', '') or '').lower()
        if (score >= MIN_POST_SCORE or comments >= MIN_POST_COMMENTS) and sub in ALLOWED_SUBREDDITS:
            filtered.append(p)
    return filtered


def _cosine_sim(a, b):
    """Cosine similarity between two vectors."""
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _parse_ts(ts_str):
    """Parse timestamp string to datetime."""
    if not ts_str:
        return None
    ts_str = ts_str.rstrip('Z')
    if '+' not in ts_str and 'T' in ts_str:
        ts_str += '+00:00'
    try:
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None


def attach_posts_to_storms(posts, storms, storm_centroids):
    """Map community posts onto existing institutional storms.

    Args:
        posts: filtered community posts (must have 'embedding' field)
        storms: list of storm dicts (actor + ecosystem)
        storm_centroids: dict of storm_id -> centroid numpy array

    Returns:
        dict of storm_id -> list of attached posts
        list of unmatched posts
    """
    attached = defaultdict(list)
    unmatched = []

    # Build storm time windows
    storm_times = {}
    for s in storms:
        ts = _parse_ts(s.get('created_at', s.get('updated_at', '')))
        if ts:
            storm_times[s['storm_id']] = ts

    for post in posts:
        post_emb = post.get('embedding')
        if post_emb is None:
            unmatched.append(post)
            continue
        post_emb = np.array(post_emb, dtype=np.float32)
        post_ts = _parse_ts(post.get('timestamp', ''))
        post_actors = set(a.upper() for a in (post.get('actors', []) or []))

        best_id = None
        best_sim = 0.0

        for storm in storms:
            sid = storm['storm_id']
            centroid = storm_centroids.get(sid)
            if centroid is None:
                continue

            sim = _cosine_sim(post_emb, centroid)
            if sim < SIMILARITY_THRESHOLD:
                continue

            # Time check
            if post_ts and sid in storm_times:
                lag = abs((post_ts - storm_times[sid]).days)
                if lag > MAX_TIME_LAG_DAYS:
                    continue

            # Actor overlap bonus
            storm_actor = storm.get('actor', '').upper()
            storm_actors = set(a.upper() for a in storm.get('actors', [storm_actor]))
            actor_bonus = 0.02 if post_actors & storm_actors else 0.0

            effective_sim = sim + actor_bonus
            if effective_sim > best_sim:
                best_sim = effective_sim
                best_id = sid

        if best_id:
            attached[best_id].append(post)
        else:
            unmatched.append(post)

    return dict(attached), unmatched


def _extract_themes(texts, top_n=10):
    """Extract simple keyword themes from texts."""
    from collections import Counter
    stop = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'shall', 'can', 'to', 'of', 'in', 'for',
            'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'between', 'out', 'off', 'over',
            'under', 'again', 'further', 'then', 'once', 'and', 'but', 'or', 'nor',
            'not', 'so', 'yet', 'both', 'each', 'few', 'more', 'most', 'other',
            'some', 'such', 'no', 'only', 'own', 'same', 'than', 'too', 'very',
            'just', 'about', 'up', 'its', 'it', 'this', 'that', 'these', 'those',
            'i', 'me', 'my', 'we', 'our', 'you', 'your', 'he', 'she', 'they',
            'them', 'their', 'what', 'which', 'who', 'whom', 'how', 'all', 'any',
            'if', 'also', 'like', 'get', 'got', 'going', 'really', 'think', 'know'}
    words = Counter()
    for text in texts:
        for w in text.lower().split():
            w = w.strip('.,!?()[]{}":;\'')
            if len(w) > 2 and w not in stop and w.isalpha():
                words[w] += 1
    return [w for w, _ in words.most_common(top_n)]


def compute_community_alignment(storm, attached_posts):
    """Compute semantic alignment between storm and community discussion.

    Uses keyword overlap between storm themes and community themes.
    """
    storm_themes = set()
    for field in ['dominant_cluster_terms', 'domain_phrases', 'cluster_titles_topN']:
        vals = storm.get(field, [])
        if isinstance(vals, list):
            for v in vals:
                storm_themes.update(v.lower().split())

    community_texts = [p.get('title', '') + ' ' + p.get('text', '') for p in attached_posts]
    community_themes = set(_extract_themes(community_texts, top_n=30))

    if not storm_themes or not community_themes:
        return {'community_alignment_score': 0.5, 'community_alignment_label': 'mixed'}

    overlap = storm_themes & community_themes
    score = len(overlap) / max(len(storm_themes), 1)
    score = min(1.0, score)

    if score >= 0.65:
        label = 'aligned'
    elif score >= 0.35:
        label = 'mixed'
    else:
        label = 'divergent'

    return {
        'community_alignment_score': round(score, 3),
        'community_alignment_label': label,
    }


def compute_community_divergence(storm, attached_posts):
    """Extract themes in community posts not strongly in the institutional storm."""
    storm_themes = set()
    for field in ['dominant_cluster_terms', 'domain_phrases', 'cluster_titles_topN']:
        vals = storm.get(field, [])
        if isinstance(vals, list):
            for v in vals:
                storm_themes.update(v.lower().split())

    community_texts = [p.get('title', '') + ' ' + p.get('text', '') for p in attached_posts]
    community_themes = _extract_themes(community_texts, top_n=20)

    divergent = [t for t in community_themes if t not in storm_themes]
    return divergent[:8]


def detect_community_precursors(unmatched_posts, min_cluster_size=MIN_POSTS_FOR_PRECURSOR_CLUSTER):
    """Find community clusters not matching any institutional storm.

    Groups unmatched posts by actor overlap and keyword similarity.
    """
    if len(unmatched_posts) < min_cluster_size:
        return []

    # Group by primary actor
    actor_groups = defaultdict(list)
    no_actor = []
    for p in unmatched_posts:
        actors = p.get('actors', [])
        if actors:
            for a in actors:
                actor_groups[a.upper()].append(p)
        else:
            no_actor.append(p)

    precursors = []
    precursor_id = 0

    for actor, posts in actor_groups.items():
        if len(posts) < min_cluster_size:
            continue
        precursor_id += 1
        texts = [p.get('title', '') + ' ' + p.get('text', '') for p in posts]
        themes = _extract_themes(texts, top_n=5)
        subs = list(set(p.get('subreddit', '') for p in posts))
        avg_score = sum(p.get('score', 0) for p in posts) / len(posts)

        label = f"{' '.join(themes[:3])} ({actor})" if themes else f"Community cluster ({actor})"
        precursors.append({
            'precursor_id': f'precursor_{precursor_id:02d}',
            'label': label,
            'top_subreddits': subs[:3],
            'post_count': len(posts),
            'avg_score': round(avg_score, 1),
            'actors': [actor],
            'key_themes': themes,
            'interpretation': f"Community discussion rising around {', '.join(themes[:3])} for {actor} with limited institutional storm coverage.",
        })

    # Also check no-actor group
    if len(no_actor) >= min_cluster_size:
        precursor_id += 1
        texts = [p.get('title', '') + ' ' + p.get('text', '') for p in no_actor]
        themes = _extract_themes(texts, top_n=5)
        subs = list(set(p.get('subreddit', '') for p in no_actor))
        avg_score = sum(p.get('score', 0) for p in no_actor) / len(no_actor)
        precursors.append({
            'precursor_id': f'precursor_{precursor_id:02d}',
            'label': f"{' '.join(themes[:3])}" if themes else "Unattached community cluster",
            'top_subreddits': subs[:3],
            'post_count': len(no_actor),
            'avg_score': round(avg_score, 1),
            'actors': [],
            'key_themes': themes,
            'interpretation': f"Community discussion around {', '.join(themes[:3])} not yet matched to institutional storms.",
        })

    return precursors


def build_community_perspective(storm, attached_posts, alignment, divergent_themes):
    """Build compact community perspective block for a storm."""
    subs = list(set(p.get('subreddit', '') for p in attached_posts))
    texts = [p.get('title', '') + ' ' + p.get('text', '') for p in attached_posts]
    key_themes = _extract_themes(texts, top_n=5)

    label = alignment['community_alignment_label']
    if label == 'aligned':
        interp = "Community discussion broadly reinforces the institutional narrative"
        if divergent_themes:
            interp += f", with additional focus on {', '.join(divergent_themes[:3])}."
        else:
            interp += "."
    elif label == 'divergent':
        if divergent_themes:
            interp = f"Community discussion diverges from institutional framing, emphasizing {', '.join(divergent_themes[:3])}."
        else:
            interp = "Community discussion diverges from the institutional narrative."
    else:
        interp = "Community discussion is mixed, suggesting the narrative is still unstable outside formal coverage."

    return {
        'community_post_count': len(attached_posts),
        'community_top_subreddits': subs[:3],
        'community_key_themes': key_themes,
        'community_alignment_score': alignment['community_alignment_score'],
        'community_alignment_label': label,
        'community_divergent_themes': divergent_themes,
        'community_interpretation': interp,
    }
