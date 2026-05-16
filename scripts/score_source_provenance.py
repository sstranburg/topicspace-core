#!/usr/bin/env python3
"""
score_source_provenance.py

For each actor, judges whether each scored top_source SUPPORTS, is
NEUTRAL toward, or CONTRADICTS the actor's current forward-view headline.

This is the provenance trail: an explicit link from L2 (the generated
expectation) back to L1 (the visible sources) on each actor page.

Reads:
  topicspace-site/public/actor_expectations.json
  topicspace-site/public/actors_detail.json    (with `relevance` field
                                                from score_source_relevance.py)

Writes:
  topicspace-site/public/actors_detail.json (in place; adds
                                             `supports_expectation` and
                                             `support_reason` per source)

Behavior:
  - Only sources with relevance == core or context are scored (others are
    not displayed and don't carry weight)
  - If an actor has no forward expectation, sources are not scored
  - One LLM batch call per actor (gpt-4o-mini)

Usage:
  source venv/bin/activate && python scripts/score_source_provenance.py
  python scripts/score_source_provenance.py --no-llm   # mark all unknown
  python scripts/score_source_provenance.py --dry-run
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).parent.parent
ACTORS_DETAIL = ROOT.parent / "topicspace-site" / "public" / "actors_detail.json"
EXPECTATIONS  = ROOT.parent / "topicspace-site" / "public" / "actor_expectations.json"


LLM_SYSTEM = """You judge whether a news headline supports, is neutral toward, or contradicts a forward-view investment thesis on a specific stock.

For each headline, return exactly one verdict:
  supports     — Headline aligns with the forward view (either as evidence for the thesis or as a development that would push the actor in the predicted direction).
  neutral      — Headline is on-topic but doesn't push for or against the forward view.
  contradicts  — Headline points in the OPPOSITE direction from the forward view.

Be strict. If the headline is just generic coverage, that's neutral, not supports.

Respond with JSON: {"items": [{"i": <index>, "verdict": "supports|neutral|contradicts", "reason": "<short>"}]}. Do not include any other text."""


def llm_score_batch(target_ticker: str,
                    forward_view: str,
                    direction: str,
                    items: list[dict],
                    client) -> list[dict]:
    """Batch-score sources for provenance via LLM.
    items: [{idx, title}]. Returns list aligned to input with {verdict, reason}."""
    if not items:
        return []

    user_lines = [
        f"TARGET: {target_ticker}",
        f"FORWARD VIEW: {forward_view}",
        f"DIRECTION: {direction}",
        "",
        "HEADLINES:",
    ]
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
                "verdict":  (out_by_idx.get(it["idx"], {}).get("verdict") or "neutral").lower(),
                "reason":   (out_by_idx.get(it["idx"], {}).get("reason") or "no_reason")[:80],
            }
            for it in items
        ]
    except Exception as e:
        print(f"    [{target_ticker}] LLM provenance scoring failed: {e}; falling back to neutral")
        return [{"verdict": "neutral", "reason": "llm_error_fallback"} for _ in items]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-llm", action="store_true",
                    help="Skip LLM; leave existing source fields unchanged")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show changes without writing")
    args = ap.parse_args()

    if not ACTORS_DETAIL.exists():
        sys.exit(f"Missing {ACTORS_DETAIL}")
    if not EXPECTATIONS.exists():
        sys.exit(f"Missing {EXPECTATIONS} — run generate_actor_expectations.py first.")

    data = json.loads(ACTORS_DETAIL.read_text())
    actors = data.get("actors", [])
    exp_data = json.loads(EXPECTATIONS.read_text())
    exp_by_t = {e["ticker"]: e for e in exp_data.get("expectations", [])}

    print(f"  scoring provenance for {len(actors)} actors against expectations")

    if args.no_llm:
        print("  --no-llm: leaving sources unchanged")
        return

    client = None
    try:
        from openai import OpenAI
        from dotenv import load_dotenv
        load_dotenv()
        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("  OPENAI_API_KEY not set; cannot score provenance")
        client = OpenAI()
    except ImportError:
        sys.exit("  openai package not available; cannot score provenance")

    counts = Counter()
    actors_scored = 0
    t_start = time.time()

    for actor in actors:
        ticker = actor.get("t")
        if not ticker:
            continue
        detail = actor.get("detail") or {}
        sources = detail.get("top_sources") or []
        if not sources:
            continue
        exp = exp_by_t.get(ticker)
        if not exp or not exp.get("headline"):
            continue

        # Only score sources that survived relevance filtering (core/context)
        scoreable = [
            (i, s) for i, s in enumerate(sources)
            if s.get("relevance") in ("core", "context")
        ]
        if not scoreable:
            continue

        forward_view = exp.get("headline", "")
        if exp.get("near_term_view"):
            forward_view += " — " + exp["near_term_view"][:180]
        direction = exp.get("direction", "")

        items = [{"idx": i, "title": s.get("title", "")} for i, s in scoreable]
        results = llm_score_batch(ticker, forward_view, direction, items, client)

        for (i, _), result in zip(scoreable, results):
            sources[i]["supports_expectation"] = result["verdict"]
            sources[i]["support_reason"]       = "llm:" + result["reason"]
            counts[result["verdict"]] += 1

        actors_scored += 1

    elapsed = time.time() - t_start
    print()
    print(f"  ── RESULTS ─────────────────────────────────")
    for k in ("supports", "neutral", "contradicts"):
        print(f"    {k:<13}  {counts.get(k, 0)}")
    print(f"  ({actors_scored} actors scored; {elapsed:.1f}s elapsed)")

    if args.dry_run:
        print("  (dry-run; not writing)")
        return

    ACTORS_DETAIL.write_text(json.dumps(data, indent=2))
    print(f"\n  wrote {ACTORS_DETAIL}")


if __name__ == "__main__":
    main()
