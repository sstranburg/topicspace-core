#!/usr/bin/env python3
"""
generate_crypto_compass.py

End-to-end crypto Attention Map:
  1. Load events from crypto_ecosystem.jsonl
  2. Window events into two halves to compute actor momentum
  3. Cluster event titles by embedding → find narrative themes
  4. Label clusters with Claude (llm_naming.py)
  5. Classify narratives into compass sections
  6. Output compass (text or JSON)

Usage:
  venv/bin/python scripts/generate_crypto_compass.py
  venv/bin/python scripts/generate_crypto_compass.py --json
  venv/bin/python scripts/generate_crypto_compass.py --no-llm   # skip labeling, use top terms
"""

import sys
import json
import argparse
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import normalize
from sentence_transformers import SentenceTransformer

from src.event import Event, events_from_jsonl_file
from src.llm_naming import (
    build_naming_evidence,
    build_naming_prompt,
    generate_llm_name,
    validate_llm_label,
    validate_llm_label_faithfulness,
    _get_client,
)

# ── Config ────────────────────────────────────────────────────────────────────

EVENTS_FILE = Path(__file__).parent.parent / "data" / "normalized" / "crypto_ecosystem.jsonl"

ACTORS = [
    "BTC", "ETH", "SOL", "AVAX", "MATIC", "ARB", "OP", "TIA",
    "UNI", "AAVE", "MKR",
    "RNDR", "TAO", "AKT", "FET",
    "PENDLE", "ETHFI",
    "WLD", "FIL", "NEAR",
]

# Split period into early / late halves for momentum calculation
SPLIT_DATE = "2026-03-17"   # splits dataset: sparse early (Mar 3-16) vs dense late (Mar 17+)

N_CLUSTERS = 10             # narrative clusters to find
MIN_CLUSTER_EVENTS = 2      # ignore tiny clusters
MAX_COMPASS_ITEMS = 3       # items per section

DIVERGE_GAP = 0.3           # density-drop fraction to qualify as "fragmented"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_events() -> list[Event]:
    if not EVENTS_FILE.exists():
        print(f"[ERROR] {EVENTS_FILE} not found. Run fetch_crypto.py first.")
        sys.exit(1)
    events = events_from_jsonl_file(str(EVENTS_FILE))
    print(f"Loaded {len(events)} events from {EVENTS_FILE.name}")
    return events


# ── Windowing ─────────────────────────────────────────────────────────────────

def split_events(events: list[Event], split_iso: str):
    """Split events into early (before split) and late (after split) periods."""
    split_dt = datetime.fromisoformat(split_iso).replace(tzinfo=timezone.utc)
    early, late = [], []
    for e in events:
        dt = datetime.fromisoformat(e.timestamp.replace("Z", "+00:00"))
        (early if dt < split_dt else late).append(e)
    return early, late


def actor_density(events: list[Event]) -> dict[str, float]:
    """Return actor mention rate (count / total events in window)."""
    counts: Counter = Counter()
    for e in events:
        for a in e.actors:
            if a in set(ACTORS):
                counts[a] += 1
    total = max(len(events), 1)
    return {a: c / total for a, c in counts.items()}


def actor_counts(events: list[Event]) -> dict[str, int]:
    """Return raw actor mention counts."""
    counts: Counter = Counter()
    for e in events:
        for a in e.actors:
            if a in set(ACTORS):
                counts[a] += 1
    return dict(counts)


# ── Pre-tagging ───────────────────────────────────────────────────────────────

_BUCKET_RULES: list[tuple[str, list[str]]] = [
    ("btc_institutional", [
        "etf", "blackrock", "cftc", "sec ", "morgan stanley", "vanguard", "fidelity",
        "treasury", "strategy acquires", "saylor", "microstrategy", "state reserve",
        "senate", "congress", "legislature", "regulation", "commodity", "msbt",
    ]),
    ("btc_macro", [
        " fed ", "federal reserve", "rate cut", "interest rate", "inflation", "bonds",
        "gold", "macro", "recession", "iran", "geopolit", "war", "oil crisis",
        "private credit", "yield curve", "dollar",
    ]),
    ("btc_sentiment", [
        "panic", "fear", "am i screwed", "what do i do", "should i sell", "stop panicking",
        "emotionally", "bear trap", "bull run", "wen moon", "hodl", "dca",
        "am i too late", "just bought", "first time", "beginner",
    ]),
    ("btc_technical", [
        "quantum", "genesis block", "optech", "mining difficulty", "hash rate",
        "lightning", "taproot", "ordinal", "inscription", "cold storage", "multisig",
        "wallet recover", "lost wallet", "private key",
    ]),
]

_OTHER_BUCKETS: list[tuple[str, list[str]]] = [
    ("tao_bittensor", ["bittensor", " tao ", "subnet", "templar", "sn3"]),
    ("eth_ecosystem",  ["ethereum", " eth ", "erc-", "eip-", "vitalik", "l2 ", "layer 2",
                        "arbitrum", "optimism", "base chain", "rollup"]),
    ("sol_ecosystem",  ["solana", " sol ", "phantom", "backpack", "sealevel"]),
    ("defi_security",  ["hack", "exploit", "scam", "stolen", "vulnerability", "drain",
                        "fake stablecoin", "address poison"]),
]


def pre_tag_event(event: Event) -> str:
    """Assign a pre-cluster bucket based on keyword heuristics."""
    text = event.title.lower()

    # BTC-primary actor gets refined buckets
    if "BTC" in event.actors or not event.actors:
        for bucket, keywords in _BUCKET_RULES:
            if any(kw in text for kw in keywords):
                return bucket

    # Non-BTC actors get their own buckets
    for bucket, keywords in _OTHER_BUCKETS:
        if any(kw in text for kw in keywords):
            return bucket

    return "other"


_BUCKET_TO_FAMILY: dict[str, str] = {
    "btc_institutional": "institutional",
    "btc_macro":         "macro",
    "btc_sentiment":     "retail_sentiment",
    "btc_technical":     "technical_product",
    "tao_bittensor":     "ecosystem_structure",
    "eth_ecosystem":     "ecosystem_structure",
    "sol_ecosystem":     "ecosystem_structure",
    "defi_security":     "security_exploit",
    "other":             "general",
}


# ── Clustering ────────────────────────────────────────────────────────────────

def _build_cluster_dict(cid: str, cluster_events: list[Event], bucket: str = "other") -> dict:
    """Build the standard cluster dict from a list of events."""
    actor_counter: Counter = Counter()
    for e in cluster_events:
        for a in e.actors:
            if a in set(ACTORS):
                actor_counter[a] += 1
    top_actors = [a for a, _ in actor_counter.most_common(3)]
    titles_in = [e.title for e in cluster_events]

    stop = {"that","this","with","from","have","will","been","they","their","more",
            "also","than","when","into","some","over","such","even","most","both",
            "then","which","these","just","about","what","bitcoin","crypto","ethereum"}
    word_counts: Counter = Counter()
    for t in titles_in:
        for w in t.lower().split():
            if len(w) > 3 and w not in stop:
                word_counts[w] += 1
    top_terms = [w for w, _ in word_counts.most_common(8)]

    bigram_list = []
    for t in titles_in[:20]:
        words = t.lower().split()
        for j in range(len(words) - 1):
            bg = f"{words[j]} {words[j+1]}"
            if len(bg) > 6:
                bigram_list.append(bg)
    top_bigrams = [b for b, _ in Counter(bigram_list).most_common(4)]

    source_counts = Counter(e.source for e in cluster_events)
    total = len(cluster_events)
    reddit_pct = int(source_counts.get("reddit", 0) / total * 100)
    news_pct   = int(source_counts.get("cryptopanic", 0) / total * 100)
    source_mix = ("Reddit-heavy" if reddit_pct >= 70
                  else "News-heavy" if news_pct >= 70
                  else "Mixed")
    dominant_source  = max(source_counts, key=source_counts.get) if source_counts else "unknown"
    cross_source_count = len(source_counts)   # distinct source types present

    # source_pct: percent breakdown for LLM context
    source_pct = {src: round(cnt / total * 100) for src, cnt in source_counts.items()}

    return {
        "cluster_id":         cid,
        "events":             cluster_events,
        "actors":             top_actors,
        "top_terms":          top_terms,
        "top_bigrams":        top_bigrams,
        "representative_title":  titles_in[0],
        "representative_titles": titles_in[:5],
        "source_mix":         source_mix,
        "source_pct":         source_pct,
        "dominant_source":    dominant_source,
        "cross_source_count": cross_source_count,
        "narrative_family":   _BUCKET_TO_FAMILY.get(bucket, "general"),
        "size":               len(cluster_events),
    }


def _embed_and_cluster(events: list[Event], n: int, model: SentenceTransformer,
                       id_prefix: str, bucket: str = "other") -> list[dict]:
    """Embed + cluster a bucket of events, return cluster dicts."""
    if len(events) < MIN_CLUSTER_EVENTS:
        return []
    n = min(n, max(1, len(events) // 2))
    if n < 2:
        return [_build_cluster_dict(f"{id_prefix}_0", events, bucket=bucket)]

    emb = normalize(model.encode([e.title for e in events], show_progress_bar=False))
    labels = AgglomerativeClustering(n_clusters=n, metric="cosine", linkage="average").fit_predict(emb)
    sub_buckets: dict[int, list] = defaultdict(list)
    for event, lbl in zip(events, labels):
        sub_buckets[int(lbl)].append(event)
    return [
        _build_cluster_dict(f"{id_prefix}_{cid}", evts, bucket=bucket)
        for cid, evts in sub_buckets.items()
        if len(evts) >= MIN_CLUSTER_EVENTS
    ]


def cluster_titles(events: list[Event], n_clusters: int = N_CLUSTERS):
    """
    Pre-tag events by narrative type, then embed+cluster within each bucket.
    Prevents BTC noise from drowning out institutional/macro/technical signals.
    """
    # 1. Tag every event
    tagged: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        tagged[pre_tag_event(e)].append(e)

    bucket_sizes = {b: len(evts) for b, evts in tagged.items()}
    print(f"Embedding {len(events)} titles…")
    print(f"  Buckets: { {b: n for b, n in sorted(bucket_sizes.items(), key=lambda x: -x[1])} }")

    model = SentenceTransformer("all-MiniLM-L6-v2")

    # 2. Cluster within each bucket; allocate sub-clusters proportionally
    result = []
    for bucket, bucket_events in sorted(tagged.items(), key=lambda x: -len(x[1])):
        share = len(bucket_events) / len(events)
        sub_n = max(1, round(n_clusters * share))
        clusters = _embed_and_cluster(bucket_events, sub_n, model, bucket, bucket=bucket)
        result.extend(clusters)

    result.sort(key=lambda c: -c["size"])
    return result


# ── LLM labeling ─────────────────────────────────────────────────────────────

def label_cluster(cluster: dict, use_llm: bool = True) -> dict:
    """Generate a narrative label for a cluster via Claude (or fallback to top terms)."""
    fallback_label = " ".join(cluster["top_terms"][:4]).title()

    if not use_llm:
        return {**cluster, "narrative": fallback_label, "explanation": "", "label_source": "terms"}

    evidence = {
        "storm_id": f"crypto_cluster_{cluster['cluster_id']}",
        "actors": cluster["actors"],
        "state": "stable",
        "event_count": cluster["size"],
        "dominant_cluster_ratio": 0.7,
        "themes": cluster["top_terms"][:5],
        "bigrams": cluster["top_bigrams"],
        "domain_phrases": [],
        "entity_actions": [],
        "dominant_cluster_terms": cluster["top_terms"][:5],
        "dominant_cluster_bigrams": cluster["top_bigrams"],
        "representative_titles": cluster.get("representative_titles", [cluster["representative_title"]]),
        "all_titles_count": cluster["size"],
    }

    result = generate_llm_name(evidence)
    if result["llm_used"] and result["llm_headline"]:
        headline = result["llm_headline"]
        one_liner = result["llm_one_liner"] or ""
        valid, _, _ = validate_llm_label(headline, one_liner, fallback_label)
        faithful, _, _ = validate_llm_label_faithfulness(headline, evidence)
        if valid and faithful:
            return {**cluster, "narrative": headline, "explanation": one_liner, "label_source": "llm"}
        else:
            print(f"  [label] cluster {cluster['cluster_id']}: LLM label rejected, using terms")

    return {**cluster, "narrative": fallback_label, "explanation": "", "label_source": "terms"}


# ── Compass classification ────────────────────────────────────────────────────

CLASSIFICATION_SYSTEM_PROMPT = """\
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
Do NOT restate inputs.


STEP 1 — VALIDATE NARRATIVE

Before scoring, determine:

Is this a real narrative or just grouped events?

A valid narrative must:
- express one clear shared idea
- be directionally consistent
- not be a generic topic (e.g. "Bitcoin news")

If not a real narrative:
→ classify as IGNORE


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
- FLAT: otherwise


STEP 3 — APPLY SOURCE CONTEXT

Interpret source quality:

High-trust sources:
- filings
- official announcements
- transcripts
- major news

Mid-trust:
- curated aggregators

Low-trust:
- reddit
- social chatter

Source rules:

- A Reddit-heavy cluster alone is not sufficient for LEAN_IN
- Cross-source reinforcement (multiple source types saying same thing) increases confidence
- A small number of high-trust events can outweigh large low-trust volume

Reddit classification rules (CRITICAL):

When Reddit is the dominant source (dominant_source = reddit OR reddit >= 70%):
- Default toward BE_CAREFUL, STEP_BACK, or IGNORE
- Require cross-source reinforcement before LEAN_IN is permitted
- If Reddit volume is HIGH but reinforcement is LOW → classify as IGNORE, not STEP_BACK
  (High Reddit volume without structural reinforcement is noise, not a declining important narrative.
   STEP_BACK implies "this was structurally important and is now fading." That logic does not apply
   to pure Reddit volume spikes.)
- If Reddit is the only source and reinforcement is MEDIUM → BE_CAREFUL at most

Reddit IS useful for detecting:
- Early narrative emergence (appropriate bucket: BE_CAREFUL with rising momentum)
- Emotionally reactive or crowded narratives (appropriate bucket: BE_CAREFUL or IGNORE)
- Attention spreading across adjacent actors (useful signal context, not classification basis)

Reddit is NOT sufficient alone for:
- HIGH confidence structural calls
- LEAN_IN (requires cross-source confirmation)
- STEP_BACK (requires that the narrative had prior structural weight)


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
- AND narrative had prior structural weight (not pure Reddit volume)

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

Case D — Reddit-dominant early signal:
- dominant_source = reddit
- Momentum = RISING
- Reinforcement = MEDIUM
- Use BE_CAREFUL, not LEAN_IN — requires cross-source confirmation

IGNORE:
- Attention = LOW
- OR not a real narrative
- OR dominated by low-signal chatter
- OR dominant_source = reddit AND reinforcement = LOW (volume without formation = noise)


HARD CONSTRAINTS

- If momentum = FALLING → cannot be LEAN_IN
- If reinforcement = LOW → cannot be LEAN_IN
- If dominant_source = reddit AND cross_source_count < 2 → cannot be LEAN_IN
- If dominant_source = reddit AND reinforcement = LOW → must be IGNORE
- If dominant_source = reddit AND cross_source_count < 2 → default to BE_CAREFUL or IGNORE
- If insufficient_data = true → cannot be LEAN_IN
- If unclear → default to BE_CAREFUL or IGNORE


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
- early or unclear signal


WRITING STYLE (CRITICAL)

- Max 12 words per summary
- 1 sentence per field
- No jargon
- No metrics
- No explanation of scoring
- No uncertainty language ("might", "possibly")

Use:
- concrete phrasing
- clear descriptors ("retail panic", "institutional flows", "conflicting narratives")

Avoid:
- "interest is fading"
- "momentum declining"
- "this suggests"

The "action" field must be a plain imperative sentence telling the reader what to do.
Examples: "Pay close attention.", "Skip this.", "Wait before acting.", "Watch for confirmation."
Do NOT use the classification name (LEAN_IN, BE_CAREFUL, etc.) as the action.


GOAL

The output must be understandable in under 5 seconds.

It must feel like a decision, not analysis.
"""


class CompassEntry(BaseModel):
    narrative: str
    summary: str
    action: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class CompassClassification(BaseModel):
    lean_in: list[CompassEntry]
    step_back: list[CompassEntry]
    be_careful: list[CompassEntry]
    ignore: list[CompassEntry]


def _attention_level(n: int) -> str:
    return "HIGH" if n > 20 else ("MEDIUM" if n >= 5 else "LOW")


def _momentum_label(cluster: dict, early_density: dict, late_density: dict,
                    early_counts: dict, min_early: int = 3) -> str:
    actors = cluster["actors"]
    if not actors:
        return "FLAT"
    # If primary actors have too few early events, momentum is unreliable
    primary = actors[0]
    if early_counts.get(primary, 0) < min_early:
        return "INSUFFICIENT_DATA"
    # Use primary actor only — secondary actors (e.g. BTC with 1 early event) skew the result
    delta = late_density.get(primary, 0) - early_density.get(primary, 0)
    if delta > 0.05:
        return "RISING"
    elif delta < -0.03:
        return "FALLING"
    return "FLAT"


def classify_with_llm(clusters: list[dict], early_density: dict, late_density: dict,
                      early_counts: dict | None = None) -> dict:
    """Classify narrative clusters using LLM with strict compass rules."""
    # Format each cluster as input for the LLM
    cluster_inputs = []
    for c in clusters:
        attention = _attention_level(c["size"])
        momentum = _momentum_label(c, early_density, late_density, early_counts or {})
        events = c.get("events", [])
        sample_size = min(15, len(events))
        # For large clusters sample from start, middle, and end to show diversity
        if len(events) > 15:
            step = len(events) // 15
            sampled = events[::step][:15]
        else:
            sampled = events[:15]
        event_lines = [
            f"  [{e.timestamp[:10]}] [{','.join(e.actors)}] {e.title}"
            for e in sampled
        ]
        src_pct = c.get("source_pct", {})
        src_pct_str = "  ".join(f"{s}={p}%" for s, p in sorted(src_pct.items(), key=lambda x: -x[1]))
        cluster_inputs.append(
            f"Narrative: \"{c['narrative']}\"\n"
            f"narrative_family: {c.get('narrative_family', 'general')}\n"
            f"Actors: {', '.join(c['actors']) or 'unknown'}\n"
            f"event_count: {c['size']}\n"
            f"source_mix: {src_pct_str or c.get('source_mix', 'unknown')}\n"
            f"dominant_source: {c.get('dominant_source', 'unknown')}\n"
            f"cross_source_count: {c.get('cross_source_count', 1)}\n"
            f"insufficient_data: {'true' if momentum == 'INSUFFICIENT_DATA' else 'false'}\n"
            f"momentum: {momentum}\n"
            f"Events (sample of {len(sampled)}/{len(events)}):\n"
            + "\n".join(event_lines)
        )

    user_message = "Classify the following narrative clusters:\n\n" + "\n\n---\n\n".join(cluster_inputs)

    client = _get_client()
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        max_tokens=1500,
        messages=[
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        response_format=CompassClassification,
    )
    result = response.choices[0].message.parsed

    # Build per-narrative lookup tables for post-processing
    # Keyed by lowercase stripped name to tolerate minor LLM rephrasing
    attention_by_narrative = {c["narrative"].lower().strip(): _attention_level(c["size"]) for c in clusters}
    momentum_by_narrative  = {
        c["narrative"].lower().strip(): _momentum_label(c, early_density, late_density, early_counts or {})
        for c in clusters
    }
    dominant_src_by_narrative = {c["narrative"].lower().strip(): c.get("dominant_source", "unknown") for c in clusters}
    cross_src_by_narrative    = {c["narrative"].lower().strip(): c.get("cross_source_count", 1) for c in clusters}

    def _lookup(d: dict, narrative: str, default):
        key = narrative.lower().strip()
        if key in d:
            return d[key]
        # Partial match fallback: find the cluster whose name shares the most words
        words = set(key.split())
        best, best_score = default, 0
        for k, v in d.items():
            overlap = len(words & set(k.split()))
            if overlap > best_score:
                best, best_score = v, overlap
        return best

    def _force_be_careful(entry, reason: str) -> dict:
        d = entry.model_dump()
        d["confidence"] = "LOW"
        d["_forced"] = reason   # internal debug tag, stripped before render
        return d

    lean_in_final  = []
    step_back_final = []
    be_careful_extra = []

    # Post-processing rules applied to all sections including ignore
    all_entries = (
        [(e, "lean_in")    for e in result.lean_in] +
        [(e, "step_back")  for e in result.step_back] +
        [(e, "be_careful") for e in result.be_careful] +
        [(e, "ignore")     for e in result.ignore]
    )
    ignore_final = []
    for e, section in all_entries:
        momentum   = _lookup(momentum_by_narrative,    e.narrative, "FLAT")
        attn       = _lookup(attention_by_narrative,   e.narrative, "MEDIUM")
        dom_src    = _lookup(dominant_src_by_narrative, e.narrative, "unknown")
        cross_src  = _lookup(cross_src_by_narrative,   e.narrative, 1)
        is_reddit_dominant = (dom_src == "reddit" and cross_src < 2)

        # Rule 1: INSUFFICIENT_DATA → force BE_CAREFUL / LOW regardless of LLM decision
        if momentum == "INSUFFICIENT_DATA" and section in ("lean_in", "step_back", "ignore"):
            be_careful_extra.append(_force_be_careful(e, "insufficient_data"))
        # Rule 2: STEP_BACK requires HIGH attention
        elif section == "step_back" and attn != "HIGH":
            be_careful_extra.append(_force_be_careful(e, "step_back_not_high_attn"))
        # Rule 3: Reddit-dominant + no cross-source → enforce hard floor
        # LEAN_IN: downgrade to BE_CAREFUL (Reddit cannot confirm structural narratives alone)
        elif is_reddit_dominant and section == "lean_in":
            be_careful_extra.append(_force_be_careful(e, "reddit_dominant_no_cross_source"))
        # STEP_BACK: downgrade to IGNORE if low confidence
        # (STEP_BACK implies "was structurally important"; pure Reddit volume spikes don't qualify)
        elif is_reddit_dominant and section == "step_back" and e.confidence == "LOW":
            ignore_final.append(e.model_dump())
        elif section == "lean_in":
            lean_in_final.append(e.model_dump())
        elif section == "step_back":
            step_back_final.append(e.model_dump())
        elif section == "be_careful":
            be_careful_extra.append(e.model_dump())
        else:
            ignore_final.append(e.model_dump())

    # Deduplicate: keep first occurrence by priority order (lean_in > step_back > be_careful > ignore)
    seen: set[str] = set()
    def dedup(items: list[dict]) -> list[dict]:
        out = []
        for item in items:
            key = item["narrative"].lower().strip()
            if key not in seen:
                seen.add(key)
                out.append({k: v for k, v in item.items() if not k.startswith("_")})
        return out

    return {
        "lean_in":    dedup(lean_in_final),
        "step_back":  dedup(step_back_final),
        "be_careful": dedup(be_careful_extra),
        "ignore":     dedup(ignore_final),
    }


def classify_compass_fallback(clusters: list[dict], early_density: dict, late_density: dict,
                              early_counts: dict | None = None) -> dict:
    """Mechanical fallback classifier for --no-llm mode."""
    sections: dict = {"lean_in": [], "step_back": [], "be_careful": [], "ignore": []}
    for c in clusters:
        momentum   = _momentum_label(c, early_density, late_density, early_counts or {})
        attention  = _attention_level(c["size"])
        dom_src    = c.get("dominant_source", "unknown")
        cross_src  = c.get("cross_source_count", 1)
        is_reddit_dominant = (dom_src == "reddit" and cross_src < 2)

        entry = {
            "narrative": c["narrative"],
            "summary": f"Actors: {', '.join(c['actors'][:3])}. Source: {c.get('source_mix', 'Mixed')}.",
            "action": "Review manually.",
            "confidence": "LOW",
        }

        if is_reddit_dominant:
            # Reddit-dominant clusters: cap at BE_CAREFUL; if low attention → IGNORE
            # High Reddit volume ≠ structural importance
            if attention == "LOW" or momentum in ("FLAT", "FALLING"):
                sections["ignore"].append(entry)
            else:
                sections["be_careful"].append(entry)
        elif attention in ("MEDIUM", "HIGH") and momentum == "RISING":
            sections["lean_in"].append(entry)
        elif attention == "HIGH" and momentum in ("FLAT", "FALLING"):
            sections["step_back"].append(entry)
        elif attention in ("MEDIUM", "HIGH"):
            sections["be_careful"].append(entry)
        else:
            sections["ignore"].append(entry)
    return sections


# ── Rendering ─────────────────────────────────────────────────────────────────

def render_text(sections: dict, date: str) -> str:
    w = 64
    lines = [
        '╔' + '═' * w + '╗',
        '║' + f'  CRYPTO COMPASS  ·  {date}'.ljust(w) + '║',
        '╚' + '═' * w + '╝',
        '',
    ]
    defs = [
        ('lean_in',    '1  LEAN IN'),
        ('step_back',  '2  STEP BACK'),
        ('be_careful', '3  BE CAREFUL'),
        ('ignore',     '4  IGNORE'),
    ]
    for key, header in defs:
        items = sections.get(key, [])
        lines.append(header)
        lines.append('─' * len(header))
        if not items:
            lines.append('   (none)')
        else:
            for item in items:
                lines.append(f'   {item["narrative"]}  [{item["confidence"]}]')
                lines.append(f'      {item["summary"]}')
                lines.append(f'      → {item["action"]}')
                lines.append('')

    return '\n'.join(lines)


def render_json(sections: dict, date: str) -> str:
    clean = {
        k: [{f: v for f, v in item.items() if not f.startswith("_")} for item in items]
        for k, items in sections.items()
    }
    return json.dumps({"ecosystem": "crypto", "date": date, "compass": clean}, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate crypto Attention Map")
    parser.add_argument("--json",   action="store_true", help="Output JSON")
    parser.add_argument("--no-llm", action="store_true", help="Skip Claude labeling, use top terms")
    parser.add_argument("--out",    help="Write output to file")
    parser.add_argument("--clusters", type=int, default=N_CLUSTERS)
    args = parser.parse_args()

    date_str = datetime.today().strftime("%Y-%m-%d")

    # 1. Load
    events = load_events()

    # 2. Window
    early_events, late_events = split_events(events, SPLIT_DATE)
    early_density = actor_density(early_events)   # rates (0–1)
    late_density  = actor_density(late_events)
    early_raw     = actor_counts(early_events)    # raw counts for min_early check
    print(f"Early window: {len(early_events)} events | Late window: {len(late_events)} events")

    # 3. Cluster (use all events)
    clusters = cluster_titles(events, n_clusters=args.clusters)
    print(f"Clusters found: {len(clusters)} (≥{MIN_CLUSTER_EVENTS} events)")

    # 4. Label
    print("Labeling clusters…")
    labeled = [label_cluster(c, use_llm=not args.no_llm) for c in clusters]
    for c in labeled:
        src = "llm" if c["label_source"] == "llm" else "terms"
        print(f"  [{src}] {c['narrative']} (actors: {c['actors']}, n={c['size']})")

    # 5. Classify
    if args.no_llm:
        sections = classify_compass_fallback(labeled, early_density, late_density, early_raw)
    else:
        print("Classifying narratives…")
        sections = classify_with_llm(labeled, early_density, late_density, early_raw)

    # 6. Output
    output = render_json(sections, date_str) if args.json else render_text(sections, date_str)

    if args.out:
        Path(args.out).write_text(output)
        print(f"Written to {args.out}")
    else:
        print("\n" + output)


if __name__ == "__main__":
    main()
