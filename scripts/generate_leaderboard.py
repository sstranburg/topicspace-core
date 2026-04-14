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
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
PRICES_DIR    = ROOT / "data" / "derived" / "prices"
PRESSURE_FILE = ROOT / "data" / "derived" / "narrative_pressure.jsonl"
LEADERSHIP_FILE = ROOT / "data" / "derived" / "narrative_leadership.json"
AI_SIGNALS_FILE = ROOT.parent / "topicspace-site" / "public" / "signals" / "ai" / "latest.json"
TEMPLATE_FILE   = ROOT / "social" / "narrative-leaderboard.html"
SITE_DEST       = ROOT.parent / "topicspace-site" / "public" / "leaderboard.html"
HISTORY_FILE    = ROOT / "data" / "derived" / "narrative_history.jsonl"
EVENTS_FILE     = ROOT / "data" / "normalized" / "tech_ecosystem_filtered.jsonl"

CHART_DAYS = 30  # rolling window for chart data

BENCHMARK = "QQQ"

TICKERS = [
    "NVDA", "MRVL", "MSFT", "ARM",  "PLTR", "META", "ADBE", "MU",
    "ORCL", "SMCI", "INTC", "AMD",  "TSLA", "DELL", "GOOGL", "ANET",
    "NBIS", "AVGO", "AMZN", "TSM",  "VRT",  "CRM",  "CRWV", "SOFI",
    "AAPL", "ASML", "SNOW", "DDOG", "CEG",  "VST",  "ZETA",
    "USAR", "MP",
]

EXPERIMENTAL_TICKERS = {"USAR", "MP"}

# Hardcoded overrides for state (for names with known persistent dynamics)
STATE_OVERRIDES = {
    "TSLA": "DISAGREEMENT",
    "SOFI": "DISAGREEMENT",
}

# Short reads by state (fallback)
STATE_READS = {
    "CONFIRMED":        "price confirming narrative",
    "EARLY":            "price starting to follow",
    "REPRICING":        "price lagging narrative",
    "DIVERGENCE":       "story not being paid",
    "NEG_CONFIRMATION": "selloff confirming narrative",
    "DISAGREEMENT":     "price rejecting negative narrative",
    "MACRO":            "moving with tape",
    "PRICE-LED":        "price ahead of story",
    "UNCLEAR":          "no follow-through",
}

# Narrative direction: +1 = positive (tailwind), -1 = negative (headwind)
# Omitted tickers default to +1
ACTOR_DIRECTIONS = {
    "MU":   -1,   # HBM demand miss → bearish
    "TSLA": -1,   # brand drag, recession risk → bearish
    "SOFI": -1,   # competition pressure → bearish
    "SNOW": -1,   # growth stalling → bearish
    "CRWV": -1,   # IPO hype fading → bearish
    "CRM":  -1,   # Agentforce fading → bearish
    "INTC": -1,   # foundry pivot skepticism → bearish
    "TSM":  -1,   # geopolitical risk dominant → bearish
}

# Per-ticker narrative descriptions (what the story is actually about)
NARRATIVES = {
    "NVDA":  "AI infrastructure buildout; China market share erosion",
    "MRVL":  "AI networking revenue accelerating",
    "MSFT":  "Copilot + OpenAI bet gaining traction",
    "ARM":   "Architecture licensing expanding into AI chips",
    "PLTR":  "Government AI contracts + commercial growth",
    "META":  "AI chips and data center build-out",
    "ADBE":  "Earnings pressure vs AI creative tools story",
    "MU":    "HBM demand uncertain after earnings miss",
    "ORCL":  "Cloud + AI infra expansion, rising price targets",
    "SMCI":  "AI server demand; VAST Data partnership",
    "INTC":  "Qualcomm acquisition chatter; foundry pivot",
    "AMD":   "AI GPU competition narrative vs NVDA",
    "TSLA":  "Brand drag from Musk politics; recession sensitivity",
    "DELL":  "AI server demand vs margin pressure",
    "GOOGL": "AI search competition + Waymo",
    "ANET":  "AI networking infrastructure demand",
    "NBIS":  "European AI cloud buildout",
    "AVGO":  "Custom silicon; insider activity cooling",
    "AMZN":  "Custom silicon (Trainium) + Globalstar buyout",
    "TSM":   "Advanced node demand; geopolitical risk",
    "VRT":   "Power and cooling for AI data centers",
    "CRM":   "Agentforce adoption narrative cooling",
    "CRWV":  "CoreWeave cloud IPO hype fading",
    "SOFI":  "Fintech competition pressures",
    "AAPL":  "AI features rollout + India manufacturing",
    "ASML":  "EUV demand tied to AI chip cycle",
    "SNOW":  "Data cloud growth narrative stalling",
    "DDOG":  "AI-native observability; enterprise monitoring adoption in AI stacks",
    "CEG":   "Nuclear power capacity for AI data centers; hyperscaler offtake deals",
    "VST":   "Gas and nuclear power generation serving AI data center demand",
    "ZETA":  "AI-native customer data platform; enterprise marketing automation adoption",
    "USAR":  "Rare earth supply chain; domestic critical minerals push",
    "MP":    "Rare earth mining; China tariff tailwind and supply chain angle",
}

# Per-ticker read overrides (only where state default is insufficient)
# Values here must come from the canonical vocabulary used by STATE_READS,
# or a clearly distinct phrase that the morning summary can interpret unambiguously.
# Do NOT use: "price ahead of narrative" (ambiguous with direction)
# DO use: "price ahead of story" (bullish), "price confirming negative story" (bearish)
READ_OVERRIDES = {
    "MRVL":  "early confirmation forming",        # EARLY but stronger signal than default
    "AMD":   "narrative active, price flat",       # REPRICING but NDS near zero, rel flat
    "AVGO":  "moving with tape",                   # UNCLEAR but narrative too weak to flag
    "ADBE":  "price ahead of story",               # classified MACRO; NDS strongly negative
    "ARM":   "price ahead of story",               # extreme price lead on bullish narrative
    "INTC":  "price confirming negative story",    # NEG_CONFIRMATION, NDS slightly negative
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


def classify_state(ticker, narr, rel, direction=1):
    if ticker in STATE_OVERRIDES:
        return STATE_OVERRIDES[ticker]

    # Negative narrative: bearish states
    if direction < 0:
        if rel > 2.0:   return "DISAGREEMENT"    # price rising against bearish narrative
        return "NEG_CONFIRMATION"                 # price flat or falling with bearish narrative

    # Positive narrative: existing logic
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
    # Price running ahead of narrative: outperforming but story not there
    price_score = max(0, min(100, 50 + rel * 5))
    nds = narr - price_score
    if rel > 2.0 and narr < 60 and nds < -20:
        return "PRICE-LED"
    if narr < 40:
        return "UNCLEAR"
    return "MACRO"


def conflict_flag(state, narr, rel):
    return state in ("DIVERGENCE", "DISAGREEMENT", "NEG_CONFIRMATION") and narr >= 60


def build_actors(pressure_by_actor, leadership, buckets, rel_returns):
    rows = []
    for t in TICKERS:
        direction = ACTOR_DIRECTIONS.get(t, 1)
        rel  = rel_returns.get(t)
        if rel is None:
            rel = 0.0
            state = "UNCLEAR"
            narr  = 35
        else:
            narr  = compute_narr_score(t, pressure_by_actor.get(t, []), leadership, buckets.get(t, ""))
            state = classify_state(t, narr, rel, direction)

        conflict = conflict_flag(state, narr, rel)
        read = READ_OVERRIDES.get(t, STATE_READS.get(state, "no clean read"))
        narrative = NARRATIVES.get(t, "")

        # Signed NDS: direction × (narr − 50) − rel × 5
        # For dir=+1 this equals the old formula without the 0–100 cap on price_score
        nds = round(direction * (narr - 50) - rel * 5, 1)

        rows.append(dict(t=t, state=state, narr=narr, rel=rel, dir=direction,
                         conflict=conflict, read=read, narrative=narrative, nds=nds,
                         exp=t in EXPERIMENTAL_TICKERS))

    # sort by NDS descending
    rows.sort(key=lambda r: r["nds"], reverse=True)
    return rows


def actors_js(rows):
    lines = ["const ACTORS = [",
             "  // state, narrative (0-100), rel_5d (% vs benchmark), conflict, short_read, narrative_desc"]
    for r in rows:
        rel_str = f"{r['rel']:+.2f}"
        conflict_str = "true" if r["conflict"] else "false"
        narrative_escaped = r["narrative"].replace("'", "\\'")
        line = (
            f"  {{ t:'{r['t']}', state:'{r['state']}', "
            f"narr:{r['narr']}, rel:{rel_str}, nds:{r['nds']}, dir:{r['dir']}, "
            f"conflict:{conflict_str}, read:'{r['read']}', "
            f"story:'{narrative_escaped}', exp:{'true' if r['exp'] else 'false'} }},"
        )
        lines.append(line)
    lines.append("];")
    return "\n".join(lines)


EARLY_CONF_READS = {"price starting to follow", "early confirmation forming"}

# Read types eligible for cluster detection (≥3 actors same read = system-level signal)
CLUSTER_READS = {
    "price rejecting negative narrative": "bearish rejection",
    "price ahead of story":              "price-led movement",
    "story not being paid":              "narrative divergence",
    "selloff confirming narrative":      "downside confirmation",
}


def detect_clusters(rows: list) -> dict[str, list[str]]:
    """
    Group actors by read type. Return {read: [tickers]} for any group ≥3.
    Sorted largest cluster first.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r["read"] in CLUSTER_READS:
            groups[r["read"]].append(r["t"])
    return dict(
        sorted(
            {read: tickers for read, tickers in groups.items() if len(tickers) >= 3}.items(),
            key=lambda x: -len(x[1])
        )
    )


def format_clusters(clusters: dict[str, list[str]]) -> str:
    """Render all clusters as comma-separated surface lines."""
    parts = []
    for read, tickers in clusters.items():
        label = CLUSTER_READS[read]
        parts.append(f"Cluster of {label} forming: {', '.join(tickers)}.")
    return " ".join(parts)


def headline(rows, rel_returns):
    clusters   = detect_clusters(rows)
    confirmed  = [r["t"] for r in rows if r["state"] == "CONFIRMED"]
    # Early confirmation: EARLY state or read override — not yet clean but directionally forming
    early_conf = [r["t"] for r in rows
                  if r["read"] in EARLY_CONF_READS and r["t"] not in confirmed]
    diverging  = [r["t"] for r in rows if r["state"] == "DIVERGENCE"]
    price_led  = [r["t"] for r in rows if r["state"] in ("MACRO", "POS_MACRO")]
    n_down = sum(1 for r in rows if r["rel"] < 0)
    total  = len([r for r in rows if r["rel"] != 0.0])

    # Cluster prefix: surface before per-actor reads when a cluster is present
    cluster_prefix = (format_clusters(clusters) + " ") if clusters else ""

    if confirmed:
        others = [t for t in (diverging + price_led) if t not in confirmed]
        insight = (
            cluster_prefix
            + f"{', '.join(confirmed[:2])} confirming. "
            + (f"{', '.join(others[:2])} price-led. " if others else "")
            + "Multiple behaviors coexisting on the board."
        )
    elif early_conf:
        insight = (
            cluster_prefix
            + f"No clean confirmation — only early follow-through forming"
            f" ({', '.join(early_conf)})."
            f" {n_down} of {total} names down."
        )
    else:
        n_price_led = len(price_led)
        insight = (
            cluster_prefix
            + f"{n_down} of {total} names down."
            + (f" {', '.join(price_led[:2])} price-led." if n_price_led else "")
            + " Multiple behaviors coexisting."
        )

    # Takeaway: dominant cluster drives the lead if present, otherwise actor-level
    if clusters:
        top_read, top_tickers = next(iter(clusters.items()))
        top_label = CLUSTER_READS[top_read]
        takeaway = (
            f"{len(top_tickers)}-name {top_label} cluster: {', '.join(top_tickers[:3])}."
            + (f" {', '.join(confirmed[:1])} confirming." if confirmed else "")
        )
    elif confirmed:
        takeaway = f"{confirmed[0]} breaking out. " + (
            f"{', '.join(diverging[:3])} diverging." if diverging else
            (f"{', '.join(price_led[:2])} price-led." if price_led else "Board behavior mixed.")
        )
    elif early_conf:
        takeaway = (
            f"Early follow-through forming — {', '.join(early_conf[:2])}. "
            + (f"{', '.join(diverging[:2])} diverging." if diverging else "Multiple behaviors coexisting.")
        )
    else:
        takeaway = (
            "Multiple behaviors coexisting. "
            + (f"{', '.join(diverging[:2])} diverging." if diverging else "No early confirmation yet.")
        )

    return insight, takeaway


def page_title(rows, buckets):
    """
    Generate a short title for actors.json meta.page_title.
    Reflects board TENSION, not direction — never a binary or directional claim.
    Titles are short, punchy, and editorially overrideable after pipeline runs.

    Preferred templates (use exactly when condition matches):
      "Mixed signals. Price leading in pockets."
      "No clean confirmation. Early follow-through forming."
      "Multiple behaviors. No dominant regime."
    """
    confirmed  = [r["t"] for r in rows if r["state"] == "CONFIRMED"]
    early_conf = [r["t"] for r in rows
                  if r["read"] in EARLY_CONF_READS and r["t"] not in confirmed]
    price_led  = [r["t"] for r in rows if r["state"] in ("MACRO", "POS_MACRO", "PRICE-LED")]
    diverging  = [r["t"] for r in rows if r["state"] == "DIVERGENCE"]
    neg_conf   = [r["t"] for r in rows if r["state"] == "NEG_CONFIRMATION"]
    disagreem  = [r["t"] for r in rows if r["state"] == "DISAGREEMENT"]
    n_down     = sum(1 for r in rows if r["rel"] < 0)
    total      = len([r for r in rows if r["rel"] != 0.0])
    n_conf     = len(confirmed)
    n_early    = len(early_conf)
    n_price    = len(price_led)
    n_div      = len(diverging)
    n_neg      = len(neg_conf)
    n_dis      = len(disagreem)
    down_ratio = n_down / total if total else 0

    # Broad clean confirmation
    if n_conf >= 5:
        return "Broad confirmation. Multiple narratives being validated."

    if n_conf >= 3 and n_price >= 3:
        return "Confirmation and price-leading coexisting. Multiple behaviors active."

    # Explicit Transitional: high price-led, meaningful confirmation and divergence
    if n_price >= 8 and n_conf >= 2 and n_div >= 2:
        return "Multiple behaviors. No dominant regime."

    # No clean confirmation but early follow-through building — surface the tension
    if n_conf == 0 and n_early >= 3 and n_price >= 4:
        return "No clean confirmation. Early follow-through forming."

    # Price-led dominant
    if n_price >= 6:
        return "Mixed signals. Price leading in pockets."

    if n_price >= 4 and n_conf >= 1:
        return "Mixed signals. Price leading in pockets."

    # Mixed board: multiple behaviors in balance
    if n_conf >= 2 and n_price >= 2 and n_div >= 2:
        return "Multiple behaviors. No dominant regime."

    if n_conf >= 1 and n_price >= 3:
        return "Mixed signals. Price leading in pockets."

    # Some early confirmation present
    if n_conf == 0 and n_early >= 1:
        return "No clean confirmation. Early follow-through forming."

    # Bearish narrative breaking down in multiple names
    if n_dis >= 4 and n_neg <= 1:
        return "Bearish narrative losing grip. Price diverging in multiple names."

    if n_dis >= 3 and n_conf >= 1:
        return "Multiple behaviors. No dominant regime."

    # Mostly down board with pockets of movement
    if down_ratio > 0.6 and (n_conf >= 1 or n_dis >= 2 or n_early >= 1):
        return "Mixed signals. Price leading in pockets."

    if down_ratio > 0.6 and n_price >= 2:
        return "Multiple behaviors. No dominant regime."

    # Divergence heavy: stories active, price not following
    if n_div >= 5:
        return "Stories active. Market not following."

    if n_div >= 3 and n_neg >= 3:
        return "Narrative-price gap widening."

    # Genuinely one-sided downside
    if n_neg >= 5 and n_conf == 0:
        return "Broad pressure. Narratives confirming."

    if n_neg >= 3 and n_conf == 0:
        return "Multiple behaviors. No dominant regime."

    # Default
    return "Multiple behaviors. No dominant regime."


def narrative_context(rows, buckets):
    clusters   = detect_clusters(rows)
    lean_in    = [r["t"] for r in rows if buckets.get(r["t"]) == "LEAN_IN"]
    confirmed  = [r["t"] for r in rows if r["state"] == "CONFIRMED"]
    early_conf = [r["t"] for r in rows
                  if r["read"] in EARLY_CONF_READS and r["t"] not in confirmed]
    diverging  = [r["t"] for r in rows if r["state"] == "DIVERGENCE"]
    price_led  = [r["t"] for r in rows if r["state"] in ("MACRO", "POS_MACRO")]
    n_confirmed = len(confirmed)
    n_price_led = len(price_led)
    n_diverging = len(diverging)

    if lean_in:
        names = ", ".join(lean_in[:4])
        cluster_suffix = (" " + format_clusters(clusters)) if clusters else ""
        return (
            f"The system is cooling, but the board shows mixed behavior — price is moving ahead of "
            f"narrative in some names while others show early follow-through. "
            f"Narratives strengthening ({names}).{cluster_suffix}"
        )

    # Confirmation clause: distinguish clean from early — never say "no confirmation"
    if n_confirmed:
        conf_clause = f"{n_confirmed} confirmed"
    elif early_conf:
        conf_clause = f"early follow-through forming ({', '.join(early_conf)})"
    else:
        conf_clause = None

    counts = " · ".join(filter(None, [
        conf_clause,
        f"{n_price_led} price-led" if n_price_led else None,
        f"{n_diverging} diverging" if n_diverging else None,
    ]))

    cluster_suffix = (" " + format_clusters(clusters)) if clusters else ""

    return (
        f"The system is cooling, but the board shows mixed behavior — price is moving ahead of "
        f"narrative in some names while others show early follow-through. "
        + (f"{counts}. " if counts else "")
        + "Multiple behaviors coexisting; no single regime dominant."
        + cluster_suffix
    )


def record_history(rows: list, today: date):
    """Append today's narr/state/nds snapshot per ticker to narrative_history.jsonl."""
    today_str = today.isoformat()
    # Load existing to avoid duplicate entries for today
    existing_today = set()
    if HISTORY_FILE.exists():
        for line in HISTORY_FILE.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("date") == today_str:
                    existing_today.add(r["t"])

    with HISTORY_FILE.open("a") as f:
        for r in rows:
            if r["t"] not in existing_today:
                f.write(json.dumps({
                    "date": today_str,
                    "t": r["t"],
                    "narr": r["narr"],
                    "state": r["state"],
                    "nds": r["nds"],
                }) + "\n")


def load_signals_per_day() -> dict:
    """Return dict: ticker → {date_str → count} from events file."""
    result: dict = defaultdict(lambda: defaultdict(int))
    if not EVENTS_FILE.exists():
        return {}
    for line in EVENTS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        ts = r.get("timestamp", "")[:10]  # "YYYY-MM-DD"
        for actor in r.get("actors", []):
            result[actor][ts] += 1
    return {t: dict(dates) for t, dates in result.items()}


def load_narr_history() -> dict:
    """Return dict: ticker → sorted list of {date, narr, state}."""
    if not HISTORY_FILE.exists():
        return {}
    by_ticker = defaultdict(list)
    for line in HISTORY_FILE.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            by_ticker[r["t"]].append(r)
    for t in by_ticker:
        by_ticker[t].sort(key=lambda x: x["date"])
    return dict(by_ticker)


def compute_rolling_narr(dates: list, signals_by_date: dict, current_narr: int) -> list:
    """
    Approximate per-day narrative score using a rolling 7-day event window,
    anchored so the last value matches today's known narr score.

    Score formula mirrors compute_narr_score: floor 35, event activity drives
    up to ~60 points above the floor, capped at 95.
    """
    counts = [signals_by_date.get(d, 0) for d in dates]

    # Rolling 7-day event sum
    rolling = []
    for i in range(len(dates)):
        rolling.append(sum(counts[max(0, i - 6): i + 1]))

    peak = max(rolling) if any(r > 0 for r in rolling) else 1

    # Raw scores in [35, 95]
    raw = [35 + (r / peak) * 60 for r in rolling]

    # Anchor last value to current_narr by scaling the activity component
    last_raw = raw[-1]
    if last_raw != 35 and current_narr != 35:
        scale = (current_narr - 35) / (last_raw - 35)
        adjusted = [35 + (v - 35) * scale for v in raw]
    else:
        adjusted = raw

    return [int(min(95, max(35, round(v)))) for v in adjusted]


def compute_chart_data(ticker: str, today: date, narr_history: list, signals_by_date: dict | None = None) -> dict:
    """
    Build 30-day chart data: ticker price (min-max normalized 0-100) + narrative score series.
    Both series share the same 0-100 scale so they can be plotted together.
    NDS is computed per day from narr[d] - price_score[d].
    """
    price_path = PRICES_DIR / f"{ticker}.parquet"
    bench_path = PRICES_DIR / f"{BENCHMARK}.parquet"
    if not price_path.exists():
        return {}

    # Load extra history before the window to support 5-day return lookback
    LOOKBACK = CHART_DAYS + 7
    df = pd.read_parquet(price_path).sort_values("timestamp").reset_index(drop=True)
    df = df[["timestamp", "close"]].tail(LOOKBACK).reset_index(drop=True)

    if len(df) < 2:
        return {}

    # Keep only the window dates for the chart
    df_window = df.tail(CHART_DAYS).reset_index(drop=True)
    dates = df_window["timestamp"].astype(str).tolist()

    # Normalize price to 0-100 using min-max over the window
    px_min = float(df_window["close"].min())
    px_max = float(df_window["close"].max())
    if px_max > px_min:
        price_series = ((df_window["close"] - px_min) / (px_max - px_min) * 100).round(2).tolist()
    else:
        price_series = [50.0] * len(df_window)

    # Per-day 5-day relative return vs benchmark → price_score → feeds into NDS
    bench_df = None
    if bench_path.exists():
        bench_df = pd.read_parquet(bench_path).sort_values("timestamp").reset_index(drop=True)
        bench_df = bench_df[["timestamp", "close"]].tail(LOOKBACK).reset_index(drop=True)

    rel5d_by_date: dict[str, float] = {}
    if bench_df is not None:
        merged = pd.merge(
            df[["timestamp", "close"]].rename(columns={"close": "px"}),
            bench_df[["timestamp", "close"]].rename(columns={"close": "bx"}),
            on="timestamp", how="inner"
        ).reset_index(drop=True)
        for i, row in merged.iterrows():
            if i < 5:
                continue
            ticker_ret = row["px"] / merged.iloc[i - 5]["px"] - 1
            bench_ret  = row["bx"] / merged.iloc[i - 5]["bx"] - 1
            rel5d_by_date[str(row["timestamp"])] = (ticker_ret - bench_ret) * 100

    # Narrative score series (0-100) from history; bridge last trading day gap
    # Exact history entries keyed by date
    narr_map = {}
    for r in narr_history:
        narr_map[r["date"]] = (r["narr"], r.get("nds"))
    # Bridge pipeline run date vs last trading date (up to 3 days ahead)
    if narr_map and dates:
        last_chart = dates[-1]
        if last_chart not in narr_map:
            last_dt = date.fromisoformat(last_chart)
            for offset in range(1, 4):
                candidate = (last_dt + timedelta(days=offset)).isoformat()
                if candidate in narr_map:
                    narr_map[last_chart] = narr_map[candidate]
                    break

    sig_map = signals_by_date or {}

    # Current known narr score (most recent history entry)
    current_narr = narr_map[max(narr_map)][0] if narr_map else None
    current_nds  = narr_map[max(narr_map)][1] if narr_map else None

    if current_narr is not None:
        # Rolling event-based approximation, anchored to current known score
        narr_series = compute_rolling_narr(dates, sig_map, current_narr)
        # Overwrite exact history dates with real values
        for d, (narr_val, _) in narr_map.items():
            if d in dates:
                narr_series[dates.index(d)] = narr_val
        # Per-day NDS = narr[d] - price_score[d]
        nds_series = []
        for i, d in enumerate(dates):
            rel = rel5d_by_date.get(d)
            if rel is not None:
                price_score = max(0, min(100, 50 + rel * 5))
                nds_series.append(round(narr_series[i] - price_score, 1))
            else:
                nds_series.append(None)
    else:
        narr_series = [None] * len(dates)
        nds_series  = [None] * len(dates)

    signals_series = [sig_map.get(d) or None for d in dates]

    return {
        "dates": dates,
        "price": price_series,
        "narr": narr_series,
        "signals": signals_series,
        "nds": nds_series,
    }


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
                  f'<div class="date-tag">Last updated: {date_str}</div>', html)
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
    today = date.today()

    # Record today's narrative scores to history
    record_history(rows, today)
    narr_history = load_narr_history()

    actors_block = actors_js(rows)
    insight, takeaway = headline(rows, rel_returns)
    context = narrative_context(rows, buckets)
    title = page_title(rows, buckets)

    print(f"\nTop 5 by NDS:")
    for r in rows[:5]:
        print(f"  {r['t']:6s}  nds:{r['nds']:+.1f}  narr:{r['narr']:2d}  rel:{r['rel']:+.2f}%  state:{r['state']}")

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

        # Write actors.json for actor detail pages (includes chart data)
        actors_json_dest = SITE_DEST.parent / "actors.json"
        signals_per_day = load_signals_per_day()
        rows_with_chart = []
        for r in rows:
            chart = compute_chart_data(r["t"], today, narr_history.get(r["t"], []),
                                       signals_per_day.get(r["t"]))
            rows_with_chart.append({**r, "chart": chart if chart else None})
        actors_json_dest.write_text(json.dumps({
            "date": today.isoformat(),
            "meta": {
                "page_title": title,
                "subhead": context,
                "page_insight": insight,
                "narrative_context": context,
                "takeaway": takeaway,
                "date_display": format_date(today),
            },
            "actors": rows_with_chart,
        }, indent=2))
        print(f"Wrote {actors_json_dest}")
    else:
        print(f"Site dest not found, skipping copy: {SITE_DEST}")


if __name__ == "__main__":
    main()
