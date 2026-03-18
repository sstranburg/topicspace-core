"""
Narrative evolution and semantic drift analysis.
"""
import math
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from collections import defaultdict


def compute_centroid(embeddings: List[List[float]]) -> List[float]:
    """Compute mean centroid from embeddings."""
    if not embeddings:
        return []
    
    dim = len(embeddings[0])
    centroid = [0.0] * dim
    
    for emb in embeddings:
        for i in range(dim):
            centroid[i] += emb[i]
    
    for i in range(dim):
        centroid[i] /= len(embeddings)
    
    return centroid


def cosine_distance(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine distance (1 - cosine similarity)."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 1.0
    
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))
    
    if mag_a == 0 or mag_b == 0:
        return 1.0
    
    similarity = dot_product / (mag_a * mag_b)
    return 1.0 - similarity


def compute_window_centroids(storm: dict, window_days: int = 7) -> List[dict]:
    """Break storm into time windows and compute centroid per window."""
    events = storm.get('events', [])
    if not events:
        return []
    
    # Parse storm start time
    start_str = storm['created_at'].rstrip('Z').replace('+00:00Z', '+00:00')
    if not start_str.endswith('+00:00'):
        start_str += '+00:00'
    storm_start = datetime.fromisoformat(start_str)
    
    # Group events by window
    windows = defaultdict(list)
    for event in events:
        event_time_str = event.get('timestamp', '').rstrip('Z').replace('+00:00Z', '+00:00')
        if not event_time_str.endswith('+00:00'):
            event_time_str += '+00:00'
        event_time = datetime.fromisoformat(event_time_str)
        
        days_from_start = (event_time - storm_start).days
        window_idx = days_from_start // window_days
        windows[window_idx].append(event)
    
    # Compute centroid per window
    window_summaries = []
    for window_idx in sorted(windows.keys()):
        window_events = windows[window_idx]
        
        # Compute centroid
        embeddings = [e['embedding'] for e in window_events if 'embedding' in e]
        if embeddings:
            centroid = compute_centroid(embeddings)
        else:
            centroid = []
        
        # Extract themes with better filtering
        stopwords = {'with', 'from', 'that', 'this', 'have', 'will', 'been', 'their', 'about', 'after', 'more', 'than', 'into', 'over'}
        all_text = ' '.join([e.get('title', '') for e in window_events])
        words = all_text.lower().split()
        word_freq = defaultdict(int)
        for word in words:
            if len(word) > 3 and word not in stopwords:
                word_freq[word] += 1
        top_terms = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        
        window_start = storm_start + timedelta(days=window_idx * window_days)
        window_end = window_start + timedelta(days=window_days)
        
        window_summaries.append({
            'window_idx': window_idx,
            'time_start': window_start.isoformat(),
            'time_end': window_end.isoformat(),
            'event_count': len(window_events),
            'centroid': centroid,
            'top_terms': [t[0] for t in top_terms],
            'is_reliable': len(window_events) >= 3 and len(centroid) > 0
        })
    
    return window_summaries


def compute_semantic_drift(windows: List[dict]) -> List[float]:
    """Compute semantic drift between consecutive windows."""
    if len(windows) < 2:
        return []
    
    drifts = []
    for i in range(len(windows) - 1):
        centroid_a = windows[i]['centroid']
        centroid_b = windows[i + 1]['centroid']
        
        # Skip if either window is unreliable
        if not windows[i].get('is_reliable', True) or not windows[i + 1].get('is_reliable', True):
            drifts.append(None)
            continue
        
        drift = cosine_distance(centroid_a, centroid_b)
        # Clamp extreme values to reasonable range
        drift = max(0.0, min(0.8, drift))
        drifts.append(drift)
    
    return drifts


def classify_drift(drift: float) -> str:
    """Classify drift magnitude."""
    if drift is None:
        return 'unreliable'
    if drift < 0.10:
        return 'stable'
    elif drift < 0.25:
        return 'gradual'
    else:
        return 'major_pivot'


# Finance noise terms that inflate drift without real thematic shift
MARKET_NOISE_TERMS = {
    'stock', 'stocks', 'buy', 'sell', 'price', 'target', 'billionaire',
    'investor', 'investors', 'trading', 'trade', 'bullish', 'bearish',
    'rally', 'rallies', 'soars', 'plunges', 'closes', 'higher', 'lower',
    'earnings', 'revenue', 'billion', 'million', 'market', 'shares',
    'analyst', 'analysts', 'forecast', 'outlook', 'valuation',
    'portfolio', 'dividend', 'gains', 'losses', 'wall', 'street'
}


def classify_shift_type(phases: list, avg_drift: float) -> str:
    """Classify whether drift is thematic, market noise, or mixed.
    
    Examines phase terms to determine if high drift comes from
    real narrative shifts or finance-language noise.
    """
    if avg_drift < 0.10:
        return 'stable'
    
    if not phases or len(phases) < 2:
        return 'unclear'
    
    # Collect terms per phase, split into noise vs substance
    phase_noise_ratios = []
    for phase in phases:
        terms = phase.get('top_terms', [])
        if not terms:
            continue
        noise_count = sum(1 for t in terms if t.lower() in MARKET_NOISE_TERMS)
        phase_noise_ratios.append(noise_count / len(terms))
    
    if not phase_noise_ratios:
        return 'unclear'
    
    avg_noise_ratio = sum(phase_noise_ratios) / len(phase_noise_ratios)
    
    # Check if substance terms actually change between phases
    phase_substance = []
    for phase in phases:
        terms = phase.get('top_terms', [])
        substance = {t.lower() for t in terms if t.lower() not in MARKET_NOISE_TERMS}
        phase_substance.append(substance)
    
    # Compute how much substance terms overlap between consecutive phases
    substance_overlaps = []
    for i in range(len(phase_substance) - 1):
        a, b = phase_substance[i], phase_substance[i + 1]
        if a and b:
            overlap = len(a & b) / max(len(a | b), 1)
            substance_overlaps.append(overlap)
    
    avg_substance_overlap = sum(substance_overlaps) / len(substance_overlaps) if substance_overlaps else 1.0
    
    # Classification logic
    if avg_noise_ratio >= 0.25 and avg_substance_overlap >= 0.3:
        return 'market_noise_shift'
    elif avg_noise_ratio < 0.15 and avg_substance_overlap < 0.5:
        return 'thematic_shift'
    elif avg_noise_ratio >= 0.15:
        return 'mixed_shift'
    else:
        return 'thematic_shift'


def summarize_narrative_evolution(storm: dict, windows: List[dict], drifts: List[float]) -> dict:
    """Generate narrative evolution summary."""
    if not windows:
        return {
            'storm_id': storm['storm_id'],
            'has_evolution': False
        }
    
    # Filter out None values for average calculation
    valid_drifts = [d for d in drifts if d is not None]
    
    # Check if we have enough reliable data
    if len(valid_drifts) == 0 or len(windows) < 2:
        return {
            'storm_id': storm['storm_id'],
            'has_evolution': False,
            'reliability': 'insufficient_data'
        }
    
    # Compute average drift
    avg_drift = sum(valid_drifts) / len(valid_drifts)
    drift_class = classify_drift(avg_drift)
    
    # Determine reliability
    total_events = sum(w['event_count'] for w in windows)
    reliability = 'high' if total_events >= 10 and len(valid_drifts) >= 2 else 'moderate'
    
    # Create phase descriptions
    phases = []
    lifecycle_states = ['Formation', 'Expansion', 'Peak', 'Decline']
    
    for i, window in enumerate(windows):
        phase_name = lifecycle_states[min(i, len(lifecycle_states) - 1)]
        phases.append({
            'phase': f'Phase {i + 1}',
            'phase_name': phase_name,
            'time_start': window['time_start'],
            'time_end': window['time_end'],
            'event_count': window['event_count'],
            'top_terms': window['top_terms'][:3],
            'drift_from_previous': drifts[i - 1] if i > 0 and i - 1 < len(drifts) else None
        })
    
    shift_type = classify_shift_type(phases, avg_drift)
    
    return {
        'storm_id': storm['storm_id'],
        'actor': storm.get('actor'),
        'has_evolution': True,
        'window_count': len(windows),
        'avg_drift': avg_drift,
        'drift_classification': drift_class,
        'shift_type': shift_type,
        'reliability': reliability,
        'phases': phases
    }


def analyze_storm_evolution(storm: dict, window_days: int = 7) -> dict:
    """Complete narrative evolution analysis for a storm."""
    windows = compute_window_centroids(storm, window_days)
    drifts = compute_semantic_drift(windows)
    summary = summarize_narrative_evolution(storm, windows, drifts)
    return summary


def format_evolution_text(evolution: dict) -> str:
    """Format evolution summary as human-readable text."""
    if not evolution.get('has_evolution'):
        return "Insufficient data for narrative evolution analysis."
    
    lines = []
    
    # Check reliability
    reliability = evolution.get('reliability', 'moderate')
    if reliability == 'insufficient_data':
        return "Insufficient data for reliable narrative evolution analysis."
    
    drift_labels = {
        'stable': 'Stable narrative',
        'gradual': 'Gradual evolution',
        'major_pivot': 'Major narrative pivot',
        'unreliable': 'Unreliable (sparse data)'
    }
    
    drift_val = evolution.get('avg_drift', 0)
    drift_class = evolution.get('drift_classification', 'unknown')
    drift_label = drift_labels.get(drift_class, 'Unknown')
    
    lines.append(f"Narrative Drift: {drift_val:.3f}")
    lines.append(f"Classification: {drift_label}")
    
    if reliability == 'moderate':
        lines.append("Note: Limited data, interpret with caution")
    
    lines.append("")
    
    for phase in evolution['phases']:
        terms = phase.get('top_terms', [])
        if not terms:
            continue
        
        terms_str = ', '.join(terms)
        phase_name = phase['phase_name']
        
        lines.append(f"{phase_name}:")
        
        # Generate more natural text based on phase
        if phase_name == 'Formation':
            lines.append(f"Initial discussion centered on {terms_str}.")
        elif phase_name == 'Expansion':
            lines.append(f"The narrative broadened to include {terms_str}.")
        elif phase_name == 'Peak':
            lines.append(f"Attention focused on {terms_str}.")
        elif phase_name == 'Decline':
            lines.append(f"Discussion shifted toward {terms_str}.")
        
        lines.append("")
    
    return '\n'.join(lines)
