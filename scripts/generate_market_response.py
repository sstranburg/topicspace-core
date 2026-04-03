#!/usr/bin/env python3
"""
Run the TopicSpace State Engine and patch market_response into
public/signals/ai/latest.json (and dated copy).

Usage:
    python scripts/generate_market_response.py
    python scripts/generate_market_response.py --date 2026-03-30
    python scripts/generate_market_response.py --tickers MSFT SOFI NVDA
"""

import argparse
import json
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from src.state_engine import classify_all, classify_actor, select_homepage_actors, system_snapshot

AI_SIGNALS_BASE = pathlib.Path("../topicspace-site/public/signals/ai")


def build_payload(states) -> list[dict]:
    return [
        {
            "ticker":           s.actor,
            "state":            s.state,
            "benchmark":        s.benchmark,
            "rel_5d":           s.relative_return_5d,
            "confidence":       s.confidence,
            "context":          s.context,
        }
        for s in states
    ]


def patch_json(path: pathlib.Path, market_response: list[dict], snapshot: dict) -> None:
    if not path.exists():
        print(f"  [skip] {path} not found")
        return
    data = json.loads(path.read_text())
    data["market_response"]  = market_response
    data["system_snapshot"]  = snapshot
    path.write_text(json.dumps(data, indent=2))
    print(f"  [patched] {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--tickers", nargs="+",
                        help="Classify specific tickers only")
    parser.add_argument("--top", type=int, default=5,
                        help="Number of homepage actors to select (default 5)")
    args = parser.parse_args()

    print(f"State Engine  date={args.date}")
    print("─" * 50)

    if args.tickers:
        all_states = [s for t in args.tickers
                      if (s := classify_actor(t.upper(), args.date)) is not None]
        homepage = all_states
    else:
        all_states = classify_all(args.date)
        # Always include SOFI (known conflict actor, separate pipeline)
        sofi = classify_actor("SOFI", args.date)
        if sofi and sofi.actor not in {s.actor for s in all_states}:
            all_states.append(sofi)
        homepage = select_homepage_actors(all_states, n=args.top)

    # Print full classification table
    print(f"{'Actor':<8} {'State':<14} {'Rel 5D':>7}  {'Conf':<8} {'Wt':>5}  Context")
    print("─" * 90)
    for s in sorted(all_states, key=lambda x: -x.narrative_weight):
        print(f"{s.actor:<8} {s.state:<14} {s.relative_return_5d:>+.1%}   "
              f"{s.confidence:<8} {s.narrative_weight:>5.2f}  {s.context[:55]}")

    print()
    print(f"Homepage selection ({len(homepage)} actors):")
    print("─" * 50)
    for s in homepage:
        print(f"  {s.actor} — {s.state}  [{s.confidence}]")
        print(f"    {s.context}")

    snapshot = system_snapshot(all_states)
    print()
    print("System Snapshot:")
    print(f"  {snapshot['summary']}")
    print(f"  {snapshot['interpretation']}")

    payload = build_payload(homepage)
    patch_json(AI_SIGNALS_BASE / "latest.json", payload, snapshot)
    patch_json(AI_SIGNALS_BASE / f"{args.date}.json", payload, snapshot)
    print("Done.")


if __name__ == "__main__":
    main()
