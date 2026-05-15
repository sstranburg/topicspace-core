#!/usr/bin/env python3
"""
score_source_relevance.py

Annotates each source on each actor's detail with a relevance tier:
  core      — directly supports the actor's expectation
  context   — relevant background (multi-actor or sector framing)
  weak      — alias-adjacent but not material
  excluded  — alias missing or amplification-only

Hybrid strategy:
  1. Rule-based scoring assigns a clear tier when possible.
  2. Borderline cases (ambiguous) are batched per actor and sent to an LLM
     for a final core/context/weak verdict.

Reads:   topicspace-site/public/actors_detail.json
Writes:  topicspace-site/public/actors_detail.json (in place; `relevance` and
                                                    `relevance_reason` added
                                                    to each source)

Usage:
  source venv/bin/activate && python scripts/score_source_relevance.py
  python scripts/score_source_relevance.py --no-llm   # rules only
  python scripts/score_source_relevance.py --dry-run  # show changes without writing
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
ACTORS_DETAIL = ROOT.parent / "topicspace-site" / "public" / "actors_detail.json"

# Import alias map from src/config.py
sys.path.insert(0, str(ROOT))
from src.config import ACTOR_ALIASES  # noqa: E402


# ── Source-type / URL heuristics ────────────────────────────────────────────

AMPLIFICATION_DOMAINS = (
    "yahoo.com", "finance.yahoo", "marketwatch.com", "investorplace.com",
    "fool.com", "thestreet.com", "247wallst.com", "msn.com",
    "seekingalpha.com",  # often aggregator-tier
)


def is_amplification(source: dict) -> bool:
    src_type = (source.get("source_type") or "").lower()
    url = (source.get("url") or "").lower()
    if "amplification" in src_type:
        return True
    if any(d in url for d in AMPLIFICATION_DOMAINS):
        return True
    return False


def count_aliases_in(title: str, aliases: list[str]) -> int:
    title_l = title.lower()
    return sum(1 for a in aliases if a.lower() in title_l)


def count_other_actors(title: str, target_ticker: str) -> int:
    """How many OTHER tracked actors are mentioned in this title?"""
    title_l = title.lower()
    n = 0
    for ticker, aliases in ACTOR_ALIASES.items():
        if ticker == target_ticker:
            continue
        if any(a.lower() in title_l for a in aliases):
            n += 1
    return n


# ── Rule-based scoring ──────────────────────────────────────────────────────

def rule_score(source: dict, target_ticker: str) -> tuple[str, str]:
    """Return (tier, reason).

    Tiers: core, context, weak, excluded, borderline
    `borderline` triggers an LLM judgment if available.
    """
    title = (source.get("title") or "").strip()
    if not title:
        return ("excluded", "empty_title")

    target_aliases = ACTOR_ALIASES.get(target_ticker, [target_ticker.lower()])
    target_hits = count_aliases_in(title, target_aliases)

    if target_hits == 0:
        return ("excluded", "target_alias_absent")

    others = count_other_actors(title, target_ticker)
    ampl = is_amplification(source)
    primary = (target_aliases[0] if target_aliases else target_ticker).lower()
    primary_in_title = primary in title.lower()

    # Strong target focus, no multi-actor noise, real publisher → CORE
    if primary_in_title and others == 0 and not ampl:
        return ("core", "primary_alias_only_target")

    # Target present in a 2-3 actor frame, real publisher → CONTEXT
    if 1 <= others <= 3 and not ampl:
        return ("context", f"multi_actor_frame_others={others}")

    # Lots of other actors → CONTEXT (sector sweep)
    if others >= 4 and not ampl:
        return ("context", f"sector_sweep_others={others}")

    # Amplification but clearly focused on the target → BORDERLINE (let LLM decide)
    if ampl and primary_in_title and others <= 1:
        return ("borderline", "amplification_focused")

    # Amplification multi-actor → WEAK
    if ampl and others >= 2:
        return ("weak", f"amplification_multi_actor_others={others}")

    # Amplification with no clear focus → WEAK
    if ampl:
        return ("weak", "amplification_no_focus")

    # Target alias present but not primary; not amplification → BORDERLINE
    if target_hits and not primary_in_title:
        return ("borderline", "alias_present_not_primary")

    return ("weak", "uncategorized")


# ── LLM borderline judgment ─────────────────────────────────────────────────

LLM_SYSTEM = """You score the relevance of news headlines to a specific stock ticker's forward expectation.

For each headline, return exactly one tier:
  core    — Headline is directly and primarily about the target company. A reader would say "this is news about TICKER."
  context — Headline mentions the target in a multi-company or sector context. Relevant background but not centrally about TICKER.
  weak    — Headline mentions the target only tangentially. Not useful for understanding what's happening to TICKER.

Be strict. Multi-actor sector roundups are context, not core. Amplification/aggregator articles that just re-package other coverage are weak unless the article is primarily about the target.

Respond with a JSON object: {"items": [{"i": <index>, "tier": "core|context|weak", "reason": "<short>"}]}. Do not include any other text."""


def llm_score_batch(target_ticker: str, items: list[dict], client) -> list[dict]:
    """Batch-score borderline items via LLM. Each item must have {idx, title}.
    Returns list aligned to input with {tier, reason}."""
    if not items:
        return []

    user_lines = [f"TARGET: {target_ticker}", "", "HEADLINES:"]
    for it in items:
        user_lines.append(f"  [{it['idx']}] {it['title']}")
    user_msg = "\n".join(user_lines)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": LLM_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=600,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        out_by_idx = {item["i"]: item for item in data.get("items", [])}
        return [
            {
                "tier":   (out_by_idx.get(it["idx"], {}).get("tier") or "weak").lower(),
                "reason": "llm:" + (out_by_idx.get(it["idx"], {}).get("reason") or "no_reason")[:60],
            }
            for it in items
        ]
    except Exception as e:
        print(f"    [{target_ticker}] LLM scoring failed: {e}; falling back to 'weak'")
        return [{"tier": "weak", "reason": "llm_error_fallback"} for _ in items]


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-llm", action="store_true",
                    help="Skip LLM for borderline cases (rules only)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show changes without writing")
    args = ap.parse_args()

    if not ACTORS_DETAIL.exists():
        sys.exit(f"Missing {ACTORS_DETAIL} — run generate_actor_detail.py first.")

    data = json.loads(ACTORS_DETAIL.read_text())
    actors = data.get("actors", [])
    print(f"  scoring sources for {len(actors)} actors")

    client = None
    if not args.no_llm:
        try:
            from openai import OpenAI
            from dotenv import load_dotenv
            load_dotenv()
            if os.environ.get("OPENAI_API_KEY"):
                client = OpenAI()
            else:
                print("  (OPENAI_API_KEY not set; running rules-only)")
        except ImportError:
            print("  (openai package not available; running rules-only)")

    tier_totals = Counter()
    borderline_count = 0
    llm_calls = 0

    t_start = time.time()
    for actor in actors:
        ticker = actor.get("t")
        if not ticker:
            continue
        detail = actor.get("detail") or {}
        sources = detail.get("top_sources") or []
        if not sources:
            continue

        # Pass 1: rule scoring
        borderline_items = []
        for i, src in enumerate(sources):
            tier, reason = rule_score(src, ticker)
            src["relevance"] = tier
            src["relevance_reason"] = reason
            if tier == "borderline":
                borderline_items.append({"idx": i, "title": src.get("title", "")})

        # Pass 2: LLM resolution for borderline cases
        if borderline_items:
            borderline_count += len(borderline_items)
            if client is not None:
                llm_calls += 1
                results = llm_score_batch(ticker, borderline_items, client)
                for item, result in zip(borderline_items, results):
                    sources[item["idx"]]["relevance"] = result["tier"]
                    sources[item["idx"]]["relevance_reason"] = result["reason"]
            else:
                # Fallback when LLM unavailable: borderline → context (conservative)
                for item in borderline_items:
                    sources[item["idx"]]["relevance"] = "context"
                    sources[item["idx"]]["relevance_reason"] = "borderline_fallback_no_llm"

        # Tally
        for src in sources:
            tier_totals[src.get("relevance", "?")] += 1

    elapsed = time.time() - t_start
    print()
    print(f"  ── RESULTS ─────────────────────────────────")
    for tier in ("core", "context", "weak", "excluded"):
        n = tier_totals.get(tier, 0)
        print(f"    {tier:<10}  {n}")
    print(f"    (borderline cases sent to LLM: {borderline_count}; {llm_calls} batches)")
    print(f"  elapsed: {elapsed:.1f}s")

    if args.dry_run:
        print("  (dry-run; not writing)")
        return

    ACTORS_DETAIL.write_text(json.dumps(data, indent=2))
    print(f"\n  wrote {ACTORS_DETAIL}")


if __name__ == "__main__":
    main()
