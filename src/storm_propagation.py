"""
Storm propagation detection and analysis.
"""
import math
from datetime import datetime
from typing import List, Dict, Tuple, Set
from collections import defaultdict

# Configuration constants
MIN_PROPAGATION_LAG_DAYS = 0
MAX_PROPAGATION_LAG_DAYS = 10  # Slightly relaxed
MIN_PROPAGATION_LAG_HOURS = 0.5   # < 30 min = same-article noise
MAX_PROPAGATION_LAG_HOURS = 168.0  # > 7 days = no causal relationship
PROPAGATION_SIMILARITY_THRESHOLD = 0.65  # Slightly lower
MIN_THEME_OVERLAP = 0.0  # No hard floor - let scoring handle quality
PROPAGATION_SCORE_THRESHOLD = 0.55  # Moderate threshold
CHAIN_EDGE_SCORE_THRESHOLD = 0.70  # For high-quality chains
MIN_CHAIN_LENGTH = 3

# Scoring weights - rebalanced
SEMANTIC_WEIGHT = 0.35  # Reduced from 0.50
THEME_WEIGHT = 0.45  # Increased from 0.30
TIME_WEIGHT = 0.20  # Same

# Noise filtering
NOISE_TERMS = {
    "wall street", "dow", "s&p", "nasdaq", "stock market", "oil prices",
    "trillion-dollar", "bullish", "bearish", "options trading",
    "share price", "stocks to buy", "market sentiment", "valuation",
    "latest options", "price target", "final trades", "motley fool"
}
NOISE_PENALTY = 0.5

# Actor roles for pathway detection
ACTOR_ROLES = {
    "NVDA": "gpu_vendor",
    "AMD": "gpu_vendor",
    "TSM": "foundry",
    "ASML": "equipment",
    "AVGO": "networking",
    "MSFT": "hyperscaler",
    "AMZN": "hyperscaler",
    "GOOGL": "hyperscaler"
}

# Plausible flows for pathway bonus
PLAUSIBLE_FLOWS = {
    ("gpu_vendor", "foundry"),
    ("foundry", "networking"),
    ("gpu_vendor", "hyperscaler"),
    ("hyperscaler", "foundry"),
    ("equipment", "foundry"),
    ("foundry", "gpu_vendor")
}
ACTOR_PATHWAY_BONUS = 1.10


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))
    
    if mag_a == 0 or mag_b == 0:
        return 0.0
    
    return dot_product / (mag_a * mag_b)


def filter_noise_terms(themes: set) -> set:
    """Remove noise terms from theme set."""
    return {t for t in themes if t.lower() not in NOISE_TERMS}


def compute_theme_overlap(storm_a: dict, storm_b: dict) -> float:
    """Compute weighted theme overlap between two storms."""
    # Collect themes with weights
    themes_a = {}
    themes_b = {}
    
    # Themes (weight 3)
    for t in storm_a.get('themes', []):
        themes_a[t] = 3
    for t in storm_b.get('themes', []):
        themes_b[t] = 3
    
    # Domain phrases (weight 2)
    for t in storm_a.get('domain_phrases', []):
        themes_a[t] = max(themes_a.get(t, 0), 2)
    for t in storm_b.get('domain_phrases', []):
        themes_b[t] = max(themes_b.get(t, 0), 2)
    
    # Entity actions (weight 2)
    for t in storm_a.get('entity_actions', []):
        themes_a[t] = max(themes_a.get(t, 0), 2)
    for t in storm_b.get('entity_actions', []):
        themes_b[t] = max(themes_b.get(t, 0), 2)
    
    # Bigrams (weight 1)
    for t in storm_a.get('bigrams', []):
        themes_a[t] = max(themes_a.get(t, 0), 1)
    for t in storm_b.get('bigrams', []):
        themes_b[t] = max(themes_b.get(t, 0), 1)
    
    # Filter noise
    themes_a = {k: v for k, v in themes_a.items() if k.lower() not in NOISE_TERMS}
    themes_b = {k: v for k, v in themes_b.items() if k.lower() not in NOISE_TERMS}
    
    if not themes_a or not themes_b:
        return 0.0
    
    # Weighted Jaccard
    intersection_weight = sum(min(themes_a.get(t, 0), themes_b.get(t, 0)) for t in set(themes_a) & set(themes_b))
    union_weight = sum(max(themes_a.get(t, 0), themes_b.get(t, 0)) for t in set(themes_a) | set(themes_b))
    
    return intersection_weight / union_weight if union_weight > 0 else 0.0


def find_propagation_candidates(storms: List[dict]) -> List[Tuple[dict, dict]]:
    """Find candidate storm pairs for propagation analysis."""
    candidates = []
    
    for i, storm_a in enumerate(storms):
        for j, storm_b in enumerate(storms):
            if i >= j:
                continue
            
            # Required: different actors
            if storm_a['actor'] == storm_b['actor']:
                continue
            
            # Parse timestamps
            ts_a = storm_a['created_at'].rstrip('Z').replace('+00:00Z', '+00:00')
            ts_b = storm_b['created_at'].rstrip('Z').replace('+00:00Z', '+00:00')
            if not ts_a.endswith('+00:00'):
                ts_a += '+00:00'
            if not ts_b.endswith('+00:00'):
                ts_b += '+00:00'
            start_a = datetime.fromisoformat(ts_a)
            start_b = datetime.fromisoformat(ts_b)
            
            # Required: B starts after A
            if start_b <= start_a:
                continue
            
            # Time lag constraint (hour precision to catch sub-day noise)
            lag_hours = (start_b - start_a).total_seconds() / 3600
            if lag_hours < MIN_PROPAGATION_LAG_HOURS or lag_hours > MAX_PROPAGATION_LAG_HOURS:
                continue
            lag_days = (start_b - start_a).days
            
            candidates.append((storm_a, storm_b))
    
    return candidates


def compute_propagation_score(storm_a: dict, storm_b: dict, lag_days: int) -> Tuple[float, dict]:
    """Compute propagation score with pathway bonus and noise penalty."""
    # Semantic similarity
    centroid_a = storm_a.get('centroid', [])
    centroid_b = storm_b.get('centroid', [])
    semantic_sim = cosine_similarity(centroid_a, centroid_b)
    
    # Theme overlap
    theme_overlap = compute_theme_overlap(storm_a, storm_b)
    
    # Time decay
    time_decay = math.exp(-lag_days / 2.0)
    
    # Size factor
    size_a = storm_a.get('event_count', 1)
    size_b = storm_b.get('event_count', 1)
    size_factor = math.log1p(min(size_a, size_b))
    
    # Base score
    base_score = (
        SEMANTIC_WEIGHT * semantic_sim +
        THEME_WEIGHT * theme_overlap +
        TIME_WEIGHT * time_decay
    ) * size_factor
    
    # Actor pathway bonus
    pathway_bonus = 1.0
    actor_a = storm_a.get('actor')
    actor_b = storm_b.get('actor')
    role_a = ACTOR_ROLES.get(actor_a)
    role_b = ACTOR_ROLES.get(actor_b)
    if role_a and role_b and (role_a, role_b) in PLAUSIBLE_FLOWS:
        pathway_bonus = ACTOR_PATHWAY_BONUS
    
    # Noise penalty
    noise_penalty = 1.0
    themes_a = set(storm_a.get('themes', [])) | set(storm_a.get('bigrams', []))
    themes_b = set(storm_b.get('themes', [])) | set(storm_b.get('bigrams', []))
    shared = themes_a & themes_b
    if shared and any(t.lower() in NOISE_TERMS for t in shared):
        noise_penalty = NOISE_PENALTY
    
    score = base_score * pathway_bonus * noise_penalty
    
    metrics = {
        'semantic_similarity': semantic_sim,
        'theme_overlap': theme_overlap,
        'time_decay': time_decay,
        'size_factor': size_factor,
        'pathway_bonus': pathway_bonus,
        'noise_penalty': noise_penalty
    }
    
    return score, metrics


def detect_propagation_edges(storms: List[dict]) -> List[dict]:
    """Detect propagation edges between storms."""
    candidates = find_propagation_candidates(storms)
    edges = []
    
    for storm_a, storm_b in candidates:
        # Parse timestamps
        ts_a = storm_a['created_at'].rstrip('Z').replace('+00:00Z', '+00:00')
        ts_b = storm_b['created_at'].rstrip('Z').replace('+00:00Z', '+00:00')
        if not ts_a.endswith('+00:00'):
            ts_a += '+00:00'
        if not ts_b.endswith('+00:00'):
            ts_b += '+00:00'
        start_a = datetime.fromisoformat(ts_a)
        start_b = datetime.fromisoformat(ts_b)
        lag_days = (start_b - start_a).days
        
        # Compute semantic similarity
        centroid_a = storm_a.get('centroid', [])
        centroid_b = storm_b.get('centroid', [])
        semantic_sim = cosine_similarity(centroid_a, centroid_b)
        
        # Filter by similarity threshold
        if semantic_sim < PROPAGATION_SIMILARITY_THRESHOLD:
            continue
        
        # Compute theme overlap
        theme_overlap = compute_theme_overlap(storm_a, storm_b)
        
        # Filter by theme overlap threshold
        if theme_overlap < MIN_THEME_OVERLAP:
            continue
        
        # Compute propagation score
        score, metrics = compute_propagation_score(storm_a, storm_b, lag_days)
        
        # Filter by score threshold
        if score < PROPAGATION_SCORE_THRESHOLD:
            continue
        
        # Extract shared themes
        themes_a = set(storm_a.get('themes', []))
        themes_b = set(storm_b.get('themes', []))
        shared_themes = list(themes_a & themes_b)
        
        # Get representative titles
        rep_events_a = storm_a.get('representative_events', [])
        rep_events_b = storm_b.get('representative_events', [])
        source_headline = rep_events_a[0]['title'] if rep_events_a else ""
        target_headline = rep_events_b[0]['title'] if rep_events_b else ""
        
        lag_hours = (start_b - start_a).total_seconds() / 3600

        edge = {
            'source_storm_id': storm_a['storm_id'],
            'target_storm_id': storm_b['storm_id'],
            'source_actor': storm_a['actor'],
            'target_actor': storm_b['actor'],
            'source_lane': storm_a.get('narrative_lane', 'default'),
            'target_lane': storm_b.get('narrative_lane', 'default'),
            'lag_days': lag_days,
            'lag_hours': lag_hours,
            'semantic_similarity': semantic_sim,
            'theme_overlap': theme_overlap,
            'propagation_score': score,
            'source_state': storm_a.get('state', 'unknown'),
            'target_state': storm_b.get('state', 'unknown'),
            'shared_themes': shared_themes[:5],  # Top 5
            'source_headline': source_headline,
            'target_headline': target_headline
        }
        
        edges.append(edge)
    
    return edges


def build_actor_propagation_graph(edges: List[dict]) -> Dict[str, dict]:
    """Build actor-level propagation graph from storm edges."""
    graph = defaultdict(lambda: {
        'edge_count': 0,
        'scores': [],
        'lags': [],
        'themes': defaultdict(int)
    })
    
    for edge in edges:
        key = f"{edge['source_actor']}->{edge['target_actor']}"
        graph[key]['edge_count'] += 1
        graph[key]['scores'].append(edge['propagation_score'])
        graph[key]['lags'].append(edge['lag_days'])
        
        for theme in edge['shared_themes']:
            graph[key]['themes'][theme] += 1
    
    # Aggregate metrics
    result = {}
    for key, data in graph.items():
        top_themes = sorted(data['themes'].items(), key=lambda x: x[1], reverse=True)[:3]
        result[key] = {
            'edge_count': data['edge_count'],
            'mean_score': sum(data['scores']) / len(data['scores']),
            'avg_lag_days': sum(data['lags']) / len(data['lags']),
            'shared_themes': [t[0] for t in top_themes]
        }
    
    return result


MAX_CHAIN_LENGTH = 5  # Cap DFS depth to prevent combinatorial explosion
MAX_CHAINS = 2000    # Hard cap on chains collected


def detect_propagation_chains(edges: List[dict], min_length: int = MIN_CHAIN_LENGTH) -> List[dict]:
    """Detect propagation chains using DFS with stricter edge filtering."""
    # Build adjacency list with high-quality edges only
    graph = defaultdict(list)
    for edge in edges:
        if edge['propagation_score'] >= CHAIN_EDGE_SCORE_THRESHOLD:
            graph[edge['source_actor']].append({
                'target': edge['target_actor'],
                'score': edge['propagation_score'],
                'themes': edge['shared_themes']
            })

    chains = []

    def dfs(actor: str, path: List[str], scores: List[float], themes: List[Set[str]]):
        if len(chains) >= MAX_CHAINS:
            return

        if len(path) >= min_length:
            # Compute chain metrics
            mean_score = sum(scores) / len(scores)
            common_themes = set.intersection(*themes) if themes else set()

            chains.append({
                'actors': path.copy(),
                'edge_scores': scores.copy(),
                'mean_score': mean_score,
                'shared_theme_hint': ', '.join(list(common_themes)[:3]) if common_themes else 'mixed'
            })

        if len(path) >= MAX_CHAIN_LENGTH:
            return

        for neighbor in graph[actor]:
            if len(chains) >= MAX_CHAINS:
                return
            if neighbor['target'] not in path:  # Avoid cycles
                dfs(
                    neighbor['target'],
                    path + [neighbor['target']],
                    scores + [neighbor['score']],
                    themes + [set(neighbor['themes'])]
                )

    # Start DFS from each actor
    all_actors = set(graph.keys())
    for actor in all_actors:
        dfs(actor, [actor], [], [])
    
    return chains


def interpret_propagation(edge: dict) -> str:
    """Generate plain English interpretation of a propagation edge."""
    source = edge['source_actor']
    target = edge['target_actor']
    lag = edge['lag_days']
    themes = edge['shared_themes']
    
    theme_str = ', '.join(themes[:2]) if themes else 'related'
    
    return f"{theme_str.capitalize()} narrative appears to propagate from {source} to {target} with a {lag}-day lag."


def compute_actor_roles(edges: List[dict]) -> Dict[str, dict]:
    """Compute propagation roles for each actor with stricter classification."""
    roles = defaultdict(lambda: {
        'outgoing_edges': 0,
        'incoming_edges': 0,
        'outgoing_scores': [],
        'incoming_scores': []
    })
    
    for edge in edges:
        source = edge['source_actor']
        target = edge['target_actor']
        score = edge['propagation_score']
        
        roles[source]['outgoing_edges'] += 1
        roles[source]['outgoing_scores'].append(score)
        
        roles[target]['incoming_edges'] += 1
        roles[target]['incoming_scores'].append(score)
    
    # Classify roles
    result = {}
    for actor, data in roles.items():
        out_count = data['outgoing_edges']
        in_count = data['incoming_edges']
        
        mean_out = sum(data['outgoing_scores']) / len(data['outgoing_scores']) if data['outgoing_scores'] else 0
        mean_in = sum(data['incoming_scores']) / len(data['incoming_scores']) if data['incoming_scores'] else 0
        
        # Stricter classification
        if out_count >= 3 and in_count == 0:
            role = 'originator'
        elif in_count >= 3 and out_count == 0:
            role = 'receiver'
        elif out_count > in_count * 2:
            role = 'originator'
        elif in_count > out_count * 2:
            role = 'receiver'
        elif out_count > 0 and in_count > 0:
            role = 'bridge'
        else:
            role = 'isolated'
        
        result[actor] = {
            'role': role,
            'outgoing_edges': out_count,
            'incoming_edges': in_count,
            'mean_outgoing_score': mean_out,
            'mean_incoming_score': mean_in
        }
    
    return result



def detect_semantic_pathways(edges: List[dict]) -> List[dict]:
    """Detect semantic pathways (narrative corridors) across chains."""
    # Build chains first
    chains = detect_propagation_chains(edges, min_length=3)
    
    pathways = []
    for chain in chains:
        actors = chain['actors']
        
        # Find edges in chain
        chain_edges = []
        for i in range(len(actors) - 1):
            for edge in edges:
                if edge['source_actor'] == actors[i] and edge['target_actor'] == actors[i+1]:
                    chain_edges.append(edge)
                    break
        
        if len(chain_edges) < 2:
            continue
        
        # Extract themes from each edge
        edge_themes = [set(e['shared_themes']) for e in chain_edges]
        
        # Find persistent themes (appear in all edges)
        persistent_themes = set.intersection(*edge_themes) if edge_themes else set()
        
        # Find corridor themes (appear in 50%+ of edges)
        theme_counts = defaultdict(int)
        for themes in edge_themes:
            for t in themes:
                theme_counts[t] += 1
        corridor_themes = {t for t, c in theme_counts.items() if c >= len(edge_themes) * 0.5}
        
        if not corridor_themes:
            continue
        
        # Check for plausible actor flow
        has_plausible_flow = False
        for i in range(len(actors) - 1):
            role_a = ACTOR_ROLES.get(actors[i])
            role_b = ACTOR_ROLES.get(actors[i+1])
            if role_a and role_b and (role_a, role_b) in PLAUSIBLE_FLOWS:
                has_plausible_flow = True
                break
        
        pathway = {
            'actors': actors,
            'persistent_themes': list(persistent_themes),
            'corridor_themes': list(corridor_themes),
            'edge_count': len(chain_edges),
            'mean_score': chain['mean_score'],
            'has_plausible_flow': has_plausible_flow
        }
        
        pathways.append(pathway)
    
    # Sort by mean score
    pathways.sort(key=lambda x: x['mean_score'], reverse=True)

    return pathways


def compute_actor_lead_lag(edges: List[dict], min_count: int = 5) -> List[dict]:
    """Aggregate propagation edges by actor pair to identify lead-lag relationships.

    Returns list of records sorted by count descending.
    Each record: source_actor, target_actor, count, mean_lag_hours, median_lag_hours,
                 std_lag_hours, source_lane (dominant), target_lane (dominant)
    Only includes pairs with count >= min_count and lag_hours > 0.
    """
    pair_data: Dict[Tuple[str, str], dict] = defaultdict(lambda: {
        'lags': [],
        'source_lanes': defaultdict(int),
        'target_lanes': defaultdict(int),
    })

    for edge in edges:
        lag = edge.get('lag_hours', 0)
        if lag <= 0:
            continue
        key = (edge['source_actor'], edge['target_actor'])
        pair_data[key]['lags'].append(lag)
        pair_data[key]['source_lanes'][edge.get('source_lane', 'default')] += 1
        pair_data[key]['target_lanes'][edge.get('target_lane', 'default')] += 1

    results = []
    for (src, tgt), data in pair_data.items():
        lags = data['lags']
        if len(lags) < min_count:
            continue
        mean_lag = sum(lags) / len(lags)
        sorted_lags = sorted(lags)
        n = len(sorted_lags)
        mid = n // 2
        median_lag = sorted_lags[mid] if n % 2 else (sorted_lags[mid - 1] + sorted_lags[mid]) / 2
        variance = sum((x - mean_lag) ** 2 for x in lags) / n
        std_lag = math.sqrt(variance)
        src_lane = max(data['source_lanes'], key=data['source_lanes'].get)
        tgt_lane = max(data['target_lanes'], key=data['target_lanes'].get)
        results.append({
            'source_actor': src,
            'target_actor': tgt,
            'count': len(lags),
            'mean_lag_hours': round(mean_lag, 1),
            'median_lag_hours': round(median_lag, 1),
            'std_lag_hours': round(std_lag, 1),
            'source_lane': src_lane,
            'target_lane': tgt_lane,
        })

    results.sort(key=lambda x: x['count'], reverse=True)
    return results


def aggregate_lane_transitions(edges: List[dict]) -> List[dict]:
    """Aggregate lane transitions across all propagation edges.

    Returns list of transition records sorted by count descending.
    Each record: source_lane, target_lane, count, avg_lag_hours, top_actors
    """
    transition_data: Dict[Tuple[str, str], dict] = defaultdict(lambda: {
        'count': 0,
        'lag_hours': [],
        'actor_pairs': defaultdict(int)
    })

    for edge in edges:
        src_lane = edge.get('source_lane', 'default')
        tgt_lane = edge.get('target_lane', 'default')
        key = (src_lane, tgt_lane)
        transition_data[key]['count'] += 1
        if 'lag_hours' in edge:
            transition_data[key]['lag_hours'].append(edge['lag_hours'])
        pair = f"{edge['source_actor']}→{edge['target_actor']}"
        transition_data[key]['actor_pairs'][pair] += 1

    results = []
    for (src_lane, tgt_lane), data in transition_data.items():
        lags = data['lag_hours']
        avg_lag = sum(lags) / len(lags) if lags else 0.0
        top_actors = sorted(data['actor_pairs'].items(), key=lambda x: x[1], reverse=True)[:3]
        results.append({
            'source_lane': src_lane,
            'target_lane': tgt_lane,
            'count': data['count'],
            'avg_lag_hours': round(avg_lag, 1),
            'top_actors': [p for p, _ in top_actors]
        })

    results.sort(key=lambda x: x['count'], reverse=True)
    return results
