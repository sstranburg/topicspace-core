import numpy as np
import math
from datetime import datetime
from collections import defaultdict
from src.narrative_lane import classify_narrative_lane

MAX_STORM_EVENTS = 150


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return float(np.dot(a, b))


def time_decay(delta_days: float, tau_days: float) -> float:
    """Compute exponential time decay."""
    return math.exp(-abs(delta_days) / tau_days)


def compute_affinity(event_i: dict, event_j: dict, embeddings: np.ndarray, tau_days: float) -> float:
    """Compute affinity between two events using cosine similarity * time decay."""
    # Cosine similarity
    emb_i = embeddings[event_i['idx']]
    emb_j = embeddings[event_j['idx']]
    cos_sim = cosine_similarity(emb_i, emb_j)
    
    # Time decay
    ts_i = datetime.fromisoformat(event_i['timestamp'].replace('Z', '+00:00'))
    ts_j = datetime.fromisoformat(event_j['timestamp'].replace('Z', '+00:00'))
    delta_days = abs((ts_i - ts_j).total_seconds() / 86400)
    decay = time_decay(delta_days, tau_days)
    
    return cos_sim * decay


def _event_lane(event: dict) -> str:
    """Return narrative lane for an event, computing it if not already stored."""
    if 'narrative_lane' in event:
        return event['narrative_lane']
    text = f"{event.get('title', '')} {event.get('text', '')}"
    return classify_narrative_lane(text)


def build_event_graph(events: list[dict], embeddings: np.ndarray, tau_days: float, affinity_threshold: float) -> dict:
    """Build graph of events connected by affinity, gated by narrative lane."""
    graph = defaultdict(list)
    lanes = [_event_lane(e) for e in events]

    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            if lanes[i] != lanes[j]:
                continue
            affinity = compute_affinity(events[i], events[j], embeddings, tau_days)
            if affinity >= affinity_threshold:
                graph[i].append(j)
                graph[j].append(i)

    return graph


def connected_components(events: list[dict], graph: dict) -> list[list[int]]:
    """Find connected components using DFS."""
    visited = set()
    components = []
    
    def dfs(node, component):
        visited.add(node)
        component.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, component)
    
    for i in range(len(events)):
        if i not in visited:
            component = []
            dfs(i, component)
            components.append(component)
    
    return components


def summarize_component(component_indices: list[int], events: list[dict], embeddings: np.ndarray, cluster_title_pool_size: int = 10) -> dict:
    """Summarize a storm component.
    
    Args:
        component_indices: Indices of events in this component
        events: Full list of events
        embeddings: Event embeddings
        cluster_title_pool_size: Number of titles to include for clustering (default 10)
    
    Returns:
        Storm summary with representative_titles (top 3) and cluster_titles_topN (top N)
    """
    component_events = [events[i] for i in component_indices]
    
    # Compute centroid
    component_embeddings = embeddings[component_indices]
    centroid = np.mean(component_embeddings, axis=0)
    centroid = centroid / np.linalg.norm(centroid)
    
    # Find representative events (closest to centroid)
    similarities = [cosine_similarity(centroid, embeddings[i]) for i in component_indices]
    sorted_indices = sorted(range(len(similarities)), key=lambda i: similarities[i], reverse=True)
    
    # Top 3 for display/summary
    top3_indices = sorted_indices[:3]
    representative_events = [component_events[i] for i in top3_indices]
    
    # Top N for clustering (with unique titles only)
    cluster_titles = []
    seen_titles = set()
    for idx in sorted_indices:
        title = component_events[idx]['title']
        if title not in seen_titles:
            cluster_titles.append(title)
            seen_titles.add(title)
        if len(cluster_titles) >= cluster_title_pool_size:
            break
    
    # Time range
    timestamps = [datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00')) for e in component_events]
    created_at = min(timestamps).isoformat() + 'Z'
    updated_at = max(timestamps).isoformat() + 'Z'
    
    return {
        'event_ids': [e['event_id'] for e in component_events],
        'created_at': created_at,
        'updated_at': updated_at,
        'event_count': len(component_events),
        'centroid': centroid.tolist(),
        'representative_events': [
            {'event_id': e['event_id'], 'title': e['title']}
            for e in representative_events
        ],
        'cluster_titles_topN': cluster_titles  # New field for clustering
    }


def split_oversized_component(component: list[int], embeddings: np.ndarray) -> list[list[int]]:
    """Split a component exceeding MAX_STORM_EVENTS into sub-clusters using KMeans."""
    from sklearn.cluster import KMeans

    n_clusters = math.ceil(len(component) / MAX_STORM_EVENTS)
    component_embeddings = embeddings[component]

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(component_embeddings)

    sub_components = [[] for _ in range(n_clusters)]
    for local_idx, cluster_label in enumerate(labels):
        sub_components[cluster_label].append(component[local_idx])

    return [sc for sc in sub_components if sc]


def detect_actor_storms(
    events: list[dict],
    embeddings: np.ndarray,
    tau_days: float = 7.0,
    affinity_threshold: float = 0.45,
    min_events_per_storm: int = 3
) -> list[dict]:
    """Detect storms for a single actor's events."""
    if len(events) < min_events_per_storm:
        return []
    
    # Build graph
    graph = build_event_graph(events, embeddings, tau_days, affinity_threshold)
    
    # Find components
    components = connected_components(events, graph)
    
    # Apply size guardrail: split oversized components
    split_diagnostics = []
    bounded_components = []
    for i, component in enumerate(components):
        if len(component) > MAX_STORM_EVENTS:
            sub_components = split_oversized_component(component, embeddings)
            split_diagnostics.append({
                'component_id': f"component_{i}",
                'original_event_count': len(component),
                'new_storm_count': len(sub_components),
                'largest_new_storm': max(len(sc) for sc in sub_components),
            })
            bounded_components.extend(sub_components)
        else:
            bounded_components.append(component)

    if split_diagnostics:
        print("\n=== STORM SIZE CHECK ===")
        for d in split_diagnostics:
            print(f"  storm_id             : {d['component_id']}")
            print(f"  original_event_count : {d['original_event_count']}")
            print(f"  new_storm_count      : {d['new_storm_count']}")
            print(f"  largest_new_storm    : {d['largest_new_storm']}")

    # Filter and summarize
    storms = []
    for component in bounded_components:
        if len(component) >= min_events_per_storm:
            storm = summarize_component(component, events, embeddings)
            # Determine dominant lane for this storm
            lane_counts = {}
            for idx in component:
                lane = _event_lane(events[idx])
                lane_counts[lane] = lane_counts.get(lane, 0) + 1
            dominant_lane = max(lane_counts, key=lane_counts.get)
            unique_lanes = set(lane_counts)
            storm['narrative_lane'] = dominant_lane
            storm['lane_counts'] = lane_counts
            storm['mixed'] = len(unique_lanes) > 1
            storms.append(storm)

    # Lane distribution diagnostics
    from collections import Counter as _Counter
    lane_dist = _Counter(s['narrative_lane'] for s in storms)
    mixed_count = sum(1 for s in storms if s.get('mixed'))
    print("\n=== LANE DISTRIBUTION ===")
    print(f"  market storms   : {lane_dist.get('market', 0)}")
    print(f"  tech storms     : {lane_dist.get('tech', 0)}")
    print(f"  policy storms   : {lane_dist.get('policy', 0)}")
    print(f"  corporate storms: {lane_dist.get('corporate', 0)}")
    print(f"  default storms  : {lane_dist.get('default', 0)}")
    print(f"  mixed           : {mixed_count}  {'⚠ lane detection needs tweaking' if mixed_count else '✓'}")

    return storms
