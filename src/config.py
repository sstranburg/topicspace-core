FIELD_ID = "tech_ecosystem"

ACTOR_ALIASES = {
    # Supply-side: chips & infrastructure
    "NVDA": ["nvidia", "nvda"],
    "AMD":  ["amd", "advanced micro devices"],
    "TSM":  ["tsmc", "taiwan semiconductor"],
    "ASML": ["asml"],
    "AVGO": ["broadcom", "avgo"],
    "ARM":  ["arm holdings", "arm chips", "arm architecture", "arm ltd"],
    "INTC": ["intel", "intc", "intel foundry", "intel arc"],
    "MU":   ["micron", " mu ", "dram", "nand flash", "hbm memory"],
    "MRVL": ["marvell", "marvell technology", "mrvl", "marvell semiconductor"],
    "SMCI": ["super micro", "supermicro", "smci"],
    "DELL": ["dell", "dell technologies", "dell server"],
    "VRT":  ["vertiv", "vrt "],
    "ANET": ["arista networks", "arista network", "anet "],
    "CEG":  ["constellation energy", "ceg "],
    "VST":  ["vistra", "vistra energy", "vst "],
    "SAMSNG": ["samsung", "samsung semiconductor", "samsung foundry", "samsung hbm"],
    "AAPL": ["apple", "aapl", "apple intelligence", "apple silicon", "apple ai"],
    # AI cloud / infra providers
    "CRWV": ["coreweave", "core weave", "gpu cloud"],
    "NBIS": ["nebius", "nebius ai", "nebius cloud"],
    "SKHX": ["sk hynix", "skhynix", "hynix"],  # SK Hynix — no US ticker, tracked by name
    # Hyperscalers
    "MSFT":  ["microsoft", "msft", "azure"],
    "AMZN":  ["amazon", "amzn", "aws"],
    "GOOGL": ["google", "googl", "alphabet", "gcp"],
    # AI demand-side
    "META": ["meta platforms", "meta ai", "facebook", "instagram", "llama", "meta "],
    "ORCL": ["oracle", "orcl"],
    "ADBE": ["adobe", "adbe"],
    "CRM":  ["salesforce", "crm "],
    "SNOW": ["snowflake"],
    "TSLA": ["tesla", "tsla"],
    # Enterprise AI software
    "PLTR": ["palantir", "pltr", "palantir aip"],
    "DDOG": ["datadog", "ddog"],
    "ZETA": ["zeta global", "zeta global holdings", "zeta cdp", "zeta marketing"],
    # Fintech / cross-sector
    "SOFI": ["sofi", "sofi technologies", "sofi bank"],
    # AI model labs (private companies — tracked by name only)
    "OPENAI":    ["openai", "chatgpt", "gpt-4", "gpt-5", "openai api"],
    "ANTHROPIC": ["anthropic", "claude ai", "anthropic claude"],
    # User-suggested — under observation
    "MP":   ["mp materials", "mp material", "rare earth", "rare-earth", " mp "],
    "USAR": ["usar", "u.s. army", "us army", "army reserve", "usar "],
}

TAG_KEYWORDS = {
    "ai_infra": ["ai infrastructure", "gpu", "tpu", "ai chip", "ai accelerator", "data center"],
    "advanced_packaging": ["cowos", "advanced packaging", "chiplet", "3d packaging"],
    "custom_silicon": ["custom silicon", "custom chip", "asic", "tpu"],
    "power_constraints": ["power", "energy efficiency", "data center power"],
    "inference_efficiency": ["inference", "inference efficiency"],
    "capex": ["capex", "capital expenditure", "spending"],
    "supply_chain": ["supply chain", "shortage", "capacity"]
}

import os

# ---------------------------------------------------------------------------
# Reddit classification rules
#
# Reddit is an overlay signal — useful for detecting early narrative formation,
# attention spikes, and spread. It is NOT structural confirmation.
#
# Bucket defaults when Reddit is the dominant source:
#   - Reddit-dominant + cross-source reinforcement  → BE_CAREFUL (at most)
#   - Reddit-dominant + no cross-source             → BE_CAREFUL or IGNORE
#   - Reddit-dominant + LOW reinforcement           → IGNORE (volume ≠ importance)
#   - Reddit-dominant + HIGH reinforcement          → BE_CAREFUL (never LEAN_IN alone)
#
# LEAN_IN requires cross-source confirmation.
# STEP_BACK requires prior structural weight — not applicable to pure Reddit volume.
# ---------------------------------------------------------------------------

# Threshold for treating a cluster as Reddit-dominant (% of events from reddit)
REDDIT_DOMINANT_PCT     = 70        # >= this pct → "Reddit-heavy"
REDDIT_CROSS_SRC_MIN    = 2         # minimum distinct source types to escape Reddit-only floor
REDDIT_RELIABILITY      = 0.50      # event-level reliability prior for Reddit events

# ---------------------------------------------------------------------------
# X (Twitter) classification rules
#
# X is a high-velocity, low-confidence signal layer — curated accounts only.
# It is faster than Reddit but structurally weaker than news.
#
# Weighting rules:
#   - X signals have LOWER weight than news and LOWER than Reddit
#   - X-dominant cluster → hard floor at STEP_BACK (cannot reach LEAN_IN alone)
#   - X-dominant + cross-source reinforcement → BE_CAREFUL (at most)
#   - X-dominant + LOW reinforcement → IGNORE
#   - Max classification without cross-source = STEP_BACK ("Explore")
#
# Use case: detect narrative formation 12–24h before news confirms.
#           Flag "X chatter increasing" when X event density spikes on a narrative.
# ---------------------------------------------------------------------------

X_DOMINANT_PCT      = 70        # >= this pct → "X-heavy" cluster
X_CROSS_SRC_MIN     = 2         # min distinct source types to escape X-only floor
X_RELIABILITY       = 0.45      # event-level reliability prior for X events (< Reddit)
X_MIN_LIKES         = 10        # minimum likes for an X event to be ingested

# Source reliability priors (higher = more trusted)
SOURCE_RELIABILITY: dict[str, float] = {
    "filing":         0.95,
    "transcript":     0.90,
    "newsapi":        0.75,
    "finnhub":        0.75,
    "cryptopanic":    0.65,
    "reddit":         0.50,
    "x":              0.45,
    "amplification":  0.30,
}

# ---------------------------------------------------------------------------
# Source tier system
#
# Three-tier model for news source classification:
#
#   primary      — direct, authoritative (earnings, filings, official releases)
#   validation   — institutional news with editorial standards (Reuters, Bloomberg)
#   amplification — secondary coverage that re-reports primary stories
#                   (Yahoo Finance, MarketWatch, Benzinga)
#
# Rules:
#   - Amplification sources CANNOT create new narrative clusters
#   - Amplification increases attention score slightly (+low weight to event count)
#   - Amplification does NOT increase narrative confidence
#   - Identical headlines across tiers: primary/validation version takes priority
#   - Amplification-dominant cluster (≥70%) → IGNORE unless primary/validation present
# ---------------------------------------------------------------------------

# Maps source name keyword → tier
# Used for source_name matching from metadata["source_name"]
SOURCE_TIER_KEYWORDS: dict[str, str] = {
    # Primary
    "sec":              "primary",
    "edgar":            "primary",
    "earnings":         "primary",
    "filing":           "primary",
    "transcript":       "primary",
    # Validation
    "reuters":          "validation",
    "bloomberg":        "validation",
    "wall street journal": "validation",
    "financial times":  "validation",
    "the information":  "validation",
    "techcrunch":       "validation",
    "axios":            "validation",
    # Amplification
    "yahoo":            "amplification",
    "marketwatch":      "amplification",
    "benzinga":         "amplification",
    "motley fool":      "amplification",
    "seeking alpha":    "amplification",
    "the street":       "amplification",
    "investopedia":     "amplification",
    "fool.com":         "amplification",
}

# Maps tier → event weight (used in attention scoring and confidence)
SOURCE_TIER_WEIGHT: dict[str, float] = {
    "primary":       1.0,
    "validation":    0.8,
    "amplification": 0.3,
    "community":     0.2,   # reddit, x
}

# Source type → tier (for the `source` field on Event, not source_name)
SOURCE_TYPE_TIER: dict[str, str] = {
    "filing":         "primary",
    "transcript":     "primary",
    "finnhub":        "validation",
    "newsapi":        "validation",   # default — overridden per article by source_name
    "cryptopanic":    "validation",
    "amplification":  "amplification",
    "reddit":         "community",
    "x":              "community",
}

AMPLIFICATION_DOMINANT_PCT = 70   # >= this pct amplification events → cluster is amplification-dominant

# LLM Naming Configuration
USE_LLM_NAMING = os.getenv('USE_LLM_NAMING', 'True').lower() == 'true'
LLM_NAMING_MODEL = os.getenv('LLM_NAMING_MODEL', 'gpt-4o-mini')
LLM_NAMING_MAX_STORMS = int(os.getenv('LLM_NAMING_MAX_STORMS', '20'))
LLM_NAMING_MIN_EVENT_COUNT = int(os.getenv('LLM_NAMING_MIN_EVENT_COUNT', '8'))
LLM_NAMING_MIN_CONFIDENCE = float(os.getenv('LLM_NAMING_MIN_CONFIDENCE', '0.65'))
