#!/usr/bin/env python3
"""
Ingest posts from AI/tech/market subreddits using Reddit's public JSON API.

No OAuth required — uses the public .json endpoint with a browser-like User-Agent.
Treated as "formation/attention signal": lower reliability than news, but early.

Subreddits covered:
  Core AI / tech:
    r/artificial, r/singularity, r/MachineLearning, r/OpenAI, r/LocalLLaMA
    r/ClaudeAI, r/GoogleDeepMind, r/Anthropic, r/ChatGPT, r/technology

  Markets / investing overlap:
    r/stocks, r/investing, r/wallstreetbets

Design note:
  Reddit is an overlay — formation signal, attention signal, noise signal.
  It is NOT a primary source of structural truth.
  Reddit-heavy narratives should map to BE_CAREFUL / STEP_BACK / IGNORE
  unless reinforced by higher-trust sources.
"""

import re
import time
import hashlib
import unicodedata
import requests
from collections import defaultdict
from datetime import datetime, timezone
from src.event import Event

USER_AGENT = "storm-narrative-system/1.0 (research; contact@topicspace.com)"

SUBREDDITS = [
    # Core AI / tech
    "artificial",
    "singularity",
    "MachineLearning",
    "OpenAI",
    "LocalLLaMA",
    "ClaudeAI",
    "GoogleDeepMind",
    "Anthropic",
    "ChatGPT",
    "technology",
    # Markets / investing overlap
    "stocks",
    "investing",
    "wallstreetbets",
]

# Minimum engagement to include — filters out zero-engagement noise
MIN_SCORE = 5
MIN_COMMENTS = 2

# Posts per subreddit per fetch (Reddit public API max is 100)
DEFAULT_LIMIT = 100

# Reliability prior — lower than curated news (0.75), above raw hype
REDDIT_RELIABILITY = 0.50

# ---------------------------------------------------------------------------
# Actor alias map — Reddit-specific. Slightly looser than config.py to catch
# consumer-context references ("claude", "gemini", "grok ai") while still
# avoiding broad false positives.
# Key = canonical actor ticker/name used in the pipeline
# Values = lowercase search strings (space-padded where needed to avoid
#          substring collisions)
# ---------------------------------------------------------------------------
AI_ACTOR_ALIASES: dict[str, list[str]] = {
    # Chips / infrastructure supply
    "NVDA":  ["nvidia", " nvda "],
    "AMD":   [" amd ", "advanced micro devices", "radeon ai"],
    "INTC":  ["intel", " intc "],
    "AVGO":  ["broadcom", " avgo "],
    "TSM":   ["tsmc", "taiwan semiconductor"],
    "ASML":  [" asml "],
    "MU":    ["micron", " hbm ", "hbm memory", "hbm chip", "high bandwidth memory"],
    "MRVL":  ["marvell", " mrvl "],
    "SMCI":  ["supermicro", "super micro"],
    "DELL":  [" dell "],
    "SAMSNG":["samsung semiconductor", "samsung foundry", "samsung hbm"],
    # AI cloud / infra providers
    "CRWV":  ["coreweave", "core weave"],
    "SKHX":  ["sk hynix", "skhynix"],
    # Hyperscalers
    "MSFT":  ["microsoft", " msft ", " azure "],
    "AMZN":  ["amazon", " aws ", " amzn "],
    "GOOGL": ["google", "alphabet", "deepmind", "google deepmind", " gcp ", "gemini ai", "gemini model", "gemini 2"],
    # AI demand-side
    "META":  [" meta ", "meta ai", "facebook ai", " llama ", "llama 3", "llama 4"],
    "ORCL":  ["oracle cloud", "oracle ai"],
    "CRM":   ["salesforce", "agentforce"],
    "TSLA":  ["tesla", " xai ", "x.ai", "grok ai", "elon ai"],
    "AAPL":  ["apple intelligence", "apple ai", " aapl "],
    "PLTR":  ["palantir", " pltr "],
    # AI labs (private — tracked by name)
    "OPENAI":    ["openai", "chatgpt", "gpt-4", "gpt-5", "gpt4", "gpt5", " o1 ", " o3 ",
                  "openai api", "openai model", "sora "],
    "ANTHROPIC": ["anthropic", " claude ", "claude 3", "claude opus", "claude sonnet",
                  "claude haiku", "claude ai"],
}


# ---------------------------------------------------------------------------
# Noise patterns — structural subreddit meta-posts and low-signal titles
# ---------------------------------------------------------------------------
_NOISE_TITLE_PATTERNS = [
    # Recurring subreddit threads
    "daily discussion", "daily general", "weekly thread", "weekly discussion",
    "megathread", "monthly thread", "monthly discussion",
    "mentor monday", "simple questions", "noob questions", "beginner questions",
    "ama ", " ama:", "ask me anything",
    "what are you", "what's everyone", "what is everyone", "what's your",
    "buy/sell/trade", "buy sell trade",
    # Generic consumer chatter
    "which ai should i", "which ai is better", "best ai for",
    "help me choose", "recommend me", "what ai do you",
    "vs claude", "vs chatgpt", "vs gemini",  # pure comparisons w/o ecosystem signal
    # Coding support
    "code not working", "help with my code", "getting an error",
    "how do i use", "how do i get",
    # Pure hype / reaction
    "this is insane", "mind blown", "blew my mind", "changed my life",
    "this is crazy", "holy moly", "no way this is real",
    # Meme/joke markers
    "[meme]", "[oc meme]", "me when", "nobody:", "reddit when",
]

# ---------------------------------------------------------------------------
# Narrative lane routing — heuristic keyword → lane name
# First match wins; returns "default" if no match.
# These lanes prevent giant catch-all clusters in downstream processing.
# ---------------------------------------------------------------------------
_LANE_RULES: list[tuple[list[str], str]] = [
    # Put more specific patterns first
    (["open source", "open-source", "open weights", "hugging face", "ollama",
      "local model", "run locally", "self-host"], "open_source_models"),

    (["price cut", "price reduction", "free tier", "commodit", "cheaper than",
      "costs less", "cost per token", "api pricing"], "pricing_commoditization"),

    (["alignment", "jailbreak", "harmful", "responsible ai", "ai safety act",
      "misuse", "bias in", "discriminat"], "safety_policy"),

    (["regulation", "regulatory", "eu ai act", "ai act", "congress", "senate",
      "legislation", "policy", "ban on", "executive order"], "regulation"),

    (["partnership", "deal with", "agreement with", "collaboration", "signed a",
      "joint venture", "licensing deal"], "partnerships"),

    (["enterprise", "business use", "workplace", "corporate", "productivity",
      "ai agent", "agentic", "deployed at", "rollout"], "enterprise_deployment"),

    (["data center", "datacenter", "gpu cluster", "server rack", "inference server",
      "chip delivery", "supply chain", "manufacturing"], "infrastructure_delivery"),

    (["gpu shortage", "compute shortage", "capacity constrain", "waitlist",
      "out of stock", "allocation", "demand outstrip"], "capacity_constraints"),

    (["stock price", "market cap", "valuation", "ipo", "fundrais", "shares",
      "investor", "earnings", "quarterly result", "revenue beat"], "market_noise"),

    (["consumer", "personal use", "everyday", "trying out", "my experience",
      "review of", "compared to gpt", "compared to claude"], "consumer_hype"),

    (["new model", "model release", "benchmark", "training run", "weights",
      "parameter", "context window", "token limit", "multimodal",
      "reasoning model", "frontier model"], "model_layer"),
]

_DEFAULT_LANE = "default"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detect_ai_actors(text: str) -> list[str]:
    """Detect AI ecosystem actors from free-form text using alias matching."""
    padded = f" {text.lower()} "
    detected: list[str] = []
    for ticker, aliases in AI_ACTOR_ALIASES.items():
        for alias in aliases:
            if alias in padded:
                detected.append(ticker)
                break
    return sorted(set(detected))


def route_narrative_lane(text: str) -> str:
    """Heuristically route text to a narrative lane. First match wins."""
    lower = text.lower()
    for keywords, lane in _LANE_RULES:
        if any(kw in lower for kw in keywords):
            return lane
    return _DEFAULT_LANE


def _normalize_title_for_dedup(title: str) -> str:
    """
    Normalize title for near-duplicate detection.
    Handles crossposts and minor rephrasing of the same story.
    """
    t = unicodedata.normalize("NFKC", title.lower())
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Take first 80 chars — enough to fingerprint the story without over-sensitivity
    return t[:80]


def _title_hash(title: str) -> str:
    norm = _normalize_title_for_dedup(title)
    return hashlib.md5(norm.encode()).hexdigest()


def _make_event_id(post_id: str) -> str:
    raw = f"reddit_ai|{post_id}"
    return "reddit_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_noise(post: dict) -> tuple[bool, str]:
    """
    Return (True, reason) if the post should be dropped, else (False, "").
    Checks: deleted, NSFW, stickied, low engagement, noise title patterns.
    """
    # Deleted / removed
    selftext = post.get("selftext", "")
    author = post.get("author", "")
    if selftext in ("[deleted]", "[removed]") or author in ("[deleted]", "AutoModerator"):
        return True, "deleted_or_removed"

    title = (post.get("title") or "").strip()
    if not title:
        return True, "empty_title"

    # NSFW
    if post.get("over_18"):
        return True, "nsfw"

    # Stickied mod posts
    if post.get("stickied"):
        return True, "stickied"

    # Low engagement
    score = post.get("score", 0)
    num_comments = post.get("num_comments", 0)
    if score < MIN_SCORE:
        return True, f"low_score({score})"
    if num_comments < MIN_COMMENTS:
        return True, f"low_comments({num_comments})"

    # Noise title patterns
    title_lower = title.lower()
    for pat in _NOISE_TITLE_PATTERNS:
        if pat in title_lower:
            return True, f"noise_pattern({pat[:20]})"

    return False, ""


def _post_to_event(post: dict, subreddit: str) -> Event | None:
    """Convert a raw Reddit post dict to an Event, or None if filtered out."""
    noisy, _ = _is_noise(post)
    if noisy:
        return None

    title = post["title"].strip()
    body = (post.get("selftext") or "")[:400].replace("\n", " ")

    # Actor detection on title + body
    combined = f"{title} {body}"
    actors = detect_ai_actors(combined)

    # Require at least one known actor — prevents generic AI chatter flooding the pipeline
    if not actors:
        return None

    created_utc = post.get("created_utc")
    if not created_utc:
        return None
    timestamp = datetime.fromtimestamp(float(created_utc), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    permalink = post.get("permalink", "")
    url = f"https://www.reddit.com{permalink}" if permalink else None

    lane = route_narrative_lane(combined)

    return Event(
        event_id=_make_event_id(post["id"]),
        timestamp=timestamp,
        source="reddit",
        title=title,
        text=body,
        url=url,
        actors=actors,
        tags=[],
        narrative_lane=lane,
        reliability=REDDIT_RELIABILITY,
        metadata={
            "subreddit": subreddit,
            "score": post.get("score", 0),
            "num_comments": post.get("num_comments", 0),
            "reddit_id": post["id"],
            "source_type": "community",
        },
    )


# ---------------------------------------------------------------------------
# Fetch functions
# ---------------------------------------------------------------------------

def fetch_reddit_posts(
    subreddit: str,
    start_date: str,
    end_date: str,
    limit: int = DEFAULT_LIMIT,
    sleep_between: float = 1.5,
) -> tuple[list[Event], int]:
    """
    Fetch recent posts from a single subreddit, filtered to [start_date, end_date].

    Returns (events, raw_count) — events that passed all filters, and raw post count.
    Reddit's public API returns the most recent posts; no historical backfill.
    Run daily; deduplication in merge_events handles overlap.
    """
    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end_date).replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )

    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    params = {"limit": min(limit, 100), "raw_json": 1}
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Reddit r/{subreddit}: fetch failed — {e}")
        return [], 0

    children = (data.get("data") or {}).get("children") or []
    raw_count = len(children)

    events: list[Event] = []
    for child in children:
        post = child.get("data") or {}
        created = post.get("created_utc")
        if not created:
            continue
        post_dt = datetime.fromtimestamp(float(created), tz=timezone.utc)
        if post_dt < start_dt or post_dt > end_dt:
            continue
        event = _post_to_event(post, subreddit)
        if event:
            events.append(event)

    time.sleep(sleep_between)
    return events, raw_count


def fetch_all_subreddits(
    start_date: str,
    end_date: str,
    subreddits: list[str] | None = None,
) -> list[Event]:
    """
    Fetch posts from all configured AI subreddits.

    Applies cross-subreddit near-duplicate suppression (same story posted on
    multiple subs) via normalized title hashing.

    Logs per-subreddit stats and a summary at the end.
    """
    targets = subreddits or SUBREDDITS
    all_events: list[Event] = []
    seen_title_hashes: set[str] = set()

    # Stats tracking
    stats: dict[str, dict] = {}
    actor_counts: dict[str, int] = defaultdict(int)

    for sub in targets:
        events, raw_count = fetch_reddit_posts(sub, start_date, end_date)

        # Near-duplicate suppression across subreddits
        deduped: list[Event] = []
        dup_count = 0
        for e in events:
            h = _title_hash(e.title)
            if h in seen_title_hashes:
                dup_count += 1
            else:
                seen_title_hashes.add(h)
                deduped.append(e)
                for actor in e.actors:
                    actor_counts[actor] += 1

        kept = len(deduped)
        dropped = raw_count - kept - dup_count  # filtered by _post_to_event
        stats[sub] = {"raw": raw_count, "kept": kept, "dupes": dup_count, "dropped": raw_count - kept - dup_count}

        print(f"  Reddit r/{sub}: {raw_count} fetched → {kept} kept, {dup_count} cross-sub dupes, {dropped} filtered")
        all_events.extend(deduped)

    # Summary
    total_raw = sum(s["raw"] for s in stats.values())
    total_kept = sum(s["kept"] for s in stats.values())
    total_dupes = sum(s["dupes"] for s in stats.values())

    print(f"\n  Reddit AI summary: {total_raw} fetched → {total_kept} kept ({total_dupes} cross-sub dupes removed)")

    top_subs = sorted(stats.items(), key=lambda x: x[1]["kept"], reverse=True)[:5]
    top_subs_str = ", ".join(f"r/{s}({v['kept']})" for s, v in top_subs)
    print(f"  Top subreddits by kept: {top_subs_str}")

    top_actors = sorted(actor_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    if top_actors:
        print(f"  Top matched actors: {', '.join(f'{a}({c})' for a, c in top_actors)}")

    return all_events
