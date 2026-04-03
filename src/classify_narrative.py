"""
classify_narrative.py — Shared Narrative Compass classification spine.

Provides for both AI and crypto ecosystems:
  - CompassEntry, CompassClassification  Pydantic models (shared output schema)
  - build_system_prompt(ecosystem)        ecosystem-specific LLM prompt
  - _attention_level(n)                   LOW / MEDIUM / HIGH from event count
  - post_process_classify_results(...)    shared + ecosystem-specific overrides
  - render_compass_text / render_compass_json   shared render functions

Design principle:
  All ecosystems use the same base model (attention × reinforcement × momentum)
  and output the same public structure. Only the classification thresholds and
  source-weighting rules differ by ecosystem.
"""

import json
from typing import Literal
from pydantic import BaseModel


# ── Shared models ──────────────────────────────────────────────────────────────

class CompassEntry(BaseModel):
    narrative: str
    summary: str
    action: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class CompassClassification(BaseModel):
    lean_in:    list[CompassEntry]
    step_back:  list[CompassEntry]
    be_careful: list[CompassEntry]
    ignore:     list[CompassEntry]


# ── Shared utility ─────────────────────────────────────────────────────────────

def _attention_level(n: int) -> str:
    return "HIGH" if n > 20 else ("MEDIUM" if n >= 5 else "LOW")


# ── Prompt: shared base ────────────────────────────────────────────────────────

_ROLE = """\
ROLE

You are a narrative classification engine, not an analyst.

Your job is to:
1. Interpret pre-clustered event groups as narratives
2. Score each narrative using fixed rules
3. Assign a classification:
   - LEAN_IN
   - STEP_BACK
   - BE_CAREFUL
   - IGNORE

You must be:
- consistent
- decisive
- non-verbose

Do NOT explain reasoning.
Do NOT hedge.
Do NOT restate inputs.\
"""

_VALIDATE = """\
STEP 1 — VALIDATE NARRATIVE

Before scoring, determine:

Is this a real narrative or just grouped events?

A valid narrative must:
- express one clear shared idea
- be directionally consistent
- not be a generic topic (e.g. "AI stocks moving" or "Bitcoin news")

If not a real narrative:
→ classify as IGNORE\
"""

_SCORE = """\
STEP 2 — SCORE EACH NARRATIVE

1. Attention Score (event_count)
- LOW: <5
- MEDIUM: 5–20
- HIGH: >20

2. Reinforcement Score (consistency of idea)
Estimate % of events expressing the same idea:
- HIGH: >60%
- MEDIUM: 30–60%
- LOW: <30%

If events conflict → LOW

3. Momentum Score (direction over time)
- RISING: strong increase in recent window
- FALLING: clear decrease
- FLAT: otherwise\
"""

_SOURCE_BASE = """\
STEP 3 — APPLY SOURCE CONTEXT

Interpret source quality:

High-trust sources:
- earnings transcripts
- filings
- official announcements
- major news

Mid-trust:
- curated aggregators
- industry publications

Low-trust:
- reddit
- social chatter

Very low-trust:
- x (Twitter/X curated accounts)
  - high-velocity, low-confidence
  - useful for detecting early narrative formation 12–24h before news confirms
  - cannot independently produce LEAN_IN
  - X-dominant cluster → hard floor at STEP_BACK
  - X-dominant + no cross-source confirmation → IGNORE if reinforcement is LOW

Amplification tier (Yahoo Finance, MarketWatch, Benzinga, Motley Fool, Seeking Alpha):
- secondary sources that re-report stories from primary/validation sources
- CANNOT independently create new narrative clusters
- increase attention score only slightly (weight = 0.3 vs primary = 1.0)
- do NOT increase narrative confidence
- amplification-dominant cluster (≥70% amplification events) → IGNORE
  unless primary or validation events are also present
- when primary + amplification present: use primary for confidence scoring,
  use amplification event count as "widely covered" attention breadth signal only
- "widely covered" = ≥3 amplification sources confirming the same narrative

Source rules:
- A low-trust-dominant cluster alone is not sufficient for LEAN_IN
- Cross-source reinforcement (multiple source types agreeing) increases confidence
- A small number of high-trust events can outweigh large low-trust volume
- X events raise early detection speed but do NOT raise classification ceiling
- Amplification events increase breadth signal but do NOT raise confidence ceiling\
"""

_CLASSIFY_BASE = """\
STEP 4 — CLASSIFY (STRICT RULES)

LEAN_IN:
- Attention = MEDIUM or HIGH
- Reinforcement = HIGH
- Momentum = RISING or very recently peaked
- AND not dominated by low-trust sources alone

STEP_BACK:
- Attention = HIGH
- Reinforcement = LOW
- Momentum = FLAT or FALLING
- AND narrative had prior structural weight (not pure chatter volume)

BE_CAREFUL:

Case A — Fragmented:
- Attention = MEDIUM or HIGH
- Reinforcement = LOW

Case B — Transition:
- Attention = LOW → MEDIUM
- Reinforcement = MEDIUM
- Momentum = RISING

Case C — Early structural signal:
- Strong high-trust events
- But not yet widely reinforced

IGNORE:
- Attention = LOW
- OR not a real narrative (generic topic grouping)
- OR dominated by low-signal chatter
- OR ambiguous / unclear → IGNORE is the DEFAULT when in doubt

The bar for avoiding IGNORE must be cleared by concrete evidence.
Produce fewer signals. Prefer 3 well-classified narratives over 8 marginal ones.\
"""

_CONFIDENCE = """\
STEP 5 — CONFIDENCE

Assign:

HIGH:
- strong reinforcement
- multiple sources
- sufficient data

MEDIUM:
- partial reinforcement
- moderate data

LOW:
- weak data
- early or unclear signal\
"""

_SHARED_CONSTRAINTS = """\
HARD CONSTRAINTS (ALL ECOSYSTEMS)

- If momentum = FALLING → cannot be LEAN_IN
- If reinforcement = LOW → cannot be LEAN_IN
- If insufficient_data = true → cannot be LEAN_IN
- If unclear or ambiguous → IGNORE is the default (not BE_CAREFUL)
- If cluster is X-dominant (source = "x" accounts for ≥70% of events) → cannot be LEAN_IN
- If cluster is X-only (no cross-source confirmation from news/reddit/filings) → max STEP_BACK
- If cluster is amplification-dominant (source = "amplification" for ≥70% of events)
  AND no primary or validation events present → classify as IGNORE (amplification alone
  cannot form a new narrative; it only confirms one already established elsewhere)
- Amplification events NEVER raise a classification above what primary/validation events support\
"""

_WRITING_STYLE = """\
WRITING STYLE (CRITICAL)

- Max 12 words per summary
- 1 sentence per field
- No jargon
- No metrics
- No explanation of scoring
- No uncertainty language ("might", "possibly")

Use:
- concrete phrasing
- clear descriptors ("institutional flows", "conflicting narratives", "retail panic")

Avoid:
- "interest is fading"
- "momentum declining"
- "this suggests"

The "action" field must be a plain imperative sentence telling the reader what to do.
Examples: "Pay close attention.", "Skip this.", "Wait before acting.", "Watch for confirmation."
Do NOT use the classification name (LEAN_IN, BE_CAREFUL, etc.) as the action.\
"""

_GOAL = """\
GOAL

The output must be understandable in under 5 seconds.

It must feel like a decision, not analysis.\
"""


# ── Prompt: ecosystem-specific addendums ──────────────────────────────────────

_AI_RULES = """\
ECOSYSTEM: AI TECH — SPECIFIC RULES

AI narratives are more institutionally structured than crypto.
Source quality carries more weight here than event count.

AI SOURCE HIERARCHY (most to least trusted):
1. Earnings transcripts, management guidance, filings
2. Major financial news (supply chain, partnerships, infrastructure)
3. Industry publications, analyst reports
4. Reddit / social (early formation signal only — low weight)

AI LEAN_IN RULES:
- LEAN_IN is permitted at MEDIUM event count if:
  - source quality is HIGH (transcript or major news confirmed)
  - reinforcement is HIGH
  - multi-actor confirmation is present (not single-company in isolation)
- Infrastructure and delivery narratives can be promoted faster than model-layer narratives
- Transcripts confirming the same theme as newsflow = strong LEAN_IN basis

AI BE_CAREFUL RULES:
Use BE_CAREFUL for:
- Early application-layer signals (single actor, narrow scope)
- Isolated single-actor momentum not yet echoed by other companies
- Transitions (infra → software monetization) where direction is clear but breadth is uncertain
- Loud announcement cycles without ecosystem pickup

AI STEP_BACK RULES:
Use STEP_BACK for:
- Model-layer fading (previously dominant narrative now declining in coverage)
- Announcement cycles that generated attention but no follow-through from other actors
- Price and volatility narratives collapsing after a spike

AI NARRATIVE FAMILY CONTEXT:

infrastructure (compute_capacity / infrastructure_delivery / semiconductor_supply):
- Cross-actor confirmation → LEAN_IN is appropriate even at MEDIUM event count
- Single-actor bottleneck signal without cross-actor echo → BE_CAREFUL

technology (model_layer / model_technology):
- Hard to sustain → BE_CAREFUL unless clearly fading (then STEP_BACK)
- Model-race chatter without confirmed releases → IGNORE or BE_CAREFUL

adoption (enterprise_deployment):
- BE_CAREFUL until multiple companies confirm the same deployment pattern
- Single company contract announcement → BE_CAREFUL, not LEAN_IN

market_sentiment (market_volatility):
- Never LEAN_IN
- Cap at BE_CAREFUL; if rapidly declining → STEP_BACK or IGNORE

macro (regulatory_policy / geopolitical):
- Default: BE_CAREFUL
- LEAN_IN only when ALL of the following are true:
  - The policy or geopolitical event directly constrains or shapes AI supply chain, compute access,
    export controls, or sovereign AI infrastructure
  - Cross-source confirmation is present (not opinion or speculation alone)
  - Reinforcement is HIGH across multiple events
- BE_CAREFUL for: emerging regulatory signals, export-control proposals not yet enacted,
  bilateral AI policy discussions without binding outcomes
- IGNORE if: general political news, trade disputes without direct AI supply chain relevance,
  opinion/commentary pieces with no confirmed policy action
- Do NOT promote to LEAN_IN based on regulatory chatter or geopolitical tension alone

ecosystem_structure (partnership_deals / talent_research):
- Default: skeptical — lean toward STEP_BACK or IGNORE
- partnership_deals:
  - STEP_BACK for: most announced partnerships, MOU-level deals, headline-only announcements
  - BE_CAREFUL for: partnerships that show cross-actor ecosystem formation (3+ companies),
    confirmed execution signals (APIs live, joint deployments announced)
  - LEAN_IN only when: a partnership demonstrably reshapes infrastructure access or model delivery
    at ecosystem scale — not a single press release
  - IGNORE for: generic vendor partnerships, single-company integration announcements
- talent_research:
  - IGNORE for: individual hire announcements, paper releases, lab blog posts
  - BE_CAREFUL for: signals of mass talent movement across labs, research breakthroughs
    confirmed by multiple sources, new lab formation with significant funding
  - LEAN_IN only when: signals a definitive capability or ecosystem shift confirmed
    by multiple high-trust sources (not based on a single announcement)
  - Do NOT promote talent news to LEAN_IN without cross-actor or institutional confirmation

general:
- Default → IGNORE

AI HARD CONSTRAINTS:
- If cluster has exactly 1 actor AND event_count < 10: cannot be LEAN_IN (cap at BE_CAREFUL)
- If narrative_family = market_sentiment or general: cannot be LEAN_IN
- If narrative_family = ecosystem_structure AND reinforcement = LOW: cannot be LEAN_IN (cap at BE_CAREFUL)
- If narrative_family = macro AND no confirmed binding policy action: cannot be LEAN_IN\
"""

_CRYPTO_RULES = """\
ECOSYSTEM: CRYPTO — SPECIFIC RULES

Crypto is noisier, more fragmented, and more retail-driven than AI.
Do NOT force crypto narratives to look as clean as AI.
Fragmentation is real and should be reflected in the output.

CRYPTO SOURCE HIERARCHY (most to least trusted):
1. Treasury accumulation filings, ETF flows, regulatory actions, major news
2. Industry aggregators (CryptoPanic, institutional coverage)
3. Reddit / community (formation signal and noise detection only)

CRYPTO LEAN_IN RULES:
A crypto narrative can only be LEAN_IN if:
- reinforcement = HIGH
- cross-source reinforcement is present (not Reddit alone)
- at least one non-Reddit / non-community source confirms it
- direction is coherent across events
- event_count is sufficient (not a handful of Reddit posts)

CRYPTO STEP_BACK RULES:
Use STEP_BACK for:
- High-volume but incoherent narrative clusters
- Discussion without directional formation
- Fragmented ecosystem chatter that was previously coherent

CRYPTO BE_CAREFUL RULES:
Use BE_CAREFUL for:
- Reddit-heavy narratives with early traction and rising momentum
- Partial institutional confirmation (one source, not cross-confirmed)
- Macro narratives still forming
- Emerging protocol narratives needing a second confirmation window

CRYPTO IGNORE RULES:
Use IGNORE for:
- Cycle chatter, price target posting, "to the moon" discourse
- Wallet / help / beginner content
- Retail regret ("I sold too early", "missed the dip")
- Generic market discussion
- narrative_family = retail_sentiment or general (always IGNORE)
- dominant_source = reddit AND reinforcement = LOW (volume without formation = noise)

REDDIT CLASSIFICATION RULES (CRITICAL):

When Reddit is the dominant source (dominant_source = reddit OR reddit >= 70%):
- Default toward BE_CAREFUL, STEP_BACK, or IGNORE
- Require cross-source reinforcement before LEAN_IN is permitted
- If Reddit volume is HIGH but reinforcement is LOW → IGNORE (not STEP_BACK)
  (High Reddit volume without structural reinforcement is noise, not a declining important
   narrative. STEP_BACK implies "this was structurally important and is now fading."
   Pure Reddit volume spikes don't qualify.)
- If Reddit is the only source and reinforcement is MEDIUM → BE_CAREFUL at most

Reddit IS useful for detecting:
- Early narrative emergence (BE_CAREFUL with rising momentum)
- Emotionally reactive narratives (BE_CAREFUL or IGNORE)

Reddit is NOT sufficient alone for:
- HIGH confidence calls
- LEAN_IN (requires cross-source confirmation)
- STEP_BACK (requires prior structural weight)

CRYPTO NARRATIVE FAMILY CONTEXT:

institutional (btc_institutional_accumulation, eth_institutional_accumulation):
- LEAN_IN appropriate even at MEDIUM event count if multi-source and HIGH reinforcement

macro (btc_macro_hedge, regulatory_pressure, macro_spillover):
- Regulatory signals → check source quality before LEAN_IN
- Macro spillover Reddit chatter → BE_CAREFUL at best

retail_sentiment (btc_sentiment_noise, sol_activity_speculation):
- Never LEAN_IN
- Default → IGNORE

security_exploit (btc_security_custody, eth_security_exploit):
- Single confirmed exploit → LEAN_IN regardless of event count
- Speculation without cross-source confirmation → BE_CAREFUL

ecosystem_structure (crypto_ai_crossover, eth_l2_fragmentation, sol_narrative_reset, etc.):
- Require ≥2 source types for LEAN_IN

general:
- Default → IGNORE

CRYPTO HARD CONSTRAINTS:
- If dominant_source = reddit AND cross_source_count < 2 → cannot be LEAN_IN
- If dominant_source = reddit AND reinforcement = LOW → must be IGNORE
- If narrative_family = retail_sentiment → cannot be LEAN_IN
- If narrative_family = general → default to IGNORE\
"""


def build_system_prompt(ecosystem: str) -> str:
    """
    Assemble the full classification system prompt for the given ecosystem.

    Parameters
    ----------
    ecosystem : "ai" | "crypto"
    """
    ecosystem_rules = _AI_RULES if ecosystem == "ai" else _CRYPTO_RULES
    sections = [
        _ROLE,
        _VALIDATE,
        _SCORE,
        _SOURCE_BASE,
        _CLASSIFY_BASE,
        ecosystem_rules,
        _SHARED_CONSTRAINTS,
        _CONFIDENCE,
        _WRITING_STYLE,
        _GOAL,
    ]
    return "\n\n\n".join(sections)


# ── Post-processing ────────────────────────────────────────────────────────────

def _partial_match_lookup(d: dict, narrative: str, default):
    """
    Exact lookup first; fall back to best partial word-overlap match.
    Tolerates minor LLM rephrasing of narrative names.
    """
    key = narrative.lower().strip()
    if key in d:
        return d[key]
    words = set(key.split())
    best, best_score = default, 0
    for k, v in d.items():
        overlap = len(words & set(k.split()))
        if overlap > best_score:
            best, best_score = v, overlap
    return best


def _force_be_careful(entry: CompassEntry, reason: str) -> dict:
    d = entry.model_dump()
    d["confidence"] = "LOW"
    d["_forced"] = reason   # internal debug tag, stripped before render
    return d


def post_process_classify_results(
    result: CompassClassification,
    momentum_by:   dict[str, str],
    attention_by:  dict[str, str],
    dom_src_by:    dict[str, str],
    cross_src_by:  dict[str, int],
    reddit_pct_by: dict[str, float],
    size_by:       dict[str, int],
    ecosystem:     str,
    actors_by:     dict[str, list[str]] | None = None,
) -> dict[str, list[dict]]:
    """
    Apply shared and ecosystem-specific post-processing overrides.

    Shared (all ecosystems):
      1. INSUFFICIENT_DATA → force BE_CAREFUL
      2. STEP_BACK requires HIGH attention

    AI-specific:
      3. Single-actor thin signal (1 actor, event_count < 10) → cap at BE_CAREFUL

    Crypto-specific:
      3a. Reddit-dominant (sole source) → hard floor: LEAN_IN → BE_CAREFUL
      3b. Reddit-heavy (≥70%) → cap at BE_CAREFUL

    Returns deduplicated sections dict with event_count annotated.
    """
    def _lkp(d, narrative, default):
        return _partial_match_lookup(d, narrative, default)

    all_entries = (
        [(e, "lean_in")    for e in result.lean_in]   +
        [(e, "step_back")  for e in result.step_back]  +
        [(e, "be_careful") for e in result.be_careful] +
        [(e, "ignore")     for e in result.ignore]
    )

    lean_in_final    = []
    step_back_final  = []
    be_careful_extra = []
    ignore_final     = []

    for e, section in all_entries:
        momentum   = _lkp(momentum_by,   e.narrative, "FLAT")
        attn       = _lkp(attention_by,  e.narrative, "MEDIUM")
        dom_src    = _lkp(dom_src_by,    e.narrative, "unknown")
        cross_src  = _lkp(cross_src_by,  e.narrative, 1)
        reddit_pct = _lkp(reddit_pct_by, e.narrative, 0)
        size       = _lkp(size_by,       e.narrative, 0)

        # ── Shared Rule 1: INSUFFICIENT_DATA → BE_CAREFUL ────────────────────
        if momentum == "INSUFFICIENT_DATA" and section in ("lean_in", "step_back", "ignore"):
            be_careful_extra.append(_force_be_careful(e, "insufficient_data"))
            continue

        # ── Shared Rule 2: STEP_BACK requires HIGH attention ─────────────────
        if section == "step_back" and attn != "HIGH":
            be_careful_extra.append(_force_be_careful(e, "step_back_not_high_attn"))
            continue

        # ── AI-specific Rule 3: single-actor thin signal ──────────────────────
        if ecosystem == "ai" and section == "lean_in":
            actor_list = _lkp(actors_by or {}, e.narrative, [])
            if len(actor_list) == 1 and size < 10:
                be_careful_extra.append(_force_be_careful(e, "ai_single_entity_thin"))
                continue

        # ── Crypto-specific Rules 3a / 3b: Reddit floors ─────────────────────
        if ecosystem == "crypto":
            is_reddit_dominant = (dom_src == "reddit" and cross_src < 2)
            is_reddit_heavy    = (reddit_pct >= 70)

            if is_reddit_dominant and section == "lean_in":
                be_careful_extra.append(_force_be_careful(e, "reddit_dominant_no_cross_source"))
                continue
            if is_reddit_dominant and section == "step_back" and e.confidence == "LOW":
                ignore_final.append(e.model_dump())
                continue
            if is_reddit_heavy and section == "lean_in":
                be_careful_extra.append(_force_be_careful(e, "reddit_heavy_70pct"))
                continue
            if is_reddit_heavy and section == "step_back":
                be_careful_extra.append(_force_be_careful(e, "reddit_heavy_70pct_stepback"))
                continue

        # ── Passthrough ───────────────────────────────────────────────────────
        if section == "lean_in":
            lean_in_final.append(e.model_dump())
        elif section == "step_back":
            step_back_final.append(e.model_dump())
        elif section == "be_careful":
            be_careful_extra.append(e.model_dump())
        else:
            ignore_final.append(e.model_dump())

    # ── Dedup by priority (lean_in > step_back > be_careful > ignore) ─────────
    seen: set[str] = set()

    def _dedup(items: list[dict]) -> list[dict]:
        out = []
        for item in items:
            key = item["narrative"].lower().strip()
            if key not in seen:
                seen.add(key)
                clean = {k: v for k, v in item.items() if not k.startswith("_")}
                if "event_count" not in clean:
                    clean["event_count"] = _lkp(size_by, item["narrative"], 0)
                out.append(clean)
        return out

    return {
        "lean_in":    _dedup(lean_in_final),
        "step_back":  _dedup(step_back_final),
        "be_careful": _dedup(be_careful_extra),
        "ignore":     _dedup(ignore_final),
    }


# ── Shared rendering ───────────────────────────────────────────────────────────

def render_compass_text(sections: dict, date: str, title: str = "NARRATIVE COMPASS") -> str:
    w = 64
    lines = [
        "╔" + "═" * w + "╗",
        "║" + f"  {title}  ·  {date}".ljust(w) + "║",
        "╚" + "═" * w + "╝",
        "",
    ]
    defs = [
        ("lean_in",    "1  LEAN IN"),
        ("step_back",  "2  STEP BACK"),
        ("be_careful", "3  BE CAREFUL"),
        ("ignore",     "4  IGNORE"),
    ]
    for key, header in defs:
        items = sections.get(key, [])
        lines.append(header)
        lines.append("─" * len(header))
        if not items:
            lines.append("   (none)")
        else:
            for item in items:
                lines.append(f'   {item["narrative"]}  [{item["confidence"]}]')
                lines.append(f'      {item["summary"]}')
                lines.append(f'      → {item["action"]}')
                lines.append("")
    return "\n".join(lines)


def render_compass_json(sections: dict, date: str, ecosystem: str) -> str:
    clean = {
        k: [{f: v for f, v in item.items() if not f.startswith("_")} for item in items]
        for k, items in sections.items()
    }
    return json.dumps({"ecosystem": ecosystem, "date": date, "compass": clean}, indent=2)
