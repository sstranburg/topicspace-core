#!/usr/bin/env python3
"""
Generate master HTML report from all storm system outputs.
"""
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
sys.path.insert(0, str(Path(__file__).parent))
from narrative_leadership import compute_leadership, compute_theme_leadership, generate_role_description
from narrative_pressure import compute_pressure_score, interpret_pressure, compute_gravity_score, compute_velocity
from narrative_lineage import group_into_lineages
from narrative_registry import update_registry
from lead_lag_alpha import compute_lead_lag_alpha
from narrative_phases import compute_macro_phases
from plot_phase_map import generate_phase_map, generate_phase_map_lineages
from strategic_watchlist import build_pressure_leadership_records, filter_watchlist, dedupe_watchlist
from storm_identity import classify_trend
from narrative_momentum import (compute_narrative_momentum, compute_narrative_momentum_full,
                                classify_momentum, classify_narrative_state,
                                compute_lead_score, classify_lead,
                                momentum_explanation, momentum_debug_row)

# Market noise terms for shift_type classification on storms without evolution data
MARKET_NOISE_TERMS = {
    'stock', 'stocks', 'buy', 'sell', 'price', 'target', 'billionaire',
    'investor', 'investors', 'trading', 'trade', 'bullish', 'bearish',
    'rally', 'rallies', 'soars', 'plunges', 'closes', 'higher', 'lower',
    'earnings', 'revenue', 'billion', 'million', 'market', 'shares',
    'analyst', 'analysts', 'forecast', 'outlook', 'valuation',
    'portfolio', 'dividend', 'gains', 'losses', 'wall', 'street'
}


def classify_shift_type_from_titles(titles, drift):
    """Classify shift type from storm titles when evolution data unavailable."""
    if drift < 0.10:
        return 'stable'
    if not titles:
        return 'unclear'
    all_text = ' '.join(titles).lower().split()
    noise_count = sum(1 for w in all_text if w in MARKET_NOISE_TERMS)
    noise_ratio = noise_count / max(len(all_text), 1)
    if noise_ratio >= 0.06:
        return 'market_noise_shift'
    elif noise_ratio >= 0.03:
        return 'mixed_shift'
    else:
        return 'thematic_shift'


def dedupe_by_storm_id(storms, label):
    """Render-layer deduplication strictly by storm_id. Logs validation results."""
    before = len(storms)
    seen = {}
    duplicates = []
    for storm in storms:
        sid = storm.get('storm_id')
        if sid in seen:
            duplicates.append(sid)
        else:
            seen[sid] = storm
    after = len(seen)
    print(f"[dedupe:{label}] before={before} after={after} removed={before - after}", end='')
    if duplicates:
        print(f" duplicate_ids={duplicates}")
    else:
        print()
    return list(seen.values())


def _apply_storm_merges(storms, storm_merges):
    """
    Collapse windows sharing a storm_identity_key to one representative row.
    Identity = (lineage_id, actor, canonical_phase) — set by clean_narrative_lineages.py.
    Representative = window with highest event_count; patched with agg_event_count.
    Storms absent from storm_merges pass through unchanged.
    """
    if not storm_merges:
        return storms

    # Pass 1: collect representative storm per identity
    identity_reps = {}
    for s in storms:
        m = storm_merges.get(s.get('storm_id'))
        if m and s['storm_id'] == m['representative_id']:
            rep = dict(s)
            rep['event_count'] = m['agg_event_count']
            identity_reps[m['storm_identity_key']] = rep

    # Pass 2: emit one row per identity in original list order
    seen = set()
    result = []
    for s in storms:
        m = storm_merges.get(s.get('storm_id'))
        if m is None:
            result.append(s)
            continue
        key = m['storm_identity_key']
        if key in seen:
            continue
        seen.add(key)
        out = identity_reps.get(key, dict(s))
        out['event_count'] = m['agg_event_count']
        result.append(out)
    return result


def load_jsonl(path):
    """Load JSONL file."""
    items = []
    if not path.exists():
        return items
    with open(path) as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def load_json(path):
    """Load JSON file."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def state_to_class(state):
    """Convert state to CSS class."""
    return state.lower().replace(' ', '-')


def format_coherence(score):
    """Convert coherence score to human-readable label."""
    if score is None:
        return "N/A"
    if score >= 0.60:
        return f"High ({score:.2f})"
    elif score >= 0.40:
        return f"Moderate ({score:.2f})"
    elif score >= 0.25:
        return f"Mixed ({score:.2f})"
    else:
        return f"Fragmented ({score:.2f})"


def displayed_velocity_state(storm):
    """Return velocity_state label adjusted for confidence and storm type.

    Ecosystem storms with low confidence → 'Needs More Evidence'
    Actor storms with low confidence     → 'tentative {state}'
    Medium/high confidence               → raw velocity_state
    """
    state   = storm.get('velocity_state', 'stable')
    conf    = storm.get('velocity_confidence', 'low')
    is_eco  = storm.get('storm_id', '').startswith('eco_')
    if conf == 'low':
        return 'Needs More Evidence' if is_eco else f'tentative {state}'
    return state




def format_evolution_text(phases):
    """Convert phase keywords into readable narrative text."""
    if not phases:
        return "Insufficient data for narrative evolution analysis."
    
    lines = []
    for phase in phases:
        phase_name = phase.get('phase_name', 'Unknown')
        terms = phase.get('top_terms', [])[:3]
        if not terms:
            continue
        
        terms_str = ', '.join(terms)
        
        # Generate more natural text based on phase
        if 'Formation' in phase_name:
            lines.append(f"<strong>{phase_name}:</strong> Initial discussion centered on {terms_str}.")
        elif 'Expansion' in phase_name:
            lines.append(f"<strong>{phase_name}:</strong> The narrative broadened to include {terms_str}.")
        elif 'Peak' in phase_name:
            lines.append(f"<strong>{phase_name}:</strong> Attention focused on {terms_str}.")
        elif 'Decline' in phase_name:
            lines.append(f"<strong>{phase_name}:</strong> Discussion shifted toward {terms_str}.")
        else:
            lines.append(f"<strong>{phase_name}:</strong> Key themes included {terms_str}.")
    
    return '<br>'.join(lines) if lines else "Insufficient data for narrative evolution analysis."


def ecosystem_priority(storm):
    """Calculate ecosystem importance score for sorting."""
    cross_actor_bonus = storm.get('num_unique_actors', 0) * 0.5
    entropy_score = storm.get('actor_entropy', 0)
    size_score = min(storm.get('event_count', 0) / 50, 1)
    state_weight = {
        'growing': 1.0,
        'peaking': 0.9,
        'stable': 0.6,
        'fading': 0.3
    }.get(storm.get('state', 'unknown'), 0.3)
    
    return cross_actor_bonus + entropy_score + size_score + state_weight


def storm_quality_score(storm):
    """Score storm quality for report selection, penalizing finance noise."""
    # Base score from event count (reduced weight)
    event_score = storm.get('event_count', 0) / 200.0
    
    # Check titles for finance noise vs tech substance
    titles = storm.get('cluster_titles_topN', [])
    all_text = ' '.join(titles).lower()
    
    # Finance noise keywords (penalize heavily)
    finance_noise = ['stock', 'stocks', 'buy', 'sell', 'price', 'target', 'billionaire', 
                     'invest', 'investor', 'trading', 'trade', 'bullish', 'bearish',
                     'closes higher', 'closes lower', 'soars', 'plunges', 'rally', 'dip']
    noise_count = sum(1 for word in finance_noise if word in all_text)
    noise_penalty = noise_count * 0.3  # Increased from 0.15
    
    # Tech substance keywords (reward)
    tech_substance = ['chip', 'semiconductor', 'ai', 'cloud', 'infrastructure', 'manufacturing',
                     'partnership', 'acquisition', 'technology', 'innovation', 'export',
                     'euv', 'lithography', 'fab', 'autonomous', 'robotaxi', 'data center',
                     'breakthrough', 'launch', 'deploy']
    substance_count = sum(1 for word in tech_substance if word in all_text)
    substance_bonus = substance_count * 0.3  # Increased from 0.2
    
    # Domain phrase density (reward)
    domain_phrases = storm.get('domain_phrases', [])
    phrase_bonus = len(domain_phrases) * 0.15  # Increased from 0.1
    
    # Coherence bonus
    coherence = storm.get('coherence') or 0
    coherence_bonus = coherence * 0.4
    
    total_score = event_score + substance_bonus + phrase_bonus + coherence_bonus - noise_penalty
    return max(0, total_score)


def _market_interpretation(rec, leadership_map):
    """Derive market_state_tag, modifiers list, and market_read_text for a lineage record."""
    gravity  = rec.get('lineage_max_gravity', 0)
    vel      = rec.get('velocity_state', '')
    accel    = 'accelerating' in vel
    decl     = 'declining' in vel

    if gravity >= 0.60 and accel:
        tag = 'Expanding'
    elif gravity >= 0.60 and decl:
        tag = 'Digesting'
    elif gravity < 0.60 and accel:
        tag = 'Emerging'
    elif gravity < 0.60 and decl:
        tag = 'Background'
    else:
        tag = 'Mixed'

    mods = []
    if rec.get('retail_event_count', 0) > 0:
        mods.append('Retail spillover')
    if len(rec.get('actor_set', rec.get('lineage_actor_set', []))) > 1:
        mods.append('Sympathy watch')
    # Primary actor role: first actor in actor_set by gravity
    actors = rec.get('actor_set', rec.get('lineage_actor_set', []))
    primary_role = None
    for a in actors:
        r = leadership_map.get(a, {})
        if r.get('role') in ('leader', 'receiver'):
            primary_role = r['role']
            break
    if primary_role == 'receiver':
        mods.append('Beneficiary')
    elif primary_role == 'leader':
        mods.append('Originator')

    # market_read_text
    if tag == 'Expanding':
        text = 'High-gravity narrative with accelerating attention; watch for further spread.'
    elif tag == 'Digesting':
        text = 'Important narrative, but momentum is cooling.'
    elif tag == 'Emerging':
        text = 'Early-stage narrative expansion; watch for broader spread.'
    elif tag == 'Background':
        text = 'Low-gravity narrative with declining momentum; background noise for now.'
    else:
        text = 'Mixed signals; narrative direction unclear.'

    if 'Sympathy watch' in mods and tag in ('Expanding', 'Emerging'):
        text = 'Cross-actor narrative with spillover potential.'
    if 'Beneficiary' in mods:
        text = 'Durable beneficiary narrative rather than a fresh catalyst.'
    if 'Retail spillover' in mods:
        text += ' Retail amplification detected.'

    return tag, mods, text.strip()


def _dh(storm, maxlen=None):
    """Return storm.display_headline, truncated to maxlen if given."""
    label = storm.get('display_headline') or '—'
    if maxlen and len(label) > maxlen:
        label = label[:maxlen - 1] + '…'
    return label


def _lifecycle_interpretation(state_counts, total):
    """One-line interpretation of the storm lifecycle distribution."""
    if total == 0:
        return ''
    fading_pct  = state_counts.get('fading', 0)  / total * 100
    growing_pct = state_counts.get('growing', 0) / total * 100
    peaking     = state_counts.get('peaking', 0)
    emerging    = state_counts.get('emerging', 0)

    if fading_pct >= 40 and peaking == 0:
        return (f'Narrative momentum skewed toward cooling: '
                f'{fading_pct:.0f}% of storms are fading while no storms are peaking.')
    elif fading_pct >= 40:
        return (f'{fading_pct:.0f}% of storms are fading; '
                f'only {peaking} peaking — ecosystem is in a cooling phase.')
    elif growing_pct >= 35 and peaking >= 1:
        return (f'Ecosystem is in an active phase: '
                f'{growing_pct:.0f}% growing with {peaking} storm(s) at peak.')
    elif emerging >= 3:
        return f'{emerging} emerging storms suggest a new narrative cycle may be forming.'
    else:
        return f'Mixed lifecycle: {state_counts.get("growing",0)} growing, {state_counts.get("fading",0)} fading, {state_counts.get("stable",0)+state_counts.get("volatile",0)} stable/volatile.'


def main(reset_registry=False):
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data' / 'derived'
    template_path = base_dir / 'topicspace_master_report_template.html'
    output_path = base_dir / 'master_report.html'
    
    # Load data
    print("Loading data...")
    actor_storms = load_jsonl(data_dir / 'actor_storms.jsonl')
    actor_summaries = load_jsonl(data_dir / 'actor_storm_summaries.jsonl')
    eco_storms = load_jsonl(data_dir / 'ecosystem_storms.jsonl')
    eco_summaries = load_jsonl(data_dir / 'ecosystem_storm_summaries.jsonl')
    trajectories = load_jsonl(data_dir / 'storm_trajectories.jsonl')
    eco_trajectories = load_jsonl(data_dir / 'ecosystem_trajectories.jsonl')
    merge_candidates = load_jsonl(data_dir / 'merge_candidates.jsonl')
    propagation_edges = load_jsonl(data_dir / 'storm_propagation.jsonl')
    propagation_chains = load_json(data_dir / 'propagation_chains.json')
    actor_lead_lag = load_json(data_dir / 'actor_lead_lag.json') if (data_dir / 'actor_lead_lag.json').exists() else []
    lane_transitions = load_json(data_dir / 'lane_transitions.json') if (data_dir / 'lane_transitions.json').exists() else []
    narrative_evolutions = load_jsonl(data_dir / 'narrative_evolution.jsonl')
    community_overlay = load_jsonl(data_dir / 'community_overlay.jsonl')
    retail_amplification = load_jsonl(data_dir / 'retail_amplification.jsonl')
    retail_amp_map = {r['lineage_id']: r for r in retail_amplification}
    retail_precision = load_json(data_dir / 'retail_amplification_precision.json')
    
    # Build actor → dominant trajectory (highest total_events wins)
    _actor_traj_map: dict = {}
    _actor_state_map: dict = {}
    for t in trajectories:
        actor = t.get('actor')
        if not actor:
            continue
        existing = _actor_traj_map.get(actor)
        if existing is None or t.get('total_events', 0) > existing.get('total_events', 0):
            _actor_traj_map[actor] = t
            _actor_state_map[actor] = t['state']

    # Enrich storms with state from trajectories
    for s in actor_storms:
        s.setdefault('state', _actor_state_map.get(s.get('actor'), 'unknown'))

    # Create overlay map
    overlay_map = {}
    for co in community_overlay:
        actor = co.get('actor', '')
        # Keep the one with most posts per actor
        if actor not in overlay_map or co['community_post_count'] > overlay_map[actor]['community_post_count']:
            overlay_map[actor] = co
    
    # Create evolution map
    evolution_map = {e['storm_id']: e for e in narrative_evolutions}
    
    # Load normalized events for source distribution and time range
    normalized_events = load_jsonl(base_dir / 'data' / 'normalized' / 'tech_ecosystem_filtered.jsonl')
    event_ts_map = {e.get('event_id', ''): e.get('timestamp', '') for e in normalized_events}

    # Shared reference time for report_latest anchor mode (ecosystem velocity)
    def _parse_ts(ts):
        ts = ts.rstrip('Z').replace('+00:00Z', '+00:00')
        if not ts.endswith('+00:00'):
            ts += '+00:00'
        return datetime.fromisoformat(ts)
    _all_ts = [_parse_ts(ts) for ts in event_ts_map.values() if ts]
    report_reference_time = max(_all_ts) if _all_ts else None

    source_counts = defaultdict(int)
    source_timestamps = defaultdict(list)
    for event in normalized_events:
        source = event.get('source', 'unknown')
        # Filter out 'n/a' and 'anchor' sources
        if source.lower() not in ['n/a', 'anchor']:
            source_counts[source] += 1
            ts = event.get('published_at', event.get('timestamp', ''))
            if ts:
                source_timestamps[source].append(ts)
    total_raw_events = len(normalized_events)
    
    # Calculate time range per source
    source_time_ranges = {}
    for source, timestamps in source_timestamps.items():
        if timestamps:
            timestamps.sort()
            start_ts = timestamps[0].rstrip('Z').replace('+00:00Z', '+00:00')
            end_ts = timestamps[-1].rstrip('Z').replace('+00:00Z', '+00:00')
            if not start_ts.endswith('+00:00'):
                start_ts += '+00:00'
            if not end_ts.endswith('+00:00'):
                end_ts += '+00:00'
            start_date = datetime.fromisoformat(start_ts)
            end_date = datetime.fromisoformat(end_ts)
            duration_days = (end_date - start_date).days
            source_time_ranges[source] = {
                'start': start_date.strftime('%b %d, %Y'),
                'end': end_date.strftime('%b %d, %Y'),
                'days': duration_days
            }
    
    # Merge summaries
    summary_map = {s['storm_id']: s for s in actor_summaries}
    for storm in actor_storms:
        if storm['storm_id'] in summary_map:
            storm.update(summary_map[storm['storm_id']])
    
    # Enrich storms with trajectory metrics
    # Match by actor and time overlap (storms are snapshots, trajectories track over time)
    for storm in actor_storms:
        actor = storm['actor']
        storm_start = storm['created_at'][:10]
        
        # Find matching trajectory for this actor
        matching_traj = None
        for traj in trajectories:
            if traj['actor'] == actor:
                # Use the trajectory with the most events (primary trajectory for actor)
                if matching_traj is None or traj['total_events'] > matching_traj.get('total_events', 0):
                    matching_traj = traj
        
        if matching_traj:
            storm['peak_ratio'] = matching_traj.get('peak_ratio', 0)
            storm['momentum'] = matching_traj.get('latest_momentum', 0)
            storm['acceleration'] = matching_traj.get('latest_acceleration', 0)
            storm['drift'] = matching_traj.get('latest_drift', 0)
        else:
            storm['peak_ratio'] = 0
            storm['momentum'] = 0
            storm['acceleration'] = 0
            storm['drift'] = 0
    
    # Assign shift_type to each storm
    for storm in actor_storms:
        evo = evolution_map.get(storm.get('storm_id', ''))
        if evo and evo.get('has_evolution') and evo.get('shift_type'):
            storm['shift_type'] = evo['shift_type']
        else:
            # Classify from titles when no evolution data
            titles = storm.get('cluster_titles_topN', [])
            storm['shift_type'] = classify_shift_type_from_titles(titles, storm.get('drift', 0))
    
    eco_summary_map = {s['storm_id']: s for s in eco_summaries}
    for storm in eco_storms:
        if storm['storm_id'] in eco_summary_map:
            storm.update(eco_summary_map[storm['storm_id']])

    # Fallback naming for ecosystem storms with no LLM/summary headline
    def _eco_fallback_headline(storm):
        actors = storm.get('dominant_actors') or storm.get('actors', [])
        titles = storm.get('cluster_titles_topN', [])
        rep    = storm.get('representative_events', [])
        # Extract key noun phrase from first cluster title or rep event title
        source_title = titles[0] if titles else (rep[0]['title'] if rep else '')
        actor_str = ' and '.join(actors[:2]) if actors else 'ecosystem'
        if source_title:
            # Truncate to a clean phrase — strip trailing noise words
            phrase = source_title[:60].rsplit(' ', 1)[0] if len(source_title) > 60 else source_title
            return f"{phrase} [{actor_str}]"
        return f"Ecosystem narrative around {actor_str}"

    for storm in eco_storms:
        if not storm.get('display_headline') and not storm.get('headline') and not storm.get('llm_headline'):
            storm['display_headline'] = _eco_fallback_headline(storm)
            storm['display_source']   = 'fallback'

    eco_traj_map = {}
    for traj in eco_trajectories:
        eco_traj_map[traj['trajectory_id']] = traj
    
    for storm in eco_storms:
        # Only add momentum/acceleration if not already present
        if 'momentum' not in storm or 'acceleration' not in storm:
            traj = eco_traj_map.get(storm.get('trajectory_id'))
            if traj:
                storm['momentum'] = traj.get('latest_momentum', 0)
                storm['acceleration'] = traj.get('latest_acceleration', 0)
            else:
                storm['momentum'] = 0
                storm['acceleration'] = 0
    
    # Compute coherence from clustering metrics (separate from drift)
    for storm in actor_storms:
        # Case A: Topic clustering used
        if storm.get('used_topic_clustering'):
            storm['coherence'] = storm.get('cluster_dominance_ratio', 0)
            storm['coherence_source'] = 'clustering'
        # Case B: No clustering but compactness available (fallback)
        elif storm.get('event_count', 0) >= 5:
            # Conservative fallback: cap at 0.75
            # Use summary confidence as proxy for compactness
            fallback_score = min(0.75, storm.get('summary_confidence', 0.5))
            storm['coherence'] = fallback_score
            storm['coherence_source'] = 'fallback'
        # Case C: Sparse storms
        else:
            storm['coherence'] = None
            storm['coherence_source'] = 'sparse'
    
    # Render-layer deduplication by storm_id
    actor_storms = dedupe_by_storm_id(actor_storms, 'actor_storms')
    eco_storms = dedupe_by_storm_id(eco_storms, 'eco_storms')

    # Apply canonical storm display names (produced by clean_narrative_lineages.py)
    _display_names_path = base_dir / 'data' / 'derived' / 'storm_display_names.json'
    if _display_names_path.exists():
        try:
            _display_names = json.loads(_display_names_path.read_text())
            for s in actor_storms + eco_storms:
                if s['storm_id'] in _display_names:
                    s['raw_display_headline'] = s.get('display_headline')
                    s['display_headline']     = _display_names[s['storm_id']]
        except Exception:
            pass

    # Load cluster merge map (produced by clean_narrative_lineages.py)
    _storm_merges: dict = {}
    _storm_merges_path = base_dir / 'data' / 'derived' / 'storm_merges.json'
    if _storm_merges_path.exists():
        try:
            _storm_merges = json.loads(_storm_merges_path.read_text())
        except Exception:
            pass

    # Count states and compute averages
    state_counts = defaultdict(int)
    total_coherence = 0
    total_events = 0
    coherence_count = 0
    for storm in actor_storms:
        state_counts[storm.get('state', 'unknown')] += 1
        if storm.get('coherence') is not None:
            total_coherence += storm['coherence']
            coherence_count += 1
        total_events += storm.get('event_count', 0)
    
    avg_coherence = total_coherence / coherence_count if coherence_count > 0 else 0
    avg_storm_size = total_events / len(actor_storms) if actor_storms else 0
    
    # Get top actors - force specific actors if desired
    actor_counts = defaultdict(int)
    for storm in actor_storms:
        actor_counts[storm['actor']] += 1
    
    # Track the six actors shown on the homepage map
    priority_actors = ['NVDA', 'INTC', 'AMZN', 'OPENAI', 'ANTHROPIC', 'META']
    top_actors = [(a, actor_counts[a]) for a in priority_actors if a in actor_counts]
    
    # Get diverse ecosystem storms (filter for cross-actor narratives)
    # Filter for true cross-actor storms with stricter entropy requirement
    cross_actor_storms = [
        s for s in eco_storms
        if s.get('num_unique_actors', 0) >= 2
        and (
            s.get('actor_entropy', 0) >= 0.5  # Primary filter: good entropy
            or (s.get('actor_entropy', 0) >= 0.3 and s.get('event_count', 0) >= 15)  # Allow lower entropy if strong event count
        )
    ]
    
    # Separate single-actor storms
    single_actor_storms = [
        s for s in eco_storms
        if s.get('num_unique_actors', 0) == 1
    ]
    
    # Sort cross-actor storms by gravity score
    cross_actor_storms_sorted = sorted(cross_actor_storms, key=lambda s: -s.get('gravity_score', 0))
    
    # Select top 3 diverse cross-actor storms
    eco_storms_diverse = []
    seen_metrics = set()
    for storm in cross_actor_storms_sorted:
        metric_key = (storm.get('event_count'), storm.get('momentum'), storm.get('acceleration'))
        if metric_key not in seen_metrics:
            eco_storms_diverse.append(storm)
            seen_metrics.add(metric_key)
            if len(eco_storms_diverse) >= 3:
                break
    
    # If we don't have 3 cross-actor storms, fill with highest priority ones
    if len(eco_storms_diverse) < 3:
        for storm in cross_actor_storms_sorted:
            if storm not in eco_storms_diverse:
                eco_storms_diverse.append(storm)
                if len(eco_storms_diverse) >= 3:
                    break
    
    eco_storms_sorted = eco_storms_diverse[:3]
    
    # Build per-storm propagation chain counts for gravity centrality
    chain_count_map = defaultdict(int)
    if isinstance(propagation_chains, list):
        for chain in propagation_chains:
            for actor in chain.get('actors', []):
                for storm in actor_storms:
                    if storm.get('actor') == actor:
                        chain_count_map[storm['storm_id']] += 1

    # Compute pressure for all storms
    pressure_map = {}
    for storm in actor_storms:
        p = compute_pressure_score(storm, storm_type='actor')
        p['pressure_interpretation'] = interpret_pressure(storm, p)
        pressure_map[storm['storm_id']] = p
    for storm in eco_storms:
        p = compute_pressure_score(storm, storm_type='ecosystem')
        p['pressure_interpretation'] = interpret_pressure(storm, p)
        pressure_map[storm['storm_id']] = p

    # Compute gravity scores
    all_storms_for_gravity = actor_storms + eco_storms
    max_event_count = max((s.get('event_count', 0) for s in all_storms_for_gravity), default=1)
    max_chain_count = max((chain_count_map.get(s['storm_id'], 0) for s in all_storms_for_gravity), default=1)

    gravity_map = {}
    for storm in all_storms_for_gravity:
        storm['chain_count'] = chain_count_map.get(storm['storm_id'], 0)
        p = pressure_map[storm['storm_id']]
        stype = 'ecosystem' if storm.get('storm_id', '').startswith('eco_') else 'actor'
        g = compute_gravity_score(storm, p['pressure_score'], max_event_count, max_chain_count, storm_type=stype)
        storm['gravity_score'] = g['gravity_score']
        storm['gravity_components'] = g['gravity_components']
        storm['gravity_formula'] = g['gravity_formula']
        gravity_map[storm['storm_id']] = g

    # Compute velocity for all storms
    for storm in all_storms_for_gravity:
        stype = 'ecosystem' if storm.get('storm_id', '').startswith('eco_') else 'actor'
        timestamps = [event_ts_map[eid] for eid in storm.get('event_ids', []) if eid in event_ts_map]
        if stype == 'ecosystem':
            v = compute_velocity(storm, timestamps, storm_type='ecosystem',
                                 anchor_mode='report_latest',
                                 report_reference_time=report_reference_time)
        else:
            v = compute_velocity(storm, timestamps, storm_type='actor')
        storm['velocity_score'] = v['velocity_score']
        storm['velocity_state'] = v['velocity_state']
        storm['velocity_confidence'] = v['velocity_confidence']
        storm['velocity_window'] = v['velocity_window']
        storm['velocity_anchor_mode'] = v['velocity_anchor_mode']
        storm['velocity_reference_time'] = v['velocity_reference_time']
        storm['events_last_48h'] = v['events_last_48h']
        storm['events_prev_48h'] = v['events_prev_48h']

    # Classify priority bucket (gravity × velocity overlay)
    PRIORITY_LABELS = {
        'high_gravity_high_velocity': 'Act Now',
        'high_gravity_low_velocity':  'Important, Cooling',
        'low_gravity_high_velocity':  'Emerging Watch',
        'low_gravity_low_velocity':   'Background',
    }
    for storm in all_storms_for_gravity:
        high_g = storm.get('gravity_score', 0) >= 0.60
        is_eco = storm.get('storm_id', '').startswith('eco_')
        accel  = storm.get('velocity_state') == 'accelerating'
        conf   = storm.get('velocity_confidence', 'low')
        if is_eco:
            high_v = accel and conf == 'high'
        else:
            high_v = accel and conf in ('medium', 'high')
        storm['velocity_high_v'] = high_v  # store for diagnostic
        bucket = ('high_gravity' if high_g else 'low_gravity') + '_' + ('high_velocity' if high_v else 'low_velocity')
        storm['priority_bucket'] = bucket
        storm['priority_label']  = PRIORITY_LABELS[bucket]

    # Narrative lineage grouping (after gravity so lineage_gravity_score is meaningful)
    all_storms_for_gravity, lineage_summaries = group_into_lineages(all_storms_for_gravity)

    # Narrative registry — match lineages to persistent narratives
    registry_path = base_dir / 'data' / 'narrative_registry.jsonl'

    if reset_registry and registry_path.exists():
        archive_dir = base_dir / 'data' / 'archive'
        archive_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_path = archive_dir / f'narrative_registry_{ts}.jsonl'
        registry_path.rename(archive_path)
        print(f"  [registry reset] Archived existing registry to: {archive_path}")
        print(f"  [registry reset] Starting fresh empty registry for this run.")

    narratives, registry_match_log, registry_load_stats = update_registry(lineage_summaries, all_storms_for_gravity, path=registry_path)

    # Lineage aggregation
    lineages = {}
    for storm in all_storms_for_gravity:
        lid = storm.get('lineage_id')
        if not lid:
            continue
        if lid not in lineages:
            lineages[lid] = {
                'lineage_id':    lid,
                'label':         storm.get('lineage_label', lid),
                'lineage_type':  storm.get('lineage_type', 'actor'),
                'storms':        [],
                'event_count':   0,
                'actor_set':     set(),
                'start_time':    storm.get('lineage_start_time', ''),
                'latest_time':   storm.get('lineage_latest_time', ''),
                'max_gravity':   0.0,
                'max_velocity':  0.0,
            }
        rec = lineages[lid]
        rec['storms'].append(storm)
        rec['event_count']  += storm.get('event_count', 0)
        rec['actor_set'].update(
            storm.get('lineage_actor_set') or
            storm.get('actors', []) or
            ([storm['actor']] if storm.get('actor') else [])
        )
        rec['max_gravity']  = max(rec['max_gravity'],  storm.get('gravity_score', 0))
        rec['max_velocity'] = max(rec['max_velocity'], storm.get('velocity_score', 0))

    # Compute derived fields and sort
    def _duration_days(start, latest):
        try:
            def _p(ts):
                ts = ts.rstrip('Z').replace('+00:00Z', '+00:00')
                return datetime.fromisoformat(ts if ts.endswith('+00:00') else ts + '+00:00')
            return abs((_p(latest) - _p(start)).days)
        except Exception:
            return 0

    for rec in lineages.values():
        rec['lineage_storm_count']    = len(rec['storms'])
        rec['lineage_event_count']    = rec['event_count']
        rec['lineage_actor_count']    = len(rec['actor_set'])
        rec['lineage_actor_set']      = sorted(rec['actor_set'])
        rec['lineage_max_gravity']    = round(rec['max_gravity'], 4)
        rec['lineage_max_velocity']   = round(rec['max_velocity'], 4)
        rec['lineage_duration_days']  = _duration_days(rec['start_time'], rec['latest_time'])
        del rec['actor_set'], rec['event_count'], rec['max_gravity'], rec['max_velocity']

    lineages_sorted = sorted(lineages.values(), key=lambda r: -r['lineage_max_gravity'])

    # Attach retail amplification stats to each lineage record
    for rec in lineages_sorted:
        amp = retail_amp_map.get(rec['lineage_id'], {})
        rec['retail_event_count']          = amp.get('retail_event_count', 0)
        rec['retail_amplification_ratio']  = amp.get('retail_amplification_ratio', 0.0)
        rec['retail_source_count']         = amp.get('retail_source_count', 0)
        rec['retail_sources']              = amp.get('retail_sources', [])
        rec['retail_events']               = amp.get('retail_events', [])
        rec['mean_retail_attach_score']    = amp.get('mean_retail_attach_score')

    # Load cleaned lineages (produced by clean_narrative_lineages.py)
    cleaned_lineages_path = base_dir / 'data' / 'derived' / 'cleaned_lineages.json'
    cleaned_lineages: dict = {}
    if cleaned_lineages_path.exists():
        try:
            cleaned_lineages = json.loads(cleaned_lineages_path.read_text())
        except Exception:
            pass

    # Merge cleaned data onto lineage records
    for rec in lineages_sorted:
        lid = rec['lineage_id']
        if lid in cleaned_lineages and 'canonical_name' in cleaned_lineages[lid]:
            cl = cleaned_lineages[lid]
            rec['label']            = cl['canonical_name']
            rec['cleaned_summary']  = cl.get('summary', '')
            rec['cleaned_phases']   = cl.get('phases', [])
            rec['narrative_type']   = cl.get('narrative_type', '')
            rec['cleaned_notes']    = cl.get('notes', '')

    # Build lineage section HTML
    def _lineage_narrative_summary(rec):
        """Generate a short prose summary for a lineage block."""
        storms_in_lin = sorted(rec['storms'], key=lambda s: s.get('created_at', ''))
        actors = rec['lineage_actor_set']
        duration = rec['lineage_duration_days']
        count = rec['lineage_storm_count']
        # Time anchor
        try:
            start_dt = datetime.fromisoformat(
                rec['start_time'].rstrip('Z').replace('+00:00Z', '+00:00')
                if rec['start_time'].endswith('+00:00') else rec['start_time'] + '+00:00'
            )
            month_str = start_dt.strftime('%B')
        except Exception:
            month_str = 'early in the period'
        # Theme hint from first storm
        first = storms_in_lin[0] if storms_in_lin else {}
        phrases = first.get('domain_phrases') or first.get('themes') or []
        theme_hint = ', '.join(phrases[:2]) if phrases else 'related themes'
        actor_str = ' and '.join(actors[:3]) if actors else 'multiple actors'
        window_word = 'storm window' if count == 1 else f'{count} storm windows'
        dur_str = f'over {duration} days' if duration > 1 else 'within a single day'
        return (f"This narrative emerged in {month_str} and developed across {window_word} {dur_str}, "
                f"centered on {theme_hint} as it propagated through {actor_str}.")

    def _storm_ts_range(storm):
        """Best-effort timestamp range label for a storm."""
        created = storm.get('created_at', '')[:10]
        updated = storm.get('updated_at', storm.get('created_at', ''))[:10]
        return created if created == updated else f"{created} → {updated}"

    def _build_lineage_section_html(lineages_sorted, top_n=8):
        if not lineages_sorted:
            return '<p class="muted">No lineages detected in this report window.</p>'
        parts = []
        for rec in lineages_sorted[:top_n]:
            storms_in_lin = sorted(rec['storms'], key=lambda s: s.get('created_at', ''))
            label = rec['label']
            actors_str = ', '.join(rec['lineage_actor_set'])
            start = rec['start_time'][:10] if rec['start_time'] else 'N/A'
            latest = rec['latest_time'][:10] if rec['latest_time'] else 'N/A'
            # Use Claude-cleaned summary if available, else procedural fallback
            summary = rec.get('cleaned_summary') or _lineage_narrative_summary(rec)

            # Use Claude-cleaned phases if available, else embedding-based
            phase_cards = []
            if rec.get('cleaned_phases'):
                for ph in rec['cleaned_phases']:
                    key_actors = ', '.join(ph.get('key_actors', [])[:4]) or '—'
                    signal     = ph.get('signal', '')
                    phase_cards.append(
                        f'<div style="border:1px solid var(--line);border-radius:6px;padding:10px 12px;margin-bottom:8px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px">'
                        f'<strong style="font-size:12px">Phase {ph["phase_number"]}: {ph["name"]}</strong>'
                        f'<span style="font-size:10px;color:var(--muted);font-style:italic">{signal}</span>'
                        f'</div>'
                        f'<div style="font-size:11px;color:var(--muted);margin-bottom:4px">'
                        f'{ph["date_range"]} &nbsp;·&nbsp; {key_actors}</div>'
                        f'<div style="font-size:12px;margin-bottom:4px">{ph["description"]}</div>'
                        f'</div>'
                    )
                if rec.get('cleaned_notes'):
                    phase_cards.append(
                        f'<p style="font-size:11px;color:var(--muted);font-style:italic;margin-top:4px">'
                        f'Note: {rec["cleaned_notes"]}</p>'
                    )
            else:
                phases = compute_macro_phases(storms_in_lin, actor_traj_map=_actor_traj_map)
                for ph in phases:
                    actors_str_ph = ', '.join(ph['dominant_actors'][:4])
                    keywords_str  = ', '.join(ph['top_keywords'][:3]) or '—'
                    trend_class   = state_to_class(ph['trend'])
                    date_range    = ph['phase_start'] if ph['phase_start'] == ph['phase_end'] else f"{ph['phase_start']} → {ph['phase_end']}"
                    v = ph['phase_velocity']
                    if v > 5:
                        momentum_bar = '<span style="color:#2ca02c;font-size:10px">▲ expanding</span>'
                    elif v < -5:
                        momentum_bar = '<span style="color:#d62728;font-size:10px">▼ contracting</span>'
                    else:
                        momentum_bar = '<span style="color:#888;font-size:10px">● stable</span>'
                    phase_cards.append(
                        f'<div style="border:1px solid var(--line);border-radius:6px;padding:10px 12px;margin-bottom:8px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px">'
                        f'<strong style="font-size:12px">Phase {ph["phase_number"]}: {ph["label"]}</strong>'
                        f'<span class="state-badge {trend_class}" style="font-size:10px">{ph["trend"]}</span>'
                        f'</div>'
                        f'<div style="font-size:11px;color:var(--muted);margin-bottom:4px">{date_range} &nbsp;·&nbsp; {actors_str_ph}</div>'
                        f'<div style="font-size:11px;color:var(--muted);margin-bottom:4px">{keywords_str}</div>'
                        f'<div style="display:flex;gap:16px;font-size:11px">'
                        f'<span>{ph["storm_count"]} windows</span>'
                        f'<span>{ph["total_events"]} events</span>'
                        f'<span>gravity {ph["phase_gravity"]:.3f}</span>'
                        f'<span>entropy {ph["actor_entropy"]:.2f}</span>'
                        f'<span>{momentum_bar}</span>'
                        f'</div>'
                        f'</div>'
                    )

            retail_count  = rec.get('retail_event_count', 0)
            retail_ratio  = rec.get('retail_amplification_ratio', 0.0)
            retail_src_ct = rec.get('retail_source_count', 0)
            retail_mean   = rec.get('mean_retail_attach_score')
            retail_badge  = ''
            retail_block  = ''
            if retail_count > 0:
                intensity   = 'high' if retail_ratio >= 0.15 else 'moderate' if retail_ratio >= 0.05 else 'low'
                badge_color = {'high': '#d62728', 'moderate': '#ff7f0e', 'low': '#888'}[intensity]
                retail_badge = (
                    f'<span style="display:inline-block;background:{badge_color};color:#fff;'
                    f'border-radius:3px;padding:1px 7px;font-size:10px;font-weight:700;'
                    f'margin-left:8px;vertical-align:middle">'
                    f'\U0001f4e2 Retail \u00d7{retail_count} ({retail_ratio:.0%})</span>'
                )
                mean_str = f'{retail_mean:.2f}' if retail_mean is not None else 'N/A'
                retail_block = (
                    f'<div style="margin-top:8px;padding:8px 10px;background:rgba(255,255,255,0.04);'
                    f'border-left:3px solid {badge_color};border-radius:2px">'
                    f'<div style="font-size:11px;font-weight:700;color:{badge_color};'
                    f'text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">'
                    f'Retail amplification</div>'
                    f'<ul style="margin:0;padding-left:16px;font-size:11px;color:var(--muted)">'
                    f'<li>{retail_count} event{"s" if retail_count != 1 else ""}</li>'
                    f'<li>{retail_src_ct} source{"s" if retail_src_ct != 1 else ""}</li>'
                    f'<li>Mean attach score {mean_str}</li>'
                    f'<li>Shared actor support present</li>'
                    f'</ul>'
                    f'</div>'
                )

            mread = rec.get('market_read_text', '')
            market_block = (
                f'<p style="font-size:11px;color:var(--muted);margin:0 0 8px">'
                f'<strong>Market read:</strong> {mread}</p>'
            ) if mread else ''

            parts.append(
                f'<div class="section card" style="margin-bottom:18px">'
                f'<h3 style="margin-bottom:6px">{label}{retail_badge}</h3>'
                f'<ul class="details-grid" style="margin-bottom:10px">'
                f'<li><strong>Actors:</strong> {actors_str}</li>'
                f'<li><strong>Period:</strong> {start} → {latest} ({len(phase_cards)} phase{"s" if len(phase_cards) != 1 else ""}, {len(storms_in_lin)} windows)</li>'
                f'<li><strong>Total events:</strong> {rec["lineage_event_count"]}</li>'
                f'<li><strong>Duration:</strong> {rec["lineage_duration_days"]}d</li>'
                f'<li><strong>Max gravity:</strong> {rec["lineage_max_gravity"]:.4f}</li>'
                f'<li><strong>Max velocity:</strong> {rec["lineage_max_velocity"]:.4f}</li>'
                f'</ul>'
                + market_block +
                f'<p class="muted" style="font-size:12px;margin-bottom:10px;font-style:italic">{summary}</p>'
                + retail_block +
                f'<div style="margin-top:8px">{"".join(phase_cards)}</div>'
                f'</div>'
            )
        return ''.join(parts)

    # Flat window lookup — used for trend history enrichment below
    _all_windows_by_id = {s['storm_id']: s for s in actor_storms + eco_storms}

    # Breakout candidate detection
    for storm in all_storms_for_gravity:
        storm['is_breakout_candidate'] = (
            0.40 <= storm.get('gravity_score', 0) < 0.60
            and storm.get('velocity_state') == 'accelerating'
            and storm.get('velocity_confidence') in ('medium', 'high')
        )

    # Build pressure signal lists — one row per storm identity (merged, not per-window)
    _actor_storms_merged = _apply_storm_merges(actor_storms, _storm_merges)
    _eco_storms_merged   = _apply_storm_merges(eco_storms,   _storm_merges)

    # Storm-level state counts (not window-level)
    storm_state_counts = defaultdict(int)
    for s in _actor_storms_merged:
        storm_state_counts[s.get('state', 'unknown')] += 1

    # Enrich merged storms with time-series history and trend classification
    for _ms in _actor_storms_merged + _eco_storms_merged:
        _m = _storm_merges.get(_ms['storm_id'], {})
        _wids = list(dict.fromkeys(_m.get('window_ids', [_ms['storm_id']])))
        _hist = []
        for _wid in _wids:
            _raw = _all_windows_by_id.get(_wid)
            if _raw is None:
                continue
            _p = pressure_map.get(_wid, {})
            _actor_ids = _raw.get('actors') or _raw.get('actor_ids') or [_raw.get('actor', '?')]
            _hist.append({
                "date":        _raw.get('created_at', '')[:10],
                "event_count": _raw.get('event_count', 0),
                "coherence":   _raw.get('coherence'),
                "gravity":     _raw.get('gravity_score'),
                "pressure":    _p.get('pressure_score'),
                "actor_count": len(_actor_ids) if isinstance(_actor_ids, list) else 1,
            })
        _ms['_history'] = _hist
        _ms['trend'], _ms['trend_explanation'] = classify_trend(_hist)
        _full = compute_narrative_momentum_full(_ms, _hist)
        _ms['momentum_score']      = _full['score']
        _ms['momentum_class']      = _full['momentum_class']
        _ms['momentum_explanation'] = momentum_explanation(_ms, _hist)
        _ms['momentum_components'] = _full['components']
        _ms['momentum_delta']      = _full['delta']
        _ms['lead_score']            = _full['lead_score']
        _ms['lead_class']            = _full['lead_class']
        _ms['narrative_state']       = _full['narrative_state']
        _ms['narrative_state_interp'] = _full['narrative_state_interp']

    # Fast lookup: storm_id → momentum data (for actor snapshot resolution)
    _momentum_lookup = {
        ms['storm_id']: {
            'momentum_score':       ms['momentum_score'],
            'momentum_class':       ms['momentum_class'],
            'momentum_explanation': ms['momentum_explanation'],
            'momentum_components':  ms['momentum_components'],
            'momentum_delta':       ms['momentum_delta'],
            'lead_score':             ms['lead_score'],
            'lead_class':             ms['lead_class'],
            'narrative_state':        ms['narrative_state'],
            'narrative_state_interp': ms['narrative_state_interp'],
        }
        for ms in _actor_storms_merged + _eco_storms_merged
    }

    actor_pressure = [(s, pressure_map[s['storm_id']]) for s in _actor_storms_merged if s['storm_id'] in pressure_map]
    eco_pressure   = [(s, pressure_map[s['storm_id']]) for s in _eco_storms_merged   if s['storm_id'] in pressure_map]
    all_pressure   = actor_pressure + eco_pressure

    high_pressure_deduped     = sorted([x for x in all_pressure if x[1]['pressure_level'] == 'high'],     key=lambda x: -x[1]['pressure_score'])
    building_pressure_deduped = sorted([x for x in all_pressure if x[1]['pressure_level'] == 'building'], key=lambda x: -x[1]['pressure_score'])
    
    # Build pressure HTML for executive overview — sorted by momentum_score
    _TREND_ARROWS = {'expanding': '↑', 'building': '↗', 'cooling': '↓', 'unstable': '~'}

    def _trend_tag(s):
        t = s.get('trend', '')
        if not t or t == 'stable':
            return ''
        arrow = _TREND_ARROWS.get(t, '')
        expl  = s.get('trend_explanation', '')
        return (f' <span title="{expl}" style="font-size:13px;cursor:default">{arrow}</span>'
                f' <span class="muted" style="font-size:10px">{t}</span>')

    def _momentum_tag(s):
        ms = s.get('momentum_score')
        mc = s.get('momentum_class', '')
        me = s.get('momentum_explanation', '')
        md = s.get('momentum_delta', 0.0) or 0.0
        if ms is None:
            return ''
        color = {'Surging': '#d62728', 'Expanding': '#ff7f0e',
                 'Building': '#2ca02c', 'Stable': '#888', 'Cooling': '#aaa'}.get(mc, '#888')
        delta_str = (f' <span style="color:#2ca02c">+{md:.0f}</span>' if md >= 2
                     else f' <span style="color:#d62728">{md:.0f}</span>' if md <= -2
                     else '')
        return (
            f'<br><span style="font-size:10px">'
            f'<span style="color:{color};font-weight:700">{mc}</span>'
            f'<span class="muted"> · {ms:.0f}</span>{delta_str}'
            f'</span>'
            f'<br><span class="muted" style="font-size:10px">{me}</span>'
        )

    # Group all pressure storms by momentum class; sort within each group by momentum_score desc
    _all_pressure_merged = [s for s in _actor_storms_merged + _eco_storms_merged
                            if s['storm_id'] in pressure_map]
    _all_pressure_merged.sort(key=lambda s: -(s.get('momentum_score') or 0))

    def _pressure_item_html(s):
        p = pressure_map[s['storm_id']]
        label = _dh(s, 70)
        return (f'<li>{label}{_trend_tag(s)}{_momentum_tag(s)}'
                f' <span class="muted">({p["pressure_score"]:.2f})</span></li>')

    _surging   = [s for s in _all_pressure_merged if s.get('momentum_class') == 'Surging']
    _expanding = [s for s in _all_pressure_merged if s.get('momentum_class') == 'Expanding']
    _building  = [s for s in _all_pressure_merged if s.get('momentum_class') == 'Building']
    _cooling   = [s for s in _all_pressure_merged
                  if s.get('momentum_class') in ('Stable', 'Cooling')]

    high_pressure_html    = [_pressure_item_html(s) for s in (_surging + _expanding)[:4]]
    building_pressure_html = [_pressure_item_html(s) for s in _building[:5]]

    # Keep legacy deduped lists for interpretation text counts
    high_pressure_deduped     = [(s, pressure_map[s['storm_id']]) for s in _surging + _expanding]
    building_pressure_deduped = [(s, pressure_map[s['storm_id']]) for s in _building]
    
    # Pressure interpretation
    n_high = len(high_pressure_deduped)
    n_building = len(building_pressure_deduped)
    if n_high > 0:
        pressure_interp = f"{n_high} narrative(s) under high pressure may expand further. {n_building} additional narrative(s) are building momentum."
    elif n_building > 0:
        pressure_interp = f"{n_building} narrative(s) show building pressure, suggesting additional ecosystem spread may follow."
    else:
        pressure_interp = "No narratives currently show significant pressure signals."
    
    # Compute ecosystem diagnostics
    total_eco_storms = len(eco_storms)
    cross_actor_count = len(cross_actor_storms)
    single_actor_count = len(single_actor_storms)
    avg_actors = sum(s.get('num_unique_actors', 0) for s in eco_storms) / len(eco_storms) if eco_storms else 0
    avg_entropy = sum(s.get('actor_entropy', 0) for s in eco_storms) / len(eco_storms) if eco_storms else 0
    
    # Get top merge candidates
    merge_sorted = sorted(merge_candidates, key=lambda x: x.get('merge_score', 0), reverse=True)[:3]
    
    # Get top propagation chains
    chains_sorted = sorted(propagation_chains, key=lambda x: x.get('mean_score', 0), reverse=True)[:3] if isinstance(propagation_chains, list) else []
    
    # Compute narrative leadership
    leadership_results = compute_leadership(propagation_edges, propagation_chains if isinstance(propagation_chains, list) else [])
    theme_leadership = compute_theme_leadership(propagation_edges, propagation_chains if isinstance(propagation_chains, list) else [])
    
    # Save leadership data
    with open(data_dir / 'narrative_leadership.json', 'w') as f:
        json.dump(leadership_results, f, indent=2)
    if theme_leadership:
        with open(data_dir / 'theme_leadership.json', 'w') as f:
            json.dump(theme_leadership, f, indent=2)
    
    # Build leadership map for actor snapshots
    leadership_map = {r['actor']: r for r in leadership_results}

    # Compute lead-lag alpha (needs gravity_map to be complete)
    actor_gravity_map = {}
    for storm in actor_storms:
        actor = storm.get('actor', '')
        g = storm.get('gravity_score', 0)
        if g > actor_gravity_map.get(actor, 0):
            actor_gravity_map[actor] = g
    chains_list = propagation_chains if isinstance(propagation_chains, list) else []
    lead_lag_results = compute_lead_lag_alpha(chains_list, actor_gravity_map)
    with open(data_dir / 'lead_lag_alpha.json', 'w') as f:
        json.dump(lead_lag_results, f, indent=2)

    # Generate narrative phase map (needs gravity + velocity + leadership_map)
    phase_map_result = generate_phase_map(all_storms_for_gravity, leadership_map, data_dir)
    phase_map_lineages_result = generate_phase_map_lineages(lineages_sorted, leadership_map, data_dir)

    # Group actors by role for report section
    role_groups = defaultdict(list)
    for r in leadership_results:
        role_groups[r['role']].append(r)
    
    # Build leadership HTML for report
    leadership_rows_html = []
    for r in sorted(leadership_results, key=lambda x: max(x['leader_score'], x['amplifier_score'], x['bridge_score'], x['receiver_score']), reverse=True):
        role_label = r['role'].title()
        top_score = max(r['leader_score'], r['amplifier_score'], r['bridge_score'], r['receiver_score'])
        desc = generate_role_description(r['actor'], r['role'], r)
        leadership_rows_html.append(
            f"<tr><td><strong>{r['actor']}</strong></td><td>{role_label}</td>"
            f"<td>{r.get('centrality_score', 0):.4f}</td>"
            f"<td>{r['chains_participated']}</td>"
            f"<td class='muted'>{desc}</td></tr>"
        )
    vars_leadership_html = ''.join(leadership_rows_html) if leadership_rows_html else '<tr><td colspan="5" class="muted">No propagation data available</td></tr>'
    
    # Role summary strings
    leader_actors = ', '.join(r['actor'] for r in role_groups.get('leader', []))
    amplifier_actors = ', '.join(r['actor'] for r in role_groups.get('amplifier', []))
    bridge_actors = ', '.join(r['actor'] for r in role_groups.get('bridge', []))
    receiver_actors = ', '.join(r['actor'] for r in role_groups.get('receiver', []))
    
    # Theme leadership HTML
    theme_leadership_html = []
    for t in theme_leadership:
        theme_leadership_html.append(
            f"<tr><td>{t['theme']}</td><td>{t['leader']}</td><td>{t['amplifier']}</td>"
            f"<td>{t['bridge']}</td><td>{t['receiver']}</td></tr>"
        )
    vars_theme_html = ''.join(theme_leadership_html) if theme_leadership_html else '<tr><td colspan="5" class="muted">No theme-level leadership detected</td></tr>'
    
    # Build strategic watchlist — ranked by lineage score
    # lineage_score = 0.5 * momentum + 0.3 * gravity + 0.2 * velocity
    # Velocity is capped at 1.5 to prevent extreme spikes from dominating gravity.

    def _pressure_for_lineage(rec, pressure_map):
        """Max pressure level and score across storms in a lineage."""
        levels = {'high': 2, 'building': 1, 'low': 0}
        best_level, best_score = 'low', 0.0
        for s in rec['storms']:
            p = pressure_map.get(s['storm_id'], {})
            ps = p.get('pressure_score', 0)
            pl = p.get('pressure_level', 'low')
            if levels.get(pl, 0) > levels.get(best_level, 0) or ps > best_score:
                best_level = pl
                best_score = ps
        return best_level, round(best_score, 3)

    def _velocity_for_lineage(rec):
        """Displayed velocity state from the most recent storm in the lineage."""
        storms_sorted = sorted(rec['storms'], key=lambda s: s.get('created_at', ''), reverse=True)
        return displayed_velocity_state(storms_sorted[0]) if storms_sorted else 'N/A'

    def _recent_window(rec):
        """Most recent storm window start date."""
        storms_sorted = sorted(rec['storms'], key=lambda s: s.get('created_at', ''), reverse=True)
        return storms_sorted[0].get('created_at', '')[:10] if storms_sorted else 'N/A'

    # Build lineage_type lookup from summaries
    lineage_type_map = {s['lineage_id']: s.get('lineage_type', 'actor') for s in lineage_summaries}

    # Momentum lookup: window_id → momentum_score (via representative_id)
    _momentum_by_sid = {ms['storm_id']: ms.get('momentum_score', 0.0)
                        for ms in _actor_storms_merged + _eco_storms_merged}
    def _max_momentum_for_lineage(rec):
        best = 0.0
        for s in rec['storms']:
            sid = s.get('storm_id', '')
            rep = _storm_merges.get(sid, {}).get('representative_id', sid)
            m = _momentum_by_sid.get(rep, _momentum_by_sid.get(sid, 0.0))
            if m > best:
                best = m
        return round(best, 1)

    # Score and rank lineages
    watchlist_lineages = []
    for rec in lineages_sorted:
        capped_vel = min(rec['lineage_max_velocity'], 1.5)
        max_mom = _max_momentum_for_lineage(rec)
        score = 0.5 * (max_mom / 100.0) + 0.3 * rec['lineage_max_gravity'] + 0.2 * min(capped_vel / 1.5, 1.0)
        pl, ps = _pressure_for_lineage(rec, pressure_map)
        actors = rec['lineage_actor_set']
        watchlist_lineages.append({
            'lineage_id':                  rec['lineage_id'],
            'lineage_type':                lineage_type_map.get(rec['lineage_id'], 'actor'),
            'label':                       rec['label'],
            'actor_set':                   actors,
            'lineage_score':               round(score, 4),
            'lineage_max_gravity':         rec['lineage_max_gravity'],
            'lineage_max_velocity':        rec['lineage_max_velocity'],
            'capped_velocity':             round(capped_vel, 4),
            'pressure_level':              pl,
            'pressure_score':              ps,
            'velocity_state':              _velocity_for_lineage(rec),
            'storm_count':                 rec['lineage_storm_count'],
            'event_count':                 rec['lineage_event_count'],
            'recent_window':               _recent_window(rec),
            'duration_days':               rec['lineage_duration_days'],
            'retail_event_count':          rec.get('retail_event_count', 0),
            'retail_amplification_ratio':  rec.get('retail_amplification_ratio', 0.0),
            'lineage_max_momentum':        max_mom,
        })
    watchlist_lineages.sort(key=lambda r: -r['lineage_max_momentum'])
    watchlist_lineages_top = watchlist_lineages[:8]

    # Attach market interpretation to every lineage record
    for rec in lineages_sorted:
        tag, mods, text = _market_interpretation(rec, leadership_map)
        rec['market_state_tag']  = tag
        rec['market_modifiers']  = mods
        rec['market_read_text']  = text
    for r in watchlist_lineages_top:
        tag, mods, text = _market_interpretation(r, leadership_map)
        r['market_state_tag'] = tag
        r['market_modifiers'] = mods
        r['market_read_text'] = text

    # Fallback: if no lineages, build single-storm entries ranked by gravity
    if not watchlist_lineages_top:
        pressure_for_watchlist = []
        for storm in _apply_storm_merges(actor_storms + eco_storms, _storm_merges):
            p = pressure_map.get(storm['storm_id'])
            if not p:
                continue
            pressure_for_watchlist.append({
                **p,
                'storm_id': storm['storm_id'],
                'label': _dh(storm),
                'actor': storm.get('actor', storm.get('storm_id', '')),
                'state': storm.get('state', 'unknown'),
                'event_count': storm.get('event_count', 0),
                'shift_type': storm.get('shift_type', 'unclear'),
                'domain_phrases': storm.get('domain_phrases', []),
                'num_unique_actors': storm.get('num_unique_actors', 1),
            })
        watchlist_raw = build_pressure_leadership_records(pressure_for_watchlist, leadership_map)
        watchlist_filtered = filter_watchlist(watchlist_raw)
        watchlist_filtered = dedupe_watchlist(watchlist_filtered)
        for r in watchlist_filtered:
            g = gravity_map.get(r['storm_id'])
            r['gravity_score'] = g['gravity_score'] if g else 0.0
        watchlist_filtered.sort(key=lambda r: -r['gravity_score'])
        for r in watchlist_filtered:
            watchlist_lineages_top.append({
                'lineage_id':           None,
                'lineage_type':         'actor',
                'label':                r['label'],
                'actor_set':            [r['actor']],
                'lineage_score':        round(0.5 * (r.get('momentum_score', 0) / 100.0) + 0.3 * r['gravity_score'], 4),
                'lineage_max_gravity':  r['gravity_score'],
                'lineage_max_velocity': 0.0,
                'capped_velocity':      0.0,
                'pressure_level':       r['pressure_level'],
                'pressure_score':       r['pressure_score'],
                'velocity_state':       'N/A',
                'storm_count':          1,
                'event_count':          r['event_count'],
                'recent_window':        'N/A',
                'duration_days':        0,
            })
        watchlist_lineages_top = watchlist_lineages_top[:8]
    else:
        # Also build watchlist_filtered for artifact save (legacy compat)
        pressure_for_watchlist = []
        for storm in _apply_storm_merges(actor_storms + eco_storms, _storm_merges):
            p = pressure_map.get(storm['storm_id'])
            if not p:
                continue
            pressure_for_watchlist.append({
                **p,
                'storm_id': storm['storm_id'],
                'label': _dh(storm),
                'actor': storm.get('actor', storm.get('storm_id', '')),
                'state': storm.get('state', 'unknown'),
                'event_count': storm.get('event_count', 0),
                'shift_type': storm.get('shift_type', 'unclear'),
                'domain_phrases': storm.get('domain_phrases', []),
                'num_unique_actors': storm.get('num_unique_actors', 1),
            })
        watchlist_raw = build_pressure_leadership_records(pressure_for_watchlist, leadership_map)
        watchlist_filtered = filter_watchlist(watchlist_raw)
        watchlist_filtered = dedupe_watchlist(watchlist_filtered)
        for r in watchlist_filtered:
            g = gravity_map.get(r['storm_id'])
            r['gravity_score'] = g['gravity_score'] if g else 0.0
        watchlist_filtered.sort(key=lambda r: -r['gravity_score'])

    wl_priority = [r for r in watchlist_filtered if r['watch_category'] == 'priority_watch']
    wl_monitor  = [r for r in watchlist_filtered if r['watch_category'] == 'monitor_closely']

    # Save watchlist artifact (lineage-ranked)
    with open(data_dir / 'strategic_watchlist.jsonl', 'w') as f:
        for r in watchlist_lineages_top:
            f.write(json.dumps(r) + '\n')

    # Build lineage watchlist HTML — two subsections: actor and ecosystem
    def _watchlist_lineage_html(items):
        actor_items = sorted(
            [r for r in items if r.get('lineage_type') != 'ecosystem'],
            key=lambda r: -r.get('lineage_max_momentum', 0)
        )[:3]
        eco_items = sorted(
            [r for r in items if r.get('lineage_type') == 'ecosystem'],
            key=lambda r: -r.get('lineage_max_momentum', 0)
        )[:3]

        def _rows(group):
            if not group:
                return '<tr><td colspan="7" class="muted" style="font-size:11px">None detected.</td></tr>'
            rows = []
            for r in group:
                actors_str = ', '.join(r['actor_set'][:5])
                retail_count = r.get('retail_event_count', 0)
                retail_ratio = r.get('retail_amplification_ratio', 0.0)
                if retail_count > 0:
                    amp_color = '#d62728' if retail_ratio >= 0.15 else '#ff7f0e' if retail_ratio >= 0.05 else '#888'
                    amp_cell = (f'<span style="color:{amp_color};font-weight:700">'
                                f'📢 {retail_count} ({retail_ratio:.0%})</span>')
                else:
                    amp_cell = '<span style="color:var(--muted)">—</span>'
                mread = r.get('market_read_text', '')
                mom = r.get('lineage_max_momentum', 0)
                mom_color = '#2ca02c' if mom >= 65 else '#ff7f0e' if mom >= 50 else 'var(--muted)'
                mom_cell = f'<span style="color:{mom_color};font-weight:700">{mom:.0f}</span>'
                rows.append(
                    f'<tr>'
                    f'<td style="font-weight:600;font-size:12px">{r["label"][:60]}</td>'
                    f'<td style="font-size:11px">{r.get("lineage_type", "actor").title()}</td>'
                    f'<td style="font-size:11px">{actors_str}</td>'
                    f'<td style="text-align:right">{mom_cell}</td>'
                    f'<td style="text-align:right;font-size:11px">{r["lineage_max_gravity"]:.3f}</td>'
                    f'<td style="font-size:11px;color:var(--muted)">{r["velocity_state"]}</td>'
                    f'<td style="text-align:right">{r["storm_count"]}</td>'
                    f'<td style="font-size:11px;color:var(--muted)">{r["recent_window"]}</td>'
                    f'<td style="font-size:11px;text-align:right">{amp_cell}</td>'
                    f'<td style="font-size:11px;color:var(--muted);font-style:italic">{mread}</td>'
                    f'</tr>'
                )
            return ''.join(rows)

        thead = (
            '<thead><tr>'
            '<th style="text-align:left">Narrative</th>'
            '<th style="text-align:left">Type</th>'
            '<th style="text-align:left">Primary actors</th>'
            '<th style="text-align:right">Momentum</th>'
            '<th style="text-align:right">Gravity</th>'
            '<th style="text-align:left">Velocity</th>'
            '<th style="text-align:right">Storm count</th>'
            '<th style="text-align:left">Latest window</th>'
            '<th style="text-align:right">Retail amp.</th>'
            '<th style="text-align:left">Market read</th>'
            '</tr></thead>'
        )

        def _section(title, group):
            return (
                f'<div style="margin-bottom:14px">'
                f'<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:.05em;color:var(--muted);margin-bottom:6px">{title}</div>'
                f'<table style="width:100%;font-size:12px">{thead}'
                f'<tbody>{_rows(group)}</tbody></table>'
                f'</div>'
            )

        return (
            _section('Actor Narratives to Watch', actor_items) +
            _section('Ecosystem Narratives to Watch', eco_items)
        )

    # Watchlist summary interpretation
    if watchlist_lineages_top:
        top = watchlist_lineages_top[0]
        wl_interp = (f"Top lineage: {top['label'][:55]} — "
                     f"momentum {top.get('lineage_max_momentum', 0):.0f}, "
                     f"gravity {top['lineage_max_gravity']:.3f}, "
                     f"{top['storm_count']} storm window(s), "
                     f"pressure {top['pressure_level']}.")
    else:
        wl_interp = "No lineages currently warrant strategic watch."

    # Build template variables
    vars = {
        'generated_at': datetime.now().strftime('%Y-%m-%d'),
        'actor_list': ', '.join(sorted(actor_counts.keys())),
        'audience_name': 'Internal review',
        
        # Executive summary
        'total_events': sum(s.get('event_count', 0) for s in actor_storms),
        'event_window': 'Feb-Mar 2026',
        'actor_storm_count': len(_actor_storms_merged),
        'trajectory_count': len(trajectories),
        'cross_actor_count': len(propagation_edges),
        'avg_coherence': f"{avg_coherence:.2f}",
        'avg_storm_size': f"{avg_storm_size:.0f}",
        
        # Data sources
        'total_raw_events': total_raw_events,
        'source_1': sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[0][0] if source_counts else 'N/A',
        'source_1_count': sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[0][1] if source_counts else 0,
        'source_1_pct': f"{sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[0][1] / total_raw_events * 100:.1f}" if source_counts and total_raw_events > 0 else '0',
        'source_1_time': f"{source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[0][0], {}).get('start', 'N/A')} - {source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[0][0], {}).get('end', 'N/A')}" if source_counts else 'N/A',
        'source_1_rate': f"{sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[0][1] / max(source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[0][0], {}).get('days', 1), 1):.1f}/day" if source_counts and source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[0][0], {}).get('days', 0) > 0 else 'N/A',
        'source_2': sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[1][0] if len(source_counts) > 1 else 'N/A',
        'source_2_count': sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[1][1] if len(source_counts) > 1 else 0,
        'source_2_pct': f"{sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[1][1] / total_raw_events * 100:.1f}" if len(source_counts) > 1 and total_raw_events > 0 else '0',
        'source_2_time': f"{source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[1][0], {}).get('start', 'N/A')} - {source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[1][0], {}).get('end', 'N/A')}" if len(source_counts) > 1 else 'N/A',
        'source_2_rate': f"{sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[1][1] / max(source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[1][0], {}).get('days', 1), 1):.1f}/day" if len(source_counts) > 1 and source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[1][0], {}).get('days', 0) > 0 else 'N/A',
        'source_3': sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[2][0] if len(source_counts) > 2 else 'N/A',
        'source_3_count': sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[2][1] if len(source_counts) > 2 else 0,
        'source_3_pct': f"{sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[2][1] / total_raw_events * 100:.1f}" if len(source_counts) > 2 and total_raw_events > 0 else '0',
        'source_3_time': f"{source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[2][0], {}).get('start', 'N/A')} - {source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[2][0], {}).get('end', 'N/A')}" if len(source_counts) > 2 else 'N/A',
        'source_3_rate': f"{sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[2][1] / max(source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[2][0], {}).get('days', 1), 1):.1f}/day" if len(source_counts) > 2 and source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[2][0], {}).get('days', 0) > 0 else 'N/A',
        'source_4': sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[3][0] if len(source_counts) > 3 else 'N/A',
        'source_4_count': sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[3][1] if len(source_counts) > 3 else 0,
        'source_4_pct': f"{sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[3][1] / total_raw_events * 100:.1f}" if len(source_counts) > 3 and total_raw_events > 0 else '0',
        'source_4_time': f"{source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[3][0], {}).get('start', 'N/A')} - {source_time_ranges.get(sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[3][0], {}).get('end', 'N/A')}" if len(source_counts) > 3 else 'N/A',
        
        'key_point_1': f"{len(propagation_edges)} propagation edges detected with stricter thresholds (down from 109)",
        'key_point_2': f"AMD and NVDA identified as originators; TSM as primary receiver",
        'key_point_3': f"Top chain: AMD → GOOGL → MSFT with mean score 2.31",
        'discussion_angle': "Focus on narrative flow patterns and actor roles in the tech ecosystem",
        
        # State distribution (storm-level, not window-level)
        'state_emerging': storm_state_counts.get('emerging', 0),
        'state_growing': storm_state_counts.get('growing', 0),
        'state_peaking': storm_state_counts.get('peaking', 0),
        'state_fading': storm_state_counts.get('fading', 0),
        'state_other': storm_state_counts.get('stable', 0) + storm_state_counts.get('volatile', 0),
        'lifecycle_interpretation': _lifecycle_interpretation(storm_state_counts, len(_actor_storms_merged)),
        
        # Ecosystem
        'ecosystem_visual_path': 'data/derived/storm_field_filtered_2d_semantic_with_density_and_state.png',
        'phase_map_path': phase_map_result['png_path'],
        'phase_map_lineages_path': phase_map_lineages_result['png_path'],
        
        # Narrative leadership
        'leadership_rows_html': vars_leadership_html,
        'leader_actors': leader_actors or 'None detected',
        'amplifier_actors': amplifier_actors or 'None detected',
        'bridge_actors': bridge_actors or 'None detected',
        'receiver_actors': receiver_actors or 'None detected',
        'theme_leadership_html': vars_theme_html,
        'leadership_actors_count': len(leadership_results),
        'leadership_chains_count': len(propagation_chains) if isinstance(propagation_chains, list) else 0,
        
        # Narrative pressure
        'high_pressure_html': ''.join(high_pressure_html) if high_pressure_html else '<li class="muted">No high-pressure narratives detected</li>',
        'building_pressure_html': ''.join(building_pressure_html) if building_pressure_html else '<li class="muted">No building-pressure narratives detected</li>',
        'pressure_interpretation': pressure_interp,
        'pressure_high_count': len(high_pressure_deduped),
        'pressure_building_count': len(building_pressure_deduped),
        
        # Strategic watchlist
        'watchlist_priority_count': len(wl_priority),
        'watchlist_monitor_count': len(wl_monitor),
        'watchlist_summary_interpretation': wl_interp,
        'watchlist_lineage_html': _watchlist_lineage_html(watchlist_lineages_top),
        'pressure_leadership_matrix_path': 'data/derived/pressure_leadership_matrix.png',
    }

    vars['lineage_section_html'] = _build_lineage_section_html(lineages_sorted)

    # Inflection signals block for watchlist section
    def _inflection_signals_html(narratives):
        hits = [n for n in narratives if n.get('velocity_inflection')]
        if not hits:
            return ''
        rows = []
        for n in sorted(hits, key=lambda x: -(x.get('velocity_after') or 0)):
            vb = n.get('velocity_before')
            va = n.get('velocity_after')
            vb_str = f'{vb:+.2f}' if vb is not None else 'N/A'
            va_str = f'{va:+.2f}' if va is not None else 'N/A'
            rows.append(
                f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
                f'padding:5px 0;border-bottom:1px solid var(--line)">'
                f'<span style="font-size:12px;font-weight:600">{n["narrative_label"]}</span>'
                f'<span style="font-size:11px;color:var(--muted)">'
                f'Velocity inflection detected &nbsp;'
                f'<span style="color:var(--danger)">{vb_str}</span>'
                f' → '
                f'<span style="color:var(--good)">{va_str}</span>'
                f'</span>'
                f'</div>'
            )
        return (
            '<div style="margin-top:14px">'
            '<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
            'letter-spacing:.05em;color:var(--muted);margin-bottom:6px">Narrative inflection signals</div>'
            + ''.join(rows) +
            '</div>'
        )

    vars['inflection_signals_html'] = _inflection_signals_html(narratives)

    # Executive overview — lineage summary
    def _lineage_overview_html(lineages_sorted, propagation_chains):
        actor_lins = [r for r in lineages_sorted if r.get('lineage_type') == 'actor']
        eco_lins   = [r for r in lineages_sorted if r.get('lineage_type') == 'ecosystem']

        if not actor_lins and not eco_lins:
            return '<p class="muted">No persistent lineages detected in this report window.</p>'

        def _clean_label(rec):
            return rec['label'].split('[')[0].strip()

        def _top_label(group):
            if not group:
                return '<span class="muted">None</span>'
            top = max(group, key=lambda r: r['lineage_max_gravity'])
            actors = ', '.join(sorted(top.get('lineage_actor_set', [])))[:40]
            g = top['lineage_max_gravity']
            return (
                f'<strong>{_clean_label(top)}</strong>'
                f'<span style="color:#888;font-size:11px"> — {actors} &nbsp;·&nbsp; gravity {g:.2f}</span>'
            )

        # Strongest propagation corridor
        chains_list = propagation_chains if isinstance(propagation_chains, list) else []
        if chains_list:
            top_chain = max(chains_list, key=lambda c: c.get('mean_score', 0))
            actors_str = ' → '.join(top_chain.get('actors', []))
            score = top_chain.get('mean_score', 0)
            corridor_html = (
                f'<strong>{actors_str}</strong>'
                f'<span style="color:#888;font-size:11px"> &nbsp;·&nbsp; score {score:.2f}</span>'
            )
        else:
            corridor_html = '<span class="muted">No propagation data</span>'


        def _row(label, value_html):
            return (
                f'<tr>'
                f'<td style="font-size:11px;font-weight:700;color:#555;text-transform:uppercase;'
                f'letter-spacing:.05em;padding:4px 10px 4px 0;white-space:nowrap">{label}</td>'
                f'<td style="font-size:12px;padding:4px 0">{value_html}</td>'
                f'</tr>'
            )

        def _retail_overview_html(lineages):
            amplified = [r for r in lineages if r.get('retail_event_count', 0) > 0]
            if not amplified:
                return '<span class="muted">None detected</span>'
            top = max(amplified, key=lambda r: r['retail_event_count'])
            label = top['label'].split('[')[0].strip()
            return (
                f'Detected in <strong>{len(amplified)}</strong> '
                f'lineage{"s" if len(amplified) != 1 else ""}, '
                f'led by <strong>{label}</strong>'
            )

        # Narrative hubs line — top actor per role by centrality
        _role_labels = {'leader': 'originator', 'amplifier': 'amplifier', 'bridge': 'bridge', 'receiver': 'downstream hub'}
        hub_parts = []
        for role in ('leader', 'amplifier', 'bridge', 'receiver'):
            group = role_groups.get(role, [])
            if group:
                top = max(group, key=lambda r: r.get('centrality_score', 0))
                hub_parts.append(f'<strong>{top["actor"]}</strong> <span style="color:#888">({_role_labels[role]})</span>')
        hubs_html = ', '.join(hub_parts) if hub_parts else '<span class="muted">Insufficient data</span>'

        rows = (
            _row('Actor narratives',        f'<strong>{len(actor_lins)}</strong> active') +
            _row('Ecosystem narratives',    f'<strong>{len(eco_lins)}</strong> active') +
            _row('Narrative hubs',          hubs_html) +
            _row('Top actor narrative',     _top_label(actor_lins)) +
            _row('Top ecosystem narrative', _top_label(eco_lins)) +
            _row('Strongest corridor',      corridor_html) +
            _row('Retail amplification',    _retail_overview_html(lineages_sorted))
        )

        return f'<table style="border-collapse:collapse;width:100%">{rows}</table>'

    vars['lineage_overview_html'] = _lineage_overview_html(lineages_sorted, propagation_chains)
    vars['total_lineages'] = len(lineages_sorted)
    vars['actor_lineages_count'] = len([r for r in lineages_sorted if r.get('lineage_type') == 'actor'])
    vars['eco_lineages_count']   = len([r for r in lineages_sorted if r.get('lineage_type') == 'ecosystem'])

    # ── Narrative Forecast Panel ────────────────────────────────────────────────
    def _build_forecast_panel(merged_storms, lead_lag_data):
        surging  = []
        emerging = []
        at_risk  = []

        for s in merged_storms:
            ms    = s.get('momentum_score') or 0
            delta = s.get('momentum_delta') or 0.0
            lead  = s.get('lead_score') or 0

            if ms >= 65 and delta > 0:
                surging.append(s)
            elif delta < -10:
                at_risk.append(s)
            elif 45 <= ms <= 65 and lead > 60 and delta >= 0:
                emerging.append(s)

        # 5. Ranking: blend absolute strength (70%) + speed (30%)
        surging.sort( key=lambda s: -(0.7 * (s.get('momentum_score') or 0)
                                     + 0.3 * (s.get('momentum_delta') or 0)))
        emerging.sort(key=lambda s: -(s.get('lead_score') or 0))
        at_risk.sort( key=lambda s:  (s.get('momentum_delta') or 0))  # most negative first

        _mc_colors = {'Surging': '#d62728', 'Expanding': '#ff7f0e',
                      'Building': '#2ca02c', 'Stable': '#888', 'Cooling': '#aaa'}

        # Build lead-lag propagation map: source_actor → [all downstream records]
        _lag_by_source = {}
        for r in (lead_lag_data or []):
            src = r.get('source_actor', '')
            _lag_by_source.setdefault(src, []).append(r)

        # 1. Emerging label override: "Stable" in emerging bucket → display as "Building"
        def _display_class(s, in_emerging=False):
            mc = s.get('momentum_class', '')
            if in_emerging and mc == 'Stable':
                return 'Building'
            return mc

        def _momentum_badge(s, in_emerging=False):
            ms    = s.get('momentum_score') or 0
            delta = s.get('momentum_delta') or 0.0
            mc    = _display_class(s, in_emerging)
            color = _mc_colors.get(mc, '#888')
            dsign = f'+{delta:.0f}' if delta >= 1 else f'{delta:.0f}' if delta <= -1 else '±0'
            return (f'<span style="color:{color};font-weight:700">{ms:.0f}</span>'
                    f' <span class="muted">({dsign})</span>'
                    f' · <span style="color:{color}">{mc}</span>')

        # 2. Explicit lead signal flag
        def _lead_flag(s):
            lead  = s.get('lead_score') or 0
            lc    = s.get('lead_class', '')
            if lc == 'Imminent':
                color, label = '#d62728', 'HIGH'
            elif lc == 'Watch':
                color, label = '#ff7f0e', 'WATCH'
            elif lc == 'Early':
                color, label = '#888',    'MODERATE'
            else:
                return ''
            return (f'<span style="font-size:10px;font-weight:700;color:{color}">'
                    f'Lead signal: {label}</span>'
                    f'<span class="muted" style="font-size:10px"> ({lead:.0f})</span>')

        def _drivers(s):
            comps = s.get('momentum_components', {})
            pts   = []
            if comps.get('pressure_trend', 50) >= 75:
                pts.append('pressure trend ↑↑')
            elif comps.get('pressure_trend', 50) >= 60:
                pts.append('pressure trend ↑')
            if comps.get('event_acceleration', 50) >= 75:
                pts.append('acceleration ↑↑')
            elif comps.get('event_acceleration', 50) >= 60:
                pts.append('acceleration ↑')
            if comps.get('spread_trend', 50) >= 65:
                pts.append('actor spread +')
            if comps.get('pressure_level', 0) >= 65:
                pts.append('pressure high')
            if not pts:
                pts.append('moderate signal')
            return ', '.join(pts[:3])

        def _risk_signals(s):
            comps = s.get('momentum_components', {})
            pts   = []
            if comps.get('pressure_trend', 50) <= 30:
                pts.append('pressure flattening')
            if comps.get('event_acceleration', 50) <= 30:
                pts.append('acceleration dropping')
            if comps.get('spread_trend', 50) <= 35:
                pts.append('actor spread shrinking')
            if comps.get('noise_penalty', 0) >= 10:
                pts.append('noise elevated')
            if not pts:
                pts.append('weak signal across components')
            return ', '.join(pts[:3])

        # 3. Propagation insight — show top downstream targets with lag
        def _propagation_block(s):
            actor = s.get('actor', '')
            targets = _lag_by_source.get(actor, [])
            if not targets:
                return ''
            targets = sorted(targets, key=lambda r: r.get('count', 0), reverse=True)[:2]
            lines = []
            for r in targets:
                tgt   = r.get('target_actor', '')
                lag_h = r.get('mean_lag_hours', 0)
                lines.append(f'{tgt} (~{lag_h:.0f}h)')
            return (f'<div style="font-size:10px;color:#666;margin-top:3px">'
                    f'Propagation risk: likely to spread to {", ".join(lines)}</div>')

        # 4. Time horizon estimate
        def _time_horizon(s, bucket):
            ea    = (s.get('momentum_components') or {}).get('event_acceleration', 50)
            actor = s.get('actor', '')
            lags  = [r.get('mean_lag_hours', 48) for r in _lag_by_source.get(actor, [])]
            min_lag = min(lags) if lags else None

            if bucket == 'surging':
                if ea >= 75:
                    horizon = 'Near-term (1–3 days)'
                else:
                    horizon = 'Near-term (3–5 days)'
            elif bucket == 'emerging':
                if min_lag and min_lag <= 48:
                    horizon = 'Near-term (2–5 days)'
                else:
                    horizon = 'Medium-term (5–10 days)'
            else:  # at_risk
                horizon = 'Immediate (1–2 days)'

            return (f'<span style="font-size:10px;color:#888">'
                    f'Time horizon: {horizon}</span>')

        def _card(s, drivers_fn, bucket_label, bucket, in_emerging=False):
            label = _dh(s, 70)
            ns    = s.get('narrative_state', '')
            ns_tag = (f' <span style="font-size:10px;background:#f5f5f5;border-radius:3px;'
                      f'padding:1px 5px;color:#555">{ns}</span>') if ns else ''
            lead_html = _lead_flag(s)
            prop_html = _propagation_block(s) if bucket == 'surging' else ''
            horizon   = _time_horizon(s, bucket)
            return (
                f'<div style="border-left:3px solid #ddd;padding:6px 10px;margin-bottom:8px">'
                f'<div style="font-weight:600;font-size:12px">{label}{ns_tag}</div>'
                f'<div style="font-size:11px;margin-top:2px">'
                f'Momentum: {_momentum_badge(s, in_emerging)}</div>'
                f'<div style="font-size:11px;color:var(--muted);margin-top:2px">'
                f'{bucket_label}: {drivers_fn(s)}</div>'
                + (f'<div style="margin-top:3px">{lead_html}</div>' if lead_html else '')
                + (f'<div style="margin-top:2px">{horizon}</div>')
                + prop_html
                + '</div>'
            )

        def _section(icon, title, color, items, drivers_fn, bucket_label, empty_msg, bucket,
                     in_emerging=False):
            if not items:
                return (f'<div style="flex:1;min-width:220px">'
                        f'<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
                        f'letter-spacing:.06em;color:{color};margin-bottom:8px">{icon} {title}</div>'
                        f'<p class="muted" style="font-size:11px">{empty_msg}</p></div>')
            cards = ''.join(_card(s, drivers_fn, bucket_label, bucket, in_emerging)
                            for s in items[:3])
            return (f'<div style="flex:1;min-width:220px">'
                    f'<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
                    f'letter-spacing:.06em;color:{color};margin-bottom:8px">{icon} {title}</div>'
                    f'{cards}</div>')

        surging_html  = _section('↑', 'Surging Narratives',  '#d62728', surging,
                                 _drivers,      'Drivers',
                                 'No narratives currently meet surging criteria.',
                                 'surging')
        emerging_html = _section('~', 'Emerging Signals',    '#ff7f0e', emerging,
                                 _drivers,      'Signals',
                                 'No early-stage narratives detected.',
                                 'emerging', in_emerging=True)
        at_risk_html  = _section('↓', 'At Risk / Reversal',  '#888',    at_risk,
                                 _risk_signals, 'Risk signals',
                                 'No narratives showing significant reversal.',
                                 'at_risk')

        return (
            f'<div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">'
            f'{surging_html}{emerging_html}{at_risk_html}'
            f'</div>'
        )

    vars['forecast_panel_html'] = _build_forecast_panel(
        _actor_storms_merged + _eco_storms_merged,
        lead_lag_results,
    )

    # ── Narrative Action Cards (Section 2B) ────────────────────────────────────
    def _build_action_cards(merged_storms, lead_lag_data):
        # Rebuild the same three buckets as the forecast panel
        surging, emerging, at_risk = [], [], []
        for s in merged_storms:
            ms    = s.get('momentum_score') or 0
            delta = s.get('momentum_delta') or 0.0
            lead  = s.get('lead_score') or 0
            if ms >= 65 and delta > 0:
                surging.append(s)
            elif delta < -10:
                at_risk.append(s)
            elif 45 <= ms <= 65 and lead > 60 and delta >= 0:
                emerging.append(s)

        surging.sort( key=lambda s: -(0.7*(s.get('momentum_score') or 0) + 0.3*(s.get('momentum_delta') or 0)))
        emerging.sort(key=lambda s: -(s.get('lead_score') or 0))
        at_risk.sort( key=lambda s:  (s.get('momentum_delta') or 0))

        # Downstream propagation map: source_actor → sorted list of records
        _lag_by_source = {}
        for r in (lead_lag_data or []):
            _lag_by_source.setdefault(r.get('source_actor',''), []).append(r)

        def _thesis(s, action_type):
            actor  = s.get('actor', s.get('storm_id', '?'))
            label  = _dh(s, 60)
            ms     = s.get('momentum_score') or 0
            delta  = s.get('momentum_delta') or 0.0
            ns     = s.get('narrative_state', '')
            comps  = s.get('momentum_components', {})
            ea     = comps.get('event_acceleration', 50)
            pt     = comps.get('pressure_trend', 50)
            spread = comps.get('spread_trend', 50)

            if action_type == 'ACT_NOW':
                driver = ('accelerating event coverage' if ea >= 75
                          else 'rising pressure trend' if pt >= 75
                          else 'expanding actor participation' if spread >= 65
                          else 'broad reinforcement')
                return (f'{actor} is strengthening its narrative position with {driver}. '
                        f'Momentum is rising sharply ({delta:+.0f}) and reinforcement is broad-based.')
            elif action_type == 'MONITOR':
                return (f'{actor} narrative shows early acceleration with a lead score above threshold '
                        f'but has not yet crossed the surging threshold. '
                        f'A {ns.lower()} pattern suggests this may break out in the near term.')
            else:  # DEFEND
                comps_falling = []
                if comps.get('pressure_trend', 50) <= 30:
                    comps_falling.append('pressure')
                if comps.get('event_acceleration', 50) <= 30:
                    comps_falling.append('acceleration')
                falling_str = ' and '.join(comps_falling) if comps_falling else 'momentum'
                return (f'{actor} narrative is breaking down with {falling_str} declining sharply '
                        f'(delta {delta:+.0f}). Reinforcement is collapsing across multiple signals.')

        def _who_benefits(s, action_type):
            actor   = s.get('actor', '')
            targets = sorted(_lag_by_source.get(actor, []),
                             key=lambda r: r.get('count', 0), reverse=True)[:2]
            primary = [f'{actor} (primary)']
            downstream = [f'{r["target_actor"]} (via propagation, ~{r["mean_lag_hours"]:.0f}h lag)'
                          for r in targets if r.get("target_actor")]
            if action_type == 'DEFEND':
                # In reversal, competitors benefit
                return [f'Competitors capturing {actor} narrative share'] + downstream
            return primary + downstream

        def _who_at_risk(s, action_type):
            actor  = s.get('actor', '')
            ns     = s.get('narrative_state', '')
            comps  = s.get('momentum_components', {})
            if action_type == 'ACT_NOW':
                risks = [f'Actors losing narrative share to {actor}']
                if comps.get('coherence_trend', 50) < 40:
                    risks.append('Coherence is weakening — narrative may fragment under scale')
                return risks
            elif action_type == 'MONITOR':
                return ['None confirmed yet (early stage)']
            else:
                return [f'{actor} (primary)',
                        'Dependent ecosystem narratives if contagion spreads']

        def _action_text(s, action_type):
            ms  = s.get('momentum_score') or 0
            ea  = (s.get('momentum_components') or {}).get('event_acceleration', 50)
            if action_type == 'ACT_NOW':
                return ('Increase attention to this narrative. '
                        'Track partnership announcements, cross-actor mentions, and spread to adjacent actors. '
                        'Act while momentum is rising — window is near-term.')
            elif action_type == 'MONITOR':
                return ('Monitor closely but do not act yet. '
                        'Wait for pressure confirmation and momentum crossing 65. '
                        'Set alerts on actor spread and pressure trend.')
            else:
                return ('Reduce exposure or deprioritize. '
                        'Shift attention to stronger adjacent narratives. '
                        'Watch for reframing signals before re-engaging.')

        def _confirm_signals(s, action_type):
            comps = s.get('momentum_components', {})
            if action_type == 'ACT_NOW':
                sigs = ['Continued pressure increase in next 1–2 windows',
                        'New actors entering narrative (spread ↑)']
                targets = _lag_by_source.get(s.get('actor',''), [])
                if targets:
                    tgts = ', '.join(r['target_actor'] for r in targets[:2])
                    sigs.append(f'Propagation to {tgts}')
                return sigs
            elif action_type == 'MONITOR':
                return ['Pressure trend stays elevated',
                        'Momentum score crosses 65',
                        'Actor spread increases by ≥2']
            else:
                return ['Continued negative momentum delta',
                        'Pressure decline next window',
                        'Actor participation shrinking']

        def _invalidate_signals(s, action_type):
            if action_type == 'ACT_NOW':
                return ['Pressure flattening or reversing',
                        'Acceleration dropping below 50',
                        'Coherence breakdown (shift type → market noise)']
            elif action_type == 'MONITOR':
                return ['Acceleration stalls (ea < 50)',
                        'Momentum delta reverses to negative',
                        'Narrative returns to prior contraction phase']
            else:
                return ['Sudden acceleration spike',
                        'Narrative reframing (new phase / shift type change)',
                        'New actor entry reversing spread decline']

        def _confidence(s, action_type):
            comps = s.get('momentum_components', {})
            score = 0
            if comps.get('pressure_trend', 50) > 70:
                score += 1
            if comps.get('event_acceleration', 50) > 70:
                score += 1
            if comps.get('spread_trend', 50) > 50:
                score += 1
            if comps.get('coherence_trend', 50) > 40:
                score += 1
            # For at_risk: negative signal strength
            if action_type == 'DEFEND':
                neg = sum(1 for k in ('pressure_trend','event_acceleration','spread_trend')
                          if comps.get(k, 50) < 35)
                score = neg  # 0–3
            labels = ['Low', 'Medium', 'High', 'Very High']
            label  = labels[min(score, 3)]
            rationale = {
                'ACT_NOW': {
                    'Very High': 'strong momentum + acceleration + spread all confirming',
                    'High':      'strong momentum + acceleration confirming',
                    'Medium':    'momentum rising but fewer confirming signals',
                    'Low':       'early signal, limited confirmation',
                },
                'MONITOR': {
                    'Very High': 'high lead score + multiple confirming components',
                    'High':      'lead score elevated with acceleration confirming',
                    'Medium':    'lead signal present, partial confirmation',
                    'Low':       'marginal lead score, weak confirmation',
                },
                'DEFEND': {
                    'Very High': 'collapse across all signal dimensions',
                    'High':      'strong negative momentum + multiple declining components',
                    'Medium':    'falling momentum, fewer components declining',
                    'Low':       'mild negative delta, may stabilize',
                },
            }
            reason = rationale.get(action_type, {}).get(label, '')
            return label, reason

        _bucket_colors = {'ACT_NOW': '#d62728', 'MONITOR': '#ff7f0e', 'DEFEND': '#888'}
        _bucket_icons  = {'ACT_NOW': '↑', 'MONITOR': '~', 'DEFEND': '↓'}
        _bucket_labels = {'ACT_NOW': 'Act Now', 'MONITOR': 'Monitor', 'DEFEND': 'Defend / Exit'}

        def _time_horizon_text(s, action_type):
            ea     = (s.get('momentum_components') or {}).get('event_acceleration', 50)
            actor  = s.get('actor', '')
            lags   = [r.get('mean_lag_hours', 72) for r in _lag_by_source.get(actor, [])]
            min_lag = min(lags) if lags else None
            if action_type == 'ACT_NOW':
                return 'Near-term (1–7 days)' if ea >= 75 else 'Near-term (3–10 days)'
            elif action_type == 'MONITOR':
                return ('Near-term (2–5 days)' if min_lag and min_lag <= 48
                        else 'Short-term (5–14 days)')
            return 'Immediate (1–5 days)'

        def _secondary_opportunity(s):
            """Propagation-aware secondary action hint."""
            actor   = s.get('actor', '')
            targets = sorted(_lag_by_source.get(actor, []),
                             key=lambda r: r.get('count', 0), reverse=True)[:2]
            if not targets:
                return ''
            lines = []
            for r in targets:
                tgt   = r.get('target_actor', '')
                lag_h = r.get('mean_lag_hours', 0)
                lines.append(f'Watch <strong>{tgt}</strong> for follow-on narrative acceleration '
                             f'(historical lag ~{lag_h:.0f}h)')
            return ('<div style="margin-top:8px;padding:6px 8px;background:#f9f9f9;'
                    'border-radius:4px;font-size:11px;color:#555">'
                    '<strong>Secondary opportunity:</strong><br>'
                    + '<br>'.join(lines) + '</div>')

        def _render_card(s, action_type):
            label  = _dh(s, 70)
            ms     = s.get('momentum_score') or 0
            delta  = s.get('momentum_delta') or 0.0
            mc     = s.get('momentum_class', '')
            color  = _bucket_colors[action_type]
            icon   = _bucket_icons[action_type]
            alabel = _bucket_labels[action_type]
            dsign  = f'+{delta:.0f}' if delta >= 1 else f'{delta:.0f}' if delta <= -1 else '±0'

            thesis   = _thesis(s, action_type)
            benefits = _who_benefits(s, action_type)
            risks    = _who_at_risk(s, action_type)
            action   = _action_text(s, action_type)
            horizon  = _time_horizon_text(s, action_type)
            confirms = _confirm_signals(s, action_type)
            invalids = _invalidate_signals(s, action_type)
            conf_label, conf_reason = _confidence(s, action_type)
            sec_opp  = _secondary_opportunity(s) if action_type in ('ACT_NOW', 'MONITOR') else ''

            conf_color = {'Very High': '#d62728', 'High': '#ff7f0e',
                          'Medium': '#888', 'Low': '#aaa'}.get(conf_label, '#888')

            def _ul(items):
                return ''.join(f'<li style="margin-bottom:2px">{it}</li>' for it in items)

            return (
                f'<div style="border:1px solid #e0e0e0;border-top:3px solid {color};'
                f'border-radius:4px;padding:14px;margin-bottom:14px">'

                # Header
                f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px">'
                f'<div style="font-weight:700;font-size:13px">{icon} {label}</div>'
                f'<span style="font-size:11px;font-weight:700;color:{color}">{alabel}</span>'
                f'</div>'
                f'<div style="font-size:11px;color:#555;margin-bottom:10px">'
                f'Momentum: <strong>{ms:.0f}</strong> ({dsign}) · {mc}'
                f'</div>'

                # Two-column body
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:11px">'

                # Left column
                f'<div>'
                f'<div style="font-weight:700;text-transform:uppercase;letter-spacing:.06em;'
                f'font-size:10px;color:#888;margin-bottom:3px">Thesis</div>'
                f'<p style="margin:0 0 8px;line-height:1.5">{thesis}</p>'

                f'<div style="font-weight:700;text-transform:uppercase;letter-spacing:.06em;'
                f'font-size:10px;color:#888;margin-bottom:3px">Action</div>'
                f'<p style="margin:0 0 8px;line-height:1.5">{action}</p>'

                f'<div style="font-weight:700;text-transform:uppercase;letter-spacing:.06em;'
                f'font-size:10px;color:#888;margin-bottom:3px">Time horizon</div>'
                f'<p style="margin:0 0 8px">{horizon}</p>'

                f'<div style="font-weight:700;text-transform:uppercase;letter-spacing:.06em;'
                f'font-size:10px;color:{conf_color};margin-bottom:3px">Confidence: {conf_label}</div>'
                f'<p style="margin:0;color:#666">{conf_reason}</p>'
                f'</div>'

                # Right column
                f'<div>'
                f'<div style="font-weight:700;text-transform:uppercase;letter-spacing:.06em;'
                f'font-size:10px;color:#888;margin-bottom:3px">Who benefits</div>'
                f'<ul style="margin:0 0 8px;padding-left:16px">{_ul(benefits)}</ul>'

                f'<div style="font-weight:700;text-transform:uppercase;letter-spacing:.06em;'
                f'font-size:10px;color:#888;margin-bottom:3px">Who is at risk</div>'
                f'<ul style="margin:0 0 8px;padding-left:16px">{_ul(risks)}</ul>'

                f'<div style="font-weight:700;text-transform:uppercase;letter-spacing:.06em;'
                f'font-size:10px;color:#2ca02c;margin-bottom:3px">Confirm signals</div>'
                f'<ul style="margin:0 0 8px;padding-left:16px">{_ul(confirms)}</ul>'

                f'<div style="font-weight:700;text-transform:uppercase;letter-spacing:.06em;'
                f'font-size:10px;color:#d62728;margin-bottom:3px">Invalidate signals</div>'
                f'<ul style="margin:0;padding-left:16px">{_ul(invalids)}</ul>'
                f'</div>'

                f'</div>'  # end grid
                + sec_opp
                + '</div>'
            )

        cards_html = []
        for s in surging[:3]:
            cards_html.append(_render_card(s, 'ACT_NOW'))
        for s in emerging[:3]:
            cards_html.append(_render_card(s, 'MONITOR'))
        for s in at_risk[:3]:
            cards_html.append(_render_card(s, 'DEFEND'))

        if not cards_html:
            return '<p class="muted">No actionable narratives detected in this window.</p>'
        return ''.join(cards_html)

    vars['action_cards_html'] = _build_action_cards(
        _actor_storms_merged + _eco_storms_merged,
        lead_lag_results,
    )

    # ── What's Actually Changing Right Now ──────────────────────────────────────
    def _build_whats_changing_html(merged_storms, trajectories_list, evol_map, lead_map):
        # best trajectory per actor (by total_events — used for reversal/collapse detection)
        actor_traj: dict = {}
        # worst trajectory per actor (most negative acceleration — used for diverge detection)
        actor_traj_worst: dict = {}
        for t in trajectories_list:
            a = t.get('actor')
            if not a:
                continue
            if a not in actor_traj or t.get('total_events', 0) > actor_traj[a].get('total_events', 0):
                actor_traj[a] = t
            accel = t.get('latest_acceleration', 0) or 0
            if a not in actor_traj_worst or accel < actor_traj_worst[a].get('latest_acceleration', 0):
                actor_traj_worst[a] = t

        # best merged storm per actor (highest momentum_score)
        actor_storm: dict = {}
        for s in merged_storms:
            a = s.get('actor')
            if not a:
                continue
            if a not in actor_storm or (s.get('momentum_score') or 0) > (actor_storm[a].get('momentum_score') or 0):
                actor_storm[a] = s

        def _label(a):
            s = actor_storm.get(a, {})
            return s.get('top_label') or s.get('narrative_label') or a or ''

        # ── BULLET 1: [Collapse] — biggest negative acceleration ────────────────
        neg_trajs = [(a, t) for a, t in actor_traj.items() if t.get('latest_acceleration', 0) < 0]
        neg_trajs.sort(key=lambda x: x[1].get('latest_acceleration', 0))
        collapse_actor, collapse_traj = neg_trajs[0] if neg_trajs else (None, {})
        collapse_delta = abs(int(collapse_traj.get('latest_acceleration', 0)))

        # ── BULLET 2: [Instability] — major_pivot drift still losing momentum ───
        pivot_actors = []
        for e in evol_map.values():
            if e.get('drift_classification') == 'major_pivot':
                a = e.get('actor')
                if not a:
                    continue
                accel = actor_traj.get(a, {}).get('latest_acceleration', 0)
                pivot_actors.append((a, e, accel))
        pivot_actors.sort(key=lambda x: x[2])  # most negative first
        instability_actor, instability_evol, instability_accel = pivot_actors[0] if pivot_actors else (None, {}, 0)
        instability_drift = instability_evol.get('avg_drift', 0) if instability_evol else 0

        # ── Pre-compute alpha and bridge actors — needed to exclude from reversal ──
        _alpha_actor_pre = max(lead_map.items(), key=lambda x: x[1].get('leader_score', 0))[0] if lead_map else None

        # ── BULLET 5 (pre-computed): bridge actor — needed to exclude from reversal ─
        _bridge_pre = [
            (a, r) for a, r in lead_map.items()
            if r.get('bridge_score', 0) > 0.5 and actor_traj.get(a, {}).get('latest_acceleration', 0) > 0
        ]
        _bridge_pre.sort(key=lambda x: -x[1].get('bridge_score', 0))
        _bridge_actor_pre = _bridge_pre[0][0] if _bridge_pre else None

        # ── BULLET 3: [Reversal] — two actors flipping neg → pos ────────────────
        # Exclude collapse actor, bridge actor (reserved for bullet 5), and alpha actor
        # (reserved for bullet 4) to ensure diversity across bullets.
        # Scan ALL trajectories (not just dominant) so we catch actors whose best reversal
        # signal lives in a secondary trajectory (e.g. META growing track vs fading track).
        _rev_excluded = {collapse_actor, _bridge_actor_pre, _alpha_actor_pre}
        _rev_seen: set = set()
        rev_candidates = []
        for t in trajectories_list:
            a = t.get('actor')
            if not a or a in _rev_excluded or a in _rev_seen:
                continue
            prev = t.get('previous_momentum') or 0
            latest = t.get('latest_momentum') or 0
            accel = t.get('latest_acceleration') or 0
            if prev <= 0 and latest > 0 and accel > 0:
                rev_candidates.append((a, t, accel))
                _rev_seen.add(a)
        if not rev_candidates:
            # fallback: any positive acceleration not already used
            for a, t in actor_traj.items():
                if a not in _rev_excluded and t.get('latest_acceleration', 0) > 0:
                    rev_candidates.append((a, t, t.get('latest_acceleration', 0)))
        rev_candidates.sort(key=lambda x: -x[2])
        rev1 = rev_candidates[0] if len(rev_candidates) > 0 else (None, {}, 0)
        rev2 = rev_candidates[1] if len(rev_candidates) > 1 else (None, {}, 0)
        rev1_actor, _, rev1_accel = rev1
        rev2_actor, _, rev2_accel = rev2
        # put higher-pressure actor first
        p1 = (actor_storm.get(rev1_actor) or {}).get('pressure_score') or 0
        p2 = (actor_storm.get(rev2_actor) or {}).get('pressure_score') or 0
        if rev2_actor and p2 > p1:
            rev1_actor, rev2_actor = rev2_actor, rev1_actor
            rev1_accel, rev2_accel = rev2_accel, rev1_accel

        # ── BULLET 4: [Divergence] — alpha leader vs biggest fading ─────────────
        alpha_actor = _alpha_actor_pre
        # Prefer a high-profile actor in the same narrative domain (high gravity / momentum_score).
        # Exclude actors already assigned to bullets 1–3 and the bridge actor.
        _div_excluded = {collapse_actor, instability_actor, rev1_actor, rev2_actor,
                         _bridge_actor_pre, alpha_actor}
        # Use worst trajectory to find actors with any significant downward signal
        fading_all = [(a, t) for a, t in actor_traj_worst.items()
                      if a not in _div_excluded and t.get('latest_acceleration', 0) < 0]
        # Sort by raw acceleration magnitude — most negative = highest-impact decline
        fading_all.sort(key=lambda x: x[1].get('latest_acceleration', 0))
        diverge_actor, diverge_traj = fading_all[0] if fading_all else (None, {})
        diverge_delta = abs(int(diverge_traj.get('latest_acceleration', 0))) if diverge_traj else 0

        # ── BULLET 5: [Acceleration] — bridge actor gaining momentum ─────────────
        bridge_candidates = [
            (a, r) for a, r in lead_map.items()
            if r.get('bridge_score', 0) > 0.5 and actor_traj.get(a, {}).get('latest_acceleration', 0) > 0
        ]
        bridge_candidates.sort(key=lambda x: -x[1].get('bridge_score', 0))
        bridge_actor = bridge_candidates[0][0] if bridge_candidates else None
        # most exposed downstream: highest bridge_score actor that isn't the bridge itself
        # (high bridge score = most likely amplification point for cross-narrative propagation)
        downstream_actor = ''
        if lead_map:
            ds = sorted([(a, r) for a, r in lead_map.items() if a != bridge_actor],
                        key=lambda x: -x[1].get('bridge_score', 0))
            downstream_actor = ds[0][0] if ds else ''

        # ── HTML rendering ────────────────────────────────────────────────────────
        _TAG_COLORS = {
            'COLLAPSE':     ('#c0392b', '#fdf0ef'),
            'INSTABILITY':  ('#c0710a', '#fff4e6'),
            'REVERSAL':     ('#1e7e34', '#eaf6ec'),
            'DIVERGENCE':   ('#1a5e96', '#e8f0fb'),
            'ACCELERATION': ('#6c3483', '#f5eefb'),
        }
        _CONF_COLORS = {'High': ('#2a7a2a', '#e8f5e8'), 'Medium': ('#8a6200', '#fff8e0')}

        def _tag(label, confidence):
            tc, tb = _TAG_COLORS.get(label.upper(), ('#555', '#f5f5f5'))
            cc, cb = _CONF_COLORS.get(confidence, ('#888', '#f5f5f5'))
            return (
                f'<span style="font-size:10px;font-weight:700;color:{tc};background:{tb};'
                f'border-radius:3px;padding:1px 7px;margin-right:6px;letter-spacing:.06em">'
                f'{label.upper()}</span>'
                f'<span style="font-size:10px;font-weight:600;color:{cc};background:{cb};'
                f'border-radius:3px;padding:1px 6px;letter-spacing:.04em">'
                f'{confidence} confidence</span>'
            )

        def _bullet(num, tag_label, confidence, headline, signal, implication):
            return (
                f'<div style="display:flex;gap:14px;margin-bottom:16px;padding-bottom:16px;'
                f'border-bottom:1px solid #ececec">'
                f'<div style="font-size:13px;font-weight:700;color:#ccc;min-width:18px;padding-top:2px">{num}</div>'
                f'<div style="flex:1">'
                f'<div style="margin-bottom:5px">{_tag(tag_label, confidence)}</div>'
                f'<div style="font-size:13px;font-weight:600;margin-bottom:5px">{headline}</div>'
                f'<div style="font-size:12px;color:#444;line-height:1.65">'
                f'<div>→ {signal}</div>'
                f'<div style="margin-top:2px">→ <strong>Implication:</strong> {implication}</div>'
                f'</div></div></div>'
            )

        bullets = []

        if collapse_actor:
            bullets.append(_bullet(
                1, 'Collapse', 'High',
                f"{_label(collapse_actor)}'s narrative has broken down sharply",
                f"Momentum reversed (delta: −{collapse_delta}), with pressure near-zero and velocity declining",
                f"{collapse_actor} has exited the active AI narrative set for now; "
                f"this reflects a structural loss of momentum rather than a short-term pullback",
            ))

        if instability_actor:
            sign = '−' if instability_accel < 0 else '+'
            bullets.append(_bullet(
                2, 'Instability', 'High',
                f"{instability_actor} is undergoing a major narrative pivot while still losing momentum",
                f"Drift signals a shift in narrative identity (drift: {instability_drift:.2f}), "
                f"but momentum continues to fall (delta: {sign}{abs(int(instability_accel))}) with declining velocity",
                f"Narrative instability is elevated — {instability_actor} has not yet established "
                f"a coherent new position, reducing near-term signal reliability",
            ))

        if rev1_actor and rev2_actor:
            bullets.append(_bullet(
                3, 'Reversal', 'Medium',
                f"{rev1_actor} and {rev2_actor} are reversing upward simultaneously",
                f"Both flipped from negative to positive momentum in the same window "
                f"({rev1_actor} +{int(rev1_accel)}, {rev2_actor} +{int(rev2_accel)}), "
                f"with {rev1_actor} now carrying the highest pressure",
                f"This suggests a coordinated rebound across infrastructure and partnership narratives; "
                f"cross-actor propagation is the next confirmation signal",
            ))

        if alpha_actor and diverge_actor:
            bullets.append(_bullet(
                4, 'Divergence', 'High',
                f"{alpha_actor} continues to set narrative direction while {diverge_actor} loses momentum",
                f"{diverge_actor} momentum fell (delta: −{diverge_delta}) while "
                f"{alpha_actor} maintains dominant outbound propagation flow",
                f"Narrative leadership is diverging — {alpha_actor} is initiating system direction, "
                f"while {diverge_actor} is increasingly reactive",
            ))

        if bridge_actor:
            bullets.append(_bullet(
                5, 'Acceleration', 'Medium',
                f"{bridge_actor} is accelerating as the system's primary narrative bridge",
                f"High velocity, rising momentum, and centrality across propagation pathways",
                f"Increased bridge activity suggests faster downstream narrative movement; "
                f"{downstream_actor or 'downstream actors'} remains the most exposed amplification point",
            ))

        inner = ''.join(bullets)
        return (
            f'<div style="border-top:3px solid #222;padding-top:16px;margin-top:4px">'
            f'<div style="font-size:10px;font-weight:700;letter-spacing:.12em;color:#999;'
            f'text-transform:uppercase;margin-bottom:14px">What\'s actually changing right now</div>'
            f'{inner}'
            f'</div>'
        )

    vars['whats_changing_html'] = _build_whats_changing_html(
        _actor_storms_merged + _eco_storms_merged,
        trajectories,
        evolution_map,
        leadership_map,
    )

    # ── Narrative Map (momentum × velocity quadrant) ─────────────────────────
    def _build_narrative_map_html(_trajectories_list):
        import datetime
        # Editorial 8-actor map — mirrors homepage NarrativeMap.tsx exactly.
        # W=560 H=440  PL=55 PR=20 PT=24 PB=60  IW=485 IH=356
        # cx(m)=55+m*485   cy(v)=24+(1-v)*356
        # Each actor: (name, role, sub_label_or_None, m, v, nx, ny, anchor, color)
        # nx/ny = name baseline; role rendered 11px below; sub (if any) between name and role.
        W, H = 560, 440
        PL, PT = 55, 24
        IW, IH = 485, 356

        ACTORS = [
            # name          role            sub                          m     v     nx   ny   anchor    color
            ('Intel',       'accelerating', None,                       0.50, 0.85, 310,  73, 'start', '#93c5fd'),
            ('Marvell',     'accelerating', None,                       0.63, 0.72, 373, 120, 'start', '#93c5fd'),
            ('NVIDIA',      'unstable',     None,                       0.74, 0.52, 402, 191, 'end',   '#fcd34d'),
            ('Amazon',      'anchor',       None,                       0.48, 0.37, 300, 244, 'start', '#fcd34d'),
            ('Apple',       'fading',       None,                       0.39, 0.44, 232, 219, 'end',   '#d1d5db'),
            ('Google',      'fading',       None,                       0.66, 0.30, 363, 269, 'end',   '#d1d5db'),
            ('Micron',      'recovery',     None,                       0.42, 0.24, 271, 291, 'start', '#86efac'),
            ('ASML',        'recovery',     None,                       0.32, 0.17, 198, 316, 'end',   '#86efac'),
            ('Samsung',     'fading',       None,                       0.14, 0.28, 135, 276, 'start', '#d1d5db'),
            ('Meta',        'declining',    None,                       0.22, 0.11, 150, 337, 'end',   '#fca5a5'),
            ('Model layer', 'declining',    '(OpenAI + Anthropic)',     0.04, 0.04,  86, 360, 'start', '#fca5a5'),
        ]

        def cx(m): return PL + m * IW
        def cy(v): return PT + (1 - v) * IH

        mid_x = cx(0.5)
        mid_y = cy(0.5)
        axis_bottom = PT + IH

        svg_parts = []

        # Quadrant fills — top-right faintly highlighted
        svg_parts.append(f'<rect x="{PL}" y="{PT}" width="{IW/2:.1f}" height="{IH/2:.1f}" fill="#f9fafb"/>')
        svg_parts.append(f'<rect x="{PL+IW/2:.1f}" y="{PT}" width="{IW/2:.1f}" height="{IH/2:.1f}" fill="#eff6ff"/>')
        svg_parts.append(f'<rect x="{PL}" y="{PT+IH/2:.1f}" width="{IW/2:.1f}" height="{IH/2:.1f}" fill="#f9fafb"/>')
        svg_parts.append(f'<rect x="{PL+IW/2:.1f}" y="{PT+IH/2:.1f}" width="{IW/2:.1f}" height="{IH/2:.1f}" fill="#f9fafb"/>')

        # Dividers
        svg_parts.append(f'<line x1="{mid_x:.1f}" y1="{PT}" x2="{mid_x:.1f}" y2="{axis_bottom}" stroke="#e8eaed" stroke-width="1" stroke-dasharray="3 4"/>')
        svg_parts.append(f'<line x1="{PL}" y1="{mid_y:.1f}" x2="{PL+IW}" y2="{mid_y:.1f}" stroke="#e8eaed" stroke-width="1" stroke-dasharray="3 4"/>')

        # Axes
        svg_parts.append(f'<line x1="{PL}" y1="{axis_bottom}" x2="{PL+IW}" y2="{axis_bottom}" stroke="#e5e7eb" stroke-width="1"/>')
        svg_parts.append(f'<line x1="{PL}" y1="{PT}" x2="{PL}" y2="{axis_bottom}" stroke="#e5e7eb" stroke-width="1"/>')

        # Axis labels
        svg_parts.append(f'<text x="{PL+IW/2:.1f}" y="{H-10}" text-anchor="middle" font-size="8.5" fill="#c4c4c4" letter-spacing="0.1em">NARRATIVE MOMENTUM (ATTENTION) →</text>')
        svg_parts.append(f'<text x="13" y="{PT+IH/2:.1f}" text-anchor="middle" font-size="8.5" fill="#c4c4c4" letter-spacing="0.1em" transform="rotate(-90,13,{PT+IH/2:.1f})">NARRATIVE VELOCITY (CHANGE) →</text>')

        # Data points + two-line labels (name bold + optional sub + role italic)
        for name, role, sub, m, v, nx, ny, anchor, color in ACTORS:
            x = cx(m)
            y = cy(v)
            svg_parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}"/>')
            # Actor name
            svg_parts.append(
                f'<text x="{nx}" y="{ny}" text-anchor="{anchor}" font-size="9" '
                f'fill="#4b5563" font-weight="600">{name}</text>'
            )
            # Sub-label (Model layer only)
            if sub:
                svg_parts.append(
                    f'<text x="{nx}" y="{ny+11}" text-anchor="{anchor}" font-size="7.5" '
                    f'fill="#b0b8c4">{sub}</text>'
                )
            # Role tag — italic, muted
            role_y = ny + (22 if sub else 11)
            svg_parts.append(
                f'<text x="{nx}" y="{role_y}" text-anchor="{anchor}" font-size="7.5" '
                f'fill="#b0b8c4" font-style="italic">{role}</text>'
            )

        svg = (
            f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'style="display:block;font-family:inherit">'
            + ''.join(svg_parts)
            + '</svg>'
        )

        legend_items = [
            ('#93c5fd', 'Accelerating'),
            ('#fcd34d', 'Active (unstable or anchoring)'),
            ('#86efac', 'Early recovery'),
            ('#d1d5db', 'Fading'),
            ('#fca5a5', 'Declining'),
        ]
        legend_html = ' &nbsp;·&nbsp; '.join(
            f'<span style="display:inline-flex;align-items:center;gap:4px">'
            f'<span style="width:8px;height:8px;border-radius:50%;background:{c};display:inline-block"></span>'
            f'<span>{lbl}</span></span>'
            for c, lbl in legend_items
        )

        report_date = datetime.date.today().strftime('%-d %B %Y')
        return (
            f'<div style="font-size:16px;font-weight:600;color:#1f2937;margin-bottom:4px">'
            f'AI ecosystem — where key players are moving right now</div>'
            f'<p style="font-size:12px;color:#9ca3af;margin:0 0 16px">'
            f'Top-right = gaining attention fast &nbsp;·&nbsp; Bottom-left = losing relevance'
            f'&nbsp;&nbsp;—&nbsp;&nbsp;{report_date}</p>'
            f'{svg}'
            f'<div style="margin-top:12px;font-size:10px;color:#aaa">{legend_html}</div>'
        )

    vars['narrative_map_html'] = _build_narrative_map_html(trajectories)

    # Ecosystem lineage narratives — top 4 ecosystem lineages by gravity
    def _eco_lineage_narratives_html(lineages_sorted, top_n=4):
        eco = [r for r in lineages_sorted if r.get('lineage_type') == 'ecosystem']
        top = sorted(eco, key=lambda r: -r.get('lineage_max_gravity', 0))[:top_n]
        if not top:
            return '<p class="muted">No ecosystem lineages detected in this report window.</p>'

        def _state_score(s):
            return {'growing': 1.0, 'peaking': 0.4, 'stable': 0.0, 'fading': -1.0}.get(s.get('state', 'unknown'), -0.3)

        blocks = []
        for rec in top:
            storms_in_lin = sorted(rec['storms'], key=lambda s: s.get('created_at', ''))
            n = len(storms_in_lin)
            recent   = storms_in_lin[max(0, n - 4):]
            earlier  = storms_in_lin[:max(0, n - 4)]

            # Direction from lifecycle state trajectory
            recent_avg  = sum(_state_score(s) for s in recent)  / len(recent)  if recent  else 0
            earlier_avg = sum(_state_score(s) for s in earlier) / len(earlier) if earlier else recent_avg

            if   recent_avg >=  0.4:                                       direction, dir_color = 'Accelerating', 'var(--good)'
            elif recent_avg <= -0.4:                                       direction, dir_color = 'Declining',    'var(--danger)'
            elif earlier_avg < -0.2 and recent_avg > earlier_avg + 0.3:   direction, dir_color = 'Reversing',    '#7e22ce'
            elif earlier_avg >  0.2 and recent_avg < earlier_avg - 0.3:   direction, dir_color = 'Reversing',    '#7e22ce'
            else:                                                           direction, dir_color = 'Stable',       'var(--muted)'

            # Strength — constrained so declining != Strong
            grav   = rec.get('lineage_max_gravity', 0)
            events = rec.get('lineage_event_count', 0)
            if direction == 'Declining':
                strength = 'Moderate' if (grav > 0.2 or events > 150) else 'Weak'
            elif direction == 'Accelerating':
                strength = 'Strong' if (grav > 0.15 or events > 200) else ('Moderate' if grav > 0.06 else 'Weak')
            elif direction == 'Reversing':
                strength = 'Moderate'
            else:
                strength = 'Moderate' if grav > 0.12 else 'Weak'

            # Confidence from data breadth
            n_weeks = len({s.get('created_at', '')[:10] for s in storms_in_lin})
            conf_vals = [s.get('velocity_confidence', 'low') for s in storms_in_lin]
            high_c = sum(1 for c in conf_vals if c == 'high')
            med_c  = sum(1 for c in conf_vals if c in ('medium', 'moderate'))
            if   high_c >= n * 0.4 or (n_weeks >= 5 and n >= 8): confidence = 'High'
            elif med_c + high_c >= n * 0.25 or n_weeks >= 3:      confidence = 'Medium'
            else:                                                   confidence = 'Low'

            # What this is — concrete theme synthesis
            from collections import Counter as _Ctr
            theme_counts = _Ctr()
            dp_counts    = _Ctr()
            for s in storms_in_lin[-6:]:
                for t in s.get('themes', []):         theme_counts[t] += 1
                for p in s.get('domain_phrases', []): dp_counts[p]    += 1
            top_terms = [p for p, _ in dp_counts.most_common(2)] + [t for t, _ in theme_counts.most_common(2)]
            top_terms = list(dict.fromkeys(top_terms))[:3]
            actors_short = rec['lineage_actor_set'][:4]
            extra = len(rec['lineage_actor_set']) - 3
            actor_mention = ', '.join(actors_short[:3]) + (f', +{extra}' if extra > 0 else '')
            if top_terms:
                what_this_is = f"{', '.join(t.replace('_',' ') for t in top_terms).capitalize()} across {actor_mention}"
            else:
                what_this_is = f"{rec['label']} across {actor_mention}"

            # What changed — directional trajectory
            first_date = storms_in_lin[0].get('created_at', '')[:10]
            last_date  = storms_in_lin[-1].get('created_at', '')[:10]
            n_windows  = len(storms_in_lin)
            if direction == 'Declining':
                consec_fading = 0
                for s in reversed(storms_in_lin):
                    if s.get('state') == 'fading': consec_fading += 1
                    else: break
                if consec_fading >= n_windows * 0.8:
                    what_changed = f"Fading across all {n_windows} windows ({first_date} to {last_date}). No recovery signal."
                else:
                    what_changed = f"Declining in {consec_fading} of the most recent windows. Attention is contracting."
            elif direction == 'Accelerating':
                consec_growing = 0
                for s in reversed(storms_in_lin):
                    if s.get('state') in ('growing', 'peaking'): consec_growing += 1
                    else: break
                what_changed = f"Growing across {consec_growing} consecutive recent windows. Momentum is building."
            elif direction == 'Reversing':
                if recent_avg > earlier_avg:
                    what_changed = "Recovering — shifted from fading in earlier windows to growing recently."
                else:
                    what_changed = "Turning — earlier growth has given way to fading in the most recent windows."
            else:
                what_changed = f"Mixed signals across {n_windows} windows ({first_date} to {last_date}). No clear trend."

            # Why it matters — ecosystem-level inference
            n_actors = len(rec['lineage_actor_set'])
            if direction == 'Declining' and n_actors >= 3:
                why_matters = f"Coordinated decline across {n_actors} actors signals this theme is exiting the active ecosystem narrative set."
            elif direction == 'Declining':
                why_matters = "High-gravity narrative losing traction — watch for rotation into adjacent themes."
            elif direction == 'Accelerating' and n_actors >= 3:
                why_matters = f"Broadening across {n_actors} actors increases the chance this becomes a dominant cross-sector narrative."
            elif direction == 'Accelerating':
                why_matters = "Narrative pressure building — expansion to additional actors would amplify significantly."
            elif direction == 'Reversing' and recent_avg > earlier_avg:
                why_matters = "Early-stage recovery in a previously fading narrative — potential re-entry signal."
            elif direction == 'Reversing':
                why_matters = "Narrative instability — prior momentum has reversed without a clear new catalyst."
            else:
                why_matters = f"Sustained presence across {n_actors} actors suggests this theme is structurally embedded in the ecosystem."

            # What to watch — forward-looking signals
            watch_items = []
            if top_terms:
                t0 = top_terms[0].replace('_', ' ')
                if direction in ('Accelerating', 'Reversing') and recent_avg > 0:
                    watch_items.append(f"Whether {t0} expands beyond current actors or stays concentrated")
                else:
                    watch_items.append(f"Any new event signal around {t0} that could restart momentum")
            if len(actors_short) >= 2:
                if direction == 'Accelerating':
                    watch_items.append(f"Cross-actor amplification between {actors_short[0]} and {actors_short[1]}")
                elif direction == 'Declining':
                    watch_items.append(f"Whether {actors_short[0]} or {actors_short[1]} breaks from the fading trend")
                else:
                    watch_items.append(f"Divergence between {actors_short[0]} and {actors_short[1]} as a leading indicator")
            if len(top_terms) >= 2:
                watch_items.append(f"Rotation from {top_terms[0].replace('_',' ')} toward {top_terms[1].replace('_',' ')}")
            watch_items = watch_items[:3]

            # Render
            actors_str = ', '.join(rec['lineage_actor_set'])
            str_color  = {'Strong': 'var(--ink)', 'Moderate': '#5b6673', 'Weak': '#5b6673'}.get(strength, '#5b6673')
            signal_line = (
                f'<div class="signal-strip" style="margin-bottom:6px">'
                f'<span class="sig-val" style="color:{dir_color}">{direction}</span>'
                f'<span class="sig-sep">·</span>'
                f'<span class="sig-val" style="color:{str_color}">{strength}</span>'
                f'<span class="sig-sep">·</span>'
                f'<span class="sig-val" style="color:var(--muted);font-weight:400">{confidence} confidence</span>'
                f'</div>'
            )
            watch_html = ''.join(f'<li style="margin-bottom:2px">{w}</li>' for w in watch_items)
            blocks.append(
                f'<div class="storm" style="margin-bottom:14px">'
                f'<div class="storm-header" style="margin-bottom:4px">'
                f'<div class="storm-title" style="font-size:13px">{rec["label"]}</div>'
                f'</div>'
                f'<div class="mini-meta" style="margin-bottom:4px">'
                f'<span><strong>Actors:</strong> {actors_str}</span>'
                f'<span><strong>Windows:</strong> {rec["lineage_storm_count"]}</span>'
                f'<span><strong>Events:</strong> {rec["lineage_event_count"]}</span>'
                f'</div>'
                f'{signal_line}'
                f'<p style="font-size:12px;margin:0 0 4px;color:var(--ink)">{what_this_is}</p>'
                f'<p style="font-size:12px;margin:0 0 4px;color:var(--muted)"><strong style="color:var(--ink)">What changed:</strong> {what_changed}</p>'
                f'<p style="font-size:12px;margin:0 0 6px;color:var(--muted)"><strong style="color:var(--ink)">Why it matters:</strong> {why_matters}</p>'
                f'<div style="font-size:11px;color:var(--muted)">'
                f'<strong style="color:var(--ink);text-transform:uppercase;letter-spacing:.05em;font-size:10px">What to watch</strong>'
                f'<ul class="bullets" style="margin-top:3px">{watch_html}</ul>'
                f'</div>'
                f'</div>'
            )
        return ''.join(blocks)

    vars['eco_lineage_narratives_html'] = _eco_lineage_narratives_html(lineages_sorted)
    vars['eco_lineage_section_html']     = _eco_lineage_narratives_html(lineages_sorted)

    # Ecosystem lineage theme evidence — Ecosystem View section
    def _eco_lineage_theme_evidence_html(lineages_sorted, top_n=4):
        eco = [r for r in lineages_sorted if r.get('lineage_type') == 'ecosystem']
        top = sorted(eco, key=lambda r: -r.get('lineage_max_momentum', 0))[:top_n]
        if not top:
            return ''

        _mom_colors = {'Surging': '#d62728', 'Expanding': '#ff7f0e',
                       'Building': '#2ca02c', 'Stable': '#888', 'Cooling': '#aaa'}
        from collections import Counter
        rows = []
        for rec in top:
            theme_counts = Counter()
            dp_counts    = Counter()
            for s in rec['storms']:
                for t in s.get('themes', []):
                    theme_counts[t] += 1
                for p in s.get('domain_phrases', []):
                    dp_counts[p] += 1

            top_themes = [t for t, _ in theme_counts.most_common(3)]
            top_dp     = [p for p, _ in dp_counts.most_common(2)]
            actors_str = ', '.join(rec['lineage_actor_set'])
            themes_str = ', '.join(top_themes) if top_themes else '—'
            dp_str     = ', '.join(top_dp)     if top_dp     else '—'
            mom = rec.get('lineage_max_momentum', 0)
            mom_class = classify_momentum(mom)
            mom_color = _mom_colors.get(mom_class, '#888')
            mom_cell = (f'<span style="color:{mom_color};font-weight:700">{mom:.0f}</span>'
                        f'<br><span class="muted" style="font-size:10px">{mom_class}</span>')

            rows.append(
                f'<tr>'
                f'<td style="font-weight:600;font-size:12px">{rec["label"]}</td>'
                f'<td style="font-size:11px">{actors_str}</td>'
                f'<td style="font-size:11px">{themes_str}</td>'
                f'<td style="font-size:11px">{dp_str}</td>'
                f'<td style="text-align:right">{rec["lineage_storm_count"]}</td>'
                f'<td style="text-align:right">{rec["lineage_event_count"]}</td>'
                f'<td style="text-align:right">{mom_cell}</td>'
                f'</tr>'
            )

        return (
            '<table style="width:100%;font-size:12px">'
            '<thead><tr>'
            '<th style="text-align:left">Lineage</th>'
            '<th style="text-align:left">Actors</th>'
            '<th style="text-align:left">Top themes</th>'
            '<th style="text-align:left">Domain phrases</th>'
            '<th style="text-align:right">Storms</th>'
            '<th style="text-align:right">Events</th>'
            '<th style="text-align:right">Momentum</th>'
            '</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody>'
            '</table>'
        )

    vars['eco_lineage_theme_evidence_html'] = _eco_lineage_theme_evidence_html(lineages_sorted)

    # Narrative dynamics for executive overview — storm-level (not window-level)
    n_storms = len(_actor_storms_merged)
    drift_stable = sum(1 for s in _actor_storms_merged if s.get('drift', 0) < 0.08)
    drift_gradual = sum(1 for s in _actor_storms_merged if 0.08 <= s.get('drift', 0) <= 0.20)
    drift_pivot = sum(1 for s in _actor_storms_merged if s.get('drift', 0) > 0.20)

    from collections import Counter as Ctr
    shift_counts = Ctr(s.get('shift_type', 'unclear') for s in _actor_storms_merged)

    def shift_detail(drift_class_storms):
        """Build shift type detail string for storms in a drift class."""
        sc = Ctr(s.get('shift_type', 'unclear') for s in drift_class_storms)
        parts = []
        for k, label in [('thematic_shift', 'thematic'), ('market_noise_shift', 'market noise'),
                         ('mixed_shift', 'mixed'), ('stable', 'stable'), ('unclear', 'unclear')]:
            if sc[k]:
                parts.append(f"{sc[k]} {label}")
        return ', '.join(parts) if parts else '—'

    stable_storms = [s for s in _actor_storms_merged if s.get('drift', 0) < 0.08]
    gradual_storms = [s for s in _actor_storms_merged if 0.08 <= s.get('drift', 0) <= 0.20]
    pivot_storms = [s for s in _actor_storms_merged if s.get('drift', 0) > 0.20]
    
    vars['drift_stable'] = drift_stable
    vars['drift_gradual'] = drift_gradual
    vars['drift_pivot'] = drift_pivot
    vars['shift_stable_detail'] = shift_detail(stable_storms)
    vars['shift_gradual_detail'] = shift_detail(gradual_storms)
    vars['shift_pivot_detail'] = shift_detail(pivot_storms)
    
    # Generate interpretation text
    pivot_pct = drift_pivot / n_storms * 100 if n_storms else 0
    noise_in_pivots = sum(1 for s in pivot_storms if s.get('shift_type') == 'market_noise_shift')
    thematic_in_pivots = sum(1 for s in pivot_storms if s.get('shift_type') == 'thematic_shift')
    
    if pivot_pct > 40:
        interp = f"High narrative churn: {drift_pivot} of {n_storms} storms ({pivot_pct:.0f}%) show major drift."
        if noise_in_pivots > 0:
            interp += f" However, {noise_in_pivots} of those are market-noise shifts rather than genuine thematic pivots."
        if thematic_in_pivots > 0:
            interp += f" {thematic_in_pivots} represent real thematic shifts worth monitoring."
    elif pivot_pct > 20:
        interp = f"Moderate narrative churn: {drift_pivot} of {n_storms} storms ({pivot_pct:.0f}%) show major drift."
        if noise_in_pivots > 0:
            interp += f" {noise_in_pivots} are market-noise driven."
    else:
        interp = f"The ecosystem is narratively stable: only {drift_pivot} of {n_storms} storms ({pivot_pct:.0f}%) show major drift."
    
    vars['narrative_dynamics_interpretation'] = interp
    
    # Ecosystem storms
    for i, storm in enumerate(eco_storms_sorted, 1):
        vars[f'eco_headline_{i}'] = _dh(storm, 80)
        vars[f'eco_state_{i}'] = storm.get('state', 'unknown')
        vars[f'eco_state_{i}_class'] = state_to_class(storm.get('state', 'unknown'))
        vars[f'eco_actors_{i}'] = storm.get('num_unique_actors', len(storm.get('actors', [])))
        vars[f'eco_events_{i}'] = storm.get('event_count', 0)
        vars[f'eco_momentum_{i}'] = f"{storm.get('momentum', 0):.0f}"
        vars[f'eco_accel_{i}'] = f"{storm.get('acceleration', 0):.0f}"
        vars[f'eco_peak_ratio_{i}'] = f"{storm.get('peak_ratio', 0):.2f}"
        vars[f'eco_drift_{i}'] = f"{storm.get('drift', 0):.3f}"
        vars[f'eco_actor_entropy_{i}'] = f"{storm.get('actor_entropy', 0):.2f}"
        vars[f'eco_one_liner_{i}'] = storm.get('display_one_liner', storm.get('one_liner', storm.get('llm_one_liner', 'Cross-actor narrative cluster')))
        vars[f'eco_gravity_{i}'] = f"{storm.get('gravity_score', 0):.2f}"
        vars[f'eco_velocity_score_{i}'] = f"{storm.get('velocity_score', 0):.3f}"
        vars[f'eco_velocity_state_{i}'] = storm.get('velocity_state', 'stable').title()
        vars[f'eco_velocity_confidence_{i}'] = storm.get('velocity_confidence', 'low').title()
        vars[f'eco_displayed_velocity_state_{i}'] = displayed_velocity_state(storm).title()
        vars[f'eco_priority_bucket_{i}'] = storm.get('priority_bucket', 'low_gravity_low_velocity')
        vars[f'eco_priority_label_{i}']  = storm.get('priority_label', 'Background')
        vars[f'eco_is_breakout_candidate_{i}'] = str(storm.get('is_breakout_candidate', False)).lower()
        vars[f'eco_lineage_id_{i}'] = storm.get('lineage_id') or 'none'
        
        # Narrative details for ecosystem
        vars[f'eco_dominant_actors_{i}'] = ', '.join(storm.get('dominant_actors', [])[:5]) if storm.get('dominant_actors') else 'N/A'
        vars[f'eco_domain_phrases_{i}'] = ', '.join(storm.get('domain_phrases', [])[:3]) if storm.get('domain_phrases') else 'N/A'
        vars[f'eco_all_actors_{i}'] = ', '.join(storm.get('actors', [])[:8]) if storm.get('actors') else 'N/A'
        
        # Get representative event titles (5 instead of 3)
        rep_events = storm.get('representative_events', [])
        event_titles_html = []
        for rep_event in rep_events[:5]:
            title = rep_event.get('title', '').strip()
            if title:
                event_titles_html.append(f'<li>{title[:120]}</li>')
        
        vars[f'eco_evidence_html_{i}'] = ''.join(event_titles_html) if event_titles_html else '<li class="muted">No representative events available</li>'
        
        # Pressure for ecosystem storm
        eco_p = pressure_map.get(storm['storm_id'], {})
        vars[f'eco_pressure_{i}'] = f"{eco_p.get('pressure_level', 'N/A').title()} ({eco_p.get('pressure_score', 0):.2f})" if eco_p else 'N/A'
        vars[f'eco_pressure_interp_{i}'] = eco_p.get('pressure_interpretation', '') if eco_p else ''
    
    # Actor-dominant storms (single-actor visible in ecosystem field)
    actor_dominant_sorted = sorted(_apply_storm_merges(single_actor_storms, _storm_merges), key=lambda x: x.get('event_count', 0), reverse=True)[:5]
    actor_dominant_html = []
    for storm in actor_dominant_sorted:
        label = _dh(storm, 50)
        state = storm.get('state', 'unknown')
        events = storm.get('event_count', 0)
        actors = ', '.join(storm.get('dominant_actors', [])[:3]) or 'N/A'
        momentum = f"{storm.get('momentum', 0):.0f}"
        actor_dominant_html.append(
            f"<tr><td>{label}</td><td>{state}</td><td>{events}</td><td>{actors}</td><td>{momentum}</td></tr>"
        )
    vars['actor_dominant_storms_html'] = ''.join(actor_dominant_html) if actor_dominant_html else '<tr><td colspan="5" class="muted">No single-actor storms detected</td></tr>'
    
    # Ecosystem diagnostics
    vars['eco_total_storms'] = total_eco_storms
    vars['eco_cross_actor_count'] = cross_actor_count
    vars['eco_single_actor_count'] = single_actor_count
    vars['eco_avg_actors'] = f"{avg_actors:.1f}"
    vars['eco_avg_entropy'] = f"{avg_entropy:.2f}"
    
    def _render_momentum_components(comps: dict, explanation: str) -> str:
        """Render momentum component scores as a readable breakdown."""
        if not comps:
            return ''
        lines = []
        pl  = comps.get('pressure_level', 50)
        pt  = comps.get('pressure_trend', 50)
        st  = comps.get('spread_trend', 50)
        ea  = comps.get('event_acceleration', 50)
        ct  = comps.get('coherence_trend', 50)
        np_ = comps.get('noise_penalty', 0)

        def _bar(v, lo=0, hi=100):
            pct = int((v - lo) / (hi - lo) * 100) if hi > lo else 50
            color = '#2ca02c' if v >= 65 else '#ff7f0e' if v >= 50 else '#aaa'
            return (f'<span style="display:inline-block;width:{pct}px;height:6px;'
                    f'background:{color};border-radius:2px;vertical-align:middle"></span>')

        rows = [
            ('Pressure level',    pl,  'Current signal strength'),
            ('Pressure trend',    pt,  'Signal direction'),
            ('Actor spread',      st,  'Expanding reach'),
            ('Event acceleration',ea,  'Coverage ramping'),
            ('Coherence trend',   ct,  'Getting clearer'),
        ]
        parts = ['<table style="font-size:11px;border-collapse:collapse;width:100%">']
        for label, val, _ in rows:
            parts.append(
                f'<tr><td style="color:var(--muted);padding:1px 6px 1px 0;white-space:nowrap">{label}</td>'
                f'<td>{_bar(val)}</td>'
                f'<td style="text-align:right;padding-left:6px;font-weight:600">{val:.0f}</td></tr>'
            )
        if np_ > 0:
            parts.append(
                f'<tr><td style="color:#d62728;padding:1px 6px 1px 0">Noise penalty</td>'
                f'<td></td>'
                f'<td style="text-align:right;color:#d62728;font-weight:600">−{np_:.0f}</td></tr>'
            )
        parts.append('</table>')
        return ''.join(parts)

    # Actor snapshots
    for i, (actor, count) in enumerate(top_actors, 1):
        actor_storms_filtered = [s for s in actor_storms if s['actor'] == actor]
        actor_storms_filtered = _apply_storm_merges(actor_storms_filtered, _storm_merges)
        top_storm = sorted(actor_storms_filtered, key=lambda s: -s.get('gravity_score', 0))[0] if actor_storms_filtered else {}
        additional_storms = sorted([s for s in actor_storms_filtered if s.get('storm_id') != top_storm.get('storm_id')],
                                   key=lambda s: -s.get('gravity_score', 0))[:3]
        
        vars[f'actor_{i}_name'] = actor
        vars[f'actor_{i}_visual_path'] = f'data/derived/storm_field_{actor}_feb_mar.png'
        vars[f'actor_{i}_top_storm_headline'] = _dh(top_storm, 80)
        vars[f'actor_{i}_top_storm_state'] = top_storm.get('state', 'unknown')
        vars[f'actor_{i}_top_storm_state_class'] = state_to_class(top_storm.get('state', 'unknown'))
        vars[f'actor_{i}_top_storm_events'] = top_storm.get('event_count', 0)
        vars[f'actor_{i}_top_storm_peak_ratio'] = f"{top_storm.get('peak_ratio', 0):.2f}"
        vars[f'actor_{i}_top_storm_momentum'] = f"{top_storm.get('momentum', 0):.0f}"
        vars[f'actor_{i}_top_storm_acceleration'] = f"{top_storm.get('acceleration', 0):.0f}"
        vars[f'actor_{i}_top_storm_coherence'] = format_coherence(top_storm.get('coherence', 0))
        vars[f'actor_{i}_top_storm_gravity'] = f"{top_storm.get('gravity_score', 0):.2f}"
        vars[f'actor_{i}_top_storm_velocity_score'] = f"{top_storm.get('velocity_score', 0):.3f}"
        vars[f'actor_{i}_top_storm_velocity_state'] = top_storm.get('velocity_state', 'stable').title()
        vars[f'actor_{i}_top_storm_velocity_confidence'] = top_storm.get('velocity_confidence', 'low').title()
        vars[f'actor_{i}_top_storm_displayed_velocity_state'] = displayed_velocity_state(top_storm).title()

        # Signal strip: status label + CSS class
        _vel_disp = displayed_velocity_state(top_storm).lower()
        if 'accelerating' in _vel_disp:
            _status_label, _status_cls = 'Accelerating', 'accel'
        elif 'declining' in _vel_disp or 'fading' in _vel_disp:
            _status_label, _status_cls = 'Declining', 'decl'
        elif 'reversing' in _vel_disp:
            _status_label, _status_cls = 'Reversing', 'rev'
        elif 'stabilizing' in _vel_disp or 'stable' in _vel_disp:
            _status_label, _status_cls = 'Stabilizing', 'stable'
        else:
            _status_label, _status_cls = _vel_disp.title() or 'Stable', 'neutral'
        vars[f'actor_{i}_top_storm_status'] = _status_label
        vars[f'actor_{i}_top_storm_status_class'] = _status_cls

        # Strength: derived from gravity + momentum class
        _grav = top_storm.get('gravity_score', 0)
        _mc_s = top_storm.get('momentum_class', '')
        if _grav > 0.15 or _mc_s == 'Surging':
            _strength = 'Strong'
        elif _grav > 0.06 or _mc_s in ('Expanding', 'Building'):
            _strength = 'Moderate'
        elif _grav > 0.02 or top_storm.get('event_count', 0) >= 5:
            _strength = 'Weak'
        else:
            _strength = 'Emerging'
        vars[f'actor_{i}_top_storm_strength'] = _strength

        # Prev → Now: compare chronologically adjacent storm windows
        _all_sorted = sorted(actor_storms_filtered, key=lambda s: s.get('created_at', ''))
        _others_sorted = [s for s in _all_sorted if s.get('storm_id') != top_storm.get('storm_id')]
        if _others_sorted:
            _prev_v = displayed_velocity_state(_others_sorted[-1]).lower()
            if 'accelerating' in _prev_v:   _prev_lbl = 'Accelerating'
            elif 'declining' in _prev_v or 'fading' in _prev_v: _prev_lbl = 'Declining'
            elif 'reversing' in _prev_v:    _prev_lbl = 'Reversing'
            elif 'stabilizing' in _prev_v or 'stable' in _prev_v: _prev_lbl = 'Stabilizing'
            else: _prev_lbl = _prev_v.title() or 'Stable'
            vars[f'actor_{i}_window_comparison'] = f"Prev: {_prev_lbl} → Now: {_status_label}"
        else:
            vars[f'actor_{i}_window_comparison'] = f"First window · Now: {_status_label}"

        vars[f'actor_{i}_top_storm_priority_bucket'] = top_storm.get('priority_bucket', 'low_gravity_low_velocity')
        vars[f'actor_{i}_top_storm_priority_label']  = top_storm.get('priority_label', 'Background')
        vars[f'actor_{i}_top_storm_is_breakout_candidate'] = str(top_storm.get('is_breakout_candidate', False)).lower()
        vars[f'actor_{i}_top_storm_lineage_id'] = top_storm.get('lineage_id') or 'none'
        vars[f'actor_{i}_top_storm_one_liner'] = top_storm.get('display_one_liner', top_storm.get('one_liner', top_storm.get('llm_one_liner', 'Actor-specific narrative')))
        
        # Narrative details
        vars[f'actor_{i}_dominant_themes'] = ', '.join(top_storm.get('dominant_cluster_terms', [])[:5]) if top_storm.get('dominant_cluster_terms') else 'N/A'
        vars[f'actor_{i}_domain_phrases'] = ', '.join(top_storm.get('domain_phrases', [])[:3]) if top_storm.get('domain_phrases') else 'N/A'
        vars[f'actor_{i}_related_actors'] = ', '.join(top_storm.get('actors', [])[:5]) if top_storm.get('actors') else actor
        
        # Narrative role for this actor
        actor_leadership = leadership_map.get(actor, {})
        if actor_leadership:
            role_label = actor_leadership['role'].title()
            vars[f'actor_{i}_narrative_role'] = role_label
        else:
            vars[f'actor_{i}_narrative_role'] = 'N/A'
        
        # Pressure for this actor's top storm
        actor_p = pressure_map.get(top_storm.get('storm_id', ''), {})
        if actor_p:
            vars[f'actor_{i}_pressure'] = f"{actor_p['pressure_level'].title()} ({actor_p['pressure_score']:.2f})"
            vars[f'actor_{i}_pressure_interp'] = actor_p.get('pressure_interpretation', '')
        else:
            vars[f'actor_{i}_pressure'] = 'N/A'
            vars[f'actor_{i}_pressure_interp'] = ''

        # Look up momentum from merged storm lookup (covers both merged and per-actor filtered storms)
        _sid = top_storm.get('storm_id', '')
        _mom = _momentum_lookup.get(_sid) or {}
        _ms_score  = _mom.get('momentum_score') if _mom else top_storm.get('momentum_score')
        _ms_class  = _mom.get('momentum_class', top_storm.get('momentum_class', ''))
        _ms_expl   = _mom.get('momentum_explanation', top_storm.get('momentum_explanation', ''))
        _ms_comps  = _mom.get('momentum_components', top_storm.get('momentum_components', {}))
        _ms_delta  = _mom.get('momentum_delta', top_storm.get('momentum_delta', 0.0)) or 0.0
        _ns_label  = _mom.get('narrative_state', top_storm.get('narrative_state', ''))
        _ns_interp = _mom.get('narrative_state_interp', top_storm.get('narrative_state_interp', ''))

        if _ms_score is not None:
            delta_str = (f' (+{_ms_delta:.0f})' if _ms_delta >= 2
                         else f' ({_ms_delta:.0f})' if _ms_delta <= -2
                         else '')
            vars[f'actor_{i}_momentum_score'] = f"{_ms_score:.0f}{delta_str}"
            vars[f'actor_{i}_momentum_class'] = _ms_class
            vars[f'actor_{i}_momentum_explanation'] = _ms_expl
            vars[f'actor_{i}_momentum_components_html'] = _render_momentum_components(_ms_comps, _ms_expl)
            vars[f'actor_{i}_narrative_state'] = _ns_label
            vars[f'actor_{i}_narrative_state_interp'] = _ns_interp
        else:
            vars[f'actor_{i}_momentum_score'] = '—'
            vars[f'actor_{i}_momentum_class'] = ''
            vars[f'actor_{i}_momentum_explanation'] = ''
            vars[f'actor_{i}_momentum_components_html'] = ''
            vars[f'actor_{i}_narrative_state'] = ''
            vars[f'actor_{i}_narrative_state_interp'] = ''
        
        # Get narrative evolution
        evolution = evolution_map.get(top_storm.get('storm_id', ''), {})
        if evolution.get('has_evolution'):
            drift_val = evolution.get('avg_drift', 0)
            reliability = evolution.get('reliability', 'moderate')
            
            # Format drift display
            if reliability == 'insufficient_data':
                vars[f'actor_{i}_drift'] = 'Insufficient data'
                vars[f'actor_{i}_drift_class'] = ''
                vars[f'actor_{i}_shift_type'] = ''
            else:
                vars[f'actor_{i}_drift'] = f"{drift_val:.3f}"
                drift_labels = {'stable': 'Stable narrative', 'gradual': 'Gradual evolution', 'major_pivot': 'Major narrative pivot', 'unreliable': 'Unreliable (sparse data)'}
                drift_class_label = drift_labels.get(evolution['drift_classification'], 'Unknown')
                if reliability == 'moderate':
                    drift_class_label += ' (limited data)'
                vars[f'actor_{i}_drift_class'] = drift_class_label
                
                shift_type = evolution.get('shift_type', top_storm.get('shift_type', 'unclear'))
                shift_labels = {'stable': '', 'thematic_shift': 'Thematic shift', 'market_noise_shift': 'Market noise shift', 'mixed_shift': 'Mixed shift', 'unclear': 'Unclear'}
                vars[f'actor_{i}_shift_type'] = shift_labels.get(shift_type, shift_type)
            
            vars[f'actor_{i}_has_evolution'] = True
            vars[f'actor_{i}_evolution_text'] = format_evolution_text(evolution.get('phases', []))
        else:
            vars[f'actor_{i}_has_evolution'] = False
            vars[f'actor_{i}_drift'] = f"{top_storm.get('drift', 0):.3f}" if top_storm.get('drift', 0) > 0 else 'Insufficient data'
            vars[f'actor_{i}_drift_class'] = ''
            shift_type = top_storm.get('shift_type', 'unclear')
            shift_labels = {'stable': '', 'thematic_shift': 'Thematic shift', 'market_noise_shift': 'Market noise shift', 'mixed_shift': 'Mixed shift', 'unclear': 'Unclear'}
            vars[f'actor_{i}_shift_type'] = shift_labels.get(shift_type, shift_type)
            vars[f'actor_{i}_evolution_text'] = 'Insufficient data for narrative evolution analysis.'
        
        # Get representative event titles (5 instead of 3)
        rep_events = top_storm.get('representative_events', [])
        event_titles_html = []
        for rep_event in rep_events[:5]:
            title = rep_event.get('title', '').strip()
            if title:
                event_titles_html.append(f'<li>{title[:120]}</li>')
        
        vars[f'actor_{i}_evidence_html'] = ''.join(event_titles_html) if event_titles_html else '<li class="muted">No representative events available</li>'
        
        # Community perspective
        co = overlay_map.get(actor)
        if co and co['community_post_count'] >= 3:
            subs = ', '.join(co['community_top_subreddits'][:3])
            themes = ', '.join(co['community_key_themes'][:4])
            div_themes = ', '.join(co['community_divergent_themes'][:3])
            comm_html = (
                '<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--line)">'
                '<div style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:6px;font-weight:700">Community Perspective</div>'
                '<ul class="details-grid">'
                f'<li><strong>Posts:</strong> {co["community_post_count"]}</li>'
                f'<li><strong>Alignment:</strong> {co["community_alignment_label"].title()}</li>'
                f'<li><strong>Subreddits:</strong> {subs}</li>'
                f'<li><strong>Key themes:</strong> {themes}</li>'
            )
            if div_themes:
                comm_html += f'<li><strong>Divergent themes:</strong> {div_themes}</li>'
            comm_html += '</ul>'
            comm_html += f'<p class="muted" style="font-size:11px;margin-top:4px">{co["community_interpretation"]}</p>'
            comm_html += '<p class="muted" style="font-size:11px;margin-top:6px;font-style:italic">⚠ Community data is currently synthetic. Real Reddit ingestion coming soon.</p></div>'
            vars[f'actor_{i}_community_html'] = comm_html
        else:
            vars[f'actor_{i}_community_html'] = ''
        
        # Additional storms table
        additional_storms_html = []
        for add_storm in additional_storms:
            storm_label = _dh(add_storm, 40)
            storm_state = add_storm.get('state', 'unknown')
            _add_vel = displayed_velocity_state(add_storm).lower()
            if 'accelerating' in _add_vel:   storm_status_lbl = 'Accelerating'
            elif 'declining' in _add_vel or 'fading' in _add_vel: storm_status_lbl = 'Declining'
            elif 'reversing' in _add_vel:    storm_status_lbl = 'Reversing'
            elif 'stabilizing' in _add_vel or 'stable' in _add_vel: storm_status_lbl = 'Stabilizing'
            else: storm_status_lbl = _add_vel.title() or '—'
            storm_events = add_storm.get('event_count', 0)
            storm_coherence = format_coherence(add_storm.get('coherence', 0))
            additional_storms_html.append(
                f"<tr><td>{storm_label}</td><td>{storm_state}</td><td>{storm_status_lbl}</td><td>{storm_events}</td><td>{storm_coherence}</td></tr>"
            )
        vars[f'actor_{i}_additional_storms_html'] = ''.join(additional_storms_html) if additional_storms_html else '<tr><td colspan="5" class="muted">No additional storms detected</td></tr>'
        
        themes = top_storm.get('themes', [])[:3]
        for j in range(1, 4):
            vars[f'actor_{i}_bullet_{j}'] = themes[j-1] if j-1 < len(themes) else 'Additional context'
    
    # Merge candidates - build HTML to skip empty rows
    merge_rows_html = []
    for i in range(1, 4):
        if i - 1 < len(merge_sorted):
            merge = merge_sorted[i - 1]
            pair = f"{merge.get('storm_a_id', 'A')} ↔ {merge.get('storm_b_id', 'B')}"
            score = f"{merge.get('merge_score', 0):.2f}"
            theme = ', '.join(merge.get('shared_themes', [])[:2]) or 'mixed'
            note = 'Potential convergence'
            merge_rows_html.append(f'<tr><td>{pair}</td><td>{score}</td><td>{theme}</td><td>{note}</td></tr>')
    
    vars['merge_rows_html'] = ''.join(merge_rows_html) if merge_rows_html else '<tr><td colspan="4" class="muted">No convergence candidates detected</td></tr>'
    
    # Propagation chains - build HTML to skip empty rows
    path_rows_html = []
    for i in range(1, 4):
        if i - 1 < len(chains_sorted):
            chain = chains_sorted[i - 1]
            actors = chain.get('actors', [])
            pathway = ' → '.join(actors)
            lag = f"{len(actors)-1} hops"
            theme = chain.get('shared_theme_hint', 'mixed')[:30]
            note = f"Score: {chain.get('mean_score', 0):.2f}"
            path_rows_html.append(f'<tr><td>{pathway}</td><td>{lag}</td><td>{theme}</td><td>{note}</td></tr>')
    
    vars['path_rows_html'] = ''.join(path_rows_html) if path_rows_html else '<tr><td colspan="4" class="muted">No propagation pathways detected</td></tr>'

    # Build lead-lag actor pair table
    lead_lag_rows_html = []
    for r in actor_lead_lag[:12]:
        pair = f"{r['source_actor']} → {r['target_actor']}"
        lanes = f"{r['source_lane']} → {r['target_lane']}"
        lead_lag_rows_html.append(
            f'<tr><td><strong>{pair}</strong></td>'
            f'<td style="text-align:right">{r["count"]}</td>'
            f'<td style="text-align:right">{r["mean_lag_hours"]}h</td>'
            f'<td style="text-align:right">{r["median_lag_hours"]}h</td>'
            f'<td class="muted">{lanes}</td></tr>'
        )
    vars['lead_lag_rows_html'] = ''.join(lead_lag_rows_html) if lead_lag_rows_html else '<tr><td colspan="5" class="muted">No actor pairs with ≥5 edges detected</td></tr>'

    # Build lane transition table
    lane_transition_rows_html = []
    for t in lane_transitions[:10]:
        transition = f"{t['source_lane']} → {t['target_lane']}"
        actors_str = ', '.join(t.get('top_actors', [])[:3])
        lane_transition_rows_html.append(
            f'<tr><td><strong>{transition}</strong></td>'
            f'<td style="text-align:right">{t["count"]}</td>'
            f'<td style="text-align:right">{t["avg_lag_hours"]}h</td>'
            f'<td class="muted">{actors_str}</td></tr>'
        )
    vars['lane_transition_rows_html'] = ''.join(lane_transition_rows_html) if lane_transition_rows_html else '<tr><td colspan="4" class="muted">No cross-lane transitions detected</td></tr>'

    # Build lead-lag narrative summary sentences
    lead_lag_summary_parts = []
    for r in actor_lead_lag[:5]:
        lead_lag_summary_parts.append(
            f'<li><strong>{r["source_actor"]}</strong> leads <strong>{r["target_actor"]}</strong> narratives '
            f'by avg <strong>{r["mean_lag_hours"]}h</strong> '
            f'<span class="muted">({r["count"]} edges, {r["source_lane"]}→{r["target_lane"]})</span></li>'
        )
    vars['lead_lag_summary_html'] = '<ul class="bullets">' + ''.join(lead_lag_summary_parts) + '</ul>' if lead_lag_summary_parts else '<p class="muted">No lead-lag pairs detected.</p>'

    top_lane_trans = lane_transitions[0] if lane_transitions else None
    if top_lane_trans:
        vars['top_lane_transition_text'] = (
            f"{top_lane_trans['source_lane'].title()} narratives lead "
            f"{top_lane_trans['target_lane'].title()} narratives by avg "
            f"{top_lane_trans['avg_lag_hours']}h ({top_lane_trans['count']} edges)"
        )
    else:
        vars['top_lane_transition_text'] = 'No cross-lane transitions detected.'

    # Build storm index — grouped by lineage
    all_storms_index = dedupe_by_storm_id(actor_storms + eco_storms, 'storm_index_all')
    all_storms_index = _apply_storm_merges(all_storms_index, _storm_merges)
    # Final display_headline dedup for heuristic-named storms not covered by merge map
    _seen_dh: set = set()
    all_storms_index = [
        s for s in all_storms_index
        if (dh := s.get('display_headline') or s['storm_id']) not in _seen_dh
        and not _seen_dh.add(dh)
    ]

    # Patch trend onto storm index entries from the already-enriched merged dicts
    _trend_lookup = {_ms['storm_id']: (_ms.get('trend', ''), _ms.get('trend_explanation', ''))
                     for _ms in _actor_storms_merged + _eco_storms_merged if 'trend' in _ms}
    for _s in all_storms_index:
        _t = _trend_lookup.get(_s['storm_id'])
        if _t:
            _s['trend'], _s['trend_explanation'] = _t

    lineage_index_groups = {}
    unassigned = []
    for storm in all_storms_index:
        lid = storm.get('lineage_id')
        if lid:
            if lid not in lineage_index_groups:
                lineage_index_groups[lid] = {
                    'label':     storm.get('lineage_label', lid),
                    'actor_set': storm.get('lineage_actor_set', []),
                    'storms':    [],
                }
            lineage_index_groups[lid]['storms'].append(storm)
        else:
            unassigned.append(storm)

    def _phase_rows(storms):
        """
        Phase-grouped rendering: one row per distinct phase, actors listed inline.
        Falls back to per-row for heuristic-named storms (no ' — ' separator).
        Phases ordered chronologically by earliest storm in each group.
        """
        by_phase: dict[str, list] = {}   # phase_name → list of storms
        ungrouped = []
        for s in storms:
            dh = _dh(s)
            if ' — ' in dh:
                phase = dh.split(' — ', 1)[1]
                by_phase.setdefault(phase, []).append(s)
            else:
                ungrouped.append(s)

        rows = []
        # Sort phases by earliest storm date
        phase_order = sorted(
            by_phase.keys(),
            key=lambda p: min(s.get('created_at', '') for s in by_phase[p])
        )
        for phase in phase_order:
            group = sorted(by_phase[phase], key=lambda s: s.get('created_at', ''))
            actors = []
            seen_a: set = set()
            for s in group:
                a = s.get('actor', '') or (s.get('dominant_actors') or ['?'])[0]
                if a and a not in seen_a:
                    seen_a.add(a)
                    actors.append(a)
            total_events = sum(s.get('event_count', 0) for s in group)
            states = [s.get('state', 'unknown') for s in group]
            dominant_state = max(set(states), key=states.count)
            actors_str = ' · '.join(actors[:14])
            # Trend from the highest-gravity storm in this phase group
            _top = max(group, key=lambda s: s.get('gravity_score', 0))
            _t   = _top.get('trend', '')
            _phase_trend_html = ''
            if _t and _t != 'stable':
                _arrow = _TREND_ARROWS.get(_t, '')
                _expl  = _top.get('trend_explanation', '')
                _phase_trend_html = (
                    f' <span title="{_expl}" '
                    f'style="font-size:11px;color:var(--muted);cursor:default">{_arrow}</span>'
                )
            rows.append(
                f'<tr style="font-size:11px">'
                f'<td style="padding-left:16px;font-weight:500">{phase}{_phase_trend_html}</td>'
                f'<td colspan="3" style="color:var(--muted)">{actors_str}</td>'
                f'<td style="text-align:right">{total_events}</td>'
                f'<td><span class="state-badge {state_to_class(dominant_state)}">{dominant_state}</span></td>'
                f'</tr>'
            )

        for s in sorted(ungrouped, key=lambda x: x.get('created_at', '')):
            actor_label = s.get('actor', '') or (s.get('dominant_actors') or ['—'])[0]
            name = _dh(s)
            name = name[:70] + '…' if len(name) > 70 else name
            rows.append(
                f'<tr style="font-size:11px;color:var(--muted)">'
                f'<td style="padding-left:16px">{name}</td>'
                f'<td>{actor_label}</td>'
                f'<td colspan="2"></td>'
                f'<td style="text-align:right">{s.get("event_count", 0)}</td>'
                f'<td>{format_coherence(s.get("coherence"))}</td>'
                f'</tr>'
            )
        return ''.join(rows)

    def _lineage_header(label, actor_set, n_phases):
        actors_str = ', '.join(actor_set[:8]) if actor_set else 'N/A'
        return (
            f'<tr style="background:var(--line)">'
            f'<td colspan="6" style="padding:6px 8px">'
            f'<strong style="font-size:12px">{label}</strong>'
            f'<span class="muted" style="font-size:11px;margin-left:10px">Actors: {actors_str}</span>'
            f'<span class="muted" style="font-size:11px;margin-left:10px">{n_phases} phase{"s" if n_phases != 1 else ""}</span>'
            f'</td></tr>'
        )

    index_parts = [
        '<table style="width:100%;font-size:11px">'
        '<thead><tr>'
        '<th style="text-align:left">Phase</th>'
        '<th colspan="3" style="text-align:left">Actors</th>'
        '<th style="text-align:right">Events</th>'
        '<th style="text-align:left">State</th>'
        '</tr></thead><tbody>'
    ]

    # Apply cleaned lineage labels to the Storm Index groups
    for lid, grp in lineage_index_groups.items():
        if lid in cleaned_lineages and 'canonical_name' in cleaned_lineages[lid]:
            grp['label'] = cleaned_lineages[lid]['canonical_name']

    for lid, grp in sorted(lineage_index_groups.items(),
                           key=lambda kv: -max((s.get('gravity_score', 0) for s in kv[1]['storms']), default=0)):
        # Count distinct phases for the header
        n_phases = len({_dh(s).split(' — ', 1)[1] for s in grp['storms'] if ' — ' in _dh(s)})
        index_parts.append(_lineage_header(grp['label'], grp['actor_set'], n_phases or len(grp['storms'])))
        index_parts.append(_phase_rows(grp['storms']))

    if unassigned:
        index_parts.append(
            f'<tr style="background:var(--line)">'
            f'<td colspan="6" style="padding:6px 8px">'
            f'<strong style="font-size:12px">Unassigned</strong>'
            f'<span class="muted" style="font-size:11px;margin-left:10px">{len(unassigned)} uncategorized</span>'
            f'</td></tr>'
        )
        index_parts.append(_phase_rows(unassigned))

    index_parts.append('</tbody></table>')
    vars['storm_index_html'] = ''.join(index_parts)
    vars['eco_storm_index_html'] = ''  # now merged into storm_index_html
    
    # Fill missing vars with defaults
    for i in range(1, 7):
        for key in ['name', 'visual_path', 'top_storm_headline', 'top_storm_state', 'top_storm_state_class',
                    'top_storm_events', 'top_storm_peak_ratio', 'top_storm_momentum', 'top_storm_acceleration',
                    'top_storm_coherence', 'top_storm_gravity', 'top_storm_one_liner', 'dominant_themes', 'domain_phrases', 'related_actors',
                    'drift', 'drift_class', 'shift_type', 'narrative_role', 'pressure', 'pressure_interp',
                    'has_evolution', 'evolution_text', 'additional_storms_html', 'evidence_html', 'community_html',
                    'momentum_score', 'momentum_class', 'momentum_explanation',
                    'top_storm_status', 'top_storm_status_class', 'top_storm_strength', 'window_comparison']:
            if f'actor_{i}_{key}' not in vars:
                vars[f'actor_{i}_{key}'] = 'N/A'
        for j in range(1, 6):
            if f'actor_{i}_event_{j}' not in vars:
                vars[f'actor_{i}_event_{j}'] = 'N/A'
    
    for i in range(1, 4):
        for key in ['headline', 'state', 'state_class', 'actors', 'events', 'momentum', 'accel', 'peak_ratio',
                    'drift', 'actor_entropy', 'one_liner', 'gravity', 'dominant_actors', 'domain_phrases', 'all_actors', 'evidence_html',
                    'pressure', 'pressure_interp']:
            if f'eco_{key}_{i}' not in vars:
                vars[f'eco_{key}_{i}'] = 'N/A'
        for j in range(1, 6):
            if f'eco_event_{i}_{j}' not in vars:
                vars[f'eco_event_{i}_{j}'] = 'N/A'
        for key in ['pair', 'score', 'theme', 'note']:
            if f'merge_{key}_{i}' not in vars:
                vars[f'merge_{key}_{i}'] = ''
        for key in ['', 'lag', 'theme', 'note']:
            if f'path_{key}_{i}' not in vars:
                vars[f'path_{key}_{i}'] = ''
    
    # Load template
    print("Loading template...")
    with open(template_path) as f:
        template = f.read()
    
    # Replace variables
    print("Generating report...")
    for key, value in vars.items():
        template = template.replace(f'{{{{ {key} }}}}', str(value))
    
    # Write output
    with open(output_path, 'w') as f:
        f.write(template)
    
    print(f"\n✓ Master report generated: {output_path}")
    print(f"  - Actor storms: {len(actor_storms)}")
    print(f"  - Ecosystem storms: {len(eco_storms)}")
    print(f"  - Propagation edges: {len(propagation_edges)}")
    print(f"  - Merge candidates: {len(merge_candidates)}")
    print(f"  - Trajectories: {len(trajectories)}")
    
    # Gravity score validation log
    print(f"\n=== Narrative Gravity Score — Top 10 ===")
    all_scored = sorted(all_storms_for_gravity, key=lambda s: -s.get('gravity_score', 0))
    for rank, storm in enumerate(all_scored[:10], 1):
        g = storm.get('gravity_components', {})
        formula = storm.get('gravity_formula', 'actor')
        label = _dh(storm, 50)
        actor = storm.get('actor', 'eco')
        entropy_str = f" entropy={g.get('actor_entropy', 0):.3f}" if formula == 'ecosystem' else ''
        print(f"  {rank:2}. [{actor}][{formula}] {label}")
        print(f"      gravity={storm['gravity_score']:.4f} | events={g.get('norm_event_count', 0):.3f} pressure={g.get('norm_pressure', 0):.3f} centrality={g.get('propagation_centrality', 0):.3f}{entropy_str} coherence={g.get('coherence_score', 0):.3f}")

    # Velocity validation log
    print(f"\n=== Narrative Velocity — All Storms ===")
    print(f"  {'storm_id':<35} {'type':<10} {'window':<6} {'anchor':<30} {'prev':>6} {'last':>6} {'score':>7} {'state':<14} {'confidence'}")
    for storm in sorted(all_storms_for_gravity, key=lambda s: -s.get('velocity_score', 0)):
        stype = 'ecosystem' if storm.get('storm_id', '').startswith('eco_') else 'actor'
        ref_ts = storm.get('velocity_reference_time', '')[:10]
        anchor = f"{storm.get('velocity_anchor_mode', '?')}({ref_ts})"
        print(f"  {storm['storm_id']:<35} {stype:<10} {storm.get('velocity_window', '?'):<6} {anchor:<30} "
              f"{storm.get('events_prev_48h', 0):>6} {storm.get('events_last_48h', 0):>6} "
              f"{storm.get('velocity_score', 0):>7.3f} {storm.get('velocity_state', 'N/A'):<14} {storm.get('velocity_confidence', 'N/A')}")

    # Priority bucket log
    print(f"\n=== Gravity × Velocity Priority Buckets ===")
    for stype, group in [('actor', actor_storms), ('ecosystem', eco_storms)]:
        bucket_counts = defaultdict(int)
        for s in group:
            bucket_counts[s.get('priority_bucket', 'low_gravity_low_velocity')] += 1
        print(f"  {stype} storms ({len(group)} total):")
        for bucket, label in [
            ('high_gravity_high_velocity', 'Act Now'),
            ('high_gravity_low_velocity',  'Important, Cooling'),
            ('low_gravity_high_velocity',  'Emerging Watch'),
            ('low_gravity_low_velocity',   'Background'),
        ]:
            print(f"    {label:<22} ({bucket}): {bucket_counts[bucket]}")

    # Confidence downgrade diagnostic
    downgraded = [
        s for s in all_storms_for_gravity
        if s.get('velocity_state') == 'accelerating'
        and not s.get('velocity_high_v')
    ]
    downgraded_actor = [s for s in downgraded if not s.get('storm_id', '').startswith('eco_')]
    downgraded_eco   = [s for s in downgraded if s.get('storm_id', '').startswith('eco_')]
    print(f"\n  Accelerating storms downgraded (insufficient confidence):")
    print(f"    actor: {len(downgraded_actor)}  ecosystem: {len(downgraded_eco)}")
    if downgraded:
        print(f"  {'storm_id':<35} {'type':<10} {'conf':<8} {'gravity':>7} {'velocity':>8} {'bucket'}")
        for s in sorted(downgraded, key=lambda s: -s.get('velocity_score', 0)):
            stype = 'ecosystem' if s.get('storm_id', '').startswith('eco_') else 'actor'
            print(f"  {s['storm_id']:<35} {stype:<10} {s.get('velocity_confidence','?'):<8} "
                  f"{s.get('gravity_score',0):>7.4f} {s.get('velocity_score',0):>8.3f} "
                  f"{s.get('priority_bucket','?')}")

    # Breakout candidate log
    breakout_actor = [s for s in actor_storms if s.get('is_breakout_candidate')]
    breakout_eco   = [s for s in eco_storms   if s.get('is_breakout_candidate')]
    breakout_all   = sorted(breakout_actor + breakout_eco,
                            key=lambda s: (-s.get('velocity_score', 0), -s.get('gravity_score', 0)))
    print(f"\n=== Breakout Candidates ===")
    print(f"  actor: {len(breakout_actor)}  ecosystem: {len(breakout_eco)}  total: {len(breakout_all)}")
    if breakout_all:
        print(f"  {'storm_id':<35} {'type':<10} {'gravity':>7} {'velocity':>8} {'conf':<8} {'priority_label'}")
        for s in breakout_all[:10]:
            stype = 'ecosystem' if s.get('storm_id', '').startswith('eco_') else 'actor'
            print(f"  {s['storm_id']:<35} {stype:<10} {s.get('gravity_score',0):>7.4f} "
                  f"{s.get('velocity_score',0):>8.3f} {s.get('velocity_confidence','?'):<8} "
                  f"{s.get('priority_label','?')}")

    # Ecosystem velocity label diagnostic
    print(f"\n=== Ecosystem Velocity Display Labels ===")
    print(f"  {'storm_id':<35} {'raw_state':<14} {'conf':<8} {'displayed'}")
    for s in eco_storms:
        raw  = s.get('velocity_state', 'stable')
        disp = displayed_velocity_state(s)
        marker = ' *' if disp != raw else '  '
        print(f"  {s['storm_id']:<35}{marker} {raw:<14} {s.get('velocity_confidence','?'):<8} {disp}")

    # Narrative lineage validation log
    total_in_lineage = sum(1 for s in all_storms_for_gravity if s.get('lineage_id'))
    avg_per_lineage  = (sum(r['lineage_storm_count'] for r in lineages_sorted) / len(lineages_sorted)
                        if lineages_sorted else 0)
    print(f"\n=== Narrative Lineage Aggregation ===")
    print(f"  Total lineages        : {len(lineages_sorted)}")
    print(f"  Storms in a lineage   : {total_in_lineage} / {len(all_storms_for_gravity)}")
    print(f"  Avg storms per lineage: {avg_per_lineage:.1f}")
    print(f"  Top 10 by gravity:")
    print(f"  {'lineage_id':<14} {'storms':>6} {'events':>7} {'actors':>7} {'gravity':>8} {'velocity':>9} {'days':>5} {'label'}")
    for rec in lineages_sorted[:10]:
        print(f"  {rec['lineage_id']:<14} {rec['lineage_storm_count']:>6} {rec['lineage_event_count']:>7} "
              f"{rec['lineage_actor_count']:>7} {rec['lineage_max_gravity']:>8.4f} "
              f"{rec['lineage_max_velocity']:>9.4f} {rec['lineage_duration_days']:>5} "
              f"{rec['label'][:50]}")
    # Storms-per-lineage distribution
    from collections import Counter as _Ctr
    size_dist = _Ctr(r['lineage_storm_count'] for r in lineages_sorted)
    print(f"  Storm count distribution:")
    for size in sorted(size_dist):
        print(f"    {size} storms: {size_dist[size]} lineage(s)")
    unassigned_count = sum(1 for s in all_storms_for_gravity if not s.get('lineage_id'))
    print(f"  Unassigned storms     : {unassigned_count}")

    # Narrative registry log
    print(f"\n=== Narrative Registry ===")
    print(f"  Registry path : {registry_path}")
    print(f"  Entries loaded          : {registry_load_stats['loaded']}")
    print(f"  Entries with centroid   : {registry_load_stats['with_centroid']}")
    print(f"  Entries missing centroid: {registry_load_stats['missing_centroid']}"
          + (" [centroid_missing=true — cosine similarity unavailable for these]" if registry_load_stats['missing_centroid'] else ""))
    print(f"  Total narratives in registry : {len(narratives)}")
    print(f"  Lineages processed this run  : {len(registry_match_log)}")
    created  = [e for e in registry_match_log if e['action'] == 'created']
    matched  = [e for e in registry_match_log if e['action'] == 'matched']
    rematched = [e for e in matched if e.get('already_seen')]
    scores   = [e['best_match_score'] for e in registry_match_log]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    print(f"  Matched existing narratives  : {len(matched)} ({len(rematched)} already seen, counts not re-added)")
    print(f"  Created new narratives       : {len(created)}")
    print(f"  Average best-match score     : {avg_score:.4f}")
    if registry_match_log:
        print(f"  {'lineage_id':<16} {'matched_or_created':<10} {'narrative_id':<22} {'best_match_id':<22} {'best_score':>10} {'storms':>6} {'vel_before':>10} {'vel_after':>9} {'inflection'}")
        for e in registry_match_log:
            vb = f"{e['velocity_before']:.4f}" if e['velocity_before'] is not None else '     N/A'
            va = f"{e['velocity_after']:.4f}"
            flag = ' *** INFLECTION' if e.get('velocity_inflection') else ''
            print(f"  {e['lineage_id']:<16} {e['matched_or_created']:<10} {e['narrative_id']:<22} {str(e['best_match_narrative_id']):<22} {e['best_match_score']:>10.4f} {e['storm_count']:>6} {vb:>10} {va:>9}{flag}")
    print(f"  Top narratives by gravity:")
    for n in sorted(narratives, key=lambda x: -x.get('max_gravity_score', 0))[:5]:
        print(f"    [{n['narrative_id']}] {n['narrative_label'][:55]}")
        print(f"      actors={n['actor_set']}  gravity={n['max_gravity_score']:.4f}  storms={n['total_storm_count']}  events={n['total_event_count']}")

    # Lead-lag alpha log
    print(f"\n=== Narrative Lead-Lag Alpha ===")
    print(f"  {'actor':<8} {'alpha_norm':>10} {'alpha_raw':>10} {'lead':>5} {'early':>6} {'late':>5} {'chains':>7} {'mean_pos':>9} {'interpretation'}")
    for r in lead_lag_results:
        print(f"  {r['actor']:<8} {r['lead_lag_alpha_normalized']:>10.4f} {r['lead_lag_alpha_raw']:>10.6f} "
              f"{r['lead_count']:>5} {r['early_count']:>6} {r['late_count']:>5} "
              f"{r['chains_appeared']:>7} {r['mean_chain_position']:>9.3f} {r['interpretation']}")

    # Phase map log
    print(f"\n=== Narrative Phase Map ===")
    print(f"  Storms plotted : {phase_map_result['plotted_count']}")
    print(f"  Quadrant distribution:")
    for q, c in sorted(phase_map_result['quadrant_counts'].items()):
        print(f"    {q:<25} {c}")
    print(f"  PNG : {phase_map_result['png_path']}")
    print(f"  SVG : {phase_map_result['svg_path']}")
    print(f"  Lineages plotted : {phase_map_lineages_result['plotted_count']}")
    print(f"  Lineage type counts:")
    for t, c in sorted(phase_map_lineages_result.get('type_counts', {}).items()):
        print(f"    {t:<12} {c}")
    if phase_map_lineages_result.get('eco_absent'):
        print(f"  NOTE: No ecosystem lineages in this window")
    print(f"  Lineage quadrant distribution:")
    for q, c in sorted(phase_map_lineages_result['quadrant_counts'].items()):
        print(f"    {q:<25} {c}")
    print(f"  Lineage PNG : {phase_map_lineages_result['png_path']}")
    print(f"  Lineage SVG : {phase_map_lineages_result['svg_path']}")

    # Retail amplification diagnostics
    print(f"\n=== Retail Amplification ===")
    amplified = [r for r in lineages_sorted if r.get('retail_event_count', 0) > 0]
    total_retail = sum(r.get('retail_event_count', 0) for r in lineages_sorted)
    print(f"  Lineages with retail amplification: {len(amplified)}/{len(lineages_sorted)}")
    print(f"  Total retail events attached: {total_retail}")
    for r in amplified:
        print(f"    {r['lineage_id']:<20} {r['retail_event_count']:>3} events  "
              f"ratio={r['retail_amplification_ratio']:.0%}  "
              f"mean_score={r.get('mean_retail_attach_score') or 'N/A'}  "
              f"{r['label']}")
    if not amplified:
        print(f"  None detected (run scripts/build_retail_amplification.py)")
    if retail_precision:
        p = retail_precision
        print(f"  Score histogram: "
              + '  '.join(f"{b}:{c}" for b, c in p.get('score_histogram', {}).items()))
        ao = p.get('actor_overlap', {})
        print(f"  Actor overlap: shared_1={ao.get('shared_1',0)}  shared_2+={ao.get('shared_2_plus',0)}")
        print(f"  Multi-candidate events: {p.get('multi_candidate_count', 0)}")
        c1, c3 = p.get('concentration_top1', 0), p.get('concentration_top3', 0)
        print(f"  Concentration: top1={c1:.0%}  top3={c3:.0%}")
    print(f"Ecosystem storms:")
    print(f"  Total loaded: {len(eco_storms)}")
    print(f"  Cross-actor featured: {len(cross_actor_storms)}")
    print(f"  Single-actor: {len(single_actor_storms)}")
    
    print(f"\nCoherence Diagnostics:")
    coherence_clustering = sum(1 for s in actor_storms if s.get('coherence_source') == 'clustering')
    coherence_fallback = sum(1 for s in actor_storms if s.get('coherence_source') == 'fallback')
    coherence_sparse = sum(1 for s in actor_storms if s.get('coherence_source') == 'sparse')
    print(f"  Clustering-based coherence: {coherence_clustering} storms")
    print(f"  Compactness fallback: {coherence_fallback} storms")
    print(f"  Sparse / N/A: {coherence_sparse} storms")
    
    coherence_high = sum(1 for s in actor_storms if s.get('coherence') is not None and s.get('coherence', 0) >= 0.60)
    coherence_mod = sum(1 for s in actor_storms if s.get('coherence') is not None and 0.40 <= s.get('coherence', 0) < 0.60)
    coherence_mixed = sum(1 for s in actor_storms if s.get('coherence') is not None and 0.25 <= s.get('coherence', 0) < 0.40)
    coherence_frag = sum(1 for s in actor_storms if s.get('coherence') is not None and s.get('coherence', 0) < 0.25)
    print(f"\nCoherence distribution:")
    print(f"  High (≥0.60): {coherence_high}")
    print(f"  Moderate (0.40-0.59): {coherence_mod}")
    print(f"  Mixed (0.25-0.39): {coherence_mixed}")
    print(f"  Fragmented (<0.25): {coherence_frag}")
    print(f"  N/A (sparse): {coherence_sparse}")
    
    print(f"\nDrift classification:")
    drift_stable = sum(1 for s in actor_storms if s.get('drift', 0) < 0.08)
    drift_gradual = sum(1 for s in actor_storms if 0.08 <= s.get('drift', 0) <= 0.20)
    drift_pivot = sum(1 for s in actor_storms if s.get('drift', 0) > 0.20)
    print(f"  Stable (<0.08): {drift_stable}")
    print(f"  Gradual evolution (0.08-0.20): {drift_gradual}")
    print(f"  Major pivots (>0.20): {drift_pivot}")
    
    print(f"\nShift type breakdown (storm-level):")
    from collections import Counter
    shift_counts_diag = Counter(s.get('shift_type', 'unclear') for s in _actor_storms_merged)
    for stype in ['stable', 'thematic_shift', 'market_noise_shift', 'mixed_shift', 'unclear']:
        print(f"  {stype}: {shift_counts_diag.get(stype, 0)}")
    
    print(f"\nFeatured actor storms (quality-based selection):")
    for i, (actor, _) in enumerate(top_actors, 1):
        storm_headline = vars.get(f'actor_{i}_top_storm_headline', 'N/A')[:50]
        coherence_val = [s.get('coherence') for s in actor_storms if s['actor'] == actor]
        coherence_str = f"{coherence_val[0]:.2f}" if coherence_val and coherence_val[0] is not None else "N/A"
        drift_val = [s.get('drift') for s in actor_storms if s['actor'] == actor]
        drift_str = f"{drift_val[0]:.3f}" if drift_val else "N/A"
        shift_val = [s.get('shift_type') for s in actor_storms if s['actor'] == actor]
        shift_str = shift_val[0] if shift_val else "unclear"
        print(f"  {actor}: {storm_headline} (coherence={coherence_str}, drift={drift_str}, shift={shift_str})")
    
    print(f"\nNarrative Pressure Diagnostics:")
    print(f"  High pressure: {len(high_pressure_deduped)} (deduped by actor)")
    print(f"  Building pressure: {len(building_pressure_deduped)} (deduped by actor)")
    print(f"  Low pressure: {len(all_pressure) - len(high_pressure_deduped) - len(building_pressure_deduped)}")
    for s, p in high_pressure_deduped[:3]:
        print(f"    High: {s.get('display_headline', s.get('headline', 'Unnamed'))[:50]} ({p['pressure_score']:.2f})")
    for s, p in building_pressure_deduped[:3]:
        print(f"    Building: {s.get('display_headline', s.get('headline', 'Unnamed'))[:50]} ({p['pressure_score']:.2f})")
    
    print(f"\nNarrative Leadership Diagnostics:")
    print(f"  Actors analyzed: {len(leadership_results)}")
    print(f"  Chains analyzed: {len(propagation_chains) if isinstance(propagation_chains, list) else 0}")
    print(f"  Leaders: {leader_actors or 'none'}")
    print(f"  Amplifiers: {amplifier_actors or 'none'}")
    print(f"  Bridges: {bridge_actors or 'none'}")
    print(f"  Receivers: {receiver_actors or 'none'}")
    if leadership_results:
        most_influential = max(leadership_results, key=lambda x: x['chains_participated'])
        print(f"  Most influential: {most_influential['actor']} ({most_influential['chains_participated']} chains)")
    if theme_leadership:
        print(f"  Theme-level roles: {len(theme_leadership)} themes")
    
    print(f"\nStrategic Watchlist Diagnostics (momentum-ranked):")
    print(f"  Lineages ranked : {len(watchlist_lineages_top)}")
    print(f"  {'lineage_id':<16} {'momentum':>8} {'score':>7} {'gravity':>8} {'pressure':<10} {'storms':>6} {'label'}")
    for r in watchlist_lineages_top:
        print(f"  {str(r['lineage_id']):<16} {r.get('lineage_max_momentum', 0):>8.1f} {r['lineage_score']:>7.4f} "
              f"{r['lineage_max_gravity']:>8.4f} {r['pressure_level']:<10} {r['storm_count']:>6} "
              f"{r['label'][:45]}")

    print(f"\n=== Market Interpretation ===")
    print(f"  {'label':<45} {'tag':<12} {'modifiers':<35} {'read_text'}")
    for rec in lineages_sorted:
        tag   = rec.get('market_state_tag', 'N/A')
        mods  = ', '.join(rec.get('market_modifiers', [])) or '—'
        text  = rec.get('market_read_text', '')
        print(f"  {rec['label'][:45]:<45} {tag:<12} {mods:<35} {text}")
    
    # Narrative momentum debug table
    print(f"\n=== Narrative Momentum Scores ===")
    print(f"  {'label':<55} {'score':>6} {'Δ':>5} {'class':<12} {'lead':>5} {'lead_cls':<10} {'narrative_state':<20} {'pl':>5} {'pt':>5} {'ea':>5} {'np':>5}")
    _all_merged = _actor_storms_merged + _eco_storms_merged
    _sorted_momentum = sorted(_all_merged, key=lambda s: -(s.get('momentum_score') or 0))
    for _s in _sorted_momentum:
        _hist = _s.get('_history', [])
        if not _hist:
            continue
        _row = momentum_debug_row(_s, _hist)
        _ns  = _s.get('narrative_state', '')
        print(f"  {_row['label']:<55} {_row['momentum_score']:>6.1f} {_row['momentum_delta']:>+5.0f}"
              f" {_row['momentum_class']:<12}"
              f" {_row['lead_score']:>5.1f} {_row['lead_class']:<10}"
              f" {_ns:<20}"
              f" {_row['pressure_level']:>5.1f} {_row['pressure_trend']:>5.1f}"
              f" {_row['event_acceleration']:>5.1f} {_row['noise_penalty']:>5.1f}")

    print(f"\nTo view: open {output_path} in a browser")
    print("To print to PDF: use browser's Print → Save as PDF")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset-narrative-registry', action='store_true',
                        help='Archive existing narrative registry and start fresh.')
    args = parser.parse_args()
    main(reset_registry=args.reset_narrative_registry)
