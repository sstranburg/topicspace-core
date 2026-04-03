"""
Curated X (Twitter) account lists for AI/tech and crypto signal ingestion.

Keep to 50–150 accounts per domain.
Focus: researchers, operators, investors with market-relevant signal.
Exclude: retail meme accounts, pure price commentary, high-noise personalities.

Expand these lists over time. Do NOT add accounts that post primarily about
personal life, politics unrelated to the domain, or price speculation.
"""

# ── AI / Tech ecosystem ──────────────────────────────────────────────────────
# Covers: model labs, hyperscalers, chips, infrastructure, enterprise AI

AI_ACCOUNTS: list[str] = [
    # Lab founders / researchers
    "sama",             # Sam Altman (OpenAI)
    "demishassabis",    # Demis Hassabis (Google DeepMind)
    "ylecun",           # Yann LeCun (Meta AI)
    "gdb",              # Greg Brockman (OpenAI)
    "karpathy",         # Andrej Karpathy (ex-OpenAI/Tesla)
    "fchollet",         # François Chollet (Keras)
    "drfeifei",         # Fei-Fei Li (Stanford HAI)
    "DarioAmodei",      # Dario Amodei (Anthropic CEO)
    "miramurati",       # Mira Murati (ex-OpenAI CTO)
    "aidan_gomez",      # Aidan Gomez (Cohere CEO)
    "ClementDelangue",  # Clément Delangue (HuggingFace CEO)
    "AndrewYNg",        # Andrew Ng (DeepLearning.AI)
    "kaifulee",         # Kai-Fu Lee (01.AI)
    # Operators / execs
    "satyanadella",     # Satya Nadella (Microsoft CEO)
    "sundarpichai",     # Sundar Pichai (Google CEO)
    "JensenHuang",      # Jensen Huang (Nvidia CEO)
    "lisamsu",          # Lisa Su (AMD CEO)
    "elonmusk",         # Elon Musk (xAI / Tesla)
    # Investors
    "paulg",            # Paul Graham (YC)
    "naval",            # Naval Ravikant
    "garrytan",         # Garry Tan (YC president)
    "pmarca",           # Marc Andreessen (a16z)
    "bgurley",          # Bill Gurley (Benchmark)
    "chamath",          # Chamath Palihapitiya
    "jason",            # Jason Calacanis (All-In)
    "rabois",           # Keith Rabois
    # Research / analysis
    "emollick",         # Ethan Mollick (Wharton AI)
    "benedictevans",    # Benedict Evans (tech analyst)
    "NathanBenaich",    # Nathan Benaich (State of AI)
    "semianalysis",     # Dylan Patel (SemiAnalysis)
    "PatrickMoorhead",  # Patrick Moorhead (chip/cloud analyst)
    # Institutional media (use as signal, not source)
    "TechCrunch",       # Tech news signal
    "TheInformation",   # Premium tech media
    "wired",            # Tech media
    # AI commentary
    "ai_explained_",    # AI news commentary
    "GaryMarcus",       # Gary Marcus (AI skeptic — counterforce signal)
    "timnitGebru",      # Timnit Gebru (AI ethics — regulatory signal)
]

# ── Crypto ecosystem ─────────────────────────────────────────────────────────
# Covers: BTC, ETH, SOL, DeFi, AI-crypto crossover, macro

CRYPTO_ACCOUNTS: list[str] = [
    # Protocol founders / builders
    "VitalikButerin",   # Ethereum founder
    "aeyakovenko",      # Anatoly Yakovenko (Solana co-founder)
    "brian_armstrong",  # Brian Armstrong (Coinbase CEO)
    "saylor",           # Michael Saylor (Strategy / BTC)
    "jack",             # Jack Dorsey (Block / BTC)
    # Research / analysis
    "hasufl",           # Hasu (MEV, crypto macro researcher)
    "nic__carter",      # Nic Carter (BTC researcher, Castle Island)
    "twobitidiot",      # Ryan Selkis (Messari CEO)
    "cburniske",        # Chris Burniske (Placeholder VC)
    "WClementeIII",     # Will Clemente (BTC on-chain)
    "woonomic",         # Willy Woo (BTC on-chain)
    "TuurDemeester",    # Tuur Demeester (BTC macro)
    "CryptoQuant_CEO",  # Ki Young Ju (CryptoQuant)
    # Investors
    "RaoulGMI",         # Raoul Pal (Real Vision — macro crypto)
    "AriDavidPaul",     # Ari Paul (BlockTower Capital CIO)
    "novogratz",        # Mike Novogratz (Galaxy Digital)
    "KyleSamani",       # Kyle Samani (Multicoin Capital)
    "CaitlinLong_",     # Caitlin Long (Custodia Bank — BTC/regulation)
    "Matthew_Sigel",    # Matthew Sigel (VanEck digital assets)
    "danheld",          # Dan Held (BTC — useful for narrative formation)
    "ErikVoorhees",     # Erik Voorhees (ShapeShift)
    # Analytics / data
    "glassnode",        # Glassnode (on-chain analytics)
    "IntoTheBlock",     # IntoTheBlock (market analytics)
    "MessariCrypto",    # Messari (institutional signal)
    # Media / institutional
    "CoinDesk",         # CoinDesk (institutional crypto news)
    "TheBlock__",       # The Block (institutional crypto news)
    "laurashin",        # Laura Shin (Unchained podcast)
    "nlw",              # Nathaniel Whittemore (Breakdown podcast)
    # Macro context
    "zhusu",            # Zhu Su (3AC — contrarian/macro signal)
    "100trillionUSD",   # PlanB (BTC S2F — popular narrative anchor)
]
