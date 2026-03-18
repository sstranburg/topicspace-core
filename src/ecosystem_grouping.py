"""Ecosystem-level storm detection across all actors."""

import numpy as np
import math
from collections import defaultdict, Counter
from datetime import datetime, timedelta

MAX_STORM_EVENTS = 150

# Ecosystem clustering parameters (stricter than actor-level)
ECO_SIMILARITY_THRESHOLD = 0.75  # Slightly relaxed from 0.82
ECO_TIME_WINDOW_DAYS = 7  # Increased from 5
ECO_MIN_EVENTS_PER_STORM = 8
MAX_ECOSYSTEM_STORM_DURATION_DAYS = 10  # Increased from 7
MAX_CLUSTER_RADIUS = 0.50  # Slightly relaxed from 0.45
MIN_MEAN_PAIRWISE_SIMILARITY = 0.72  # Slightly relaxed from 0.78
MAX_ACCEPTABLE_CLUSTER_RADIUS = 0.50  # Slightly relaxed from 0.45

# Domain relevance lexicon
TECH_ECOSYSTEM_TERMS = {
    'ai', 'artificial intelligence', 'gpu', 'chip', 'chips', 'semiconductor',
    'foundry', 'tsmc', 'nvidia', 'amd', 'broadcom', 'asml', 'microsoft',
    'google', 'amazon', 'cloud', 'data center', 'datacenter', 'hyperscaler',
    'inference', 'training', 'custom silicon', 'export controls',
    'supply chain', 'chip shortage', 'chip demand', 'advanced packaging',
    'manufacturing', 'compute', 'copilot', 'anthropic', 'openai',
    'server', 'networking', 'capex', 'investment', 'fab', 'euv',
    'processor', 'cpu', 'tpu', 'accelerator', 'hardware', 'software',
    'azure', 'aws', 'gcp', 'infrastructure', 'capacity', 'expansion'
}


def is_ecosystem_relevant(event):
    """Check if event is relevant to tech ecosystem."""
    text = f"{event.title} {event.text}".lower()
    
    # Count matching ecosystem terms
    matches = sum(1 for term in TECH_ECOSYSTEM_TERMS if term in text)
    
    # Require at least 2 ecosystem terms OR 1 term + tracked actor
    has_actor = len(event.actors) > 0
    
    if matches >= 2:
        return True
    elif matches >= 1 and has_actor:
        return True
    
    return False

def compute_affinity(emb1, emb2, t1, t2, tau_days=7.0):
    """Compute affinity between two events (semantic + time decay)."""
    from datetime import datetime
    
    # Convert timestamps if needed
    if isinstance(t1, str):
        t1 = datetime.fromisoformat(t1.replace('Z', '+00:00'))
    if isinstance(t2, str):
        t2 = datetime.fromisoformat(t2.replace('Z', '+00:00'))
    
    # Cosine similarity
    cos_sim = np.dot(emb1, emb2)
    
    # Time decay
    time_delta_days = abs((t2 - t1).total_seconds()) / 86400.0
    time_weight = np.exp(-time_delta_days / tau_days)
    
    # Combined affinity
    affinity = cos_sim * time_weight
    return affinity


def detect_ecosystem_storms(events, embeddings, affinity_threshold=None, tau_days=None, min_events=None):
    """Detect ecosystem storms across all actors using graph clustering.
    
    Args:
        events: List of event objects
        embeddings: numpy array of embeddings
        affinity_threshold: Minimum affinity for edge (uses ECO_SIMILARITY_THRESHOLD if None)
        tau_days: Time decay parameter (uses ECO_TIME_WINDOW_DAYS if None)
        min_events: Minimum events per storm (uses ECO_MIN_EVENTS_PER_STORM if None)
    
    Returns:
        List of ecosystem storm dicts
    """
    # Use stricter ecosystem defaults
    if affinity_threshold is None:
        affinity_threshold = ECO_SIMILARITY_THRESHOLD
    if tau_days is None:
        tau_days = ECO_TIME_WINDOW_DAYS
    if min_events is None:
        min_events = ECO_MIN_EVENTS_PER_STORM
    
    # Filter for ecosystem-relevant events
    print("Filtering for ecosystem-relevant events...")
    relevant_indices = []
    relevant_events = []
    relevant_embeddings = []
    
    for i, event in enumerate(events):
        if is_ecosystem_relevant(event):
            relevant_indices.append(i)
            relevant_events.append(event)
            relevant_embeddings.append(embeddings[i])
    
    relevant_embeddings = np.array(relevant_embeddings)
    n = len(relevant_events)
    
    print(f"Relevant events: {n} (excluded {len(events) - n} out-of-domain)")
    
    if n == 0:
        return []
    
    # Build affinity graph with stricter constraints
    print(f"Building affinity graph for {n} relevant events...")
    edges = []
    
    for i in range(n):
        for j in range(i + 1, n):
            # Check time window first (fast filter)
            t1 = relevant_events[i].timestamp
            t2 = relevant_events[j].timestamp
            if isinstance(t1, str):
                t1 = datetime.fromisoformat(t1.replace('Z', '+00:00'))
            if isinstance(t2, str):
                t2 = datetime.fromisoformat(t2.replace('Z', '+00:00'))
            
            time_delta_days = abs((t2 - t1).total_seconds()) / 86400.0
            if time_delta_days > ECO_TIME_WINDOW_DAYS:
                continue
            
            # Compute affinity
            affinity = compute_affinity(
                relevant_embeddings[i],
                relevant_embeddings[j],
                relevant_events[i].timestamp,
                relevant_events[j].timestamp,
                tau_days
            )
            
            if affinity >= affinity_threshold:
                edges.append((i, j, affinity))
    
    print(f"Found {len(edges)} edges above threshold {affinity_threshold}")
    
    # Build adjacency list
    adj = defaultdict(list)
    for i, j, aff in edges:
        adj[i].append(j)
        adj[j].append(i)
    
    # Find connected components (storms) using iterative DFS
    visited = set()
    components = []
    
    for i in range(n):
        if i not in visited:
            # Iterative DFS
            component = []
            stack = [i]
            
            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                
                visited.add(node)
                component.append(node)
                
                for neighbor in adj[node]:
                    if neighbor not in visited:
                        stack.append(neighbor)
            
            if len(component) >= min_events:
                components.append(component)
    
    print(f"Found {len(components)} candidate ecosystem storms (min_events={min_events})")
    
    # Apply size guardrail: split oversized components
    split_diagnostics = []
    bounded_components = []
    for i, component in enumerate(components):
        if len(component) > MAX_STORM_EVENTS:
            from sklearn.cluster import KMeans
            n_clusters = math.ceil(len(component) / MAX_STORM_EVENTS)
            comp_embs = relevant_embeddings[component]
            km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = km.fit_predict(comp_embs)
            sub_components = [[] for _ in range(n_clusters)]
            for local_idx, label in enumerate(labels):
                sub_components[label].append(component[local_idx])
            sub_components = [sc for sc in sub_components if sc]
            split_diagnostics.append({
                'component_id': f"eco_component_{i}",
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

    # Build storm objects with quality checks
    storms = []
    rejected_diffuse = 0
    rejected_duration = 0
    rejected_radius = 0

    for comp_idx, component in enumerate(bounded_components):
        # Get events in component
        comp_events = [relevant_events[i] for i in component]
        comp_embeddings = relevant_embeddings[component]
        
        # Compute centroid
        centroid = np.mean(comp_embeddings, axis=0)
        centroid = centroid / np.linalg.norm(centroid)
        
        # Quality check 1: Compute cluster radius
        distances = [1.0 - np.dot(emb, centroid) for emb in comp_embeddings]
        cluster_radius = max(distances)
        
        if cluster_radius > MAX_ACCEPTABLE_CLUSTER_RADIUS:
            rejected_radius += 1
            continue
        
        # Quality check 2: Compute mean pairwise similarity
        pairwise_sims = []
        for i in range(len(comp_embeddings)):
            for j in range(i + 1, len(comp_embeddings)):
                sim = np.dot(comp_embeddings[i], comp_embeddings[j])
                pairwise_sims.append(sim)
        
        mean_pairwise_sim = np.mean(pairwise_sims) if pairwise_sims else 1.0
        
        if mean_pairwise_sim < MIN_MEAN_PAIRWISE_SIMILARITY:
            rejected_diffuse += 1
            continue
        
        # Get time range
        timestamps = []
        for e in comp_events:
            if isinstance(e.timestamp, str):
                timestamps.append(datetime.fromisoformat(e.timestamp.replace('Z', '+00:00')))
            else:
                timestamps.append(e.timestamp)
        
        start_time = min(timestamps)
        end_time = max(timestamps)
        duration_days = (end_time - start_time).days
        
        # Quality check 3: Duration cap
        if duration_days > MAX_ECOSYSTEM_STORM_DURATION_DAYS:
            rejected_duration += 1
            continue
        
        # Get actors involved with proper event counts
        actors_involved = []
        actor_counts = Counter()
        
        for e in comp_events:
            for actor in e.actors:
                if actor not in actors_involved:
                    actors_involved.append(actor)
                actor_counts[actor] += 1  # Count per event, not per storm
        
        # Determine dominant actors (top 3 by count)
        dominant_actors = [actor for actor, count in actor_counts.most_common(3)]
        
        # Classify storm scope
        num_unique_actors = len(actors_involved)
        if num_unique_actors == 0:
            storm_scope = "no_actor"
        elif num_unique_actors == 1:
            storm_scope = "single_actor"
        elif num_unique_actors <= 3:
            storm_scope = "cross_actor"
        else:
            storm_scope = "ecosystem_wide"
        
        # Get representative titles (top 3 by centroid similarity)
        similarities = []
        for i, e in enumerate(comp_events):
            sim = np.dot(comp_embeddings[i], centroid)
            similarities.append((sim, e))
        
        similarities.sort(reverse=True, key=lambda x: x[0])
        representative_events = [
            {
                'event_id': e.event_id,
                'title': e.title,
                'timestamp': e.timestamp if isinstance(e.timestamp, str) else e.timestamp.isoformat(),
                'actors': e.actors,
                'similarity': float(sim)
            }
            for sim, e in similarities[:3]
        ]
        
        # Get all unique titles for clustering
        unique_titles = []
        seen_titles = set()
        for sim, e in similarities:
            if e.title not in seen_titles:
                unique_titles.append(e.title)
                seen_titles.add(e.title)
                if len(unique_titles) >= 10:
                    break
        
        # Compute actor composition metrics
        num_unique_actors = len(actors_involved)
        total_actor_mentions = sum(actor_counts.values())
        dominant_actor_ratio = actor_counts.most_common(1)[0][1] / total_actor_mentions if total_actor_mentions > 0 else 0
        
        # Compute actor entropy
        actor_entropy = 0.0
        if total_actor_mentions > 0:
            for count in actor_counts.values():
                p = count / total_actor_mentions
                if p > 0:
                    actor_entropy -= p * np.log2(p)
        
        # Create storm object
        storm = {
            'storm_id': f"eco_{start_time.strftime('%Y-%m-%d')}_{comp_idx}",
            'storm_scope': storm_scope,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_days': duration_days,
            'event_ids': [e.event_id for e in comp_events],
            'event_count': len(comp_events),
            'actors_involved': actors_involved,
            'dominant_actors': dominant_actors,
            'actor_counts': dict(actor_counts),
            'num_unique_actors': num_unique_actors,
            'dominant_actor_ratio': round(dominant_actor_ratio, 3),
            'actor_entropy': round(actor_entropy, 3),
            'mean_pairwise_similarity': round(float(mean_pairwise_sim), 3),
            'cluster_radius': round(float(cluster_radius), 3),
            'representative_events': representative_events,
            'cluster_titles_topN': unique_titles,
            'centroid_embedding': centroid.tolist()
        }
        
        storms.append(storm)
    
    # Sort by start time
    storms.sort(key=lambda x: x['start_time'])

    # Print diagnostics
    print(f"\nEcosystem Clustering Diagnostics:")
    print(f"  Relevant events considered: {n}")
    print(f"  Candidate clusters formed: {len(bounded_components)}")
    print(f"  Accepted storms: {len(storms)}")
    print(f"  Rejected (diffuse): {rejected_diffuse}")
    print(f"  Rejected (duration): {rejected_duration}")
    print(f"  Rejected (radius): {rejected_radius}")

    if storms:
        avg_size = sum(s['event_count'] for s in storms) / len(storms)
        largest_size = max(s['event_count'] for s in storms)
        avg_actors = sum(s['num_unique_actors'] for s in storms) / len(storms)
        scope_counts = Counter(s['storm_scope'] for s in storms)

        print(f"  Average storm size: {avg_size:.1f}")
        print(f"  Largest storm size: {largest_size}")
        print(f"  Average unique actors per storm: {avg_actors:.1f}")
        print(f"  Storm scope distribution:")
        for scope, count in scope_counts.most_common():
            print(f"    {scope}: {count}")

    # Coverage diagnostics
    cross_actor_storms = [s for s in storms if s['num_unique_actors'] > 1]
    mean_actors = sum(s['num_unique_actors'] for s in storms) / len(storms) if storms else 0.0

    # Top actor pairs and triples
    pair_counts: Counter = Counter()
    triple_counts: Counter = Counter()
    for s in storms:
        actors = sorted(s.get('actors_involved', []))
        for i in range(len(actors)):
            for j in range(i + 1, len(actors)):
                pair_counts[(actors[i], actors[j])] += 1
                for k in range(j + 1, len(actors)):
                    triple_counts[(actors[i], actors[j], actors[k])] += 1

    print(f"\n=== ECOSYSTEM STORM COVERAGE ===")
    print(f"  total ecosystem events  : {n}")
    print(f"  total ecosystem storms  : {len(storms)}")
    print(f"  cross-actor storms      : {len(cross_actor_storms)}")
    print(f"  mean actors per storm   : {mean_actors:.2f}")
    if pair_counts:
        print(f"  top actor pairs:")
        for pair, cnt in pair_counts.most_common(5):
            print(f"    {' + '.join(pair)}: {cnt}")
    if triple_counts:
        print(f"  top actor triples:")
        for triple, cnt in triple_counts.most_common(3):
            print(f"    {' + '.join(triple)}: {cnt}")

    return storms


def summarize_ecosystem_component(storm):
    """Generate summary for an ecosystem storm."""
    summary = {
        'storm_id': storm['storm_id'],
        'event_count': storm['event_count'],
        'actors_involved': storm['actors_involved'],
        'dominant_actors': storm['dominant_actors'],
        'num_unique_actors': storm['num_unique_actors'],
        'dominant_actor_ratio': storm['dominant_actor_ratio'],
        'actor_entropy': storm['actor_entropy'],
        'duration_days': (
            datetime.fromisoformat(storm['end_time']) - 
            datetime.fromisoformat(storm['start_time'])
        ).days,
        'representative_titles': [e['title'] for e in storm['representative_events']]
    }
    
    return summary
