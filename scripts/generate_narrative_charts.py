#!/usr/bin/env python3
"""
Generate narrative-to-market response charts for tracked actors.

Usage:
    python scripts/generate_narrative_charts.py          # all
    python scripts/generate_narrative_charts.py --ticker SOFI
"""

import argparse
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.chart_narrative import make_narrative_price_chart

ROOT = Path(__file__).parent.parent
SITE_CHARTS_DIR = ROOT.parent / "topicspace-site" / "public" / "charts"
ACTORS_FILE = ROOT.parent / "topicspace-site" / "public" / "actors.json"

# Semiconductor / chip tickers — bench against SMH
SEMI_TICKERS = {"NVDA", "AMD", "INTC", "MU", "ASML", "TSM", "AVGO", "ARM", "MRVL", "SMCI"}

_today = date.today()
END_DATE  = _today.strftime("%Y-%m-%d")
START_DATE = (_today - timedelta(days=30)).strftime("%Y-%m-%d")

CHARTS = {

    "MSFT": dict(
        ticker="MSFT",
        benchmark="QQQ",
        start_date=START_DATE,
        end_date=END_DATE,
        state="REPRICING",
        event_markers=[
            {"date": "2026-03-17", "label": "Critique launch",  "tier": "secondary"},
            {"date": "2026-03-27", "label": "Price inflection", "tier": "primary"},
        ],
        title="MSFT: Narrative intact, not confirming",
        subtitle="Slight outperformance vs QQQ — holding, not breaking out.",
    ),

    "SOFI": dict(
        ticker="SOFI",
        benchmark="IWM",
        start_date=START_DATE,
        end_date=END_DATE,
        state="DISAGREEMENT",
        event_markers=[
            {"date": "2026-03-08", "label": "CEO $1M buy",        "tier": "secondary"},
            {"date": "2026-03-24", "label": "Muddy Waters short",  "tier": "primary"},
        ],
        title="SOFI: Active conflict, price resolving lower",
        subtitle="If continuation, confirms short-pressure dominance.",
    ),

    "NVDA": dict(
        ticker="NVDA",
        benchmark="QQQ",
        start_date=START_DATE,
        end_date=END_DATE,
        state="MACRO",
        event_markers=[
            {"date": "2026-03-18", "label": "GTC keynote", "tier": "secondary"},
        ],
        title="NVDA: Macro overriding actor-specific signals",
        subtitle="Stock-level interpretation currently unreliable.",
    ),

    "MU": dict(
        ticker="MU",
        benchmark="QQQ",
        start_date=START_DATE,
        end_date=END_DATE,
        state="REPRICING",
        event_markers=[
            {"date": "2026-03-20", "label": "Dalio +52,355%", "tier": "primary"},
        ],
        title="MU: Market rejecting the demand thesis",
        subtitle="–6.8% vs QQQ — price not paying for the narrative yet.",
    ),

    "META": dict(
        ticker="META",
        benchmark="QQQ",
        start_date=START_DATE,
        end_date=END_DATE,
        state="REPRICING",
        event_markers=[
            {"date": "2026-03-15", "label": "Verified subs signal", "tier": "secondary"},
        ],
        title="META: Narrative intact, price compressing",
        subtitle="Broad repricing — thesis not broken, not confirmed.",
    ),

    "CRM": dict(
        ticker="CRM",
        benchmark="QQQ",
        start_date=START_DATE,
        end_date=END_DATE,
        state="EARLY",
        event_markers=[
            {"date": "2026-03-25", "label": "Enterprise AI signal", "tier": "primary"},
        ],
        title="CRM: Narrative forming, watch for confirmation",
        subtitle="+2.4% vs QQQ — first positive divergence in the window.",
    ),

}


def build_auto_configs() -> dict:
    """Build chart configs for all actors in actors.json not already in CHARTS."""
    if not ACTORS_FILE.exists():
        return {}
    data = json.loads(ACTORS_FILE.read_text())
    configs = {}
    for actor in data.get("actors", []):
        t = actor["t"]
        if t in CHARTS:
            continue
        narrative = actor.get("narrative", "")
        read      = actor.get("read", "")
        state     = actor.get("state", "MACRO")
        nds       = actor.get("nds", 0)
        rel       = actor.get("rel", 0)
        benchmark = "QQQ"
        rel_str   = f"{rel:+.1f}% vs {benchmark}"
        subtitle  = f"{rel_str} — {read[:80]}" if read else rel_str
        configs[t] = dict(
            ticker=t,
            benchmark=benchmark,
            start_date=START_DATE,
            end_date=END_DATE,
            state=state,
            event_markers=[],
            title=f"{t}: {narrative[:55]}" if narrative else t,
            subtitle=subtitle,
        )
    return configs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker (e.g. MSFT)")
    args = parser.parse_args()

    all_configs = {**build_auto_configs(), **CHARTS}  # curated overrides auto

    targets = [args.ticker.upper()] if args.ticker else list(all_configs.keys())
    print(f"Generating {len(targets)} narrative chart(s)")
    print("─" * 50)

    SITE_CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    for ticker in targets:
        if ticker not in all_configs:
            print(f"  [skip] {ticker} — not in actors list")
            continue
        try:
            out_path = make_narrative_price_chart(**all_configs[ticker])
            dest = SITE_CHARTS_DIR / f"{ticker.lower()}_narrative.png"
            shutil.copy2(out_path, dest)
            print(f"  [site] {dest}")
        except Exception as e:
            print(f"  [error] {ticker}: {e}")

    print("─" * 50)
    print("Done.")


if __name__ == "__main__":
    main()
