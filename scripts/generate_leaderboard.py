#!/usr/bin/env python3
"""
generate_leaderboard.py

Regenerates narrative-leaderboard.html from live pipeline data:
  - narrative scores   : pressure_score + recent activity + AI signal bucket boosts
  - relative returns   : 5-day return vs QQQ from price parquets
  - market state       : derived from narr score × rel_5d

Writes to:
  - social/narrative-leaderboard.html
  - ../topicspace-site/public/leaderboard.html  (if path exists)

Usage:
  venv/bin/python scripts/generate_leaderboard.py
"""

import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
PRICES_DIR   = ROOT / "data" / "derived" / "prices"
PRESSURE_FILE = ROOT / "data" / "derived" / "narrative_pressure.jsonl"
LEADERSHIP_FILE = ROOT / "data" / "derived" / "narrative_leadership.json"
AI_SIGNALS_FILE = ROOT.parent / "topicspace-site" / "public" / "signals" / "ai" / "latest.json"
TEMPLATE_FILE   = ROOT / "social" / "narrative-leaderboard.html"
SITE_DEST       = ROOT.parent / "topicspace-site" / "public" / "leaderboard.html"

BENCHMARK = "QQQ"

TICKERS = [
    "NVDA", "MRVL", "MSFT", "ARM",  "PLTR", "META", "ADBE", "MU",
    "ORCL", "SMCI", "INTC", "AMD",  "TSLA", "DELL", "GOOGL", "ANET",
    "NBIS", "AVGO", "AMZN", "TSM",  "VRT",  "CRM",  "CRWV", "SOFI",
    "AAPL", "ASML", "SNOW",
]

# Hardcoded overrides for state (for names with known persistent dynamics)
STATE_OVERRIDES = {
    "TSLA": "DISAGREEMENT",
    "SOFI": "DISAGREEMENT",
}

# Short reads by state (fallback)
STATE_READS = {
    "CONFIRMED":    "breakout confirming story",
    "EARLY":        "narrative finding price",
    "REPRICING":    "story intact, price softer",
    "DIVERGENCE":   "price rejecting story",
    "DISAGREEMENT": "conflict unresolved",
    "MACRO":        "moving with tape",
    "UNCLEAR":      "no clean read",
}

# Per-ticker read overrides
READ_OVERRIDES = {
    "NVDA":  "infra rotation, market cautious",
    "MSFT":  "holding and starting to validate",
    "ARM":   "breakout confirming story",
    "PLTR":  "strong story, price diverging",
    "MU":    "earnings narrative hard rejected",
    "ADBE":  "earnings narrative confirmed",
    "SMCI":  "flat, story holding",
    "TSLA":  "brand drag overriding narrative",
    "CRWV":  "narrative fading, price following",
    "VRT":   "infra story, market not paying up",
    "ANET":  "infrastructure narrative, price declining",
    "NBIS":  "story not landing",
    "INTC":  "market not buying it yet",
    "GOOGL": "holding, not breaking",
    "DELL":  "price rejecting story",
    "ORCL":  "recovered from prior selloff",
    "AMZN":  "moving with tape, Globalstar noise",
    "ASML":  "macro overriding signal",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def load_pressure():
    records = []
    if not PRESSURE_FILE.exists():
        return {}
    for line in PRESSURE_FILE.read_text().splitlines():
        if line.strip():
            records.append(json.loads(line))
    by_actor = defaultdict(list)
    for r in records:
        by_actor[r["actor"]].append(r)
    return by_actor


def load_leadership():
    if not LEADERSHIP_FILE.exists():
        return {}
    items = json.loads(LEADERSHIP_FILE.read_text())
    return {x["actor"]: x for x in items}


def load_ai_signal_buckets():
    """Return dict: ticker → bucket (LEAN_IN / BE_CAREFUL / etc.)"""
    if not AI_SIGNALS_FILE.exists():
        return {}
    data = json.loads(AI_SIGNALS_FILE.read_text())
    result = {}
    for sig in data.get("signals", []):
        for ent in sig.get("affected_entities", []):
            t = ent.upper()
            # keep highest-priority bucket seen
            existing = result.get(t)
            bucket = sig["bucket"]
            priority = {"LEAN_IN": 5, "STEP_BACK": 4, "BE_CAREFUL": 3, "WATCH": 2, "IGNORE": 1}
            if existing is None or priority.get(bucket, 0) > priority.get(existing, 0):
                result[t] = bucket
    return result


def load_rel_returns():
    """Return dict: ticker → rel_5d (%)"""
    if not PRICES_DIR.exists():
        return {}
    bench_path = PRICES_DIR / f"{BENCHMARK}.parquet"
    if not bench_path.exists():
        return {}
    bench = pd.read_parquet(bench_path).sort_values("timestamp")
    bench_5d = bench["return_5d"].iloc[-1] * 100

    results = {}
    for t in TICKERS:
        p = PRICES_DIR / f"{t}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p).sort_values("timestamp")
        if len(df) < 2:
            continue
        ticker_5d = df["return_5d"].iloc[-1] * 100
        results[t] = round(ticker_5d - bench_5d, 2)
    return results


def compute_narr_score(ticker, pressure_recs, leadership, bucket):
    """Compute narrative score 35–95 from pipeline + AI signals."""
    if pressure_recs:
        max_pressure = max(r["pressure_score"] for r in pressure_recs)
        recent_48h   = sum(r["events_last_48h"] for r in pressure_recs)
    else:
        max_pressure = 0.0
        recent_48h   = 0

    # base formula: pressure drives 60pts, recency drives 15pts
    base = max_pressure * 60 + min(recent_48h, 250) / 250 * 15
    score = 35 + base  # floor at 35

    # AI signal bucket boosts
    boosts = {"LEAN_IN": 18, "STEP_BACK": 10, "BE_CAREFUL": 8, "WATCH": 4, "IGNORE": 0}
    score += boosts.get(bucket, 0)

    # leadership boost (capped)
    if ticker in leadership:
        ls = leadership[ticker].get("leader_score", 0)
        score += ls * 8

    return min(95, round(score))


def classify_state(ticker, narr, rel):
    if ticker in STATE_OVERRIDES:
        return STATE_OVERRIDES[ticker]

    if narr >= 65 and rel >= 5.0:
        return "CONFIRMED"
    if narr >= 55 and rel >= 1.5:
        return "EARLY"
    if narr >= 45 and rel < -5.0:
        return "DIVERGENCE"
    if narr >= 45 and -5.0 <= rel < 1.5:
        return "REPRICING"
    if rel < -6.0:
        return "DIVERGENCE"
    if narr < 40:
        return "UNCLEAR"
    return "MACRO"


def conflict_flag(state, narr, rel):
    return state in ("DIVERGENCE", "DISAGREEMENT") and narr >= 60


def build_actors(pressure_by_actor, leadership, buckets, rel_returns):
    rows = []
    for t in TICKERS:
        rel  = rel_returns.get(t)
        if rel is None:
            rel = 0.0
            state = "UNCLEAR"
            narr  = 35
        else:
            narr  = compute_narr_score(t, pressure_by_actor.get(t, []), leadership, buckets.get(t, ""))
            state = classify_state(t, narr, rel)

        conflict = conflict_flag(state, narr, rel)
        read = READ_OVERRIDES.get(t, STATE_READS.get(state, "no clean read"))

        rows.append(dict(t=t, state=state, narr=narr, rel=rel, conflict=conflict, read=read))

    # sort by narr descending
    rows.sort(key=lambda r: r["narr"], reverse=True)
    return rows


def actors_js(rows):
    lines = ["const ACTORS = [",
             "  // state, narrative (0-100), rel_5d (% vs benchmark), conflict, short_read"]
    for r in rows:
        rel_str = f"{r['rel']:+.2f}"
        conflict_str = "true" if r["conflict"] else "false"
        line = (
            f"  {{ t:'{r['t']}', state:'{r['state']}', "
            f"narr:{r['narr']}, rel:{rel_str}, "
            f"conflict:{conflict_str}, read:'{r['read']}' }},"
        )
        lines.append(line)
    lines.append("];")
    return "\n".join(lines)


def headline(rows, rel_returns):
    confirmed = [r["t"] for r in rows if r["state"] == "CONFIRMED"]
    diverging  = [r["t"] for r in rows if r["state"] == "DIVERGENCE"]
    n_down = sum(1 for r in rows if r["rel"] < 0)
    total  = len([r for r in rows if r["rel"] != 0.0])

    if confirmed:
        insight = f"{', '.join(confirmed[:2])} confirming. Most others moving with or below the tape."
    else:
        insight = f"No confirmed narratives. {n_down} of {total} high-narrative names down on the week."

    if confirmed:
        takeaway = f"{confirmed[0]} breaking out. " + (
            f"{', '.join(diverging[:3])} diverging." if diverging else "Infrastructure still not confirmed."
        )
    else:
        takeaway = "Narratives are expanding. Market isn't confirming them."

    return insight, takeaway


def narrative_context(rows, buckets):
    lean_in = [r["t"] for r in rows if buckets.get(r["t"]) == "LEAN_IN"]
    if lean_in:
        names = ", ".join(lean_in[:4])
        return (
            f"The rotation is in motion — software development out, AI infrastructure in. "
            f"Data center growth is the lone LEAN IN signal ({names}). "
            f"The market has not confirmed it. Most high-narrative names remain under pressure."
        )
    return (
        "Narratives are active but the market is not paying up. "
        "Most high-pressure names are flat to down on the week."
    )


def format_date(d: date) -> str:
    return d.strftime("%b %-d, %Y")


def update_html(html: str, actors_block: str, insight: str, context: str,
                takeaway: str, today: date) -> str:
    date_str    = format_date(today)
    iso_str     = today.strftime("%Y-%m-%d")
    source_line = f"//  Sources: state engine Mar–Apr 2026, pipeline signals {iso_str}"

    # Replace ACTORS block (from "const ACTORS = [" to "];")
    html = re.sub(
        r"const ACTORS = \[.*?\];",
        actors_block,
        html, flags=re.DOTALL
    )

    # Replace inline strings
    html = re.sub(r'<div class="date-tag">.*?</div>',
                  f'<div class="date-tag">{date_str}</div>', html)
    html = re.sub(r'<div class="page-insight">.*?</div>',
                  f'<div class="page-insight">{insight}</div>', html)
    html = re.sub(r'<div class="narrative-context">.*?</div>',
                  f'<div class="narrative-context">{context}</div>', html)
    html = re.sub(r'<div class="takeaway">.*?</div>',
                  f'<div class="takeaway">{takeaway}</div>', html)
    html = re.sub(r'//  Sources:.*',
                  source_line, html)
    return html


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading pipeline data…")
    pressure    = load_pressure()
    leadership  = load_leadership()
    buckets     = load_ai_signal_buckets()
    rel_returns = load_rel_returns()

    print(f"  {len(pressure)} actors with pressure data")
    print(f"  {len(rel_returns)} tickers with price data")
    print(f"  AI signal buckets: {dict(list(buckets.items())[:6])} …")

    rows = build_actors(pressure, leadership, buckets, rel_returns)
    actors_block = actors_js(rows)
    insight, takeaway = headline(rows, rel_returns)
    context = narrative_context(rows, buckets)
    today = date.today()

    print(f"\nTop 5 by narrative score:")
    for r in rows[:5]:
        print(f"  {r['t']:6s}  narr:{r['narr']:2d}  rel:{r['rel']:+.2f}%  state:{r['state']}")

    # Load and update template
    if not TEMPLATE_FILE.exists():
        print(f"ERROR: template not found at {TEMPLATE_FILE}", file=sys.stderr)
        sys.exit(1)

    html = TEMPLATE_FILE.read_text()
    html = update_html(html, actors_block, insight, context, takeaway, today)

    TEMPLATE_FILE.write_text(html)
    print(f"\nWrote {TEMPLATE_FILE}")

    if SITE_DEST.exists() or SITE_DEST.parent.exists():
        shutil.copy2(TEMPLATE_FILE, SITE_DEST)
        print(f"Copied to {SITE_DEST}")
    else:
        print(f"Site dest not found, skipping copy: {SITE_DEST}")


if __name__ == "__main__":
    main()
