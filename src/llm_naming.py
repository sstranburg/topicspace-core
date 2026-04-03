import json
import os
from pydantic import BaseModel
from dotenv import load_dotenv

import openai

load_dotenv()

SPECULATIVE_WORDS = {'likely', 'could', 'may', 'might', 'possibly', 'perhaps', 'probably'}
GENERIC_PHRASES = {'developments', 'activity', 'market activity', 'trends', 'updates', 'news', 'moves'}
FORBIDDEN_INTERPRETIVE_PHRASES = {
    'focus on', 'strategy', 'conviction', 'market presence', 'positioning',
    'outlook', 'thesis', 'wall street concerns overblown', 'sleeping giant',
    'bull case', 'backed up the truck', 'bear case', 'hidden gem'
}

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


class NarrativeLabel(BaseModel):
    headline: str
    one_liner: str


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

    if storm_summary.get('representative_title'):
        evidence['representative_titles'].append(storm_summary['representative_title'])

    return evidence


def build_naming_prompt(evidence):
    """Build LLM prompt for storm naming. Domain-agnostic."""
    state = evidence.get('state', 'stable')
    dominance = evidence.get('dominant_cluster_ratio', 1.0)

    state_guidance = {
        'fading':   'Use language like "fading narrative", "declining attention", "narrative losing momentum"',
        'growing':  'Use language like "growing narrative", "accelerating interest", "expanding narrative"',
        'peaking':  'Use language like "high-attention narrative", "peak narrative", "intense focus"',
        'volatile': 'Use language like "unstable narrative", "shifting narrative", "volatile attention"',
        'emerging': 'Use language like "emerging narrative", "developing attention", "new narrative"',
        'stable':   'Use language like "sustained narrative", "steady attention", "ongoing narrative"',
    }

    if dominance < 0.40:
        coherence_guidance = "The cluster has LOW coherence. Use broad labels that capture the mixed themes present."
    elif dominance < 0.60:
        coherence_guidance = "The cluster has MODERATE coherence. Use theme + subject labels like 'Export-control narrative around X'."
    else:
        coherence_guidance = "The cluster has HIGH coherence. You may use specific labels like 'Rating-upgrade narrative around X'."

    prompt = f"""You are naming a narrative cluster from news/event data.

IMPORTANT RULES:
1. Name the NARRATIVE, not the entity's strategy or intent
2. Stay close to the evidence provided — do not invent themes
3. Do NOT infer intent or strategy from the subject
4. Do NOT over-index on one title unless it clearly dominates
5. Labels must be understandable without domain context
6. Labels must work across any industry or topic — not just technology

AVOID these phrases:
- "focus on", "strategy", "conviction", "positioning", "market presence"
- "outlook", "thesis"
- Speculative words: "likely", "could", "may", "might"
- Generic: "developments", "activity", "trends", "updates", "news"

PREFER narrative-style phrasing:
- "[theme] narrative around [subject]"
- "[theme] pressure on [subject]"
- "[theme] demand for [subject]"
- "[theme] between [subject1] and [subject2]"

STATE GUIDANCE ({state}):
{state_guidance.get(state, '')}

COHERENCE GUIDANCE:
{coherence_guidance}

Based on the evidence below, produce:
1. A short narrative label (4-10 words)
2. A one-sentence explanation (plain language, no jargon)

Evidence:
{json.dumps(evidence, indent=2)}
"""
    return prompt


def generate_llm_name(evidence):
    """Generate narrative label using OpenAI structured output."""
    try:
        from src.config import LLM_NAMING_MODEL

        client = _get_client()
        prompt = build_naming_prompt(evidence)

        response = client.beta.chat.completions.parse(
            model=LLM_NAMING_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
            response_format=NarrativeLabel,
        )

        label = response.choices[0].message.parsed
        return {
            'llm_headline': label.headline,
            'llm_one_liner': label.one_liner,
            'llm_used': True,
            'llm_error': None,
        }

    except Exception as e:
        return {
            'llm_headline': None,
            'llm_one_liner': None,
            'llm_used': False,
            'llm_error': str(e),
        }


def validate_llm_label(llm_headline, llm_one_liner, heuristic_headline):
    """Validate LLM output quality."""
    if not llm_headline or not llm_one_liner:
        return False, "Empty output", []

    rejection_reasons = []
    headline_lower = llm_headline.lower()

    word_count = len(llm_headline.split())
    if word_count < 4 or word_count > 12:
        return False, f"Headline length {word_count} words (expected 4-12)", ['length']

    for phrase in GENERIC_PHRASES:
        if phrase in headline_lower:
            rejection_reasons.append('generic_phrase')
            return False, f"Contains generic phrase: {phrase}", rejection_reasons

    for phrase in FORBIDDEN_INTERPRETIVE_PHRASES:
        if phrase in headline_lower:
            rejection_reasons.append('forbidden_phrase')
            return False, f"Contains forbidden interpretive phrase: {phrase}", rejection_reasons

    for word in SPECULATIVE_WORDS:
        if word in headline_lower:
            rejection_reasons.append('speculative')
            return False, f"Contains speculative word: {word}", rejection_reasons

    return True, None, rejection_reasons


def validate_llm_label_faithfulness(llm_headline, evidence):
    """Validate LLM headline faithfulness to evidence. Domain-agnostic."""
    headline_lower = llm_headline.lower()
    rejection_reasons = []

    # Build evidence term set from the cluster itself — no hardcoded domain terms
    evidence_terms = set()

    for actor in evidence.get('actors', []):
        evidence_terms.add(actor.lower())

    for theme in evidence.get('themes', []):
        evidence_terms.add(theme.lower())

    for phrase in evidence.get('domain_phrases', []):
        evidence_terms.update(phrase.lower().split())

    for action in evidence.get('entity_actions', []):
        evidence_terms.update(action.lower().split())

    for bigram in evidence.get('bigrams', []):
        evidence_terms.update(bigram.lower().split())

    for term in evidence.get('dominant_cluster_terms', []):
        evidence_terms.add(term.lower())

    for bigram in evidence.get('dominant_cluster_bigrams', []):
        evidence_terms.update(bigram.lower().split())

    for title in evidence.get('representative_titles', []):
        evidence_terms.update(title.lower().split())

    # Require at least 2 meaningful overlapping terms
    common_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were',
    }
    headline_words = set(headline_lower.split())
    meaningful_overlap = (headline_words & evidence_terms) - common_words

    min_overlap = 1 if len(evidence.get('representative_titles', [])) <= 2 else 2
    if len(meaningful_overlap) < min_overlap:
        rejection_reasons.append('low_overlap')
        return False, f"Low overlap with evidence (only {len(meaningful_overlap)} terms)", rejection_reasons

    # Check for capitalized words not traceable to evidence or generic narrative vocabulary
    import re
    narrative_vocab = {
        'narrative', 'pressure', 'demand', 'expansion', 'partnership', 'rating',
        'upgrade', 'downgrade', 'attention', 'momentum', 'fading', 'growing',
        'peaking', 'emerging', 'stable', 'volatile', 'declining', 'rising',
        'accelerating', 'intensifying', 'sustained', 'mixed', 'broad', 'around',
    }
    # Build known-actor set from the evidence itself
    known_from_evidence = {a.lower() for a in evidence.get('actors', [])}
    for title in evidence.get('representative_titles', []):
        known_from_evidence.update(title.lower().split())

    for cap_word in re.findall(r'\b[A-Z][a-z]+\b', llm_headline):
        word_lower = cap_word.lower()
        if word_lower in narrative_vocab or word_lower in known_from_evidence or word_lower in evidence_terms:
            continue
        rejection_reasons.append('introduced_entity')
        return False, f"Introduced unsupported entity: {cap_word}", rejection_reasons

    return True, None, rejection_reasons
