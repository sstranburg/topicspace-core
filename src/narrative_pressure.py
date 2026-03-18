"""
Narrative pressure detection.
Measures whether a narrative is building energy before peak attention.
"""

HIGH_PRESSURE_THRESHOLD = 0.75
BUILDING_PRESSURE_THRESHOLD = 0.35
MOMENTUM_SCALE = 25.0
ACCELERATION_SCALE = 25.0
MAX_ACTOR_SPREAD = 5.0

STATE_PRESSURE_MODIFIER = {
    'emerging': 0.10,
    'growing': 0.10,
    'volatile': 0.05,
    'peaking': 0.00,
    'stable': -0.05,
    'fading': -0.15,
}


COHERENCE_NUMERIC = {
    None: 0.0,
    'sparse': 0.0,
    'low': 0.25,
    'moderate': 0.50,
    'high': 0.75,
    'very_high': 1.0,
}


def coherence_to_numeric(storm):
    """Map storm coherence value to 0-1 numeric."""
    c = storm.get('coherence')
    if c is None:
        return 0.0
    if c >= 0.75:
        return 1.0
    elif c >= 0.60:
        return 0.75
    elif c >= 0.40:
        return 0.50
    elif c >= 0.25:
        return 0.25
    return 0.0


def compute_velocity(storm, event_timestamps, storm_type='actor',
                     anchor_mode='storm_latest', report_reference_time=None):
    """Compute narrative velocity from event flow in two consecutive windows.

    Actor storms:     last 48h vs previous 48h  (windows of 48h each)
    Ecosystem storms: last 14d vs previous 14d (windows of 14d each)

    anchor_mode:
      'storm_latest'  — reference time = latest event timestamp in this storm (default)
      'report_latest' — reference time = report_reference_time (shared across all storms)

    event_timestamps: list of ISO timestamp strings for events in this storm.

    Returns dict with velocity_score, velocity_state, velocity_confidence,
    velocity_window, velocity_anchor_mode, velocity_reference_time,
    events_last_48h, events_prev_48h.
    """
    from datetime import datetime, timedelta

    def parse_ts(ts):
        ts = ts.rstrip('Z').replace('+00:00Z', '+00:00')
        if not ts.endswith('+00:00'):
            ts += '+00:00'
        return datetime.fromisoformat(ts)

    if anchor_mode == 'report_latest' and report_reference_time is None:
        raise ValueError(
            "compute_velocity: anchor_mode='report_latest' requires report_reference_time to be set."
        )

    parsed = []
    for ts in event_timestamps:
        try:
            parsed.append(parse_ts(ts))
        except (ValueError, AttributeError):
            pass

    window = timedelta(days=14) if storm_type == 'ecosystem' else timedelta(hours=48)
    velocity_window = '14d' if storm_type == 'ecosystem' else '48h'

    if not parsed:
        ref_str = report_reference_time.isoformat() if anchor_mode == 'report_latest' else 'none'
        return {
            'velocity_score': 0.0, 'velocity_state': 'stable', 'velocity_confidence': 'low',
            'velocity_window': velocity_window, 'velocity_anchor_mode': anchor_mode,
            'velocity_reference_time': ref_str,
            'events_last_48h': 0, 'events_prev_48h': 0,
        }

    if anchor_mode == 'report_latest':
        ref_time = report_reference_time
    else:
        ref_time = max(parsed)

    cutoff_last = ref_time - window
    cutoff_prev = ref_time - 2 * window

    events_last_48h = sum(1 for t in parsed if t > cutoff_last)
    events_prev_48h = sum(1 for t in parsed if cutoff_prev < t <= cutoff_last)

    if events_last_48h == 0 and events_prev_48h == 0:
        velocity_score = 0.0
        velocity_state = 'stable'
    elif events_prev_48h == 0:
        velocity_score = 1.0
        velocity_state = 'accelerating'
    else:
        velocity_score = round((events_last_48h - events_prev_48h) / events_prev_48h, 4)
        if velocity_score > 0.50:
            velocity_state = 'accelerating'
        elif velocity_score < -0.20:
            velocity_state = 'declining'
        else:
            velocity_state = 'stable'

    window_event_total = events_last_48h + events_prev_48h
    if events_prev_48h == 0 and events_last_48h > 0:
        velocity_confidence = 'high' if events_last_48h >= 6 else 'low'
    elif window_event_total >= 6 and events_prev_48h >= 2:
        velocity_confidence = 'high'
    elif window_event_total >= 4:
        velocity_confidence = 'medium'
    else:
        velocity_confidence = 'low'

    return {
        'velocity_score': velocity_score,
        'velocity_state': velocity_state,
        'velocity_confidence': velocity_confidence,
        'velocity_window': velocity_window,
        'velocity_anchor_mode': anchor_mode,
        'velocity_reference_time': ref_time.isoformat(),
        'events_last_48h': events_last_48h,
        'events_prev_48h': events_prev_48h,
    }


def compute_gravity_score(storm, pressure_score, max_event_count, max_chain_count, storm_type='actor'):
    """Compute narrative gravity score — strategic importance ranking metric.

    Uses separate formulas for actor vs ecosystem storms since actor_entropy
    is always 0 for single-actor storms and provides no differentiation there.

    Actor formula:     0.45 * events + 0.30 * pressure + 0.20 * centrality + 0.05 * coherence
    Ecosystem formula: 0.40 * events + 0.25 * pressure + 0.20 * centrality + 0.10 * entropy + 0.05 * coherence
    """
    norm_events = storm.get('event_count', 0) / max(max_event_count, 1)
    norm_pressure = min(max(pressure_score, 0.0), 1.0)
    norm_centrality = storm.get('chain_count', 0) / max(max_chain_count, 1)
    norm_entropy = min(max(storm.get('actor_entropy', 0.0), 0.0), 1.0)
    norm_coherence = coherence_to_numeric(storm)

    if storm_type == 'ecosystem':
        score = (
            0.40 * norm_events +
            0.25 * norm_pressure +
            0.20 * norm_centrality +
            0.10 * norm_entropy +
            0.05 * norm_coherence
        )
        formula = 'ecosystem'
    else:
        score = (
            0.45 * norm_events +
            0.30 * norm_pressure +
            0.20 * norm_centrality +
            0.05 * norm_coherence
        )
        formula = 'actor'

    return {
        'gravity_score': round(min(score, 1.0), 4),
        'gravity_formula': formula,
        'gravity_components': {
            'norm_event_count': round(norm_events, 4),
            'norm_pressure': round(norm_pressure, 4),
            'propagation_centrality': round(norm_centrality, 4),
            'actor_entropy': round(norm_entropy, 4) if storm_type == 'ecosystem' else None,
            'coherence_score': round(norm_coherence, 4),
        }
    }


def compute_pressure_score(storm, storm_type='actor'):
    """Compute narrative pressure score for a storm."""
    momentum = storm.get('momentum', 0) or 0
    acceleration = storm.get('acceleration', 0) or 0
    peak_ratio = storm.get('peak_ratio')
    num_actors = storm.get('num_unique_actors', 1) or 1
    state = storm.get('state', 'unknown')
    event_count = storm.get('event_count', 0) or 0

    momentum_norm = min(max(momentum, 0) / MOMENTUM_SCALE, 1.0)
    acceleration_norm = min(max(acceleration, 0) / ACCELERATION_SCALE, 1.0)
    actor_spread_norm = min(num_actors / MAX_ACTOR_SPREAD, 1.0)

    if peak_ratio is None:
        pre_peak_norm = 0.5
    else:
        pre_peak_norm = max(0.0, 1.0 - peak_ratio)

    base_score = (
        0.35 * momentum_norm +
        0.35 * acceleration_norm +
        0.20 * actor_spread_norm +
        0.10 * pre_peak_norm
    )

    # Mild ecosystem bonus
    if storm_type == 'ecosystem':
        base_score += 0.05 * actor_spread_norm

    # State modifier
    state_mod = STATE_PRESSURE_MODIFIER.get(state, 0.0)
    pressure_score = min(1.0, max(0.0, base_score + state_mod))

    # Cap very small storms
    if event_count < 4 and pressure_score > BUILDING_PRESSURE_THRESHOLD:
        pressure_score = min(pressure_score, 0.49)

    # Classify level
    if state == 'fading' and momentum <= 0 and acceleration <= 0:
        pressure_level = 'low'
    elif pressure_score >= HIGH_PRESSURE_THRESHOLD:
        pressure_level = 'high'
    elif pressure_score >= BUILDING_PRESSURE_THRESHOLD:
        pressure_level = 'building'
    else:
        pressure_level = 'low'

    return {
        'pressure_score': round(pressure_score, 3),
        'pressure_level': pressure_level,
        'pressure_components': {
            'momentum': round(0.35 * momentum_norm, 3),
            'acceleration': round(0.35 * acceleration_norm, 3),
            'actor_spread': round(0.20 * actor_spread_norm, 3),
            'pre_peak': round(0.10 * pre_peak_norm, 3),
            'state_modifier': round(state_mod, 3),
        }
    }


def interpret_pressure(storm, pressure):
    """Generate human-readable pressure interpretation."""
    level = pressure['pressure_level']
    components = pressure['pressure_components']
    state = storm.get('state', 'unknown')

    if level == 'high':
        drivers = []
        if components['momentum'] > 0.15:
            drivers.append('strong momentum')
        if components['acceleration'] > 0.15:
            drivers.append('rising acceleration')
        if components['actor_spread'] > 0.10:
            drivers.append('cross-actor spread')
        driver_str = ' and '.join(drivers) if drivers else 'multiple factors'
        return f"Narrative is under high pressure driven by {driver_str}; may expand further."
    elif level == 'building':
        return "Narrative is building pressure and may deserve monitoring even if attention is not yet broad."
    else:
        if state == 'fading':
            return "Narrative pressure is low; attention is declining."
        else:
            return "Narrative pressure is low; attention appears stable or mature."
