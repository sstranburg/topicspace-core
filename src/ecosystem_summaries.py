"""Generate narrative summaries for ecosystem storms."""

from src.storm_summaries import (
    extract_key_terms, extract_bigrams, extract_domain_phrases,
    extract_entity_actions, compute_summary_confidence, WEAK_DESCRIPTOR_WORDS
)

def generate_ecosystem_headline(themes, bigrams, domain_phrases, entity_actions, actors, num_actors):
    """Generate ecosystem-level headline."""
    # Priority: domain_phrases > entity_actions > bigrams > themes
    if domain_phrases:
        primary = domain_phrases[0]
    elif entity_actions:
        primary = entity_actions[0]
    elif bigrams:
        primary = bigrams[0]
    elif themes:
        primary = themes[0]
    else:
        primary = "market activity"
    
    primary_title = primary.title()
    
    # Format actors
    n = len(actors)
    if n == 0:
        actor_str = "tech ecosystem"
    elif n == 1:
        actor_str = actors[0]
    elif n == 2:
        actor_str = f"{actors[0]} and {actors[1]}"
    elif n == 3:
        actor_str = f"{actors[0]}, {actors[1]}, and {actors[2]}"
    else:
        actor_str = f"{actors[0]}, {actors[1]}, {actors[2]}, and {n - 3} others"
    
    # Ecosystem-aware templates
    if num_actors == 1:
        # Single actor - use actor-style template
        return f"{primary_title} narrative around {actor_str}"
    elif num_actors == 2:
        # Two actors - emphasize relationship
        if primary in ['partnership', 'legal dispute']:
            return f"{primary_title} between {actors[0]} and {actors[1]}"
        else:
            return f"{primary_title} across {actors[0]} and {actors[1]}"
    else:
        # Multiple actors - ecosystem-level
        if primary in ['ai chip', 'ai chips', 'ai infrastructure']:
            return f"{primary_title} demand across {actor_str}"
        elif primary in ['export controls', 'export restrictions']:
            return f"{primary_title} pressure across {actor_str}"
        elif primary in ['custom silicon', 'chip manufacturing']:
            return f"{primary_title} competition across {actor_str}"
        else:
            return f"{primary_title} narrative across {actor_str}"


def generate_ecosystem_one_liner(state, themes, bigrams, domain_phrases, actors, num_actors):
    """Generate ecosystem-level one-liner."""
    # Get primary phrase
    if domain_phrases:
        phrase = domain_phrases[0]
    elif bigrams:
        phrase = bigrams[0]
    elif themes:
        phrase = themes[0]
    else:
        phrase = "market activity"
    
    # Format actors
    if len(actors) <= 2:
        actor_str = " and ".join(actors) if actors else "ecosystem players"
    elif len(actors) == 3:
        actor_str = f"{actors[0]}, {actors[1]}, and {actors[2]}"
    else:
        actor_str = f"{actors[0]}, {actors[1]}, {actors[2]}, and {len(actors) - 3} others"
    
    # State-based templates
    if state == 'emerging':
        return f"Emerging {phrase} narrative across {actor_str}."
    elif state == 'growing':
        return f"Rapidly intensifying {phrase} narrative across {actor_str}."
    elif state == 'peaking':
        return f"Peak ecosystem attention on {phrase} involving {actor_str}."
    elif state == 'fading':
        return f"Declining {phrase} narrative across {actor_str}."
    elif state == 'volatile':
        return f"Rapidly shifting {phrase} narrative across {actor_str}."
    else:  # stable
        return f"Sustained {phrase} narrative across {actor_str}."


def generate_ecosystem_storm_summary(storm, trajectory=None, title_embeddings_map=None, use_clustering=True, use_llm_naming=False):
    """Generate summary for an ecosystem storm.
    
    Args:
        storm: Ecosystem storm dict
        trajectory: Optional trajectory dict
        title_embeddings_map: Optional dict for clustering
        use_clustering: Whether to use topic clustering
        use_llm_naming: Whether to use LLM naming
    
    Returns:
        dict with headline, one_liner, themes, actors, etc.
    """
    # Extract titles
    display_titles = storm.get('cluster_titles_topN', [])
    if not display_titles:
        display_titles = [e['title'] for e in storm.get('representative_events', [])]
    if not display_titles:
        display_titles = ['Unnamed ecosystem storm']
    
    actors = storm.get('dominant_actors', [])
    num_actors = storm.get('num_unique_actors', 0)
    
    # Apply topic clustering if enabled
    clustering_info = {
        'used_topic_clustering': False,
        'num_title_clusters': 1,
        'dominant_cluster_size': len(display_titles),
        'cluster_dominance_ratio': 1.0,
        'cluster_titles_count': len(display_titles),
        'clustering_eligible': False
    }
    
    titles = display_titles
    
    if use_clustering and title_embeddings_map:
        from src.storm_topic_clustering import get_dominant_topic_titles
        cluster_result = get_dominant_topic_titles(storm, title_embeddings_map)
        
        if cluster_result['used_clustering']:
            titles = cluster_result['dominant_titles']
            clustering_info = {
                'used_topic_clustering': True,
                'num_title_clusters': cluster_result['num_clusters'],
                'dominant_cluster_size': cluster_result['dominant_cluster_size'],
                'cluster_dominance_ratio': cluster_result['cluster_dominance_ratio'],
                'cluster_titles_count': cluster_result['cluster_titles_count'],
                'clustering_eligible': True,
                'dominant_cluster_terms': cluster_result.get('dominant_cluster_terms', []),
                'dominant_cluster_bigrams': cluster_result.get('dominant_cluster_bigrams', [])
            }
    
    # Extract phrases
    domain_phrases = extract_domain_phrases(titles)
    entity_actions = extract_entity_actions(titles, actors)
    themes_raw = extract_key_terms(titles, top_n=6, actors=actors)
    bigrams = extract_bigrams(titles, min_freq=2)
    
    # Filter weak descriptors
    themes = [t for t in themes_raw if t not in WEAK_DESCRIPTOR_WORDS]
    weak_terms_removed = len(themes_raw) - len(themes)
    
    # Generate headline
    headline = generate_ecosystem_headline(themes, bigrams, domain_phrases, entity_actions, actors, num_actors)
    
    # Get state
    state = trajectory.get('state', 'stable') if trajectory else 'stable'
    
    # Generate one-liner
    one_liner = generate_ecosystem_one_liner(state, themes, bigrams, domain_phrases, actors, num_actors)
    
    # Compute confidence
    confidence = compute_summary_confidence(themes, bigrams, domain_phrases, entity_actions, weak_terms_removed, clustering_info)
    
    result = {
        'storm_id': storm.get('storm_id', 'unknown'),
        'headline': headline,
        'one_liner': one_liner,
        'themes': themes[:3],
        'bigrams': bigrams[:2],
        'domain_phrases': domain_phrases[:2],
        'entity_actions': entity_actions[:2],
        'actors': actors,
        'num_unique_actors': num_actors,
        'all_actors_involved': storm.get('actors_involved', []),
        'dominant_actor_ratio': storm.get('dominant_actor_ratio', 0),
        'actor_entropy': storm.get('actor_entropy', 0),
        'event_count': storm.get('event_count', 0),
        'state': state,
        'summary_confidence': confidence,
        'representative_title': display_titles[0] if display_titles else None,
        'weak_terms_removed': weak_terms_removed
    }
    
    # Add clustering info
    result.update(clustering_info)
    
    # LLM naming (if enabled)
    llm_info = {
        'llm_headline': None,
        'llm_one_liner': None,
        'llm_used': False,
        'llm_error': None,
        'llm_validation_passed': False,
        'llm_validation_reason': None,
        'llm_rejection_reasons': [],
        'llm_faithful': False,
        'llm_faithfulness_reason': None,
        'naming_evidence': None,
        'display_source': 'heuristic'
    }
    
    if use_llm_naming:
        from src.config import LLM_NAMING_MIN_EVENT_COUNT
        from src.llm_naming import build_naming_evidence, generate_llm_name, validate_llm_label, validate_llm_label_faithfulness
        
        eligible = (
            storm.get('event_count', 0) >= LLM_NAMING_MIN_EVENT_COUNT
            and (clustering_info.get('used_topic_clustering') 
                 or 'developments' in headline.lower() 
                 or confidence < 0.90)
        )
        
        if eligible:
            evidence = build_naming_evidence(result, trajectory)
            llm_info['naming_evidence'] = evidence
            
            llm_result = generate_llm_name(evidence)
            llm_info.update(llm_result)
            
            if llm_result['llm_used'] and llm_result['llm_headline']:
                valid, reason, rejection_reasons = validate_llm_label(
                    llm_result['llm_headline'],
                    llm_result['llm_one_liner'],
                    headline
                )
                llm_info['llm_validation_passed'] = valid
                llm_info['llm_validation_reason'] = reason
                llm_info['llm_rejection_reasons'] = rejection_reasons
                
                if valid:
                    faithful, faith_reason, faith_rejection = validate_llm_label_faithfulness(
                        llm_result['llm_headline'],
                        evidence
                    )
                    llm_info['llm_faithful'] = faithful
                    llm_info['llm_faithfulness_reason'] = faith_reason
                    
                    if not faithful:
                        llm_info['llm_validation_passed'] = False
                        llm_info['llm_validation_reason'] = faith_reason
                        llm_info['llm_rejection_reasons'].extend(faith_rejection)
                else:
                    llm_info['llm_faithful'] = False
    
    result.update(llm_info)
    
    # Set display fields
    if llm_info['llm_validation_passed'] and llm_info['llm_faithful']:
        result['display_headline'] = llm_info['llm_headline']
        result['display_one_liner'] = llm_info['llm_one_liner']
        result['display_source'] = 'llm'
    else:
        result['display_headline'] = headline
        result['display_one_liner'] = one_liner
        result['display_source'] = 'heuristic'
    
    return result
