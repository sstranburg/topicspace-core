"""
Narrative lane classification for events.

Separates market/investor coverage from technical AI coverage and policy news
so storms remain thematically coherent during clustering.

Priority order: policy > tech > market > default
"""

MARKET_KEYWORDS = [
    "stock", "shares", "analyst", "upgrade", "downgrade",
    "buy", "sell", "valuation", "price target", "market cap",
    "earnings", "investor", "trades",
]

TECH_KEYWORDS = [
    "gpu", "cuda", "cluster", "training", "ai chip",
    "hbm", "datacenter", "inference", "compute",
    "architecture", "gtc", "model",
    "supercomputer", "ai infrastructure", "ai compute",
    "training cluster", "model training", "accelerator",
    "ai system", "ai platform", "foundation model",
    "machine learning", "deep learning", "processor",
    "semiconductor", "chiplet", "fabrication", "wafer",
]

POLICY_KEYWORDS = [
    "export", "ban", "sanction", "regulation",
    "china", "restriction",
]

CORPORATE_KEYWORDS = [
    "deal", "partnership", "collaboration", "investment",
    "joint venture", "agreement", "stake", "acquisition",
    "strategic alliance", "funding",
]


def classify_narrative_lane(text: str) -> str:
    """Classify event text into a narrative lane.

    Args:
        text: Combined event title + body text.

    Returns:
        One of: "policy", "tech", "corporate", "market", "default"
    """
    lower = text.lower()

    if any(kw in lower for kw in POLICY_KEYWORDS):
        return "policy"
    if any(kw in lower for kw in TECH_KEYWORDS):
        return "tech"
    if any(kw in lower for kw in CORPORATE_KEYWORDS):
        return "corporate"
    if any(kw in lower for kw in MARKET_KEYWORDS):
        return "market"
    return "default"
