import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SPECULATIVE_WORDS = {'likely', 'could', 'may', 'might', 'possibly', 'perhaps', 'probably'}
GENERIC_PHRASES = {'developments', 'activity', 'market activity', 'trends', 'updates', 'news', 'moves'}
FORBIDDEN_INTERPRETIVE_PHRASES = {
    'focus on', 'strategy', 'conviction', 'market presence', 'positioning', 
    'outlook', 'thesis', 'wall street concerns overblown', 'sleeping giant',
    'bull case', 'backed up the truck', 'bear case', 'hidden gem'
}

# API Configuration
API_URL = "https://api.openai.com"
API_KEY = os.getenv("OPENAI_API_KEY")

def build_naming_evidence(storm_summary, trajectory_summary=None):
    """Build compact evidence bundle for LLM naming."""
    evidence = {
        'storm_id': storm_summary.get('storm_id'),
        'actors': storm_summary.get('actors', []),
        'state': storm_summary.get('state', 'stable'),
        'event_count': storm_summary.get('event_count', 0),
        'dominant_cluster_ratio': storm_summary.get('cluster_dominance_ratio', 1.0),
        'themes': storm_summary.get('themes', []),
        'bigrams': storm_summary.get('bigrams', []),
        'domain_phrases': storm_summary.get('domain_phrases', []),
        'entity_actions': storm_summary.get('entity_actions', []),
        'dominant_cluster_terms': storm_summary.get('dominant_cluster_terms', []),
        'dominant_cluster_bigrams': storm_summary.get('dominant_cluster_bigrams', []),
        'representative_titles': [],
        'all_titles_count': storm_summary.get('cluster_titles_count', 0)
    }
    
    # Add representative title
    if storm_summary.get('representative_title'):
        evidence['representative_titles'].append(storm_summary['representative_title'])
    
    return evidence

def build_naming_prompt(evidence):
    """Build LLM prompt for storm naming."""
    state = evidence.get('state', 'stable')
    dominance = evidence.get('dominant_cluster_ratio', 1.0)
    
    # State-aware guidance
    state_guidance = {
        'fading': 'Use language like "fading narrative", "declining attention", "narrative losing momentum"',
        'growing': 'Use language like "growing narrative", "accelerating demand", "expanding narrative"',
        'peaking': 'Use language like "high-attention narrative", "peak narrative", "intense focus"',
        'volatile': 'Use language like "unstable narrative", "shifting narrative", "volatile attention"',
        'emerging': 'Use language like "emerging narrative", "developing attention", "new narrative"',
        'stable': 'Use language like "sustained narrative", "steady attention", "ongoing narrative"'
    }
    
    # Coherence-based guidance
    if dominance < 0.40:
        coherence_guidance = "The cluster has LOW coherence. Use broader labels like 'Mixed AI-chip narrative' or 'Broad semiconductor narrative'."
    elif dominance < 0.60:
        coherence_guidance = "The cluster has MODERATE coherence. Use theme + actor labels like 'Export-control narrative around X'."
    else:
        coherence_guidance = "The cluster has HIGH coherence. You may use more specific labels like 'Rating-upgrade narrative around X'."
    
    prompt = f"""You are naming a narrative cluster from market/news data.

IMPORTANT RULES:
1. Name the NARRATIVE/STORM, not the company strategy
2. Stay close to the dominant cluster evidence provided
3. Do NOT infer company intent or strategy
4. Do NOT over-index on one article title unless it clearly dominates
5. Attach state to the storm, not the company

AVOID these unsupported phrases:
- "focus on", "strategy", "conviction", "positioning", "market presence"
- "outlook", "thesis", "Wall Street concerns overblown"
- Speculative words: "likely", "could", "may", "might"

PREFER narrative-style phrasing:
- "[theme] narrative around [actor]"
- "[theme] pressure on [actor]"
- "[theme] demand around [actor]"
- "[theme] partnership between [actor1] and [actor2]"

STATE GUIDANCE ({state}):
{state_guidance.get(state, '')}

COHERENCE GUIDANCE:
{coherence_guidance}

Do not base the label on a single title unless the cluster is highly coherent (ratio >= 0.60) and the same theme appears repeatedly.

Based on the evidence below, produce:
1. A short narrative label (5-10 words)
2. A one-sentence explanation

Evidence:
"""
    prompt += json.dumps(evidence, indent=2)
    prompt += "\n\nRespond in JSON format:\n{\"headline\": \"...\", \"one_liner\": \"...\"}"
    
    return prompt

def generate_llm_name(evidence):
    """Generate LLM-based storm name."""
    try:
        from src.config import LLM_NAMING_MODEL
        
        prompt = build_naming_prompt(evidence)
        
        response = requests.post(
            f"{API_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": LLM_NAMING_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"}
            },
            timeout=30
        )
        
        # Check for error response
        if response.status_code != 200:
            error_detail = response.text
            return {
                'llm_headline': None,
                'llm_one_liner': None,
                'llm_used': False,
                'llm_error': f"{response.status_code}: {error_detail[:200]}"
            }
        
        data = response.json()
        content = data['choices'][0]['message']['content']
        result = json.loads(content)
        
        return {
            'llm_headline': result.get('headline'),
            'llm_one_liner': result.get('one_liner'),
            'llm_used': True,
            'llm_error': None
        }
    
    except Exception as e:
        return {
            'llm_headline': None,
            'llm_one_liner': None,
            'llm_used': False,
            'llm_error': str(e)
        }

def validate_llm_label(llm_headline, llm_one_liner, heuristic_headline):
    """Validate LLM output quality."""
    if not llm_headline or not llm_one_liner:
        return False, "Empty output", []
    
    rejection_reasons = []
    
    # Check headline length
    word_count = len(llm_headline.split())
    if word_count < 4 or word_count > 12:
        return False, f"Headline length {word_count} words (expected 4-12)", ['length']
    
    # Check for generic phrases
    headline_lower = llm_headline.lower()
    for phrase in GENERIC_PHRASES:
        if phrase in headline_lower:
            rejection_reasons.append('generic_phrase')
            return False, f"Contains generic phrase: {phrase}", rejection_reasons
    
    # Check for forbidden interpretive phrases
    for phrase in FORBIDDEN_INTERPRETIVE_PHRASES:
        if phrase in headline_lower:
            rejection_reasons.append('forbidden_phrase')
            return False, f"Contains forbidden interpretive phrase: {phrase}", rejection_reasons
    
    # Check for speculative words
    for word in SPECULATIVE_WORDS:
        if word in headline_lower:
            rejection_reasons.append('speculative')
            return False, f"Contains speculative word: {word}", rejection_reasons
    
    # Check for repeated actor names
    words = llm_headline.lower().split()
    actor_words = [w for w in words if w in {'nvda', 'nvidia', 'amd', 'tsm', 'msft', 'microsoft', 'googl', 'google', 'amzn', 'amazon', 'asml', 'avgo', 'broadcom'}]
    if len(actor_words) > 2:
        rejection_reasons.append('actor_repetition')
        return False, "Too many actor name repetitions", rejection_reasons
    
    return True, None, rejection_reasons


def validate_llm_label_faithfulness(llm_headline, evidence):
    """Validate LLM headline faithfulness to evidence."""
    headline_lower = llm_headline.lower()
    rejection_reasons = []
    
    # Extract all evidence terms
    evidence_terms = set()
    
    # Add actors
    for actor in evidence.get('actors', []):
        evidence_terms.add(actor.lower())
    
    # Add themes
    for theme in evidence.get('themes', []):
        evidence_terms.add(theme.lower())
    
    # Add domain phrases
    for phrase in evidence.get('domain_phrases', []):
        evidence_terms.update(phrase.lower().split())
    
    # Add entity actions
    for action in evidence.get('entity_actions', []):
        evidence_terms.update(action.lower().split())
    
    # Add bigrams
    for bigram in evidence.get('bigrams', []):
        evidence_terms.update(bigram.lower().split())
    
    # Add dominant cluster terms
    for term in evidence.get('dominant_cluster_terms', []):
        evidence_terms.add(term.lower())
    
    # Add dominant cluster bigrams
    for bigram in evidence.get('dominant_cluster_bigrams', []):
        evidence_terms.update(bigram.lower().split())
    
    # Check for overlap
    headline_words = set(headline_lower.split())
    overlap = headline_words & evidence_terms
    
    # Require at least 2 overlapping terms (excluding common words)
    common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were'}
    meaningful_overlap = overlap - common_words
    
    if len(meaningful_overlap) < 2:
        rejection_reasons.append('low_overlap')
        return False, f"Low overlap with evidence (only {len(meaningful_overlap)} terms)", rejection_reasons
    
    # Check for introduced entities not in evidence
    # Extract potential company names (capitalized words)
    import re
    capitalized = re.findall(r'\b[A-Z][a-z]+\b', llm_headline)
    known_actors = {'nvidia', 'amd', 'tsm', 'tsmc', 'microsoft', 'google', 'alphabet', 'amazon', 'asml', 'broadcom', 'avgo', 'meta', 'tesla', 'marvell', 'intel'}
    state_words = {'fading', 'growing', 'peaking', 'emerging', 'stable', 'volatile', 'declining', 'rising', 'accelerating', 'intensifying'}
    common_descriptors = {'narrative', 'pressure', 'demand', 'expansion', 'partnership', 'rating', 'upgrade', 'downgrade', 'focus', 'attention', 'momentum'}
    
    for cap_word in capitalized:
        word_lower = cap_word.lower()
        
        # Skip if it's a known actor, state word, or common descriptor
        if word_lower in known_actors or word_lower in state_words or word_lower in common_descriptors:
            continue
        
        # Skip if it's in evidence terms
        if word_lower in evidence_terms:
            continue
        
        # Check if it's in the representative titles
        found_in_titles = False
        for title in evidence.get('representative_titles', []):
            if cap_word.lower() in title.lower():
                found_in_titles = True
                break
        
        if not found_in_titles:
            rejection_reasons.append('introduced_entity')
            return False, f"Introduced unsupported entity: {cap_word}", rejection_reasons
    
    return True, None, rejection_reasons
