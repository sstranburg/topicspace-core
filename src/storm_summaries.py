from collections import Counter
import re

# Extended stopwords list
STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
    'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
    'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this',
    'that', 'these', 'those', 'it', 'its', 'they', 'their', 'them',
    'new', 'latest', 'report', 'says', 'analysis', 'about', 'after',
    'stock', 'stocks', 'today', 'now', 'just', 'more', 'than', 'what',
    'why', 'how', 'when', 'where', 'who', 'which', 'here', 'there'
}

# Weak descriptors to filter out
WEAK_DESCRIPTOR_WORDS = {
    'massive', 'major', 'huge', 'big', 'large', 'small', 'great', 'good',
    'platforms', 'platform', 'surge', 'surges', 'surging', 'soaring',
    'plunging', 'tumbling', 'rallying', 'rally', 'rallies', 'developments',
    'development', 'updates', 'update', 'news', 'moves', 'move', 'shift',
    'shifts', 'change', 'changes', 'trend', 'trends', 'activity', 'activities',
    # Weak standalone qualifiers that produce garbage like "High developments around X"
    'high', 'low', 'broad', 'significant', 'notable', 'increased', 'decreased',
    'various', 'multiple', 'recent', 'continued', 'ongoing',
}

# Publisher, media outlet, and brokerage names that should never become a storm's
# primary phrase. These appear as top bigrams/themes in analyst-heavy article titles
# and produce source-shaped names like "Wedbush developments around MSFT".
PUBLISHER_SOURCE_TERMS = frozenset({
    # Media / publications
    "motley", "fool", "cnbc", "bloomberg", "reuters",
    "seekingalpha", "seeking", "benzinga", "thestreet", "wsj", "barrons",
    # Brokerages / investment banks
    "wedbush", "hsbc", "rbc", "goldman", "sachs", "davidson",
    "zacks", "barclays", "morgan", "stanley", "jpmorgan", "citigroup",
    "jefferies", "bernstein", "piper", "sandler", "needham",
    "oppenheimer", "cantor", "cowen", "stifel", "raymond", "truist",
    "baird", "td", "mizuho", "dbs", "nomura", "bofa",
})


def _is_publisher_residue(phrase: str) -> bool:
    """True if phrase consists primarily of publisher/brokerage metadata."""
    words = phrase.lower().split()
    return bool(words) and any(w in PUBLISHER_SOURCE_TERMS for w in words)

# Domain-specific phrases (prioritized) - expanded lexicon
DOMAIN_PHRASES = [
    'ai chips', 'ai chip', 'ai models', 'ai infrastructure', 'ai compute',
    'ai training', 'ai inference', 'export controls', 'export restrictions',
    'custom silicon', 'semiconductor manufacturing', 'chip manufacturing',
    'foundry capacity', 'chip supply', 'gpu demand', 'gpu shortage',
    'data center', 'data centers', 'data center expansion', 'cloud infrastructure', 'cloud computing',
    'supply chain', 'supply chains', 'chip shortage', 'chip demand',
    'market share', 'market competition', 'revenue growth', 'earnings report', 'earnings reports',
    'product launch', 'product launches', 'partnership', 'partnerships',
    'partnership announcement', 'acquisition', 'acquisitions', 
    'regulatory', 'regulations', 'regulatory scrutiny', 'government restrictions',
    'legal challenge', 'legal dispute', 'tariffs', 'trade war', 'geopolitical', 'sanctions',
    'manufacturing expansion', 'capacity expansion', 'factory expansion'
]

# Action verbs for entity+action detection
ACTION_VERBS = [
    'launch', 'launches', 'launched', 'expand', 'expands', 'expanded', 'expanding',
    'sue', 'sues', 'sued', 'suing', 'partner', 'partners', 'partnered', 'partnering',
    'invest', 'invests', 'invested', 'investing', 'build', 'builds', 'built', 'building',
    'shift', 'shifts', 'shifted', 'shifting', 'restrict', 'restricts', 'restricted',
    'acquire', 'acquires', 'acquired', 'acquiring', 'announce', 'announces', 'announced',
    'develop', 'develops', 'developed', 'developing', 'release', 'releases', 'released'
]

# Actor names to treat as stopwords when excessive
ACTOR_NAMES = {'nvda', 'nvidia', 'amd', 'tsm', 'msft', 'microsoft', 'googl', 
               'google', 'alphabet', 'amzn', 'amazon', 'asml', 'meta', 'tesla'}


def extract_key_terms(titles, top_n=5, actors=None):
    """Extract most common meaningful terms from titles."""
    # Combine all titles
    text = ' '.join(titles).lower()
    
    # Remove punctuation
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    
    # Extract words
    words = text.split()
    
    # Filter stop words, short words, and excessive actor names
    actor_set = set()
    if actors:
        for actor in actors:
            actor_set.add(actor.lower())
    
    meaningful_words = []
    actor_count = Counter()
    
    for w in words:
        if len(w) <= 2:
            continue
        if w in STOPWORDS:
            continue
        if w in ACTOR_NAMES:
            actor_count[w] += 1
            # Allow actor names once, but not repeatedly
            if actor_count[w] <= 1:
                meaningful_words.append(w)
        else:
            meaningful_words.append(w)
    
    # Count frequencies
    word_counts = Counter(meaningful_words)
    
    # Return top N
    return [word for word, count in word_counts.most_common(top_n)]


def extract_entity_actions(titles, actors):
    """Extract entity+action patterns from titles."""
    patterns = []
    text = ' '.join(titles).lower()
    
    # Look for action verbs
    for verb in ACTION_VERBS:
        if verb in text:
            # Try to construct meaningful patterns
            if 'partner' in verb:
                patterns.append('partnership')
            elif 'sue' in verb or 'sued' in verb:
                patterns.append('legal dispute')
            elif 'expand' in verb:
                patterns.append('expansion')
            elif 'launch' in verb:
                patterns.append('launch')
            elif 'invest' in verb:
                patterns.append('investment')
            elif 'build' in verb or 'built' in verb:
                patterns.append('buildout')
            elif 'acquire' in verb:
                patterns.append('acquisition')
            elif 'announce' in verb:
                patterns.append('disclosure')
    
    # Remove duplicates while preserving order
    seen = set()
    unique_patterns = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique_patterns.append(p)
    
    return unique_patterns


def extract_domain_phrases(titles):
    """Extract domain-specific phrases from titles."""
    text = ' '.join(titles).lower()
    found_phrases = []
    for phrase in DOMAIN_PHRASES:
        if phrase in text:
            found_phrases.append(phrase)
    return found_phrases


def extract_bigrams(titles, min_freq=2):
    """Extract important bigrams from titles, filtering weak descriptors."""
    # Combine all titles
    text = ' '.join(titles).lower()
    
    # Remove punctuation
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    
    # Extract words
    words = text.split()
    
    # Filter stop words, short words, and weak descriptors
    filtered_words = [w for w in words 
                      if w not in STOPWORDS 
                      and w not in WEAK_DESCRIPTOR_WORDS
                      and len(w) > 2]
    
    # Extract bigrams
    bigrams = []
    for i in range(len(filtered_words) - 1):
        bigram = f"{filtered_words[i]} {filtered_words[i+1]}"
        # Reject if either word is weak descriptor
        words_in_bigram = bigram.split()
        if not any(w in WEAK_DESCRIPTOR_WORDS for w in words_in_bigram):
            bigrams.append(bigram)
    
    # Count frequencies
    bigram_counts = Counter(bigrams)
    
    # Return bigrams with frequency >= min_freq
    return [bigram for bigram, count in bigram_counts.most_common(10) if count >= min_freq]


_GENERIC_ACTION_PHRASES = {"product launch", "announcement", "prediction", "launch", "disclosure"}

def generate_headline(themes, bigrams, domain_phrases, entity_actions, actors):
    """Generate clean analyst-style headline using actor-aware templates."""
    # Priority: domain_phrases > entity_actions > bigrams > themes.
    # Publisher/source residue is filtered from all candidate lists before selection.
    # Generic action wrappers (announcement, product launch, prediction) are also filtered
    # — they name the event type, not the narrative.

    def _clean(lst):
        """Remove publisher residue and weak standalone qualifiers from candidate list."""
        return [
            p for p in (lst or [])
            if not _is_publisher_residue(p)
            and not (len(p.split()) == 1 and p.lower() in WEAK_DESCRIPTOR_WORDS)
        ]

    clean_domain  = _clean(domain_phrases)
    # Strip generic action wrappers that produce clunky headlines
    clean_actions = [p for p in _clean(entity_actions) if p.lower() not in _GENERIC_ACTION_PHRASES]
    clean_bigrams = _clean(bigrams)
    clean_themes  = _clean(themes)

    # Select primary phrase from cleaned candidates
    if clean_domain:
        primary   = clean_domain[0]
        secondary = clean_domain[1] if len(clean_domain) > 1 else None
    elif clean_actions:
        primary   = clean_actions[0]
        secondary = clean_actions[1] if len(clean_actions) > 1 else None
    elif clean_bigrams:
        primary   = clean_bigrams[0]
        secondary = clean_bigrams[1] if len(clean_bigrams) > 1 else None
    elif clean_themes:
        primary   = clean_themes[0]
        secondary = clean_themes[1] if len(clean_themes) > 1 else None
    else:
        primary = None
        secondary = None
    
    # Format actors
    if not actors:
        actor_str = "tech ecosystem"
        actor_count = 0
    elif len(actors) == 1:
        actor_str = actors[0]
        actor_count = 1
    elif len(actors) == 2:
        actor_str = f"{actors[0]} and {actors[1]}"
        actor_count = 2
    else:
        actor_str = f"{actors[0]}, {actors[1]}, and {actors[2]}"
        actor_count = 3
    
    # No phrases available
    if not primary:
        return f"Market activity involving {actor_str}"
    
    # Actor-aware templates with improved grammar
    primary_title = primary.title()
    
    if actor_count == 1:
        # Single actor templates
        if primary in ['partnership', 'legal dispute', 'expansion', 'acquisition', 'investment']:
            return f"{primary_title} involving {actor_str}"
        elif primary in ['buildout']:
            return f"{primary_title} narrative around {actor_str}"
        else:
            return f"{primary_title} narrative around {actor_str}"
    
    elif actor_count == 2:
        # Two actor templates - emphasize relationships
        if primary in ['partnership', 'legal dispute']:
            return f"{primary_title} between {actors[0]} and {actors[1]}"
        elif secondary:
            return f"{primary_title} and {secondary} dynamics between {actors[0]} and {actors[1]}"
        else:
            return f"{primary_title} dynamics between {actors[0]} and {actors[1]}"
    
    else:
        # Multiple actors
        if primary in ['expansion', 'buildout']:
            return f"{primary_title} across {actor_str}"
        elif primary in ['partnership', 'legal dispute']:
            return f"{primary_title} involving {actor_str}"
        else:
            return f"{primary_title} pressure around {actor_str}"


def generate_one_liner(state, state_reason, themes, bigrams, domain_phrases, entity_actions, actors):
    """Generate structured one-liner based on state."""
    # Get primary phrase (priority: domain > entity_actions > bigrams > themes)
    if domain_phrases:
        phrase = domain_phrases[0]
    elif entity_actions:
        phrase = entity_actions[0]
    elif bigrams:
        phrase = bigrams[0]
    elif themes:
        phrase = themes[0]
    else:
        phrase = "market activity"
    
    # Format actors
    if not actors:
        actor_str = "tech ecosystem"
    elif len(actors) == 1:
        actor_str = actors[0]
    elif len(actors) == 2:
        actor_str = f"{actors[0]} and {actors[1]}"
    else:
        actor_str = f"{actors[0]}, {actors[1]}, and others"
    
    # State-based templates with stronger phrase insertion
    if state == 'emerging':
        return f"Developing {phrase} narrative involving {actor_str}."
    elif state == 'growing':
        return f"Rapidly intensifying {phrase} narrative across {actor_str}."
    elif state == 'peaking':
        return f"Peak market attention on {phrase} with high event density."
    elif state == 'fading':
        if 'drop_from_peak' in state_reason:
            return f"Previously dominant {phrase} narrative now declining."
        else:
            return f"Declining {phrase} activity involving {actor_str}."
    elif state == 'volatile':
        return f"Rapidly shifting {phrase} narrative with high semantic drift."
    else:  # stable
        return f"Sustained {phrase} narrative involving {actor_str}."


def compute_summary_confidence(themes, bigrams, domain_phrases, entity_actions, weak_terms_removed, clustering_info=None):
    """Compute confidence score for summary quality.
    
    Args:
        themes: List of key terms
        bigrams: List of bigrams
        domain_phrases: List of domain phrases
        entity_actions: List of entity actions
        weak_terms_removed: Count of filtered weak terms
        clustering_info: Optional dict with clustering metrics
    
    Returns:
        float confidence score [0, 1]
    """
    # Score based on phrase quality
    score = 0.0
    
    # Domain phrases are highest quality
    score += len(domain_phrases) * 0.3
    
    # Entity actions are high quality
    score += len(entity_actions) * 0.25
    
    # Bigrams are medium quality
    score += len(bigrams) * 0.2
    
    # Single terms are lower quality
    score += len(themes) * 0.1
    
    # Penalty for weak terms removed
    score -= weak_terms_removed * 0.05
    
    # Clustering quality boost
    if clustering_info and clustering_info.get('used_topic_clustering'):
        dominance_ratio = clustering_info.get('cluster_dominance_ratio', 0)
        
        # Boost for strong dominant cluster (>0.7)
        if dominance_ratio > 0.7:
            score += 0.1
        # Smaller boost for moderate dominance (0.5-0.7)
        elif dominance_ratio > 0.5:
            score += 0.05
        # Penalty for weak dominance (<0.4)
        elif dominance_ratio < 0.4:
            score -= 0.05
    
    # Normalize to [0, 1]
    confidence = min(1.0, max(0.0, score))
    return round(confidence, 2)


def generate_storm_summary(storm, trajectory=None, title_embeddings_map=None, use_clustering=True, use_llm_naming=False):
    """Generate human-readable summary for a storm.
    
    Args:
        storm: Storm object with representative_titles, cluster_titles_topN, actors, tags, etc.
        trajectory: Optional trajectory object with state, momentum, etc.
        title_embeddings_map: Optional dict mapping title -> embedding for clustering
        use_clustering: Whether to use topic clustering (default True)
        use_llm_naming: Whether to use LLM naming (default False)
    
    Returns:
        dict with headline, one_liner, themes, actors, tags, confidence, clustering info, LLM info
    """
    # Extract display titles (top 3 for backward compatibility)
    display_titles = [e['title'] for e in storm.get('representative_events', [])] if 'representative_events' in storm else storm.get('representative_titles', [])
    if not display_titles:
        display_titles = ['Unnamed storm']
    
    actors = storm.get('actors', [])
    if isinstance(actors, list) and actors:
        actor_list = actors
    else:
        actor_list = [actors] if actors else []
    
    # Apply topic clustering if enabled and embeddings available
    clustering_info = {
        'used_topic_clustering': False,
        'num_title_clusters': 1,
        'dominant_cluster_size': len(display_titles),
        'cluster_dominance_ratio': 1.0,
        'cluster_titles_count': len(display_titles),
        'clustering_eligible': False
    }
    
    titles = display_titles  # Default: use display titles
    
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
        else:
            clustering_info['clustering_eligible'] = cluster_result.get('clustering_eligible', False)
            clustering_info['cluster_titles_count'] = cluster_result.get('cluster_titles_count', len(display_titles))
    
    # Extract domain phrases first (highest priority)
    domain_phrases = extract_domain_phrases(titles)
    
    # Extract entity+action patterns
    entity_actions = extract_entity_actions(titles, actor_list)
    
    # Extract themes and bigrams
    themes_raw = extract_key_terms(titles, top_n=6, actors=actor_list)
    bigrams = extract_bigrams(titles, min_freq=2)
    
    # Filter weak descriptors from themes
    themes = [t for t in themes_raw if t not in WEAK_DESCRIPTOR_WORDS]
    weak_terms_removed = len(themes_raw) - len(themes)
    
    # Generate headline
    headline = generate_headline(themes, bigrams, domain_phrases, entity_actions, actor_list)
    
    # Get state information
    state = trajectory.get('state', 'stable') if trajectory else 'stable'
    state_reason = trajectory.get('state_reason', '') if trajectory else ''
    
    # Generate one-liner
    one_liner = generate_one_liner(state, state_reason, themes, bigrams, domain_phrases, entity_actions, actor_list)
    
    # Compute confidence with clustering boost
    confidence = compute_summary_confidence(themes, bigrams, domain_phrases, entity_actions, weak_terms_removed, clustering_info)
    
    # Extract tags
    tags = storm.get('tags', [])
    if not tags:
        tags = []
    
    result = {
        'storm_id': storm.get('storm_id', 'unknown'),
        'headline': headline,
        'one_liner': one_liner,
        'themes': themes[:3],  # Top 3 themes
        'bigrams': bigrams[:2],  # Top 2 bigrams
        'domain_phrases': domain_phrases[:2],  # Top 2 domain phrases
        'entity_actions': entity_actions[:2],  # Top 2 entity actions
        'actors': actor_list,
        'tags': tags,
        'event_count': storm.get('event_count', 0),
        'state': state,
        'summary_confidence': confidence,
        'representative_title': display_titles[0] if display_titles else None,
        'weak_terms_removed': weak_terms_removed
    }
    
    # Add clustering info
    result.update(clustering_info)
    
    # Apply LLM naming if enabled
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
        
        # Check eligibility
        eligible = (
            storm.get('event_count', 0) >= LLM_NAMING_MIN_EVENT_COUNT
            and (clustering_info.get('used_topic_clustering') 
                 or 'developments' in headline.lower() 
                 or confidence < 0.90)
        )
        
        if eligible:
            # Build evidence
            evidence = build_naming_evidence(result, trajectory)
            llm_info['naming_evidence'] = evidence
            
            # Generate LLM name
            llm_result = generate_llm_name(evidence)
            llm_info.update(llm_result)
            
            # Validate if LLM succeeded
            if llm_result['llm_used'] and llm_result['llm_headline']:
                # Basic validation
                valid, reason, rejection_reasons = validate_llm_label(
                    llm_result['llm_headline'],
                    llm_result['llm_one_liner'],
                    headline
                )
                llm_info['llm_validation_passed'] = valid
                llm_info['llm_validation_reason'] = reason
                llm_info['llm_rejection_reasons'] = rejection_reasons
                
                # Faithfulness validation
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
                    llm_info['llm_faithfulness_reason'] = None
    
    result.update(llm_info)
    
    # Set display fields with tie-breaking logic
    if llm_info['llm_validation_passed'] and llm_info['llm_faithful']:
        result['display_headline'] = llm_info['llm_headline']
        result['display_one_liner'] = llm_info['llm_one_liner']
        result['display_source'] = 'llm'
    else:
        result['display_headline'] = headline
        result['display_one_liner'] = one_liner
        result['display_source'] = 'heuristic'
    
    return result


def generate_trajectory_summary(trajectory):
    """Generate summary for a trajectory across its lifecycle."""
    # Get state history
    state_history = trajectory.get('state_history', [])
    
    # Describe lifecycle
    if not state_history:
        lifecycle_desc = "No state history available"
    elif len(state_history) == 1:
        lifecycle_desc = f"Remained {state_history[0]}"
    else:
        # Simplify history by removing consecutive duplicates
        simplified = [state_history[0]]
        for state in state_history[1:]:
            if state != simplified[-1]:
                simplified.append(state)
        
        lifecycle_desc = " → ".join(simplified)
    
    # Get metrics
    total_events = trajectory.get('total_events', 0)
    max_density = trajectory.get('max_density_seen', 0)
    peak_ratio = trajectory.get('peak_ratio', 1.0)
    latest_momentum = trajectory.get('latest_momentum', 0)
    
    # Build summary
    summary = {
        'trajectory_id': trajectory.get('trajectory_id', 'unknown'),
        'actor': trajectory.get('actor', 'unknown'),
        'lifecycle': lifecycle_desc,
        'total_events': total_events,
        'max_density': max_density,
        'current_density': trajectory.get('latest_density', 0),
        'peak_ratio': round(peak_ratio, 2),
        'momentum': latest_momentum,
        'state': trajectory.get('state', 'unknown'),
        'state_reason': trajectory.get('state_reason', 'unknown')
    }
    
    # Add interpretation
    if peak_ratio < 0.3:
        summary['interpretation'] = "Significantly declined from peak"
    elif peak_ratio < 0.7:
        summary['interpretation'] = "Moderately declined from peak"
    elif peak_ratio >= 0.95:
        summary['interpretation'] = "At or near peak"
    else:
        summary['interpretation'] = "Slightly below peak"
    
    return summary
