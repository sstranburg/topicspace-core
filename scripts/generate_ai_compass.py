#!/usr/bin/env python3
"""
generate_ai_compass.py

End-to-end AI ecosystem Narrative Compass (parallel to generate_crypto_compass.py):
  1. Load events from tech_ecosystem.jsonl
  2. Window events into early / late halves for momentum
  3. Pre-tag events into AI narrative families before clustering
  4. Cluster within each family bucket (prevents NVDA noise from absorbing everything)
  5. Label clusters with Claude (llm_naming.py)
  6. Classify with shared LLM spine — AI-specific rules
  7. Output Narrative Compass (text or JSON)

Usage:
  venv/bin/python scripts/generate_ai_compass.py
  venv/bin/python scripts/generate_ai_compass.py --json
  venv/bin/python scripts/generate_ai_compass.py --no-llm
  venv/bin/python scripts/generate_ai_compass.py --out ai_compass.json --json
"""

import re
import sys
import json
import argparse
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import normalize
from sentence_transformers import SentenceTransformer

from src.event import Event, events_from_jsonl_file
from src.llm_naming import (
    generate_llm_name,
    validate_llm_label,
    validate_llm_label_faithfulness,
    _get_client,
)
from src.classify_narrative import (
    CompassClassification,
    _attention_level,
    build_system_prompt,
    post_process_classify_results,
    render_compass_text,
    render_compass_json,
)
from src.compose_homepage import compose_homepage, check_deployable

# ── Config ─────────────────────────────────────────────────────────────────────

EVENTS_FILE = Path(__file__).parent.parent / "data" / "normalized" / "tech_ecosystem.jsonl"

ACTORS = [
    "NVDA", "AMD", "TSM", "MSFT", "AMZN", "GOOGL", "ASML", "AVGO",
    "META", "ORCL", "ADBE", "CRM", "SNOW", "TSLA",
    "ARM", "SMCI", "DELL", "INTC", "MU", "CRWV", "NBIS",
    "PLTR", "OPENAI", "ANTHROPIC",
    "VRT", "ANET",
]

N_CLUSTERS        = 20    # narrative clusters to find
MIN_CLUSTER_EVENTS = 2    # ignore tiny clusters
MAX_COMPASS_ITEMS  = 3    # items per section

# ── Time-decay schedule ────────────────────────────────────────────────────────
# (max_age_days, weight)  — first matching bracket wins
_DECAY_SCHEDULE: list[tuple[int, float]] = [
    (2,   1.0),   # 0–2 days:  full weight
    (7,   0.7),   # 3–7 days:  near baseline
    (30,  0.4),   # 8–30 days: historical context
    (9999, 0.2),  # >30 days:  background noise
]

# Momentum comparison windows (days)
_HOT_WINDOW_DAYS  = 2   # recent signal
_NEAR_WINDOW_DAYS = 7   # prior baseline (days 3–7)


# ── Data loading ───────────────────────────────────────────────────────────────

def load_events() -> list[Event]:
    if not EVENTS_FILE.exists():
        print(f"[ERROR] {EVENTS_FILE} not found. Run fetch_today.py first.")
        sys.exit(1)
    events = events_from_jsonl_file(str(EVENTS_FILE))
    print(f"Loaded {len(events)} events from {EVENTS_FILE.name}")
    return events


# ── Time-decay helpers ─────────────────────────────────────────────────────────

def _event_age_days(event: Event, today: datetime) -> float:
    try:
        ts = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        return max(0.0, (today - ts).total_seconds() / 86400)
    except Exception:
        return 9999.0


def _decay_weight(age_days: float) -> float:
    for max_age, weight in _DECAY_SCHEDULE:
        if age_days <= max_age:
            return weight
    return 0.2


def _is_velocity_source(event: Event) -> bool:
    """Returns False for amplification sources — excluded from velocity/momentum."""
    return (
        event.source != "amplification"
        and event.metadata.get("source_tier") != "amplification"
        and event.metadata.get("source_type") != "amplification"
    )


# ── Windowing ──────────────────────────────────────────────────────────────────

def partition_windows(events: list[Event], today: datetime) -> tuple[list[Event], list[Event]]:
    """
    Returns (hot_events, near_events) for momentum calculation.
      hot  = 0–2 days ago,  non-amplification only
      near = 3–7 days ago,  non-amplification only
    """
    hot, near = [], []
    for e in events:
        if not _is_velocity_source(e):
            continue
        age = _event_age_days(e, today)
        if age <= _HOT_WINDOW_DAYS:
            hot.append(e)
        elif age <= _NEAR_WINDOW_DAYS:
            near.append(e)
    return hot, near


def weighted_actor_density(events: list[Event], today: datetime) -> dict[str, float]:
    """
    Decay-weighted actor density.  Amplification sources already excluded by caller.
    Returns fraction of total weight attributed to each actor.
    """
    weights: Counter = Counter()
    total_w = 0.0
    for e in events:
        age = _event_age_days(e, today)
        w   = _decay_weight(age)
        total_w += w
        for a in e.actors:
            if a in set(ACTORS):
                weights[a] += w
    if total_w == 0:
        return {}
    return {a: w / total_w for a, w in weights.items()}


def actor_counts(events: list[Event]) -> dict[str, int]:
    counts: Counter = Counter()
    for e in events:
        for a in e.actors:
            if a in set(ACTORS):
                counts[a] += 1
    return dict(counts)


# ── Pre-tagging ────────────────────────────────────────────────────────────────
# Routes events into coherent family buckets before clustering.
# Prevents NVDA noise from absorbing cross-actor infrastructure/model narratives.

_AI_BUCKET_RULES: list[tuple[str, list[str]]] = [
    # Physical infrastructure — most distinctive cross-actor theme
    ("infrastructure_delivery", [
        "data center", "datacenter", " capex", "power capacity", "rack deployment",
        "cooling", "colocation", "build-out", "buildout", "infrastructure spend",
        "hyperscale build", "megawatt", "gigawatt", "networking fabric",
        "lease data", "server farm", "campus build",
        "vertiv", "thermal management", "power distribution",
        "arista", "ethernet switch", "ai networking", "spine-leaf",
    ]),
    # Chip and memory supply chain
    ("semiconductor_supply", [
        " hbm", "high bandwidth memory", " wafer", " packaging",
        "semiconductor supply", "chip supply", "advanced packaging",
        "foundry capacity", " tsmc", " asml", "memory bandwidth",
        "manufacturing yield", "chip shortage", "node ",
    ]),
    # Compute demand and capacity constraints (distinct from infrastructure delivery)
    ("compute_capacity", [
        "capacity constraint", "gpu shortage", "gpu scarcity", "compute scarcity",
        "supply bottleneck", "hyperscaler demand", "inference capacity",
        "gpu availability", "compute demand", "capacity crunch", "gpu supply",
        "waitlist", "demand shortage",
    ]),
    # Model and research layer
    ("model_technology", [
        "model release", " llm ", "frontier model", "benchmark", "reasoning model",
        "pretraining", "open weights", "model architecture", "training run",
        "model race", "fine-tun", " gpt-", "model competition",
    ]),
    # Enterprise application and deployment
    ("enterprise_deployment", [
        "enterprise deployment", "enterprise contract", "agentforce", "ai agent",
        "workflow automation", "productivity gain", "customer adoption",
        "pilot program", "annual recurring revenue", "copilot deployment",
        "enterprise rollout", "b2b ai",
    ]),
    # Volatility and financial sentiment — catch this before it bleeds into above
    ("market_volatility", [
        "earnings beat", "earnings miss", "guidance cut", "guidance raise",
        "analyst downgrade", "analyst upgrade", "price target raised",
        "price target cut", "short interest", "sell-off on", "rally on earnings",
        "quarterly results", "q1 results", "q2 results", "q3 results", "q4 results",
    ]),
]

_AI_BUCKET_TO_FAMILY: dict[str, str] = {
    # Keyword-first buckets
    "infrastructure_delivery": "infrastructure",
    "semiconductor_supply":    "infrastructure",
    "compute_capacity":        "infrastructure",
    "model_technology":        "technology",
    "enterprise_deployment":   "adoption",
    "market_volatility":       "market_sentiment",
    # Semantic-only buckets
    "energy_power":            "infrastructure",
    "regulatory_policy":       "macro",
    "geopolitical":            "macro",
    "partnership_deals":       "ecosystem_structure",
    "talent_research":         "ecosystem_structure",
    "market_noise":            "market_sentiment",
    "other":                   "general",
}

# ── Semantic routing ────────────────────────────────────────────────────────────
# Each family has 5 natural-language descriptions written in news-headline style.
# Events are assigned to the closest family by cosine similarity.
# Keyword rules above act as high-precision overrides on top of this routing.

_SEMANTIC_FAMILIES: dict[str, list[str]] = {
    "infrastructure_delivery": [
        "data center construction, expansion, and physical build-out announcements",
        "power capacity, cooling systems, and thermal management for AI compute",
        "hyperscaler capital expenditure on server farms and campuses",
        "Vertiv power distribution and Arista networking fabric deployments",
        "colocation lease signings and rack deployment at scale",
    ],
    "semiconductor_supply": [
        "chip manufacturing capacity, yield improvements, and foundry output",
        "HBM high bandwidth memory production ramp and supply constraints",
        "TSMC and ASML advanced node wafer capacity expansions",
        "advanced packaging, chiplet, and CoWoS technology developments",
        "semiconductor supply chain bottlenecks and capacity investment",
    ],
    "compute_capacity": [
        "GPU availability, shortages, and allocation for AI training clusters",
        "inference compute capacity constraints and cloud GPU waitlists",
        "AI cluster demand outpacing available compute supply",
        "compute bottlenecks limiting AI model training and deployment",
        "hyperscaler GPU reservation and capacity crunch signals",
    ],
    "model_technology": [
        "new AI model releases, capability benchmarks, and evaluations",
        "large language model training runs and architectural improvements",
        "frontier AI research, reasoning improvements, and open-weight releases",
        "AI model performance comparisons and competitive positioning",
        "research breakthroughs in deep learning and AI capabilities",
    ],
    "enterprise_deployment": [
        "enterprise software AI feature rollouts and business adoption",
        "AI agent and copilot deployments in corporate workflows",
        "B2B AI contract wins, pilot programs, and customer case studies",
        "Salesforce Agentforce, Microsoft Copilot, Oracle AI enterprise launches",
        "AI productivity gains and return-on-investment in large organizations",
    ],
    "energy_power": [
        "power grid capacity and energy sourcing deals for data center demand",
        "nuclear, solar, and renewable energy procurement for AI compute",
        "electricity costs, power purchase agreements, and grid strain from AI",
        "hyperscaler energy infrastructure build-out and sustainability targets",
        "data center power density limits and utility grid interconnection",
    ],
    "regulatory_policy": [
        "AI regulation, government policy proposals, and legislative hearings",
        "export controls on advanced chips and AI technology shipments",
        "antitrust scrutiny of big tech AI acquisitions and market power",
        "EU AI Act, US executive orders, and AI safety compliance requirements",
        "government subsidies and CHIPS Act incentives for domestic manufacturing",
    ],
    "geopolitical": [
        "US-China trade tensions and semiconductor technology restrictions",
        "Taiwan geopolitical risk and supply chain disruption scenarios",
        "tariffs on technology hardware and trade policy impacts on AI",
        "national security concerns about AI chip dependencies and exports",
        "allied country coordination on AI standards and semiconductor policy",
    ],
    "partnership_deals": [
        "strategic partnership announcements between AI and technology companies",
        "mergers, acquisitions, and buyouts in AI and semiconductor space",
        "licensing deals, joint ventures, and co-development agreements",
        "cloud provider partnerships with AI model labs and startups",
        "venture investment rounds and funding in AI infrastructure companies",
    ],
    "talent_research": [
        "AI researcher hiring, poaching, and talent competition between labs",
        "key executive appointments, departures, and leadership changes at AI firms",
        "academic AI research publications, papers, and lab announcements",
        "AI lab team expansions, reorganizations, and new research divisions",
        "university partnerships and research grant announcements in AI",
    ],
    "market_volatility": [
        "quarterly earnings beats, misses, and financial results for tech companies",
        "analyst price target changes, upgrades, and downgrades on AI stocks",
        "guidance revisions, forward outlook, and margin commentary",
        "stock reactions to earnings reports and financial performance",
        "AI sector valuation debates, PE multiples, and investor positioning",
    ],
    "market_noise": [
        "generic stock price movement with no specific news catalyst",
        "routine financial market commentary and daily price watching",
        "unrelated company news incidentally mentioning technology names",
        "broad macro economic news affecting all equities indiscriminately",
        "general market index moves with no AI or semiconductor specific narrative",
    ],
}


def pre_tag_event(event: Event) -> str | None:
    """
    Return a keyword-matched bucket if a high-precision rule fires, otherwise None.
    None signals that semantic routing should handle this event.
    """
    text = event.title.lower()
    for bucket, keywords in _AI_BUCKET_RULES:
        if any(kw in text for kw in keywords):
            return bucket
    return None


# ── Clustering ─────────────────────────────────────────────────────────────────

def _normalize_ai_source(source: str) -> str:
    """Group AI sources into broad trust tiers for source_mix reporting."""
    if source == "reddit":
        return "reddit"
    if source in ("sec", "anchor"):
        return "filings"
    return "news"  # finnhub, newsapi, etc.


def _build_cluster_dict(cid: str, cluster_events: list[Event], bucket: str = "other") -> dict:
    actor_counter: Counter = Counter()
    for e in cluster_events:
        for a in e.actors:
            if a in set(ACTORS):
                actor_counter[a] += 1
    top_actors = [a for a, _ in actor_counter.most_common(3)]

    titles_in = [e.title for e in cluster_events]

    stop = {"that","this","with","from","have","will","been","they","their","more",
            "also","than","when","into","some","over","such","even","most","both",
            "then","which","these","just","about","what","nvidia","microsoft","google",
            "amazon","meta","apple","intel","broadcom","artificial","intelligence"}
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

    # Normalise sources into broad tiers for source_mix
    source_counts: Counter = Counter(_normalize_ai_source(e.source) for e in cluster_events)
    total = len(cluster_events)
    reddit_pct = int(source_counts.get("reddit", 0) / total * 100)
    news_pct   = int(source_counts.get("news",   0) / total * 100)
    source_mix = ("Reddit-heavy" if reddit_pct >= 70
                  else "News-heavy" if news_pct >= 70
                  else "Mixed")
    dominant_source  = max(source_counts, key=source_counts.get) if source_counts else "unknown"
    cross_source_count = len(source_counts)

    source_pct = {src: round(cnt / total * 100) for src, cnt in source_counts.items()}

    return {
        "cluster_id":            cid,
        "events":                cluster_events,
        "actors":                top_actors,
        "top_terms":             top_terms,
        "top_bigrams":           top_bigrams,
        "representative_title":  titles_in[0],
        "representative_titles": titles_in[:5],
        "source_mix":            source_mix,
        "source_pct":            source_pct,
        "dominant_source":       dominant_source,
        "cross_source_count":    cross_source_count,
        "narrative_family":      _AI_BUCKET_TO_FAMILY.get(bucket, "general"),
        "narrative_bucket":      bucket,
        "size":                  len(cluster_events),
    }


def _embed_and_cluster(events: list[Event], n: int, model: SentenceTransformer,
                       id_prefix: str, bucket: str = "other") -> list[dict]:
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


def _route_events_semantic(events: list[Event], model: SentenceTransformer) -> dict[int, str]:
    """
    Assign each event to the nearest semantic family by cosine similarity.
    Returns {id(event): family_name}. Used when no keyword rule fires.
    """
    family_names = list(_SEMANTIC_FAMILIES.keys())
    family_embs = normalize(model.encode(
        [" | ".join(descs) for descs in _SEMANTIC_FAMILIES.values()],
        show_progress_bar=False,
    ))
    event_embs = normalize(model.encode(
        [e.title for e in events],
        show_progress_bar=False,
    ))
    sims = event_embs @ family_embs.T          # (n_events, n_families)
    best = sims.argmax(axis=1)                 # index of best family per event
    return {id(e): family_names[int(best[i])] for i, e in enumerate(events)}


def cluster_titles(events: list[Event], n_clusters: int = N_CLUSTERS) -> list[dict]:
    """
    Route events into narrative families, then cluster within each family.

    Two-pass routing:
      1. Keyword overrides  — high-precision rules fire first (pre_tag_event)
      2. Semantic routing   — all remaining events assigned by cosine similarity
                              to _SEMANTIC_FAMILIES descriptions

    Guard: if >30% still land in "other" after semantic routing, a warning is
    printed — indicates gap in family coverage to address.
    """
    print(f"Routing {len(events)} events…")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Pass 1: collect events that need semantic routing
    keyword_tagged:  dict[int, str]  = {}
    semantic_needed: list[Event]     = []
    for e in events:
        bucket = pre_tag_event(e)
        if bucket is not None:
            keyword_tagged[id(e)] = bucket
        else:
            semantic_needed.append(e)

    # Pass 2: semantic routing for the remainder
    semantic_map = _route_events_semantic(semantic_needed, model) if semantic_needed else {}

    # Merge
    tagged: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        if id(e) in keyword_tagged:
            tagged[keyword_tagged[id(e)]].append(e)
        else:
            tagged[semantic_map.get(id(e), "other")].append(e)

    # 30% guard
    other_pct = len(tagged.get("other", [])) / max(len(events), 1)
    if other_pct > 0.30:
        print(f"  [WARNING] 'other' bucket is {other_pct:.0%} — semantic family coverage may need expansion")

    bucket_sizes = {b: len(evts) for b, evts in tagged.items()}
    print(f"  Buckets: { {b: n for b, n in sorted(bucket_sizes.items(), key=lambda x: -x[1])} }")

    result = []
    for bucket, bucket_events in sorted(tagged.items(), key=lambda x: -len(x[1])):
        share = len(bucket_events) / len(events)
        sub_n = max(1, round(n_clusters * share))
        clusters = _embed_and_cluster(bucket_events, sub_n, model, bucket, bucket=bucket)
        result.extend(clusters)

    result.sort(key=lambda c: -c["size"])
    return result


# ── LLM labeling ──────────────────────────────────────────────────────────────

# Concept-first fallback labels by cluster family.
# Used when the term-join fallback is entity/residue-heavy.
_BUCKET_FAMILY_LABELS: dict[str, str] = {
    "infrastructure_delivery": "Data center infrastructure growth",
    "compute_capacity":        "AI compute capacity signal",
    "semiconductor_supply":    "Chip supply narrative",
    "geopolitical":            "Geopolitical supply-chain risk",
    "regulatory_policy":       "Regulatory risk to AI adoption",
    "model_technology":        "AI model competition",
    "enterprise_deployment":   "Software AI adoption signal",
    "partnership_deals":       "AI partnership momentum",
    "energy_power":            "Power infrastructure signal",
    "market_volatility":       "Market repricing signal",
    "market_noise":            "General market activity",
    "talent_research":         "AI talent and research signal",
}

# Words that indicate a term-join fallback is entity/residue-heavy rather than conceptual.
_LABEL_RESIDUE_WORDS = {
    "says", "deal", "stock", "stocks", "today", "week", "going",
    "anyone", "win", "advice", "alternatives", "highlighted", "bull",
    "bear", "nano", "aggressive", "uncensored", "brushed", "spins",
}
_LABEL_COUNTRY_WORDS = {"china", "taiwan", "iran", "russia", "india", "korea"}
# AI product/company names used as bare tokens (indicate entity residue, not concepts)
_LABEL_ENTITY_TOKENS = {
    "claude", "chatgpt", "gemini", "gpt", "llm", "llms", "openai", "anthropic",
    "copilot", "gemma", "grok", "mistral", "llama", "deepseek",
    "oracle", "zacks", "benzinga", "cnbc", "bloomberg",
}


def _term_join_is_weak(label: str, cluster: dict) -> bool:
    """True if the 4-term fallback label is entity-heavy or residue-heavy.

    Checks for: residue verbs, country names, AI product name tokens,
    and actor tickers that ended up in the top_terms list.
    """
    words = [w.lower().strip("():,?!'\"") for w in label.split() if w.strip()]
    actors_lower = {a.lower() for a in cluster.get("actors", [])}
    junk = sum(
        1 for w in words
        if w in _LABEL_RESIDUE_WORDS
        or w in _LABEL_COUNTRY_WORDS
        or w in _LABEL_ENTITY_TOKENS
        or w in actors_lower
    )
    return len(words) > 0 and junk / len(words) >= 0.5


def _concept_first_fallback(cluster: dict) -> str:
    """Return a concept-first label derived from the cluster's bucket family."""
    family = "_".join(cluster["cluster_id"].split("_")[:-1])
    return _BUCKET_FAMILY_LABELS.get(family, "Narrative signal forming")


def label_cluster(cluster: dict, use_llm: bool = True) -> dict:
    raw_terms_label = " ".join(cluster["top_terms"][:4]).title()
    # Prefer concept-first fallback when raw term-join is entity/residue-heavy
    fallback_label = (
        raw_terms_label if not _term_join_is_weak(raw_terms_label, cluster)
        else _concept_first_fallback(cluster)
    )

    if not use_llm:
        return {**cluster, "narrative": fallback_label, "explanation": "", "label_source": "terms"}

    evidence = {
        "storm_id":                f"ai_cluster_{cluster['cluster_id']}",
        "actors":                  cluster["actors"],
        "state":                   "stable",
        "event_count":             cluster["size"],
        "dominant_cluster_ratio":  0.7,
        "themes":                  cluster["top_terms"][:5],
        "bigrams":                 cluster["top_bigrams"],
        "domain_phrases":          [],
        "entity_actions":          [],
        "dominant_cluster_terms":  cluster["top_terms"][:5],
        "dominant_cluster_bigrams": cluster["top_bigrams"],
        "representative_titles":   cluster.get("representative_titles", [cluster["representative_title"]]),
        "all_titles_count":        cluster["size"],
    }

    result = generate_llm_name(evidence)
    if result["llm_used"] and result["llm_headline"]:
        headline  = result["llm_headline"]
        one_liner = result["llm_one_liner"] or ""
        valid, _, _    = validate_llm_label(headline, one_liner, fallback_label)
        faithful, _, _ = validate_llm_label_faithfulness(headline, evidence)
        if valid and faithful:
            return {**cluster, "narrative": headline, "explanation": one_liner, "label_source": "llm"}
        else:
            print(f"  [label] cluster {cluster['cluster_id']}: LLM label rejected, using terms")

    return {**cluster, "narrative": fallback_label, "explanation": "", "label_source": "terms"}


# ── Momentum ───────────────────────────────────────────────────────────────────

def _momentum_label(cluster: dict, hot_density: dict, near_density: dict,
                    near_counts: dict, min_near: int = 2) -> str:
    """
    Compare hot window (0–2d) actor density vs near window (3–7d) actor density.
    Amplification sources already excluded from both density dicts.
    """
    actors = cluster["actors"]
    if not actors:
        return "FLAT"
    primary = actors[0]
    if near_counts.get(primary, 0) < min_near:
        return "INSUFFICIENT_DATA"
    hot  = hot_density.get(primary, 0.0)
    near = near_density.get(primary, 0.0)
    # If both zero → no recent coverage at all
    if hot == 0 and near == 0:
        return "INSUFFICIENT_DATA"
    delta = hot - near
    if delta > 0.01:
        return "RISING"
    elif delta < -0.01:
        return "FALLING"
    return "FLAT"


def _cluster_change_vs_prior(cluster: dict, today: datetime) -> int:
    """
    Momentum score for site display.
    = (hot 48h weighted event count) - (near 3–7d avg-daily * 2),
      expressed as a signed integer scaled to cluster size.
    Amplification sources excluded.
    """
    events = [e for e in cluster.get("events", []) if _is_velocity_source(e)]
    hot_w  = sum(_decay_weight(_event_age_days(e, today))
                 for e in events if _event_age_days(e, today) <= _HOT_WINDOW_DAYS)
    near_w = sum(_decay_weight(_event_age_days(e, today))
                 for e in events
                 if _HOT_WINDOW_DAYS < _event_age_days(e, today) <= _NEAR_WINDOW_DAYS)
    # Scale near to 2-day equivalent (near window spans 5 days)
    near_norm = near_w * (_HOT_WINDOW_DAYS / (_NEAR_WINDOW_DAYS - _HOT_WINDOW_DAYS))
    delta = hot_w - near_norm
    max_possible = max(len(events) * 1.0, 1)
    return int(round(delta / max_possible * 100))


# ── Classification ─────────────────────────────────────────────────────────────

def _inject_cluster_ids(sections: dict, clusters: list[dict]) -> None:
    """
    Inject cluster_id onto every entry in sections after classification.

    Uses exact narrative-text match first.  Falls back to word-overlap only when the
    LLM rephrased the narrative title; marks those entries with _cluster_id_source='fuzzy'
    and emits a log line so degraded mode is visible.

    Mutates sections in-place.
    """
    exact_map = {c["narrative"].lower().strip(): c["cluster_id"] for c in clusters}
    n_exact = n_fuzzy = n_miss = 0

    for bucket_entries in sections.values():
        for entry in bucket_entries:
            key = entry.get("narrative", "").lower().strip()
            if key in exact_map:
                entry["cluster_id"] = exact_map[key]
                n_exact += 1
            else:
                # Word-overlap fallback — LLM may slightly rephrase the title
                words = set(key.split())
                best_c, best_score = None, 0
                for c in clusters:
                    overlap = len(words & set(c["narrative"].lower().split()))
                    if overlap > best_score:
                        best_c, best_score = c, overlap
                if best_c and best_score > 0:
                    entry["cluster_id"] = best_c["cluster_id"]
                    entry["_cluster_id_source"] = "fuzzy"
                    n_fuzzy += 1
                else:
                    n_miss += 1
                    print(f"  [WARN][cluster_id] no match for: '{key[:60]}'")

    parts = [f"exact={n_exact}"]
    if n_fuzzy:
        parts.append(f"fuzzy(DEGRADED)={n_fuzzy}")
    if n_miss:
        parts.append(f"UNMATCHED={n_miss}")
    print(f"  [cluster_id] {', '.join(parts)}")


def classify_with_llm(clusters: list[dict], hot_density: dict, near_density: dict,
                      near_counts: dict | None = None) -> dict:
    """Classify AI narrative clusters using LLM + shared post-processing spine."""
    cluster_inputs = []
    for c in clusters:
        momentum = _momentum_label(c, hot_density, near_density, near_counts or {})
        events = c.get("events", [])
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
            {"role": "system", "content": build_system_prompt("ai")},
            {"role": "user", "content": user_message},
        ],
        response_format=CompassClassification,
    )
    result = response.choices[0].message.parsed

    key = lambda c: c["narrative"].lower().strip()
    sections = post_process_classify_results(
        result,
        momentum_by   = {key(c): _momentum_label(c, hot_density, near_density, near_counts or {}) for c in clusters},
        attention_by  = {key(c): _attention_level(c["size"]) for c in clusters},
        dom_src_by    = {key(c): c.get("dominant_source", "unknown") for c in clusters},
        cross_src_by  = {key(c): c.get("cross_source_count", 1) for c in clusters},
        reddit_pct_by = {key(c): c.get("source_pct", {}).get("reddit", 0) for c in clusters},
        size_by       = {key(c): c["size"] for c in clusters},
        ecosystem     = "ai",
        actors_by     = {key(c): c["actors"] for c in clusters},
    )
    _inject_cluster_ids(sections, clusters)
    return sections


def classify_compass_fallback(clusters: list[dict], hot_density: dict, near_density: dict,
                              near_counts: dict | None = None) -> dict:
    """Mechanical fallback classifier for --no-llm mode."""
    sections: dict = {"lean_in": [], "step_back": [], "be_careful": [], "ignore": []}
    for c in clusters:
        momentum  = _momentum_label(c, hot_density, near_density, near_counts or {})
        attention = _attention_level(c["size"])
        dom_src   = c.get("dominant_source", "unknown")
        family    = c.get("narrative_family", "general")

        entry = {
            "narrative":   c["narrative"],
            "cluster_id":  c["cluster_id"],
            "summary":     f"Actors: {', '.join(c['actors'][:3])}. Source: {c.get('source_mix', 'Mixed')}.",
            "action":      "Review manually.",
            "confidence":  "LOW",
            "event_count": c["size"],
        }

        # AI: family-based floor rules in fallback
        if family in ("market_sentiment", "general"):
            sections["ignore"].append(entry)
        elif family == "ecosystem_structure":
            # Partnership/talent: skeptical default; suppress unless clearly meaningful
            sections["ignore"].append(entry)
        elif family == "macro":
            # Regulatory/geopolitical: hold at BE_CAREFUL; never LEAN_IN in fallback
            sections["be_careful"].append(entry)
        elif dom_src == "reddit":
            sections["ignore"].append(entry)
        elif attention in ("MEDIUM", "HIGH") and momentum == "RISING":
            sections["lean_in"].append(entry)
        elif attention == "HIGH" and momentum in ("FLAT", "FALLING"):
            sections["step_back"].append(entry)
        elif attention in ("MEDIUM", "HIGH"):
            sections["be_careful"].append(entry)
        else:
            sections["ignore"].append(entry)
    return sections


# ── Cluster ranking and selection ──────────────────────────────────────────────

_CONFIDENCE_SCORE: dict[str, float] = {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.25}
_MOMENTUM_SCORE:   dict[str, float] = {
    "RISING": 1.0, "FLAT": 0.5, "FALLING": 0.0, "INSUFFICIENT_DATA": 0.25,
}


def _score_cluster_entry(entry: dict, cluster: dict | None, momentum: str) -> float:
    """
    cluster_score =
        (reinforcement    * 0.4)   — proxied by LLM confidence (HIGH/MEDIUM/LOW)
      + (cross_actor_count * 0.3)  — len(actors) normalised over 5
      + (source_diversity  * 0.2)  — cross_source_count normalised over 3
      + (momentum          * 0.1)
    """
    reinforcement = _CONFIDENCE_SCORE.get(entry.get("confidence", "LOW"), 0.25)
    if cluster is None:
        return reinforcement * 0.4
    cross_actor = min(len(cluster.get("actors", [])), 5) / 5
    source_div  = min(cluster.get("cross_source_count", 1), 3) / 3
    mom         = _MOMENTUM_SCORE.get(momentum, 0.5)
    return reinforcement * 0.4 + cross_actor * 0.3 + source_div * 0.2 + mom * 0.1


def _find_cluster_for_entry(narrative: str, labeled: list[dict]) -> dict | None:
    """Match a classified entry back to its raw cluster dict by narrative title."""
    key = narrative.lower().strip()
    # exact match first
    for c in labeled:
        if c["narrative"].lower().strip() == key:
            return c
    # partial word-overlap fallback (tolerates LLM rephrasing)
    words = set(key.split())
    best, best_score = None, 0
    for c in labeled:
        overlap = len(words & set(c["narrative"].lower().split()))
        if overlap > best_score:
            best, best_score = c, overlap
    return best if best_score > 0 else None


def _is_market_noise_cluster(cluster: dict | None) -> bool:
    """True if the cluster originated from market_noise or market_volatility routing bucket."""
    if cluster is None:
        return False
    cid = cluster.get("cluster_id", "")
    return cid.startswith("market_noise") or cid.startswith("market_volatility")


def select_and_rank_clusters(
    sections: dict,
    labeled:  list[dict],
    momentum_by: dict[str, str],
) -> dict:
    """
    Re-rank classified entries by cluster_score and apply selection rules:

      1. Score each entry:  reinforcement×0.4 + cross_actor×0.3 + source_div×0.2 + momentum×0.1
      2. Noise penalty:     IGNORE entries from market_noise/market_volatility clusters → score×0.2
      3. Selection:         sort LEAN_IN / STEP_BACK / BE_CAREFUL by score descending
                            cap IGNORE at 2 (highest-scoring non-noise first)

    Does NOT change classification, format, or downstream rendering.
    """
    cluster_by_id = {c["cluster_id"]: c for c in labeled}

    def _resolve_cluster(entry: dict) -> dict | None:
        cid = entry.get("cluster_id")
        if cid and cid in cluster_by_id:
            return cluster_by_id[cid]
        # Degraded: fuzzy fallback (entries without cluster_id pre-injected)
        return _find_cluster_for_entry(entry["narrative"], labeled)

    def _momentum(narrative: str) -> str:
        key = narrative.lower().strip()
        if key in momentum_by:
            return momentum_by[key]
        words = set(key.split())
        best, best_score = "FLAT", 0
        for k, v in momentum_by.items():
            overlap = len(words & set(k.split()))
            if overlap > best_score:
                best, best_score = v, overlap
        return best

    result: dict[str, list[dict]] = {}

    for section in ("lean_in", "step_back", "be_careful", "ignore"):
        entries = sections.get(section, [])
        scored: list[tuple[float, dict]] = []
        for entry in entries:
            cluster  = _resolve_cluster(entry)
            mom      = _momentum(entry["narrative"])
            score    = _score_cluster_entry(entry, cluster, mom)
            if section == "ignore" and _is_market_noise_cluster(cluster):
                score *= 0.2
            scored.append((score, entry))
        scored.sort(key=lambda x: -x[0])
        result[section] = [e for _, e in scored]

    # Cap IGNORE at 2 to prevent noise cluster dominance
    result["ignore"] = result["ignore"][:2]

    kept_ignore = len(result["ignore"])
    print(f"  [rank] LEAN_IN={len(result['lean_in'])}  STEP_BACK={len(result['step_back'])}"
          f"  BE_CAREFUL={len(result['be_careful'])}  IGNORE={kept_ignore} (capped at 2)")

    return result


# ── Rendering ──────────────────────────────────────────────────────────────────

def render_text(sections: dict, date: str) -> str:
    return render_compass_text(sections, date, title="AI COMPASS")


def render_json(sections: dict, date: str) -> str:
    return render_compass_json(sections, date, ecosystem="ai")


# ── AI tab override ────────────────────────────────────────────────────────────
# Applied post-compose when compass output is too weak to reflect leaderboard reality.

_WEAK_COMPASS_OVERRIDE = (
    "Mixed signals. Downside still confirming in software, while selective upside "
    "and early follow-through are emerging in infrastructure and adjacent names."
)

# Phrases that indicate the compass drifted into generic/abstract framing — override regardless
_BANNED_STATE_PHRASES = [
    "fragmenting",
    "deployment out",
    "fragmentation",
]

# Entity names that indicate a WATCH signal has no real ticker match (generic fallback)
_GENERIC_ENTITY_NAMES = {
    "governments", "regulatory bodies", "ai companies", "industry",
    "investors", "companies", "regulators", "policymakers",
}


def _compass_needs_override(pkg: dict) -> bool:
    """
    Return True if the compass output is too weak or abstract to reflect leaderboard reality.

    Triggers:
    - 0 LEAN_IN signals in the composition output
    - majority BE_CAREFUL signals (more BE_CAREFUL than all others combined)
    - any WATCH signal has only generic entity names (no real tickers)
    - system_state contains a banned phrase
    """
    signals = pkg.get("selected_signals", [])
    state   = pkg.get("system_state", "") or ""

    lean_in    = [s for s in signals if s.get("bucket") == "LEAN_IN"]
    be_careful = [s for s in signals if s.get("bucket") == "BE_CAREFUL"]

    if len(lean_in) == 0:
        return True

    if len(be_careful) > len(signals) - len(be_careful):
        return True

    watch = [s for s in signals if s.get("bucket") == "WATCH"]
    for sig in watch:
        entities = [e.lower() for e in sig.get("affected_entities", [])]
        if entities and all(e in _GENERIC_ENTITY_NAMES for e in entities):
            return True

    if any(phrase in state.lower() for phrase in _BANNED_STATE_PHRASES):
        return True

    return False


# ── Site JSON rendering ────────────────────────────────────────────────────────

_BUCKET_UPPER = {
    "lean_in": "LEAN_IN", "step_back": "STEP_BACK",
    "be_careful": "BE_CAREFUL", "ignore": "IGNORE",
}

_TIME_HORIZON_MAP: dict[tuple[str, str], str] = {
    ("RISING", "HIGH"):              "days_to_weeks",
    ("RISING", "MEDIUM"):            "days_to_weeks",
    ("RISING", "LOW"):               "weeks",
    ("FLAT",   "HIGH"):              "weeks",
    ("FLAT",   "MEDIUM"):            "weeks",
    ("FLAT",   "LOW"):               "months",
    ("FALLING","HIGH"):              "weeks",
    ("FALLING","MEDIUM"):            "months",
    ("FALLING","LOW"):               "months",
    ("INSUFFICIENT_DATA", "HIGH"):   "weeks",
    ("INSUFFICIENT_DATA", "MEDIUM"): "months",
    ("INSUFFICIENT_DATA", "LOW"):    "months",
}


def render_site_json(
    sections:             dict,
    labeled:              list[dict],
    momentum_by:          dict[str, str],
    date:                 str,
    composition_package:  dict | None = None,
    today:                datetime | None = None,
) -> str:
    """
    Produce topicspace-site public/signals/ai/latest.json format.

    When composition_package is provided (normal production path):
      - Uses the composed signal selection (4–8 editorially chosen signals)
      - Uses composed top_read, explanation, and system_state
      - Uses notes injected by the composition layer

    When composition_package is None (fallback / --no-llm path):
      - Renders all classified signals with mechanical metadata

    In both cases, each entry is enriched with cluster metadata:
      narrative_id, affected_entities, sources, momentum, time_horizon, narrative_family.
    """
    # Determine the entry list and header metadata
    if composition_package:
        entries       = composition_package["selected_signals"]
        system_state      = composition_package["system_state"]
        top_read          = composition_package["top_read"]
        explanation       = composition_package.get("explanation", "")
        watch_signals     = composition_package.get("watch_signals", [])
        primary_pressure  = composition_package.get("primary_pressure", "")
        primary_trigger   = composition_package.get("primary_trigger", "")
        regime            = composition_package.get("regime", "")
    else:
        # Fallback: all classified signals, mechanical metadata
        entries = [
            {**e, "_bucket": sk}
            for sk in ("lean_in", "step_back", "be_careful", "ignore")
            for e in sections.get(sk, [])
        ]
        system_state = explanation = top_read = primary_pressure = primary_trigger = regime = None
        watch_signals = []

    # ── Exact cluster lookup — built once, used throughout ───────────────────
    _cluster_by_id: dict[str, dict] = {c["cluster_id"]: c for c in labeled}
    _ref = today or datetime.now(timezone.utc)

    def _resolve_cluster_exact(entry: dict) -> dict | None:
        """
        Exact cluster lookup via cluster_id.  Falls back to fuzzy title matching
        only if cluster_id is missing, and logs a DEGRADED warning.
        """
        cid = entry.get("cluster_id")
        if cid:
            c = _cluster_by_id.get(cid)
            if c:
                return c
            print(f"  [WARN][sources] cluster_id '{cid}' not found in labeled set")
        # Degraded fallback — should not normally fire after _inject_cluster_ids
        c = _find_cluster_for_entry(
            entry.get("narrative", entry.get("title", "")), labeled
        )
        if c:
            print(f"  [DEGRADED][sources] using fuzzy match for: "
                  f"'{entry.get('narrative','')[:60]}'")
        else:
            print(f"  [WARN][sources] no cluster found for: "
                  f"'{entry.get('narrative','')[:60]}'")
        return c

    def _cluster_sources(cluster: dict, limit: int = 5) -> list[dict]:
        """Most-recent non-amplification events from a cluster, formatted for site JSON."""
        evs = sorted(
            (e for e in cluster.get("events", []) if _is_velocity_source(e)),
            key=lambda e: e.timestamp,
            reverse=True,
        )[:limit]
        out = []
        for ev in evs:
            src: dict = {"title": ev.title, "source_type": ev.source}
            if ev.url:
                src["url"] = ev.url
            if ev.timestamp:
                src["timestamp"] = ev.timestamp
            out.append(src)
        return out

    # Company name → ticker mapping for WATCH signal actor resolution
    _NAME_TO_TICKER: dict[str, str] = {
        "google": "GOOGL", "alphabet": "GOOGL",
        "microsoft": "MSFT",
        "amazon": "AMZN",
        "meta": "META",
        "nvidia": "NVDA",
        "apple": "AAPL",
        "tesla": "TSLA",
        "oracle": "ORCL",
        "broadcom": "AVGO",
        "tsmc": "TSM",
        "amd": "AMD",
        "intel": "INTC",
        "salesforce": "CRM",
        "adobe": "ADBE",
        "openai": "MSFT",      # OpenAI narratives cluster around MSFT in our data
        "anthropic": "GOOGL",  # Anthropic narratives cluster around GOOGL
        "deepseek": "NVDA",
        # Extended
        "arista": "ANET",
        "palantir": "PLTR",
        "servicenow": "NOW",
        "cloudflare": "NET",
        "arm": "ARM",
        "marvell": "MRVL",
        "qualcomm": "QCOM",
        "netflix": "NFLX",
        "samsung": "SSNLF",
        "aws": "AMZN",
    }

    # Generic multi-entity terms → list of tickers to search
    _MULTI_ENTITY_TICKERS: dict[str, list[str]] = {
        "hyperscaler":             ["AMZN", "MSFT", "GOOGL"],
        "hyperscalers":            ["AMZN", "MSFT", "GOOGL"],
        "cloud service providers": ["AMZN", "MSFT", "GOOGL"],
        "major cloud providers":   ["AMZN", "MSFT", "GOOGL"],
        "cloud providers":         ["AMZN", "MSFT", "GOOGL"],
        "big tech":                ["MSFT", "GOOGL", "META", "AMZN", "AAPL"],
        "large language model":    ["MSFT", "GOOGL", "META"],
        "foundation models":       ["MSFT", "GOOGL", "META", "NVDA"],
    }

    def _watch_sources(watch_actors: list[str], headline: str = "", limit: int = 3) -> list[dict]:
        """
        Find 2–3 representative sources for a WATCH signal by locating
        the highest-event-count clusters that share any of its actors,
        then taking the most recent non-amplification events from those clusters.

        When actor matching produces no results, falls back to keyword overlap
        between the watch headline and cluster top_terms — so generic actors like
        "governments" or "infrastructure regulators" still get relevant sources
        instead of the largest unrelated clusters.
        """
        _STOPWORDS = {"that","this","with","from","have","will","been","they","their",
                      "more","also","than","when","into","some","over","such","even",
                      "most","both","then","which","these","just","about","what","could",
                      "would","should","becoming","binding","constraint","increase",
                      "signs","could","would","revive","reshape","launch","entrants","focus"}

        # Build keyword set from headline + actor names for relevance scoring
        query_words = (
            {w for w in re.findall(r"[a-z]+", headline.lower()) if len(w) > 3}
            | {w for a in watch_actors for w in re.findall(r"[a-z]+", a.lower()) if len(w) > 3}
        ) - _STOPWORDS

        def _title_score(ev_title: str) -> int:
            """How many query words appear in an event title."""
            title_words = {w for w in re.findall(r"[a-z]+", ev_title.lower()) if len(w) > 3}
            return len(query_words & title_words)

        def _title_ok(ev_title: str) -> bool:
            """Filter out obviously irrelevant or malformed titles."""
            t = ev_title.strip()
            if len(t) < 20:
                return False
            lower = t.lower()
            # Spaced-letter correction notices: "C O R R E C T I O N"
            # Detect by counting consecutive single-char tokens
            tokens = lower.split()
            single_run = max(
                (sum(1 for _ in g) for k, g in
                 __import__("itertools").groupby(tokens, key=lambda w: len(w) == 1)
                 if k),
                default=0,
            )
            if single_run >= 4:
                return False
            junk_patterns = ["correction --", "i'm a ", "unpopular opinion",
                             "i am a ", "f*", "wtf ", "shit "]
            return not any(p in lower for p in junk_patterns)

        # Expand actor set to include ticker equivalents
        expanded: set[str] = set()
        for a in watch_actors:
            expanded.add(a)
            ticker = _NAME_TO_TICKER.get(a.lower())
            if ticker:
                expanded.add(ticker)
            for multi_key, tickers in _MULTI_ENTITY_TICKERS.items():
                if multi_key in a.lower():
                    expanded.update(tickers)
        actor_set = expanded

        # Rank clusters by actor overlap first
        matched = [c for c in labeled if set(c.get("actors", [])) & actor_set]

        # Keyword fallback: when no actor match, score clusters by overlap
        # with headline words against cluster top_terms and representative titles
        if not matched:
            def _kw_score(c: dict) -> int:
                terms  = set(c.get("top_terms", []))
                titles = " ".join(c.get("representative_titles", [])).lower()
                title_words = {w for w in re.findall(r"[a-z]+", titles) if len(w) > 3}
                return len(query_words & (terms | title_words))

            ranked = sorted(labeled, key=lambda c: (_kw_score(c), c["size"]), reverse=True)
        else:
            ranked = sorted(
                matched,
                key=lambda c: (len(set(c.get("actors", [])) & actor_set), c["size"]),
                reverse=True,
            )

        seen_urls: set[str] = set()
        out: list[dict] = []
        for cluster in ranked:
            if len(out) >= limit:
                break
            # Sort events: relevant titles first, then by recency
            candidate_events = [
                e for e in cluster.get("events", [])
                if _is_velocity_source(e) and _title_ok(e.title)
            ]
            candidate_events.sort(
                key=lambda e: (_title_score(e.title), e.timestamp or ""),
                reverse=True,
            )
            for ev in candidate_events:
                if len(out) >= limit:
                    break
                url = ev.url or ""
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                src: dict = {"title": ev.title, "source_type": ev.source}
                if ev.url:
                    src["url"] = ev.url
                if ev.timestamp:
                    src["timestamp"] = ev.timestamp
                out.append(src)
        return out

    # ── Main signal loop ──────────────────────────────────────────────────────
    signals: list[dict] = []
    signal_counts: dict[str, int] = {"LEAN_IN": 0, "STEP_BACK": 0, "BE_CAREFUL": 0, "WATCH": 0, "IGNORE": 0}

    _MIN_SIGNAL_COUNT = 20  # hard floor — mis-clustered noise rarely exceeds this

    for entry in entries:
        # Drop entries with too few underlying events — catches mis-clustered noise
        # that slipped through classification (e.g. food/lifestyle articles at 6 events)
        if entry.get("event_count", 0) < _MIN_SIGNAL_COUNT:
            print(f"  [render] skip low-signal entry ({entry.get('event_count',0)} events): "
                  f"'{(entry.get('narrative') or entry.get('title',''))[:60]}'")
            continue

        # Resolve bucket — prefer _bucket (set by composition / selection layer)
        bucket_key = entry.get("_bucket") or "be_careful"
        bucket     = _BUCKET_UPPER.get(bucket_key, bucket_key.upper())
        signal_counts[bucket] = signal_counts.get(bucket, 0) + 1

        title         = entry.get("narrative", entry.get("title", ""))
        display_title = entry.get("headline") or title   # LLM headline overrides if present
        cluster       = _resolve_cluster_exact(entry)
        mom           = momentum_by.get(title.lower().strip(), "FLAT")
        attn          = _attention_level(entry.get("event_count", 0))

        slug         = re.sub(r'[^a-z0-9]+', '_', title.lower()).strip("_")[:40]
        narrative_id = f"ai_{slug}"
        actors       = cluster.get("actors", []) if cluster else []
        sources      = _cluster_sources(cluster) if cluster else []
        change_vs_prior = _cluster_change_vs_prior(cluster, _ref) if cluster else 0

        signals.append({
            "narrative_id":      narrative_id,
            "title":             display_title,
            "summary":           entry.get("summary", ""),
            "bucket":            bucket,
            "momentum":          mom if mom != "INSUFFICIENT_DATA" else "FLAT",
            "reinforcement":     entry.get("confidence", "LOW"),
            "confidence":        entry.get("confidence", "LOW"),
            "time_horizon":      _TIME_HORIZON_MAP.get((mom, attn), "weeks"),
            "narrative_family":  cluster.get("narrative_family", "general") if cluster else "general",
            "affected_entities": actors,
            "notes":             entry.get("notes", ""),
            "total_event_count": entry.get("event_count", 0),
            "change_vs_prior":   change_vs_prior,
            "sources":           sources,
        })

    # ── WATCH signals — lightweight with supporting sources ───────────────────
    for w in watch_signals:
        slug        = re.sub(r'[^a-z0-9]+', '_', w["headline"].lower()).strip("_")[:40]
        watch_actors = w.get("actors", [])
        signals.append({
            "narrative_id":      f"ai_watch_{slug}",
            "title":             w["headline"],
            "summary":           w["summary"],
            "bucket":            "WATCH",
            "momentum":          "FLAT",
            "reinforcement":     "MEDIUM",
            "confidence":        "MEDIUM",
            "time_horizon":      "weeks",
            "narrative_family":  "watch",
            "affected_entities": watch_actors,
            "notes":             w.get("note", ""),
            "trigger":           w.get("trigger", ""),
            "total_event_count": 0,
            "change_vs_prior":   0,
            "sources":           _watch_sources(watch_actors, headline=w["headline"], limit=3),
        })
        signal_counts["WATCH"] = signal_counts.get("WATCH", 0) + 1

    # Mechanical fallback for header metadata (only when no composition package)
    if system_state is None:
        lean_in_s    = [s for s in signals if s["bucket"] == "LEAN_IN"]
        step_back_s  = [s for s in signals if s["bucket"] == "STEP_BACK"]
        be_careful_s = [s for s in signals if s["bucket"] == "BE_CAREFUL"]
        infra_fams   = {"infrastructure", "compute_capacity", "semiconductor_supply",
                        "infrastructure_delivery", "energy_power"}
        if len(lean_in_s) >= 2:
            system_state = f"{len(lean_in_s)} narratives strengthening. Multiple behaviors coexisting."
        elif len(lean_in_s) == 1 and any(s["narrative_family"] in infra_fams for s in lean_in_s):
            system_state = "Transitional. Infrastructure narrative strengthening; multiple behaviors coexisting."
        elif len(lean_in_s) == 1:
            system_state = "Transitional. One narrative strengthening; multiple behaviors coexisting."
        elif len(step_back_s) >= 3:
            system_state = "Transitional. Multiple behaviors coexisting; no single regime dominant."
        else:
            system_state = "Transitional. Multiple behaviors coexisting; no single regime dominant."

        if lean_in_s:
            top = lean_in_s[0]
            top_read = f"{top['title']}. {top['summary']}"
        elif step_back_s:
            top = step_back_s[0]
            top_read = f"Fading: {top['title']}. {top['summary']}"
        elif be_careful_s:
            top = be_careful_s[0]
            top_read = f"Watch: {top['title']}. {top['summary']}"
        else:
            top_read = "No high-signal narratives today."

        explanation      = ""
        primary_pressure = ""
        primary_trigger  = ""
        regime           = ""

    return json.dumps({
        "date":             date,
        "domain":           "ai",
        "regime":           regime,
        "system_state":     system_state,
        "primary_pressure": primary_pressure,
        "primary_trigger":  primary_trigger,
        "top_read":         top_read,
        "explanation":      explanation,
        "signal_counts":    signal_counts,
        "signals":          signals,
    }, indent=2)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate AI ecosystem Narrative Compass")
    parser.add_argument("--json",   action="store_true", help="Output JSON")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM labeling, use top terms")
    parser.add_argument("--out",    help="Write output to file")
    parser.add_argument("--clusters", type=int, default=N_CLUSTERS)
    parser.add_argument("--site",   action="store_true",
                        help="Write site-format JSON to topicspace-site/public/signals/ai/")
    args = parser.parse_args()

    today    = datetime.now(timezone.utc)
    date_str = today.strftime("%Y-%m-%d")

    events = load_events()

    hot_events, near_events = partition_windows(events, today)
    hot_density  = weighted_actor_density(hot_events, today)
    near_density = weighted_actor_density(near_events, today)
    near_raw     = actor_counts(near_events)
    print(f"Hot window (0–{_HOT_WINDOW_DAYS}d, non-amp): {len(hot_events)} events"
          f" | Near window ({_HOT_WINDOW_DAYS+1}–{_NEAR_WINDOW_DAYS}d, non-amp): {len(near_events)} events")

    clusters = cluster_titles(events, n_clusters=args.clusters)
    print(f"Clusters found: {len(clusters)} (≥{MIN_CLUSTER_EVENTS} events)")

    print("Labeling clusters…")
    labeled = [label_cluster(c, use_llm=not args.no_llm) for c in clusters]
    for c in labeled:
        src = "llm" if c["label_source"] == "llm" else "terms"
        print(f"  [{src}] {c['narrative']} (actors: {c['actors']}, n={c['size']})")

    # Pre-compute momentum for every labeled cluster (used by both classify and rank)
    momentum_by = {
        c["narrative"].lower().strip(): _momentum_label(c, hot_density, near_density, near_raw)
        for c in labeled
    }

    if args.no_llm:
        sections = classify_compass_fallback(labeled, hot_density, near_density, near_raw)
    else:
        print("Classifying narratives…")
        sections = classify_with_llm(labeled, hot_density, near_density, near_raw)

    print("Ranking and selecting clusters…")
    sections = select_and_rank_clusters(sections, labeled, momentum_by)

    # ── QA: family distribution of ranked BE_CAREFUL signals ────────────────
    _family_by_narrative = {c["narrative"].lower().strip(): c.get("narrative_family", "general")
                            for c in labeled}
    _bc_families: dict[str, int] = {}
    for entry in sections.get("be_careful", []):
        fam = _family_by_narrative.get(entry["narrative"].lower().strip(), "general")
        _bc_families[fam] = _bc_families.get(fam, 0) + 1
    if _bc_families:
        print(f"  [qa] BE_CAREFUL by family: { {k: v for k, v in sorted(_bc_families.items())} }")

    # ── Compass output (text / JSON) — unchanged machine-readable format ─────
    output = render_json(sections, date_str) if args.json else render_text(sections, date_str)

    if args.out:
        Path(args.out).write_text(output)
        print(f"Written to {args.out}")
    else:
        print("\n" + output)

    # ── Composition layer — homepage-ready editorial package ─────────────────
    if args.site:
        print("Composing homepage…")
        pkg = compose_homepage(
            sections    = sections,
            labeled     = labeled,
            momentum_by = momentum_by,
            date        = date_str,
            use_llm     = not args.no_llm,
        )

        # Override weak/abstract state framing before writing site JSON
        if _compass_needs_override(pkg):
            pkg["system_state"] = _WEAK_COMPASS_OVERRIDE
            print(f"  [override] system_state → weak compass detected, applying leaderboard-aligned override")

        print(f"  [compose] system_state: {pkg['system_state']}")
        print(f"  [compose] top_read:     {pkg['top_read']}")
        print(f"  [compose] signals:      {len(pkg['selected_signals'])}")

        # QA: ecosystem_structure share of visible signals
        _visible_eco = sum(
            1 for s in pkg["selected_signals"]
            if _family_by_narrative.get(s.get("narrative", "").lower().strip(), "general")
            == "ecosystem_structure"
        )
        _visible_total = len(pkg["selected_signals"])
        if _visible_eco > 1 or (_visible_total > 0 and _visible_eco / _visible_total >= 0.4):
            print(f"  [qa] ⚠  ecosystem_structure = {_visible_eco}/{_visible_total} visible signals"
                  f" — partnership/talent may be inflating output. Review before deploy.")

        if pkg["warnings"]:
            print("  [compose] WARNINGS:")
            for w in pkg["warnings"]:
                print(f"    ⚠  {w}")
        if pkg["is_deployable"]:
            print("  [compose] ✓ deployable")
        else:
            print("  [compose] ✗ NOT deployable — review warnings before publishing")

        site_json_str = render_site_json(
            sections            = sections,
            labeled             = labeled,
            momentum_by         = momentum_by,
            date                = date_str,
            composition_package = pkg,
            today               = today,
        )
        site_dir = Path(__file__).parent.parent.parent / "topicspace-site" / "public" / "signals" / "ai"
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "latest.json").write_text(site_json_str)
        (site_dir / f"{date_str}.json").write_text(site_json_str)
        print(f"  Site JSON → {site_dir / 'latest.json'}")


if __name__ == "__main__":
    main()
