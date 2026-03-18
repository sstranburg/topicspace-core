from src.config import ACTOR_ALIASES, TAG_KEYWORDS


def detect_actors(text: str) -> list[str]:
    """Detect actors in text using lowercase substring matching."""
    text_lower = text.lower()
    detected = []
    
    for actor, aliases in ACTOR_ALIASES.items():
        for alias in aliases:
            if alias in text_lower:
                detected.append(actor)
                break
    
    return sorted(list(set(detected)))


def detect_tags(text: str) -> list[str]:
    """Detect theme tags in text using lowercase substring matching."""
    text_lower = text.lower()
    detected = []
    
    for tag, keywords in TAG_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                detected.append(tag)
                break
    
    return sorted(list(set(detected)))
