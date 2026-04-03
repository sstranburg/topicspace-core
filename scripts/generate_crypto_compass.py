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
from src.classify_narrative import (
    CompassClassification,
    _attention_level,
    build_system_prompt,
    post_process_classify_results,
    render_compass_text,
    render_compass_json,
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
    # BTC-primary events are routed through these rules first (most specific → least specific)
    ("btc_institutional_accumulation", [
        "etf", "blackrock", "fidelity", "vanguard", "morgan stanley",
        "treasury", "strategy acquires", "saylor", "microstrategy",
        "state reserve", "reserve bill", "senate bitcoin", "congress bitcoin",
        "bitcoin reserve", "btc reserve", "institutional buys", "h100 bitcoin",
        "bitcoin etf", "bitcoin fund", "accumulation",
    ]),
    ("btc_macro_hedge", [
        " fed ", "federal reserve", "rate cut", "interest rate", "inflation",
        " bond", "gilt", "gold", "macro", "recession", "geopolit", "war",
        "oil crisis", "yield curve", "dollar", "sovereign alternative",
        "bond panic", "safe haven", "hard asset", "store of value",
    ]),
    ("btc_security_custody", [
        "samourai", "domain hijack", "fbi seiz", "fbi took", "privacy wallet",
        "mixer", "tornado", "lost wallet", "cold storage recover", "custody risk",
        "multisig", "private key", "hardware wallet", "wallet seized",
        "address poison", "scam site",
    ]),
    ("btc_sentiment_noise", [
        "panic", "fear", "am i screwed", "should i sell", "stop panicking",
        "bear trap", "bull run", "wen moon", "hodl", "dca", "am i too late",
        "first time", "beginner", "i regret", "i sold too", "should have bought",
        "missed the dip", "paper hands", "diamond hands",
    ]),
    ("btc_technical", [
        "quantum", "mining difficulty", "hash rate", "lightning network",
        "taproot", "ordinal", "inscription", "genesis block", "optech",
    ]),
]

_OTHER_BUCKETS: list[tuple[str, list[str]]] = [
    # AI-crypto crossover — check first, these actors are distinctive
    ("crypto_ai_crossover", [
        "bittensor", " tao ", "subnet", "sn3",
        "render network", " rndr ", "render token",
        "fetch.ai", " fet ", "fetchai",
        "akash", " akt ", "akash network",
        "ai crossover", "ai token", "depin", "decentralized ai",
        " near protocol", "near ai",
    ]),
    # ETH — specific before general
    ("eth_l2_fragmentation", [
        "l2 fragmentation", "ethereum fragmentation", "layer 2 fragmentation",
        "arbitrum", "optimism", "base chain", " rollup", "op mainnet",
        "l2 ecosystem", "ethereum bridge", "bridge time", "l2 fees",
        "ethereum scaling", "zk rollup", "zkevm",
    ]),
    ("eth_institutional_accumulation", [
        "bitmine", "eth treasury", "ethereum treasury", "institutional eth",
        "eth accumulation", "tom lee eth", "eth etf", "ethereum etf",
        "ethereum fund", "eth institutional",
    ]),
    ("eth_security_exploit", [
        "hack", "exploit", "stolen", "vulnerability", "drain wallet",
        "fake stablecoin", "hacker mints", "phishing", "rug pull",
        "protocol exploit", "defi exploit", "smart contract bug",
    ]),
    # SOL — specific before general
    ("sol_narrative_reset", [
        "solana foundation", "gaming is dead", "solana pivot",
        "sol future", "sol positioning", "solana 2026",
        "solana leadership", "real world assets solana",
        "solana strategic", "solana narrative",
    ]),
    ("sol_activity_speculation", [
        "solana bull", "sol price", "solana gambling", "solana dapp",
        "solana defi", "backpack wallet", "bonk", "solana meme",
        "phantom wallet", "solana nft", "pump.fun",
    ]),
    # Cross-asset structural
    ("regulatory_pressure", [
        "sec crypto", "cftc crypto", "crypto ban", "government bitcoin",
        "crypto bill", "crypto law", "crypto regulation", "crypto policy",
        "doj crypto", "crypto enforcement", "wash trading crypto",
    ]),
    ("macro_spillover", [
        "crypto market", "crypto winter", "crypto rally", "crypto crash",
        "market cap crypto", "crypto cycle", "bull market crypto",
        "bear market crypto", "total crypto", "crypto portfolio",
    ]),
    # Catch-alls — must come last
    ("eth_ecosystem_general", [
        "ethereum", " eth ", "erc-", "eip-", "vitalik", "ethereum ecosystem",
    ]),
    ("sol_ecosystem_general", [
        "solana", " sol ", "sealevel",
    ]),
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
    "btc_institutional_accumulation": "institutional",
    "btc_macro_hedge":                "macro",
    "btc_security_custody":           "security_exploit",
    "btc_sentiment_noise":            "retail_sentiment",
    "btc_technical":                  "technical_product",
    "crypto_ai_crossover":            "ecosystem_structure",
    "eth_l2_fragmentation":           "ecosystem_structure",
    "eth_institutional_accumulation": "institutional",
    "eth_security_exploit":           "security_exploit",
    "sol_narrative_reset":            "ecosystem_structure",
    "sol_activity_speculation":       "retail_sentiment",
    "regulatory_pressure":            "macro",
    "macro_spillover":                "macro",
    "eth_ecosystem_general":          "ecosystem_structure",
    "sol_ecosystem_general":          "ecosystem_structure",
    "other":                          "general",
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
# CompassEntry, CompassClassification, _attention_level, build_system_prompt,
# and post_process_classify_results all live in src/classify_narrative.py.

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
    """Classify narrative clusters using LLM + shared post-processing spine."""
    # ── Format cluster inputs for LLM ─────────────────────────────────────────
    cluster_inputs = []
    for c in clusters:
        momentum = _momentum_label(c, early_density, late_density, early_counts or {})
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

    # ── LLM call ──────────────────────────────────────────────────────────────
    client = _get_client()
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        max_tokens=1500,
        messages=[
            {"role": "system", "content": build_system_prompt("crypto")},
            {"role": "user", "content": user_message},
        ],
        response_format=CompassClassification,
    )
    result = response.choices[0].message.parsed

    # ── Build lookup dicts for post-processing ─────────────────────────────────
    key = lambda c: c["narrative"].lower().strip()
    return post_process_classify_results(
        result,
        momentum_by   = {key(c): _momentum_label(c, early_density, late_density, early_counts or {}) for c in clusters},
        attention_by  = {key(c): _attention_level(c["size"]) for c in clusters},
        dom_src_by    = {key(c): c.get("dominant_source", "unknown") for c in clusters},
        cross_src_by  = {key(c): c.get("cross_source_count", 1) for c in clusters},
        reddit_pct_by = {key(c): c.get("source_pct", {}).get("reddit", 0) for c in clusters},
        size_by       = {key(c): c["size"] for c in clusters},
        ecosystem     = "crypto",
    )


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
            "event_count": c["size"],
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


# ── Rendering (shared via src/classify_narrative) ─────────────────────────────

def render_text(sections: dict, date: str) -> str:
    return render_compass_text(sections, date, title="CRYPTO COMPASS")


def render_json(sections: dict, date: str) -> str:
    return render_compass_json(sections, date, ecosystem="crypto")


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
