import numpy as np
from datetime import datetime, timedelta
from src.actor_grouping import detect_actor_storms, cosine_similarity

# State derivation thresholds
MIN_DENSITY_FOR_STATE = 3
SMALL_MOMENTUM = 1.0
GROWTH_THRESHOLD = 2.0
FADE_THRESHOLD = 2.0
LOW_DRIFT = 0.05
HIGH_DRIFT = 0.15
STABLE_MIN_WINDOWS = 4
EMERGING_MAX_WINDOWS = 3  # Increased from 2 to 3
HIGH_DENSITY = 12
MODERATE_DENSITY = 6
PEAK_RATIO_THRESHOLD = 0.75


def generate_rolling_windows(events: list[dict], window_days: int, step_days: int):
    """Generate rolling time windows over events."""
    if not events:
        return []
    
    timestamps = [datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00')) for e in events]
    min_time = min(timestamps)
    max_time = max(timestamps)
    
    windows = []
    current_start = min_time
    
    while current_start <= max_time:
        window_end = current_start + timedelta(days=window_days)
        
        # Filter events in this window
        window_events = [
            e for e, ts in zip(events, timestamps)
            if current_start <= ts < window_end
        ]
        
        if window_events:
            windows.append({
                'start': current_start.isoformat() + 'Z',
                'end': window_end.isoformat() + 'Z',
                'events': window_events
            })
        
        current_start += timedelta(days=step_days)
    
    return windows


def match_storms_across_windows(storms_t: list[dict], storms_t_prev: list[dict], match_threshold: float = 0.75):
    """Match storms between adjacent windows by centroid similarity."""
    matches = []
    
    for i, storm_curr in enumerate(storms_t):
        best_match = None
        best_score = 0
        
        centroid_curr = np.array(storm_curr['centroid'])
        
        for j, storm_prev in enumerate(storms_t_prev):
            centroid_prev = np.array(storm_prev['centroid'])
            score = cosine_similarity(centroid_curr, centroid_prev)
            
            if score >= match_threshold and score > best_score:
                best_score = score
                best_match = j
        
        matches.append({
            'current_idx': i,
            'previous_idx': best_match,
            'match_score': best_score if best_match is not None else 0
        })
    
    return matches


def derive_storm_state(
    density: float,
    momentum: float,
    drift: float,
    num_windows_seen: int,
    previous_momentum: float | None = None,
    peak_ratio: float = 1.0,
    previous_density: float | None = None,
) -> tuple[str, str]:
    """Derive human-readable storm state from trajectory dynamics.
    
    Returns: (state, reason) tuple
    Precedence order: fading > emerging > growing > peaking > volatile > stable
    """
    # 1. Fading - sustained decline or clear drop from peak
    # Condition A: sustained decline
    if momentum <= -FADE_THRESHOLD and previous_momentum is not None and previous_momentum < 0:
        return "fading", "sustained_decline"
    
    # Condition B: clear drop from peak
    if peak_ratio < PEAK_RATIO_THRESHOLD and momentum < 0:
        return "fading", "drop_from_peak"
    
    # 2. Emerging - young and rising, small to moderate density
    if (num_windows_seen <= EMERGING_MAX_WINDOWS and 
        momentum > 0 and 
        MIN_DENSITY_FOR_STATE <= density < MODERATE_DENSITY):
        return "emerging", "early_growth"
    
    # 3. Growing - strong positive momentum
    if momentum >= GROWTH_THRESHOLD and density >= MODERATE_DENSITY:
        return "growing", "strong_momentum"
    
    # 4. Peaking - high density, flattening momentum
    if density >= HIGH_DENSITY and abs(momentum) <= SMALL_MOMENTUM and num_windows_seen > EMERGING_MAX_WINDOWS:
        return "peaking", "high_density_stable"
    
    # 5. Volatile - high drift
    if drift >= HIGH_DRIFT:
        return "volatile", "high_drift"
    
    # 6. Stable - persistent, low momentum, low drift
    if num_windows_seen >= STABLE_MIN_WINDOWS and abs(momentum) <= SMALL_MOMENTUM and drift <= LOW_DRIFT:
        return "stable", "persistent_low_drift"
    
    # Default
    return "stable", "default"


def compute_trajectory_metrics(trajectory: list[dict]):
    """Compute density, momentum, drift, and state for a storm trajectory."""
    metrics = []
    max_density_seen = 0
    previous_density = None
    previous_momentum = None
    state_history = []
    
    for i, window_data in enumerate(trajectory):
        density = window_data['event_count']
        
        # Track max density
        max_density_seen = max(max_density_seen, density)
        peak_ratio = density / max_density_seen if max_density_seen > 0 else 1.0
        
        # Momentum: change in density
        if i > 0:
            momentum = density - trajectory[i-1]['event_count']
        else:
            momentum = 0
        
        # Drift: 1 - cosine similarity with previous centroid
        if i > 0:
            centroid_curr = np.array(window_data['centroid'])
            centroid_prev = np.array(trajectory[i-1]['centroid'])
            drift = 1 - cosine_similarity(centroid_curr, centroid_prev)
        else:
            drift = 0
        
        # Derive state for this window
        state, state_reason = derive_storm_state(
            density=density,
            momentum=momentum,
            drift=drift,
            num_windows_seen=i + 1,
            previous_momentum=previous_momentum,
            peak_ratio=peak_ratio,
            previous_density=previous_density
        )
        
        state_history.append(state)
        
        metrics.append({
            'window_idx': i,
            'window_start': window_data['window_start'],
            'window_end': window_data['window_end'],
            'density': density,
            'momentum': momentum,
            'drift': drift,
            'state': state,
            'state_reason': state_reason,
            'peak_ratio': peak_ratio,
            'previous_momentum': previous_momentum,
            'previous_density': previous_density,
            'representative_events': window_data['representative_events']
        })
        
        # Update previous values
        previous_density = density
        previous_momentum = momentum
    
    return metrics, max_density_seen, state_history


def track_storms_over_time(
    events: list[dict],
    embeddings: np.ndarray,
    window_days: int = 30,
    step_days: int = 7,
    tau_days: float = 7.0,
    affinity_threshold: float = 0.45,
    min_events_per_storm: int = 3,
    match_threshold: float = 0.75
):
    """Track storms across rolling windows."""
    
    # Generate windows
    windows = generate_rolling_windows(events, window_days, step_days)
    
    if not windows:
        return []
    
    # Detect storms in each window
    window_storms = []
    for window in windows:
        storms = detect_actor_storms(
            window['events'],
            embeddings,
            tau_days=tau_days,
            affinity_threshold=affinity_threshold,
            min_events_per_storm=min_events_per_storm
        )
        
        # Add window info to each storm
        for storm in storms:
            storm['window_start'] = window['start']
            storm['window_end'] = window['end']
        
        window_storms.append(storms)
    
    # Build trajectories by matching across windows
    trajectories = []
    trajectory_map = {}  # Maps (window_idx, storm_idx) to trajectory_id
    next_trajectory_id = 0
    
    for window_idx in range(len(window_storms)):
        if window_idx == 0:
            # First window: create new trajectories
            for storm_idx, storm in enumerate(window_storms[0]):
                trajectory_id = next_trajectory_id
                next_trajectory_id += 1
                
                trajectory_map[(0, storm_idx)] = trajectory_id
                trajectories.append([storm])
        else:
            # Match with previous window
            matches = match_storms_across_windows(
                window_storms[window_idx],
                window_storms[window_idx - 1],
                match_threshold
            )
            
            for match in matches:
                curr_idx = match['current_idx']
                prev_idx = match['previous_idx']
                storm = window_storms[window_idx][curr_idx]
                
                if prev_idx is not None:
                    # Matched: extend existing trajectory
                    trajectory_id = trajectory_map[(window_idx - 1, prev_idx)]
                    trajectory_map[(window_idx, curr_idx)] = trajectory_id
                    trajectories[trajectory_id].append(storm)
                else:
                    # No match: new trajectory
                    trajectory_id = next_trajectory_id
                    next_trajectory_id += 1
                    trajectory_map[(window_idx, curr_idx)] = trajectory_id
                    trajectories.append([storm])
    
    # Compute metrics for each trajectory
    trajectory_results = []
    for traj_id, trajectory in enumerate(trajectories):
        if len(trajectory) > 1:  # Only track multi-window trajectories
            metrics, max_density_seen, state_history = compute_trajectory_metrics(trajectory)
            
            # Extract latest state and metrics
            latest = metrics[-1]
            
            # Compute acceleration
            latest_acceleration = None
            if latest['previous_momentum'] is not None:
                latest_acceleration = latest['momentum'] - latest['previous_momentum']
            
            trajectory_results.append({
                'trajectory_id': traj_id,
                'window_count': len(trajectory),
                'total_events': sum(s['event_count'] for s in trajectory),
                'state': latest['state'],
                'state_reason': latest['state_reason'],
                'state_history': state_history,
                'latest_density': latest['density'],
                'latest_momentum': latest['momentum'],
                'latest_drift': latest['drift'],
                'latest_acceleration': latest_acceleration,
                'previous_momentum': latest['previous_momentum'],
                'previous_density': latest['previous_density'],
                'peak_ratio': latest['peak_ratio'],
                'max_density_seen': max_density_seen,
                'num_windows_seen': len(trajectory),
                'metrics': metrics
            })
    
    return trajectory_results
