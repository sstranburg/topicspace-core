"""
compose_homepage.py — Editorial composition layer for Narrative Compass homepage.

Runs AFTER signal classification and ranking. Does NOT modify underlying signals
or classification logic.

Responsibilities:
  - Select 4–8 signals from the ranked output for homepage display
  - Generate punchy top read, explanation sentence, and system state
  - Generate or fill in notes/implications per visible signal
  - Apply thin-day framing when LEAN_IN is empty
  - Run a deployability check before the page goes live

Design principle:
  The homepage is a composed daily product, not a raw classifier dump.
  Signals stay honest. Presentation is intentional.
"""

from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel


# ── AI homepage allowlist ────────────────────────────────────────────────────────
# Controls which routing buckets are eligible for the AI homepage.
# Based on narrative_bucket (the routing label, more granular than narrative_family).
#
# Two tiers:
#   CORE        — always eligible; backbone of the AI system
#   CONDITIONAL — eligible only when AI context is clearly present
#
# Everything else is excluded regardless of classification or confidence.

_ALLOWED_CORE_BUCKETS: frozenset[str] = frozenset({
    "compute_capacity",
    "semiconductor_supply",
    "infrastructure_delivery",
    "enterprise_deployment",
    "model_technology",
})

_ALLOWED_CONDITIONAL_BUCKETS: frozenset[str] = frozenset({
    # Allowed only when clearly AI-linked (see _ai_context_strong)
    "regulatory_policy",
    "geopolitical",
    "energy_power",
    "partnership_deals",
})

# Excluded buckets (implicit — anything not in the above two sets):
#   market_noise, market_volatility, talent_research, other, general

# Actor + keyword sets used by the conditional context check
_AI_CORE_ACTORS: frozenset[str] = frozenset({
    "NVDA", "AMD", "INTC", "TSM", "MU", "AVGO", "ARM", "QCOM",
    "ANET", "VRT", "NBIS",
    "OPENAI", "ANTHROPIC", "DEEPMIND", "MISTRAL",
})

_AI_KEYWORDS_SINGLE: frozenset[str] = frozenset({
    "ai", "chip", "chips", "semiconductor", "semiconductors",
    "gpu", "gpus", "compute", "inference", "training",
    "model", "models", "llm", "transformer", "neural",
    "datacenter", "hyperscaler", "capex", "quantum", "hpc",
    "nvidia", "cuda", "tpu", "accelerator",
})

_AI_KEYWORDS_PHRASE: tuple[str, ...] = (
    "artificial intelligence", "machine learning", "data center", "data centers",
    "supply chain", "export control", "export controls", "sovereign compute",
    "foundation model", "large language", "energy infrastructure",
)


def _ai_context_strong(cluster: dict) -> bool:
    """
    Returns True when a conditional-bucket cluster has clear AI ecosystem linkage.

    Requires BOTH:
      - at least one core AI actor in the cluster
      - at least one AI keyword in the narrative title

    This is intentionally strict: a conditional narrative that can't demonstrate
    both signals does not belong on the AI homepage.
    """
    actors      = set(cluster.get("actors", []))
    title       = cluster.get("narrative", cluster.get("title", "")).lower()
    title_words = set(re.split(r"\W+", title))

    has_core_actor = bool(actors & _AI_CORE_ACTORS)
    has_ai_keyword = (
        bool(title_words & _AI_KEYWORDS_SINGLE)
        or any(p in title for p in _AI_KEYWORDS_PHRASE)
    )
    return has_core_actor and has_ai_keyword


def is_ai_homepage_relevant(cluster: dict) -> bool:
    """
    Two-tier allowlist gate for AI homepage inclusion.

    CORE buckets    → always pass.
    CONDITIONAL     → pass only when _ai_context_strong is True.
    Everything else → excluded.
    """
    bucket = cluster.get("narrative_bucket", "other")
    if bucket in _ALLOWED_CORE_BUCKETS:
        return True
    if bucket in _ALLOWED_CONDITIONAL_BUCKETS:
        return _ai_context_strong(cluster)
    return False


# ── Weak title detection ────────────────────────────────────────────────────────
# Term-based fallback labels look like "Says Chip Anthropic Tesla" or
# "China Taiwan Chip Semiconductor" — they should not appear on the homepage.

_WEAK_PHRASES = {
    "says chip",
    "stock stocks",
    "trump wall street",
    "wall street response",
    "alphabet spins fiber",
    "arm: likely",
    "says inference",
    "market engagement",
    "china taiwan chip semiconductor",
    "bom:",
    # entity-residue patterns from term-join fallback
    "china taiwan iran",
    "chip says anthropic",
    "claude oracle software",
    "says anthropic deal",
    "highlighted zacks",
    "chatgpt gemini going",
    "alternatives? win",
    "alternatives win linux",
    "nemotron-3 nano",
    "steve jobs once",
    "epstein files",
    "zacks bull bear",
}


def is_weak_title(title: str) -> bool:
    """
    True if the title is a raw term-join or clearly non-narrative label.
    These originate from the fallback term labeler and shouldn't appear on the homepage.
    """
    t = title.lower()
    return any(p in t for p in _WEAK_PHRASES)


# ── Emerging expansion detection ────────────────────────────────────────────────

_FORWARD_LOOKING_PHRASES: tuple[str, ...] = (
    "inflection point", "new phase", "new era", "has arrived", "turning point",
    "transition", "pivoting", "restructuring", "entering", "declares",
    "shift from", "shift to", "moving from", "moving toward",
    "inflection", "beginning of", "paradigm", "pivots to",
)

_LAYER_FAMILIES: dict[str, frozenset[str]] = {
    "model":      frozenset({"model_technology", "model_layer"}),
    "infra":      frozenset({"infrastructure_delivery", "compute_capacity",
                              "semiconductor_supply", "energy_power"}),
    "deployment": frozenset({"enterprise_deployment", "partnership_deals"}),
}


def detect_emerging_expansion(
    selected_signals: list[dict],
    step_back_count: int,
) -> bool:
    """
    True when ≥2 STEP_BACK signals span multiple layers AND include
    forward-looking language — a structural shift is forming with direction,
    not just fragmentation.

    Criteria (all must be true):
      - step_back_count ≥ 2
      - signals span ≥ 2 distinct narrative layers
      - at least one signal contains forward-looking language
      - ≥ 3 distinct actors named across signals
    """
    if step_back_count < 2:
        return False

    # Cross-layer span
    present_layers: set[str] = set()
    for sig in selected_signals:
        fam = sig.get("narrative_family", "")
        for layer, families in _LAYER_FAMILIES.items():
            if fam in families:
                present_layers.add(layer)
    if len(present_layers) < 2:
        return False

    # Forward-looking language
    all_text = " ".join(
        f"{sig.get('narrative', '')} {sig.get('summary', '')} {sig.get('notes', '')}"
        for sig in selected_signals
    ).lower()
    if not any(phrase in all_text for phrase in _FORWARD_LOOKING_PHRASES):
        return False

    # Actor count ≥ 3
    all_actors: set[str] = set()
    for sig in selected_signals:
        for a in sig.get("affected_entities", sig.get("actors", [])):
            all_actors.add(str(a).strip().upper())
    return len(all_actors) >= 3


# ── Signal selection ────────────────────────────────────────────────────────────

_CONF_RANK: dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def select_homepage_signals(
    sections: dict[str, list[dict]],
    labeled:  list[dict],
    max_signals: int = 8,
    min_signals: int = 4,
) -> list[dict]:
    """
    Select 4–8 signals for homepage display.

    Priority order:
      1. LEAN_IN — all, highest value
      2. STEP_BACK — all, up to max
      3. BE_CAREFUL — strongest first, family-diverse, no weak titles
      4. IGNORE — up to 2 for contrast/context only, no weak titles

    Family diversity pass first, then duplicate families allowed if below min.

    An AI homepage allowlist is applied before selection. Only CORE bucket
    narratives and CONDITIONAL bucket narratives with strong AI context are
    eligible. Filtering may produce fewer than min_signals — that is intentional;
    irrelevant content is never added to meet a quota.
    """
    # ── AI homepage allowlist pre-filter ────────────────────────────────────
    cluster_by_narrative = {c["narrative"].lower().strip(): c for c in labeled}

    def _is_relevant(entry: dict) -> bool:
        key     = entry.get("narrative", "").lower().strip()
        cluster = cluster_by_narrative.get(key)
        return cluster is not None and is_ai_homepage_relevant(cluster)

    before = sum(len(v) for v in sections.values())
    sections = {bucket: [e for e in entries if _is_relevant(e)]
                for bucket, entries in sections.items()}
    after = sum(len(v) for v in sections.values())
    if before != after:
        filtered = before - after
        print(f"  [allowlist] {after}/{before} signals passed AI homepage allowlist"
              f" ({filtered} excluded)")

    def _score(entry: dict) -> float:
        return _CONF_RANK.get(entry.get("confidence", "LOW"), 1) * 10 + entry.get("event_count", 0) / 100

    def _label_ok(entry: dict) -> bool:
        return not is_weak_title(entry.get("narrative", entry.get("title", "")))

    selected: list[dict] = []
    seen_families: set[str] = set()
    selected_ids: set[int] = set()

    def _add(entry: dict, bucket: str, allow_dup_family: bool = False) -> bool:
        if id(entry) in selected_ids:
            return False
        if not _label_ok(entry):
            return False
        family = entry.get("narrative_family", "general")
        if not allow_dup_family and family in seen_families:
            return False
        selected.append({**entry, "_bucket": bucket})
        seen_families.add(family)
        selected_ids.add(id(entry))
        return True

    # Pass 1: LEAN_IN + STEP_BACK — take all, family-diverse
    for bucket in ("lean_in", "step_back"):
        for entry in sections.get(bucket, []):
            if len(selected) >= max_signals:
                break
            _add(entry, bucket)

    # Pass 2a: BE_CAREFUL — sort by score, family-diverse first
    be_careful = sorted(sections.get("be_careful", []), key=_score, reverse=True)
    for entry in be_careful:
        if len(selected) >= max_signals:
            break
        _add(entry, "be_careful")

    # Pass 2b: BE_CAREFUL — allow duplicate families if below min
    if len(selected) < min_signals:
        for entry in be_careful:
            if len(selected) >= max_signals:
                break
            _add(entry, "be_careful", allow_dup_family=True)

    # Pass 3a: IGNORE — up to 2 for contrast, family-diverse
    ignore_added = 0
    ignore_sorted = sorted(sections.get("ignore", []), key=_score, reverse=True)
    for entry in ignore_sorted:
        if len(selected) >= max_signals or ignore_added >= 2:
            break
        if _add(entry, "ignore"):
            ignore_added += 1

    # Pass 3b: IGNORE with dup family allowed if still below min
    if len(selected) < min_signals:
        for entry in ignore_sorted:
            if len(selected) >= max_signals or ignore_added >= 2:
                break
            if id(entry) not in selected_ids and _label_ok(entry):
                selected.append({**entry, "_bucket": "ignore"})
                selected_ids.add(id(entry))
                ignore_added += 1

    return selected


# ── LLM composition ─────────────────────────────────────────────────────────────

class _NoteItem(BaseModel):
    narrative: str  # original title for joining — do NOT change this
    headline:  str  # cross-actor, directional headline for display (overrides title)
    summary:   str  # paragraph 1: pattern across actors + why it matters
    note:      str  # paragraph 2: connection to spine, what would confirm it


class NarrativeSpine(BaseModel):
    away_from:   str  # layer/narrative losing attention across multiple actors
    toward:      str  # layer/narrative gaining attention or forming
    uncertainty: str  # why the rotation hasn't consolidated yet


class WatchSignal(BaseModel):
    headline: str        # conditional or decisive framing (3–10 words)
    actors:   list[str]  # supporting actors
    summary:  str        # what is forming / current state (1–2 sentences)
    note:     str        # why it matters / system consequence (1–2 sentences)
    trigger:  str        # "If X happens → Y system change"


class HomepageComposition(BaseModel):
    spine:            NarrativeSpine
    primary_pressure: str
    primary_trigger:  str
    top_read:         str
    explanation:      str
    system_state:     str
    signal_notes:     list[_NoteItem]
    watch_signals:    list[WatchSignal]


_COMPOSITION_SYSTEM_PROMPT = """\
You are the editorial composer for Narrative Compass, a daily AI market intelligence product.

You receive pre-classified signals and produce the homepage composition for the day.

The entire homepage must tell ONE system story. Every section must align to a single narrative spine.

═══════════════════════════════════════════════════════
STEP 1 — DERIVE THE NARRATIVE SPINE (do this first)
═══════════════════════════════════════════════════════

Before writing anything else, examine all signals and identify:

  away_from   — which layer/narrative is LOSING attention (multiple actors declining simultaneously)
  toward      — which layer/narrative is GAINING attention or forming
  uncertainty — why the rotation has NOT consolidated yet (missing confirmation, new disruptor, etc.)

This spine governs EVERYTHING else. No section may contradict it.

If signals are genuinely directionless (no discernible rotation), state that explicitly in the spine.

═══════════════════════════════════════════════════════
STEP 1.5 — PRIMARY_PRESSURE
═══════════════════════════════════════════════════════

A single sentence describing the dominant tension in the system. This is NOT a summary — it names
the unresolved pressure that governs everything else on the page.

RULES:
- Max 20 words
- Declarative. Precise. No hype. No adjectives like "massive", "huge", "critical", "unprecedented".
- Grounded in the highest-impact signals — especially WATCH signals in fragmentation
- Must reflect the current regime (EXPANSION, COOLING, FRAGMENTATION, EMERGING_EXPANSION)

IF EMERGING_EXPANSION (see REGIME line in user message):
- Must describe the shift itself (not uncertainty about whether it will happen)
- Must name the structural change in progress across layers
- Directional — forward-looking, not hedged

IF FRAGMENTATION (LEAN_IN=0, STEP_BACK≥2):
- Must reflect unresolved competition between narratives
- Must reference the key decision variable (e.g. hyperscaler capex, model release, chip adoption)
- Must NOT make directional claims or express certainty about the outcome

GOOD examples:
  "The system is waiting on hyperscaler capital to resolve a rotation already in motion."
  "Competing narratives are forming, but no actor has committed enough to define the system."
  "Infrastructure is building, but without cost or demand confirmation, expansion is not locked in."

BAD examples:
  "The AI ecosystem is undergoing massive transformation."  ← hype, no tension
  "Multiple trends are converging."  ← vague, no decision variable
  "Uncertainty remains elevated."  ← describes state, not tension

═══════════════════════════════════════════════════════
STEP 1.75 — PRIMARY_TRIGGER
═══════════════════════════════════════════════════════

A single conditional statement — the ONE event that would most change the current system state.

FORMAT: "If [specific actor action] → [system-level outcome]"

RULES:
- Must reference named actors (not generic placeholders like "a hyperscaler")
- Must be grounded in existing WATCH signals — do not invent new triggers
- Choose ONLY ONE: highest expected system impact, clearest causal pathway
- Not speculative or vague — must be a real, plausible near-term event

IF EMERGING_EXPANSION (see REGIME line in user message):
- Must identify WHO controls the consolidation of the new structure
- Frame as: "If [actor who owns the transition] does X → new structure locks in"
- Forward-looking: not "if this changes" but "if this confirms"

IF FRAGMENTATION (LEAN_IN=0, STEP_BACK≥2):
- Must resolve the competition between narratives
- Must be the most decisive action that could lock in a dominant narrative

GOOD examples:
  "If Amazon, Microsoft, or Google commits to large-scale AI infrastructure capex → infrastructure becomes the dominant narrative."
  "If a second hyperscaler adopts ARM chips at scale → the AI hardware stack becomes multi-vendor."
  "If OpenAI launches a significant new model → model-layer attention re-enters and competes with infrastructure."

BAD examples:
  "If AI adoption accelerates → the system will change."  ← vague, no actor
  "If something happens with chips → outcomes shift."     ← not specific
  "If conditions improve → narratives consolidate."       ← no causal pathway

═══════════════════════════════════════════════════════
STEP 2 — TOP READ
═══════════════════════════════════════════════════════

Must express the spine in exactly two sentences:
  Sentence 1: system movement — what is moving away, what is forming
  Sentence 2: uncertainty — why it has not consolidated

GOOD (spine-aligned):
    "The system is rotating out of the model layer and into infrastructure delivery.
     But no hyperscaler has committed, and ARM just disrupted the hardware stack before it locks in."

    "Model race fading. Delivery race forming.
     The delivery layer is visible but not yet confirmed."

    "Attention has left the model layer across seven actors simultaneously.
     Infrastructure is absorbing it — but hasn't yet produced a dominant narrative."

BAD (not spine-aligned):
    "The system is fragmenting. Competing narratives swirl, yet none leads."  ← formless, no direction
    "Conviction is weak and scattered."  ← describes state without direction
    "Multiple narratives are active but none is consolidating."  ← no away_from, no toward

REGIME NOTE: Read the REGIME line in the user message. But even in FRAGMENTATION, there is usually
a directional rotation — identify it. Fragmentation does not mean no direction; it means the toward
layer is forming but has not consolidated.

═══════════════════════════════════════════════════════
STEP 3 — SIGNAL HEADLINES + EXPLANATIONS
═══════════════════════════════════════════════════════

Each signal IS a system-level insight. Signals are not summaries of actor activity.
There is no separate "insights" section — the insights ARE the signals.

HEADLINE (the `headline` field — overrides the display title):
- Must be cross-actor, directional, declarative
- Describes a system-level pattern, not a single actor's activity
- 3–10 words

GOOD headlines:
    "The model layer is losing the narrative"
    "The delivery layer is forming as a unified front"
    "ARM just entered the AI chip layer"
    "Chip pricing is stabilizing across the infrastructure stack"

BAD headlines:
    "NVDA compute capacity constrained"          ← single actor
    "OpenAI momentum declining"                  ← single actor
    "Mixed signals across semiconductor actors"  ← no direction

EXPLANATION — paragraph 1 (the `summary` field):
- Describe the pattern across the specific actors
- Name actors and what they are doing
- Explain why this pattern matters to the system
- 2–3 sentences

EXPLANATION — paragraph 2 (the `note` field):
- Connect explicitly to the spine: name whether this is away_from, toward, or disruption
- Name the concrete event that would confirm or consolidate this signal
- Must not repeat paragraph 1
- 1–2 sentences

RULES:
- Each signal = one distinct system insight. Zero duplication.
- STEP_BACK signals = system shifts important but not yet confirmed (NOT fading)
- BE_CAREFUL signals = early formation of the toward layer
- LEAN_IN signals = the toward layer locking in
- No analytical language: no scores, event counts, source types

GOOD paragraph 2 examples:
    "This is the away_from side of the current rotation — the attention is not disappearing, it is migrating into infrastructure delivery."
    "Early toward-layer signal — hyperscaler capex commitments would confirm this is structural, not reactive."
    "ARM's entry disrupts the toward narrative before it consolidates — changes the competitive topology for inference hardware."

═══════════════════════════════════════════════════════
STEP 3.5 — WATCH SIGNALS (2–4 total)
═══════════════════════════════════════════════════════

WATCH signals role depends on regime (see REGIME line in user message):

IF EMERGING_EXPANSION:
  WATCH signals represent COUNTERFORCES — things that could SLOW or STOP the structural shift.
  They answer: "What could prevent the shift from completing?"
  Examples: compression technologies that reduce capex demand, competing architectures,
  regulatory friction, or actors that defect from the emerging structure.

IF FRAGMENTATION or other regime:
  WATCH signals represent ALTERNATIVE system paths — secondary triggers and competing outcomes.
  They answer: "What else could change the system state, besides the primary trigger?"

CRITICAL DEDUPLICATION RULE:
PRIMARY_TRIGGER (from Step 1.75) already owns the main system decision.
WATCH signals must NOT repeat or restate it.

If a WATCH signal represents the same trigger as PRIMARY_TRIGGER → do not include it.
Every WATCH signal must introduce a DISTINCT possible system outcome.

Each WATCH signal must:
- Extend an existing STEP_BACK or BE_CAREFUL signal (not introduce unrelated narratives)
- Represent a system-level shift (not actor-level)
- Be a different causal pathway from PRIMARY_TRIGGER
- Include an explicit trigger in "If X → Y" format

FIELDS:
  headline  — conditional or decisive framing (3–10 words, may start with "If...")
  actors    — the actors that would drive or be affected by the trigger
  summary   — what is forming right now and why it's close to a trigger point (1–2 sentences)
  note      — what the system-level consequence would be if the trigger fires (1–2 sentences)
  trigger   — "If [specific event] → [system change]"

EXAMPLE of deduplication in action:
  If PRIMARY_TRIGGER = "If Amazon, Microsoft, or Google commits to AI capex → infrastructure becomes dominant"
  Then a WATCH signal with trigger "If hyperscalers announce capex → delivery layer confirms" is FORBIDDEN — same path.
  Instead, a valid WATCH might be: "If OpenAI launches a major model → model layer re-enters the rotation"

GOOD WATCH examples (distinct from a capex-based primary trigger):
  headline: "A second hyperscaler adopting ARM chips reshapes the hardware stack"
  trigger:  "If Amazon or Google adopts ARM-based AI infrastructure at scale → delivery layer shifts from NVDA-centric to multi-vendor"

  headline: "A new model release could reverse the model layer exit"
  trigger:  "If OpenAI or Anthropic launches a significant new capability → model layer attention reverses and competes with infrastructure"

  headline: "Chip pricing compression could stall infrastructure build-out"
  trigger:  "If NVDA or AMD signals margin pressure → infrastructure capex slows before the delivery layer locks in"

RULES:
- 2 minimum, 4 maximum
- Must extend current STEP_BACK or BE_CAREFUL signals — not introduce new topics
- No overlap with PRIMARY_TRIGGER — each must be a distinct causal path
- Trigger must be specific and actionable (not vague)
- Tone: precise, conditional, forward-looking

═══════════════════════════════════════════════════════
STEP 4 — EXPLANATION + SYSTEM STATE
═══════════════════════════════════════════════════════

explanation:
  One sentence. Connects the visible signals into the spine.
  Must be specific to today's actual actor names and layer names.
  Do NOT repeat the top_read.

system_state:
  3–6 words. Plain English. What is the system doing?
  Must reflect the spine direction, not just a regime label.

GOOD system_state:
    "Rotating — model layer out, delivery forming"
    "Infrastructure delivery layer consolidating"
    "Model attention exiting, delivery absorbing"
    "Selective confirmation forming — price-led cluster dominant"

BAD system_state:
    "Active but dispersed"          ← no direction
    "Fragmented"                    ← describes state without direction
    "Mixed signals"                 ← meaningless
    "Broad confirmation building"   ← overstates; use "selective" when price-led names outnumber confirmed
    "Confirmation forming"          ← too vague; qualify which layer or type

PRECISION RULE: If price-led names outnumber confirmed names on the board, do NOT describe
the system as broadly confirming. Use "selective confirmation" or "confirmation forming in
pockets" to reflect the actual distribution. Prefer narrower claims over broad market-sweeping
language. When in doubt, qualify.
"""


def compose_with_llm(
    selected_signals:      list[dict],
    has_lean_in:           bool,
    step_back_count:       int,
    date:                  str,
    is_emerging_expansion: bool = False,
) -> HomepageComposition:
    """Call gpt-4o-mini to generate top_read, explanation, system_state, and signal notes."""
    from src.llm_naming import _get_client

    lines = []
    for i, sig in enumerate(selected_signals, 1):
        bucket   = sig.get("_bucket", "be_careful").upper().replace("_", " ")
        family   = sig.get("narrative_family", "general")
        momentum = sig.get("momentum", "FLAT")
        actors   = sig.get("affected_entities", sig.get("actors", []))
        count    = sig.get("event_count", 0)
        title    = sig.get("narrative", sig.get("title", ""))
        summary  = sig.get("summary", "")
        lines.append(
            f"{i}. [{bucket}] {title}\n"
            f"   family={family}  momentum={momentum}  confidence={sig.get('confidence','?')}  events={count}\n"
            f"   actors={', '.join(str(a) for a in actors[:3]) or 'unknown'}\n"
            f"   summary={summary}"
        )

    if not has_lean_in:
        if is_emerging_expansion:
            regime_note = (
                f"\nREGIME: EMERGING_EXPANSION — LEAN_IN=0, STEP_BACK={step_back_count}, "
                "cross-layer span detected, forward-looking language present.\n"
                "A structural shift is forming across multiple layers simultaneously.\n"
                "This is NOT fragmentation — there is a clear direction.\n"
                "Multiple actors are referencing the same structural transition at the same time.\n"
                "IMPORTANT: PRIMARY_PRESSURE must describe the shift itself, not uncertainty about it.\n"
                "IMPORTANT: PRIMARY_TRIGGER must name who controls the consolidation of the new structure.\n"
                "IMPORTANT: WATCH signals must represent counterforces (what could SLOW or STOP the shift).\n"
                "Homepage must feel: directional, forward-looking, not fragmented.\n"
                "Elevate: cross-actor confirmations, supply chain shifts, public declarations.\n"
            )
        elif step_back_count >= 2:
            regime_note = (
                f"\nREGIME: FRAGMENTATION — LEAN_IN=0, STEP_BACK={step_back_count}.\n"
                "The system is active but not consolidating. No narrative is dominant.\n"
                "This is NOT a weak or thin day — do NOT use thin-day language.\n"
                "IMPORTANT: Even in fragmentation there is usually a directional rotation.\n"
                "Look for which layer is losing attention (away_from) and which is forming (toward).\n"
                "STEP_BACK signals = important but not yet confirmed — NOT fading.\n"
            )
        else:
            regime_note = (
                f"\nREGIME: THIN DAY — LEAN_IN=0, STEP_BACK={step_back_count}. "
                "Genuinely low activity. Frame as pre-formation or quiet.\n"
            )
    else:
        regime_note = ""

    user_msg = (
        f"Date: {date}{regime_note}\n\n"
        "Homepage signals (ranked by importance):\n\n"
        + "\n\n".join(lines)
    )

    client = _get_client()
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        max_tokens=900,
        messages=[
            {"role": "system", "content": _COMPOSITION_SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        response_format=HomepageComposition,
    )
    return response.choices[0].message.parsed


# ── Mechanical fallback ────────────────────────────────────────────────────────

def _mechanical_note(sig: dict) -> str:
    """Generate a note without LLM when --no-llm is set."""
    bucket   = sig.get("_bucket", "be_careful")
    momentum = sig.get("momentum", "FLAT")
    family   = sig.get("narrative_family", "general")

    if bucket == "lean_in":
        return "Strong signal forming — monitor for continuation."
    if bucket == "step_back":
        return "Important but not yet confirmed — needs reinforcement across more actors to become durable."
    if bucket == "ignore":
        return "High volume, low directional signal — context only."
    if momentum == "RISING" and family == "infrastructure":
        return "Infrastructure delivery is building — watch for cross-actor confirmation."
    if momentum == "RISING":
        return "Momentum is present but not yet broadly confirmed."
    if momentum == "FALLING":
        return "Attention is declining — assess whether the narrative still holds."
    if family == "market_sentiment":
        return "Market noise is elevated — signal context, not a call to act."
    return "Watch for a second confirmation window before treating this as durable."


def _fallback_composition(
    selected_signals:      list[dict],
    has_lean_in:           bool,
    step_back_count:       int = 0,
    is_emerging_expansion: bool = False,
) -> HomepageComposition:
    """Mechanical composition for --no-llm mode."""
    has_infra       = any(
        s.get("narrative_family") in ("infrastructure", "compute_capacity", "energy_power")
        for s in selected_signals
    )
    has_model_layer = any(
        s.get("narrative_family") == "model_layer"
        for s in selected_signals
    )
    is_fragmentation = not has_lean_in and step_back_count >= 2

    # Mechanical spine detection
    if has_infra and has_model_layer:
        spine = NarrativeSpine(
            away_from="the model layer — attention declining across multiple actors",
            toward="the infrastructure delivery layer — compute and delivery signals forming",
            uncertainty="delivery layer not yet confirmed; no hyperscaler commitment landed",
        )
    elif has_infra:
        spine = NarrativeSpine(
            away_from="prior narratives — no dominant theme carrying forward",
            toward="the infrastructure layer — compute and delivery signals building",
            uncertainty="infrastructure narrative not yet cross-actor confirmed",
        )
    else:
        spine = NarrativeSpine(
            away_from="no clear layer identified",
            toward="no clear layer identified",
            uncertainty="insufficient signal to determine rotation direction",
        )

    if has_lean_in:
        top_read         = "Narratives forming. Watch the infrastructure layer."
        system_state     = "Forming"
        explanation      = "Infrastructure and compute signals are reinforcing across multiple actors."
        primary_pressure = "Infrastructure delivery is forming, but cross-actor confirmation has not landed."
        primary_trigger  = "If Amazon, Microsoft, or Google announces major AI infrastructure capex → delivery layer rotation confirms as dominant narrative."
    elif is_emerging_expansion:
        top_read         = "A structural shift is forming across layers. Direction is visible; consolidation is not yet locked in."
        system_state     = "Emerging — structural shift forming"
        explanation      = "Cross-layer signals are pointing to the same transition simultaneously."
        primary_pressure = "A structural shift is forming across model, infrastructure, and deployment layers simultaneously."
        primary_trigger  = "If the leading actors in the shift confirm at scale → the new structure becomes the dominant narrative."
    elif is_fragmentation:
        top_read         = "Multiple narratives active. None is dominant yet."
        system_state     = "Fragmented — no leader"
        explanation      = (
            f"The system is dispersed across {step_back_count} active narratives — "
            "attention is real, but no single theme is claiming direction."
        )
        primary_pressure = "Competing narratives are forming, but no actor has committed enough to define the system."
        primary_trigger  = "If Amazon, Microsoft, or Google commits to large-scale AI infrastructure capex → infrastructure becomes the dominant narrative."
    elif has_infra:
        top_read         = "Infrastructure is taking shape, but conviction is still thin."
        system_state     = "Pre-formation"
        explanation      = "Infrastructure and compute signals are present but not yet reinforced across the system."
        primary_pressure = "Infrastructure is building, but without demand confirmation, expansion is not locked in."
        primary_trigger  = "If a major hyperscaler confirms AI infrastructure spending → infrastructure narrative consolidates."
    elif selected_signals:
        top_read         = "No narrative has confirmed. System is quiet."
        system_state     = "Quiet"
        explanation      = "Low activity. No signal has formed with enough reinforcement to act on."
        primary_pressure = "No dominant tension — system is in a quiet phase."
        primary_trigger  = ""
    else:
        top_read         = "No high-signal narratives today."
        system_state     = "Quiet"
        explanation      = "No signals passed the relevance threshold today."
        primary_pressure = "No dominant tension — system is in a quiet phase."
        primary_trigger  = ""

    notes = [
        _NoteItem(
            narrative=s.get("narrative", s.get("title", "")),
            headline="",  # fallback: no headline override
            summary="",   # fallback: keep existing cluster summary
            note=s.get("notes") or _mechanical_note(s),
        )
        for s in selected_signals
    ]

    return HomepageComposition(
        spine=spine,
        primary_pressure=primary_pressure,
        primary_trigger=primary_trigger,
        top_read=top_read,
        explanation=explanation,
        system_state=system_state,
        signal_notes=notes,
        watch_signals=[],
    )


# ── Note injection ──────────────────────────────────────────────────────────────

def _inject_notes(
    selected_signals: list[dict],
    composition: HomepageComposition,
) -> list[dict]:
    """
    Inject generated headline, summary, and note back into selected signals by title matching.
    Uses partial word-overlap fallback to tolerate LLM rephrasing.
    """
    note_map: dict[str, _NoteItem] = {}
    for item in composition.signal_notes:
        note_map[item.narrative.lower().strip()] = item

    def _find_item(title: str) -> _NoteItem | None:
        key = title.lower().strip()
        if key in note_map:
            return note_map[key]
        words = set(key.split())
        best, best_score = None, 0
        for k, v in note_map.items():
            overlap = len(words & set(k.split()))
            if overlap > best_score:
                best, best_score = v, overlap
        return best if best_score >= 2 else None

    enriched = []
    for sig in selected_signals:
        title = sig.get("narrative", sig.get("title", ""))
        item  = _find_item(title)
        patch: dict = {}
        if item:
            if item.headline:
                patch["headline"] = item.headline
            if item.summary:
                patch["summary"] = item.summary
            patch["notes"] = item.note or sig.get("notes") or _mechanical_note(sig)
        else:
            patch["notes"] = sig.get("notes") or _mechanical_note(sig)
        enriched.append({**sig, **patch})
    return enriched


# ── Deployability check ─────────────────────────────────────────────────────────

def check_deployable(package: dict) -> tuple[bool, list[str]]:
    """
    Quality gate before homepage goes live.
    Returns (is_deployable, warnings).

    Checks:
      - top_read is present and non-trivial
      - explanation is present
      - at least 3 signals selected
      - no visible signal has a weak/raw title
      - no visible signal has empty notes
    """
    warnings: list[str] = []

    if not package.get("top_read", "").strip() or len(package["top_read"]) < 15:
        warnings.append("top_read is missing or too short")

    if not package.get("explanation", "").strip() or len(package["explanation"]) < 20:
        warnings.append("explanation is missing or too short")

    signals = package.get("selected_signals", [])
    if len(signals) < 2:
        warnings.append(f"Only {len(signals)} signal(s) selected — page may feel sparse")

    for sig in signals:
        title = sig.get("narrative", sig.get("title", ""))
        if is_weak_title(title):
            warnings.append(f"Weak title on homepage: '{title[:60]}'")
        if not sig.get("notes", "").strip():
            warnings.append(f"Empty notes for: '{title[:60]}'")

    return len(warnings) == 0, warnings


# ── Main entry ──────────────────────────────────────────────────────────────────

def compose_homepage(
    sections:    dict[str, list[dict]],
    labeled:     list[dict],
    momentum_by: dict[str, str],
    date:        str,
    use_llm:     bool = True,
) -> dict:
    """
    Editorial composition layer. Call after select_and_rank_clusters.

    Returns a homepage package:
      {
        "top_read":         str,
        "explanation":      str,
        "system_state":     str,
        "selected_signals": list[dict],   # enriched with notes, _bucket set
        "is_deployable":    bool,
        "warnings":         list[str],
      }

    Does NOT modify classified sections or underlying signal data.
    """
    has_lean_in           = bool(sections.get("lean_in"))
    step_back_count       = len(sections.get("step_back", []))
    is_fragmentation      = not has_lean_in and step_back_count >= 2

    # Pre-select to run emergence detection against actual selected signals
    max_signals_pre = 5 if is_fragmentation else 8
    min_signals_pre = 3 if is_fragmentation else 4
    selected = select_homepage_signals(sections, labeled,
                                       max_signals=max_signals_pre, min_signals=min_signals_pre)

    is_emerging_expansion = (
        not has_lean_in
        and detect_emerging_expansion(selected, step_back_count)
    )

    if is_emerging_expansion:
        print(f"  [compose] EMERGING_EXPANSION detected"
              f" (step_back={step_back_count}, cross-layer, forward-looking)")

    if use_llm and selected:
        try:
            composition = compose_with_llm(
                selected, has_lean_in, step_back_count, date,
                is_emerging_expansion=is_emerging_expansion,
            )
        except Exception as exc:
            print(f"  [compose] LLM failed ({exc}), using mechanical fallback")
            composition = _fallback_composition(
                selected, has_lean_in, step_back_count,
                is_emerging_expansion=is_emerging_expansion,
            )
    else:
        composition = _fallback_composition(
            selected, has_lean_in, step_back_count,
            is_emerging_expansion=is_emerging_expansion,
        )

    enriched = _inject_notes(selected, composition)

    regime = (
        "EMERGING_EXPANSION" if is_emerging_expansion
        else "EXPANSION"     if has_lean_in
        else "FRAGMENTATION" if is_fragmentation
        else "QUIET"
    )

    package: dict[str, Any] = {
        "regime":           regime,
        "primary_pressure": composition.primary_pressure,
        "primary_trigger":  composition.primary_trigger,
        "top_read":         composition.top_read,
        "explanation":      composition.explanation,
        "system_state":     composition.system_state,
        "selected_signals": enriched,
        "watch_signals": [
            {
                "headline": w.headline,
                "actors":   w.actors,
                "summary":  w.summary,
                "note":     w.note,
                "trigger":  w.trigger,
            }
            for w in (composition.watch_signals or [])
        ],
        "spine": {
            "away_from":   composition.spine.away_from,
            "toward":      composition.spine.toward,
            "uncertainty": composition.spine.uncertainty,
        },
    }

    is_deployable, warnings = check_deployable(package)
    package["is_deployable"] = is_deployable
    package["warnings"]      = warnings

    return package
