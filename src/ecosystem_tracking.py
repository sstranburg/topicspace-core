"""Track ecosystem storm trajectories over time."""

import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

def compute_trajectory_similarity(storm1, storm2):
    """Compute semantic similarity between two storms."""
    emb1 = np.array(storm1['centroid_embedding'])
    emb2 = np.array(storm2['centroid_embedding'])
    return float(np.dot(emb1, emb2))


def track_ecosystem_trajectories(storms, similarity_threshold=0.70, max_time_gap_days=14):
    """Track ecosystem storm trajectories over time.
    
    Args:
        storms: List of ecosystem storm dicts
        similarity_threshold: Minimum similarity to link storms
        max_time_gap_days: Maximum time gap between storms
    
    Returns:
        List of trajectory dicts
    """
    if not storms:
        return []
    
    # Sort storms by start time
    sorted_storms = sorted(storms, key=lambda x: x['start_time'])
    
    # Build trajectory graph
    trajectories = []
    storm_to_traj = {}
    
    for i, storm in enumerate(sorted_storms):
        storm_id = storm['storm_id']
        
        # Check if this storm extends an existing trajectory
        best_traj = None
        best_sim = 0.0
        
        for traj_id, traj in enumerate(trajectories):
            # Get last storm in trajectory
            last_storm_id = traj['storm_ids'][-1]
            last_storm = next(s for s in sorted_storms if s['storm_id'] == last_storm_id)
            
            # Check time gap
            time_gap = (
                datetime.fromisoformat(storm['start_time']) -
                datetime.fromisoformat(last_storm['end_time'])
            ).days
            
            if time_gap > max_time_gap_days:
                continue
            
            # Check similarity
            sim = compute_trajectory_similarity(storm, last_storm)
            
            if sim >= similarity_threshold and sim > best_sim:
                best_sim = sim
                best_traj = traj_id
        
        if best_traj is not None:
            # Extend existing trajectory
            trajectories[best_traj]['storm_ids'].append(storm_id)
            storm_to_traj[storm_id] = best_traj
        else:
            # Start new trajectory
            traj_id = len(trajectories)
            trajectories.append({
                'trajectory_id': f"eco_traj_{traj_id}",
                'storm_ids': [storm_id],
                'actors_involved': storm['actors_involved'].copy()
            })
            storm_to_traj[storm_id] = traj_id
    
    # Compute trajectory dynamics
    for traj in trajectories:
        compute_trajectory_dynamics(traj, sorted_storms)
    
    return trajectories


def compute_trajectory_dynamics(trajectory, all_storms):
    """Compute dynamics for a trajectory."""
    storm_ids = trajectory['storm_ids']
    storms = [s for s in all_storms if s['storm_id'] in storm_ids]
    storms.sort(key=lambda x: x['start_time'])
    
    # Compute densities (events per day)
    densities = []
    for storm in storms:
        duration = max(1, (
            datetime.fromisoformat(storm['end_time']) -
            datetime.fromisoformat(storm['start_time'])
        ).days)
        density = storm['event_count'] / duration
        densities.append(density)
    
    # Compute momentum (change in density)
    momentums = []
    for i in range(1, len(densities)):
        momentum = int(densities[i] - densities[i-1])
        momentums.append(momentum)
    
    # Compute acceleration (change in momentum)
    accelerations = []
    for i in range(1, len(momentums)):
        accel = momentums[i] - momentums[i-1]
        accelerations.append(accel)
    
    # Compute drift (semantic movement)
    drifts = []
    for i in range(1, len(storms)):
        sim = compute_trajectory_similarity(storms[i-1], storms[i])
        drift = 1.0 - sim
        drifts.append(drift)
    
    # Compute peak ratio
    max_density = max(densities) if densities else 0
    latest_density = densities[-1] if densities else 0
    peak_ratio = latest_density / max_density if max_density > 0 else 1.0
    
    # Derive state
    latest_momentum = momentums[-1] if momentums else 0
    latest_acceleration = accelerations[-1] if accelerations else 0
    latest_drift = drifts[-1] if drifts else 0
    
    state, state_reason = derive_trajectory_state(
        latest_density,
        latest_momentum,
        latest_acceleration,
        latest_drift,
        peak_ratio,
        max_density
    )
    
    # Update trajectory
    trajectory.update({
        'total_events': sum(s['event_count'] for s in storms),
        'num_storms': len(storms),
        'densities': densities,
        'latest_density': latest_density,
        'max_density_seen': max_density,
        'peak_ratio': round(peak_ratio, 2),
        'latest_momentum': latest_momentum,
        'latest_acceleration': latest_acceleration,
        'latest_drift': round(latest_drift, 3),
        'state': state,
        'state_reason': state_reason,
        'start_time': storms[0]['start_time'],
        'end_time': storms[-1]['end_time']
    })


def derive_trajectory_state(density, momentum, acceleration, drift, peak_ratio, max_density):
    """Derive trajectory state from dynamics."""
    # Fading: significant drop from peak
    if peak_ratio < 0.5:
        return 'fading', 'drop_from_peak'
    
    # Emerging: low density, positive momentum
    if density < max_density * 0.3 and momentum > 0:
        return 'emerging', 'low_density_positive_momentum'
    
    # Growing: positive momentum and acceleration
    if momentum > 5 and acceleration > 0:
        return 'growing', 'positive_momentum_and_acceleration'
    
    # Peaking: high density, near peak
    if peak_ratio >= 0.9 and density >= max_density * 0.8:
        return 'peaking', 'at_peak'
    
    # Volatile: high drift
    if drift > 0.3:
        return 'volatile', 'high_semantic_drift'
    
    # Stable: default
    return 'stable', 'steady_state'
