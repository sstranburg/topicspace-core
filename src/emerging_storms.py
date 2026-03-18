import json
import numpy as np
from datetime import datetime

# Tunable parameters
MIN_MOMENTUM = 1
MIN_DENSITY = 3
MIN_WINDOWS = 2
TOP_K = 10

# Scoring weights
W_MOMENTUM = 0.4
W_DENSITY = 0.3
W_YOUTH = 0.2
W_MATURITY = -0.1


def normalize_values(values):
    """Min-max normalization with zero-range guard."""
    values = np.array(values)
    vmin, vmax = values.min(), values.max()
    if vmax - vmin < 1e-6:
        return np.zeros_like(values)
    return (values - vmin) / (vmax - vmin)


def compute_storm_age(trajectory):
    """Compute age metrics for a trajectory."""
    num_windows = trajectory['window_count']
    
    first_ts = datetime.fromisoformat(trajectory['metrics'][0]['window_start'].rstrip('Z'))
    last_ts = datetime.fromisoformat(trajectory['metrics'][-1]['window_end'].rstrip('Z'))
    age_days = (last_ts - first_ts).days
    
    return {
        'num_windows': num_windows,
        'first_seen_ts': trajectory['metrics'][0]['window_start'],
        'last_seen_ts': trajectory['metrics'][-1]['window_end'],
        'age_days': age_days
    }


def compute_emerging_score(trajectory, norm_density, norm_momentum, norm_windows):
    """Compute emerging score for a trajectory."""
    # Get latest metrics
    latest = trajectory['metrics'][-1]
    momentum = latest['momentum']
    
    # Youth bonus: higher for fewer windows
    youth_bonus = 1.0 / (1.0 + trajectory['window_count'])
    
    # Maturity penalty: higher for long-lived storms
    maturity_penalty = norm_windows
    
    # Positive momentum only
    positive_momentum = max(momentum, 0)
    
    # Compute score
    score = (
        W_MOMENTUM * positive_momentum +
        W_DENSITY * norm_density +
        W_YOUTH * youth_bonus +
        W_MATURITY * maturity_penalty
    )
    
    return max(score, 0)


def detect_emerging_storms(trajectories_path='data/derived/storm_trajectories.jsonl',
                          storms_path='data/derived/actor_storms.jsonl'):
    """Detect and rank emerging storms."""
    
    # Load trajectories
    trajectories = []
    with open(trajectories_path, 'r') as f:
        for line in f:
            trajectories.append(json.loads(line))
    
    # Load storms for titles
    storms = []
    with open(storms_path, 'r') as f:
        for line in f:
            storms.append(json.loads(line))
    
    storm_titles = {}
    for storm in storms:
        storm_titles[storm['storm_id']] = [e['title'] for e in storm.get('representative_events', [])]
    
    # Extract metrics
    densities = []
    momentums = []
    num_windows_list = []
    
    for traj in trajectories:
        latest = traj['metrics'][-1]
        densities.append(latest['density'])
        momentums.append(latest['momentum'])
        num_windows_list.append(traj['window_count'])
    
    # Normalize
    norm_densities = normalize_values(densities)
    norm_momentums = normalize_values(momentums)
    norm_windows = normalize_values(num_windows_list)
    
    # Compute scores
    emerging_storms = []
    for i, traj in enumerate(trajectories):
        latest = traj['metrics'][-1]
        
        # Filter criteria
        if latest['momentum'] < MIN_MOMENTUM:
            continue
        if latest['density'] < MIN_DENSITY:
            continue
        if traj['window_count'] < MIN_WINDOWS:
            continue
        
        # Compute age
        age_info = compute_storm_age(traj)
        
        # Compute score
        score = compute_emerging_score(traj, norm_densities[i], norm_momentums[i], norm_windows[i])
        
        # Get latest titles
        latest_titles = []
        actor = traj['actor']
        for storm in storms:
            if storm['actor'] == actor:
                latest_titles.extend(storm_titles.get(storm['storm_id'], [])[:2])
        latest_titles = latest_titles[:3]
        
        emerging_storms.append({
            'trajectory_id': traj['trajectory_id'],
            'actor': traj['actor'],
            'latest_titles': latest_titles,
            'current_density': float(latest['density']),
            'current_momentum': float(latest['momentum']),
            'drift': float(latest['drift']),
            'first_seen_ts': age_info['first_seen_ts'],
            'last_seen_ts': age_info['last_seen_ts'],
            'age_days': age_info['age_days'],
            'num_windows': age_info['num_windows'],
            'emerging_score': float(score)
        })
    
    # Rank by score
    emerging_storms.sort(key=lambda x: x['emerging_score'], reverse=True)
    
    return emerging_storms[:TOP_K]


def save_emerging_storms(emerging_storms, output_path='data/derived/emerging_storms.jsonl'):
    """Save emerging storms to JSONL."""
    with open(output_path, 'w') as f:
        for storm in emerging_storms:
            f.write(json.dumps(storm) + '\n')
