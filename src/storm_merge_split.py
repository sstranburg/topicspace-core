import numpy as np
from datetime import datetime
from src.actor_grouping import cosine_similarity

# Merge detection thresholds
MERGE_SEMANTIC_THRESHOLD = 0.70
MERGE_TIME_OVERLAP_THRESHOLD = 0.20
MERGE_SCORE_THRESHOLD = 0.50

# Split detection thresholds
SPLIT_LOOKAHEAD_WINDOWS = 3
PARENT_MIN_PEAK_DENSITY = 8
CHILD_SEMANTIC_THRESHOLD = 0.65
MIN_CHILDREN_FOR_SPLIT = 2


def trajectory_centroid(trajectory):
    """Compute average centroid across trajectory windows."""
    centroids = []
    for metric in trajectory['metrics']:
        if 'representative_events' in metric and metric['representative_events']:
            # Use first representative event as proxy for window centroid
            # In practice, would compute from all events in window
            centroids.append(metric['representative_events'][0])
    
    if not centroids:
        return None
    
    # For now, return latest centroid as proxy
    # In full implementation, would average embeddings
    return trajectory['metrics'][-1] if trajectory['metrics'] else None


def time_overlap_score(traj_a, traj_b):
    """Compute temporal overlap between two trajectories."""
    # Get time ranges
    a_start = datetime.fromisoformat(traj_a['metrics'][0]['window_start'].rstrip('Z'))
    a_end = datetime.fromisoformat(traj_a['metrics'][-1]['window_end'].rstrip('Z'))
    b_start = datetime.fromisoformat(traj_b['metrics'][0]['window_start'].rstrip('Z'))
    b_end = datetime.fromisoformat(traj_b['metrics'][-1]['window_end'].rstrip('Z'))
    
    # Compute overlap
    overlap_start = max(a_start, b_start)
    overlap_end = min(a_end, b_end)
    
    if overlap_start >= overlap_end:
        return 0.0
    
    overlap_duration = (overlap_end - overlap_start).total_seconds()
    a_duration = (a_end - a_start).total_seconds()
    b_duration = (b_end - b_start).total_seconds()
    
    if a_duration == 0 or b_duration == 0:
        return 0.0
    
    # Overlap as fraction of shorter trajectory
    min_duration = min(a_duration, b_duration)
    return overlap_duration / min_duration


def semantic_similarity_between_trajectories(traj_a, traj_b, embedding_lookup):
    """Compute semantic similarity between trajectory centroids."""
    # Get latest representative events
    a_events = traj_a['metrics'][-1].get('representative_events', [])
    b_events = traj_b['metrics'][-1].get('representative_events', [])
    
    if not a_events or not b_events:
        return 0.0
    
    # Get embeddings for representative events
    a_event_id = a_events[0].get('event_id')
    b_event_id = b_events[0].get('event_id')
    
    if not a_event_id or not b_event_id:
        return 0.0
    
    if a_event_id not in embedding_lookup or b_event_id not in embedding_lookup:
        return 0.0
    
    a_emb = embedding_lookup[a_event_id]
    b_emb = embedding_lookup[b_event_id]
    
    return cosine_similarity(a_emb, b_emb)


def detect_merge_candidates(trajectories, embedding_lookup):
    """Detect pairs of trajectories that may be merging."""
    candidates = []
    
    for i, traj_a in enumerate(trajectories):
        for j, traj_b in enumerate(trajectories[i+1:], i+1):
            # Skip if same actor (merges are cross-actor)
            if traj_a['actor'] == traj_b['actor']:
                continue
            
            # Compute semantic similarity
            semantic_sim = semantic_similarity_between_trajectories(traj_a, traj_b, embedding_lookup)
            
            if semantic_sim < MERGE_SEMANTIC_THRESHOLD:
                continue
            
            # Compute time overlap
            time_overlap = time_overlap_score(traj_a, traj_b)
            
            if time_overlap < MERGE_TIME_OVERLAP_THRESHOLD:
                continue
            
            # Actor diversity bonus (cross-actor merges are interesting)
            actor_diversity_bonus = 1.2
            
            # Compute merge score
            merge_score = semantic_sim * time_overlap * actor_diversity_bonus
            
            if merge_score >= MERGE_SCORE_THRESHOLD:
                candidates.append({
                    'trajectory_a': traj_a['trajectory_id'],
                    'trajectory_b': traj_b['trajectory_id'],
                    'merge_score': merge_score,
                    'semantic_similarity': semantic_sim,
                    'time_overlap': time_overlap,
                    'actors_a': [traj_a['actor']],
                    'actors_b': [traj_b['actor']],
                    'density_a': traj_a['latest_density'],
                    'density_b': traj_b['latest_density']
                })
    
    # Sort by merge score
    candidates.sort(key=lambda x: x['merge_score'], reverse=True)
    
    return candidates


def detect_split_candidates(trajectories, embedding_lookup):
    """Detect trajectories that may be splitting into multiple children."""
    candidates = []
    
    for i, parent in enumerate(trajectories):
        # Check if parent has high enough peak density
        if parent['max_density_seen'] < PARENT_MIN_PEAK_DENSITY:
            continue
        
        # Find potential children: trajectories from same actor that start later
        parent_end = datetime.fromisoformat(parent['metrics'][-1]['window_end'].rstrip('Z'))
        
        potential_children = []
        for j, child in enumerate(trajectories):
            if i == j:
                continue
            
            # Must be same actor
            if child['actor'] != parent['actor']:
                continue
            
            # Child must start within lookahead window
            child_start = datetime.fromisoformat(child['metrics'][0]['window_start'].rstrip('Z'))
            
            # Check if child starts near parent end
            time_diff_days = (child_start - parent_end).days
            if 0 <= time_diff_days <= SPLIT_LOOKAHEAD_WINDOWS * 7:
                # Check semantic similarity to parent
                semantic_sim = semantic_similarity_between_trajectories(parent, child, embedding_lookup)
                
                if semantic_sim >= CHILD_SEMANTIC_THRESHOLD:
                    potential_children.append({
                        'trajectory_id': child['trajectory_id'],
                        'semantic_similarity': semantic_sim,
                        'time_offset_days': time_diff_days
                    })
        
        # Check if we have enough children
        if len(potential_children) >= MIN_CHILDREN_FOR_SPLIT:
            # Compute split score based on parent peak and number of children
            split_score = (parent['max_density_seen'] / 20.0) * (len(potential_children) / 3.0)
            split_score = min(split_score, 1.0)
            
            candidates.append({
                'parent_trajectory': parent['trajectory_id'],
                'child_trajectories': [c['trajectory_id'] for c in potential_children],
                'split_score': split_score,
                'parent_peak_density': parent['max_density_seen'],
                'num_children': len(potential_children),
                'child_details': potential_children
            })
    
    # Sort by split score
    candidates.sort(key=lambda x: x['split_score'], reverse=True)
    
    return candidates
