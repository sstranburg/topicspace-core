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
    # AI model labs (private companies — tracked by name only)
    "OPENAI":    ["openai", "chatgpt", "gpt-4", "gpt-5", "openai api"],
    "ANTHROPIC": ["anthropic", "claude ai", "anthropic claude"],
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

# Source reliability priors (higher = more trusted)
SOURCE_RELIABILITY: dict[str, float] = {
    "filing":       0.95,
    "transcript":   0.90,
    "newsapi":      0.75,
    "finnhub":      0.75,
    "cryptopanic":  0.65,
    "reddit":       0.50,
}

# LLM Naming Configuration
USE_LLM_NAMING = os.getenv('USE_LLM_NAMING', 'True').lower() == 'true'
LLM_NAMING_MODEL = os.getenv('LLM_NAMING_MODEL', 'gpt-4o-mini')
LLM_NAMING_MAX_STORMS = int(os.getenv('LLM_NAMING_MAX_STORMS', '20'))
LLM_NAMING_MIN_EVENT_COUNT = int(os.getenv('LLM_NAMING_MIN_EVENT_COUNT', '8'))
LLM_NAMING_MIN_CONFIDENCE = float(os.getenv('LLM_NAMING_MIN_CONFIDENCE', '0.65'))
