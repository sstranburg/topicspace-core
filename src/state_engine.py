"""
TopicSpace State Engine

Classifies each actor into a market state by combining:
  - narrative signals (from pipeline / signals JSON)
  - price behavior (relative performance vs benchmark)

States (mutually exclusive):
  CONFIRMED   strong narrative + price moving in same direction
  EARLY       narrative forming + little/no price response
  DIVERGENCE  strong narrative + price moving opposite direction
  DISAGREEMENT conflicting narrative signals + price underperformance
  REPRICING   narrative intact + price compressing (no structural break)
  MACRO       price correlated with benchmark, no actor-specific catalyst

Usage:
    from src.state_engine import classify_all, select_homepage_actors
    states = classify_all("2026-03-30")
    top = select_homepage_actors(states, n=5)
"""

from __future__ import annotations
import json
import pathlib
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from src.config import ACTOR_ALIASES
from src.price_analysis import load_prices, relative_return, detect_price_move

# ── Benchmark assignments ─────────────────────────────────────────────────────
# Small-cap / fintech → IWM; large-cap tech default → QQQ
BENCHMARKS: dict[str, str] = {
    "SOFI":  "IWM",
    "SMCI":  "IWM",
    "CRWV":  "IWM",
    "NBIS":  "IWM",
}
DEFAULT_BENCH = "QQQ"

# Private companies — no price data
NO_PRICE = {"OPENAI", "ANTHROPIC", "SKHX", "SAMSNG"}

# Manually-known opposing theses the pipeline cannot auto-detect.
# Format: ticker → (bull_label, bear_label)
# These override the `has_conflict` signal in classification.
KNOWN_CONFLICTS: dict[str, tuple[str, str]] = {
    "SOFI": ("CEO $1M open-market buy", "Muddy Waters short report"),
}

# ── Narrative input sources ───────────────────────────────────────────────────
SIGNALS_PATH  = pathlib.Path("../topicspace-site/public/signals/ai/latest.json")
EVENTS_PATH   = pathlib.Path("data/normalized/tech_ecosystem.jsonl")
LOOKBACK_DAYS = 7


@dataclass
class ActorState:
    actor:               str
    state:               str
    explanation:         str
    context:             str          # one-line homepage sentence
    relative_return_5d:  float
    benchmark:           str
    confidence:          str          # high / medium / low
    narrative_momentum:  str          # RISING / FLAT / FALLING
    signal_count:        int
    has_conflict:        bool
    narrative_weight:    float = 0.0  # 0–1, used for ranking


# ── Narrative extraction ──────────────────────────────────────────────────────

def _load_actor_signals(ticker: str) -> list[dict]:
    """Return signal records from ai/latest.json that mention this actor."""
    if not SIGNALS_PATH.exists():
        return []
    data = json.loads(SIGNALS_PATH.read_text())
    out = []
    for s in data.get("signals", []):
        entities = [e.upper() for e in s.get("affected_entities", [])]
        if ticker in entities:
            out.append(s)
    return out


def _count_recent_events(ticker: str, as_of: str) -> int:
    """Count events mentioning this actor in the last LOOKBACK_DAYS days."""
    if not EVENTS_PATH.exists():
        return 0
    aliases = [a.lower() for a in ACTOR_ALIASES.get(ticker, [])]
    if not aliases:
        return 0
    cutoff = pd.to_datetime(as_of) - pd.Timedelta(days=LOOKBACK_DAYS)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    count = 0
    with EVENTS_PATH.open() as f:
        for line in f:
            try:
                e = json.loads(line)
                if e.get("timestamp", "") < cutoff_str:
                    continue
                text = (e.get("title", "") + " " + e.get("text", "")).lower()
                if any(a in text for a in aliases):
                    count += 1
            except Exception:
                pass
    return count


def _has_conflicting_signals(actor_sigs: list[dict]) -> bool:
    """True if actor appears in both positive (LEAN_IN) and negative (BE_CAREFUL) buckets."""
    buckets = {s["bucket"] for s in actor_sigs}
    return "LEAN_IN" in buckets and "BE_CAREFUL" in buckets


def _dominant_momentum(actor_sigs: list[dict]) -> str:
    if not actor_sigs:
        return "FLAT"
    counts = {"RISING": 0, "FLAT": 0, "FALLING": 0}
    for s in actor_sigs:
        m = s.get("momentum", "FLAT")
        counts[m] = counts.get(m, 0) + 1
    return max(counts, key=counts.__getitem__)


def _narrative_weight(event_count: int, actor_sigs: list[dict]) -> float:
    """0–1 score combining event volume and signal presence."""
    event_score = min(event_count / 200, 1.0)           # saturates at 200 events
    signal_score = min(len(actor_sigs) / 3, 1.0)        # saturates at 3 signals
    return round(0.6 * event_score + 0.4 * signal_score, 3)


# ── Price extraction ──────────────────────────────────────────────────────────

def _benchmark_correlation(ticker: str, benchmark: str, as_of: str, window: int = 20) -> float:
    """Pearson correlation of 1D returns over the window. Returns -1 if insufficient data."""
    stock_df  = load_prices(ticker)
    bench_df  = load_prices(benchmark)
    if stock_df is None or bench_df is None:
        return -1.0
    cutoff = pd.to_datetime(as_of) - pd.Timedelta(days=window + 5)
    def trim(df):
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.date
        return df[df["timestamp"] >= cutoff.date()].copy()
    s = trim(stock_df).dropna(subset=["return_1d"])
    b = trim(bench_df).dropna(subset=["return_1d"])
    shared = set(s["timestamp"]).intersection(set(b["timestamp"]))
    s = s[s["timestamp"].isin(shared)].sort_values("timestamp")["return_1d"].values
    b = b[b["timestamp"].isin(shared)].sort_values("timestamp")["return_1d"].values
    if len(s) < 5:
        return -1.0
    return float(np.corrcoef(s, b)[0, 1])


# ── Classification ────────────────────────────────────────────────────────────

def _classify(
    ticker:       str,
    rel:          float,
    stock_ret:    float,
    bench_ret:    float,
    corr:         float,
    has_conflict: bool,
    momentum:     str,
    event_count:  int,
    actor_sigs:   list[dict],
) -> tuple[str, str, str]:
    """
    State = f(narrative_strength, price_relative_behavior).

    Priority: CONFIRMED > DISAGREEMENT > MACRO > DIVERGENCE > REPRICING > EARLY

    DISAGREEMENT requires a known opposing thesis (KNOWN_CONFLICTS) OR
    mixed buckets PLUS significant underperformance — not tags alone.
    """
    has_narrative    = event_count > 20 or len(actor_sigs) >= 1
    strong_narrative = event_count > 80 or len(actor_sigs) >= 2
    rel_abs          = abs(rel)
    known_conflict   = ticker in KNOWN_CONFLICTS

    # 1. CONFIRMED — narrative and price moving in the same direction
    if strong_narrative and rel > 0.015:
        conf = "high" if rel > 0.03 else "medium"
        return "CONFIRMED", "Narrative intact — price outperforming benchmark.", conf
    if strong_narrative and momentum == "FALLING" and rel < -0.025 and stock_ret < 0:
        conf = "high" if rel < -0.04 else "medium"
        return "CONFIRMED", "Negative narrative confirmed by price underperformance.", conf

    # 2. DISAGREEMENT — requires a known opposing thesis, not just mixed tags
    # known_conflict = explicit bull/bear collision (e.g. insider buy vs short)
    # fallback: mixed buckets + significant underperformance
    has_structural_conflict = known_conflict or (has_conflict and rel < -0.025)
    if has_structural_conflict and rel < -0.01:
        conf = "high" if known_conflict else "medium"
        return "DISAGREEMENT", "Competing narratives unresolved — price trending lower.", conf

    # 3. MACRO — price tracking benchmark tightly, no actor-specific story
    if corr > 0.85 and rel_abs < 0.02:
        conf = "high" if corr > 0.92 else "medium"
        return "MACRO", "Price moving tightly with benchmark — no actor-specific catalyst.", conf

    # 4. DIVERGENCE — strong narrative, price moving opposite direction
    if strong_narrative and momentum == "RISING" and rel < -0.03:
        conf = "high" if rel < -0.05 else "medium"
        return "DIVERGENCE", "Rising narrative — price diverging negatively.", conf
    if strong_narrative and momentum == "FALLING" and rel > 0.03:
        return "DIVERGENCE", "Negative narrative — price diverging positively.", "medium"

    # 5. REPRICING — narrative present, price compressing (underperforming or flat)
    if has_narrative and rel < 0.01 and rel > -0.07:
        conf = "high" if event_count > 100 else "medium"
        return "REPRICING", "Narrative intact — price compressing, repricing timing or terms.", conf

    # 6. EARLY — narrative forming, no price response yet
    if has_narrative and rel_abs < 0.025:
        conf = "medium" if event_count > 40 else "low"
        return "EARLY", "Narrative forming — price not yet responding.", conf

    # Fallback
    return "MACRO", "Insufficient signal to distinguish from macro pressure.", "low"


# ── Context sentences ─────────────────────────────────────────────────────────

def _make_context(ticker: str, state: str, rel: float, benchmark: str,
                  explanation: str) -> str:
    rel_str   = f"{rel:+.0%}".replace("-", "–")
    direction = "outperforming" if rel > 0 else "underperforming"

    templates = {
        "CONFIRMED":    f"Narrative and price aligned — {direction} {benchmark} ({rel_str}).",
        "EARLY":        f"Narrative forming — no price confirmation yet ({rel_str} vs {benchmark}).",
        "DIVERGENCE":   f"Narrative building — price {direction} {benchmark} ({rel_str}). Pre-inflection divergence.",
        "DISAGREEMENT": f"Active disagreement regime — price resolving {direction} {benchmark} ({rel_str}).",
        "REPRICING":    f"Narrative pressure active — price {direction} {benchmark} ({rel_str}). Repricing, not reversal.",
        "MACRO":        f"Moving with {benchmark} ({rel_str}) — macro overriding actor-specific signals.",
    }
    return templates.get(state, explanation)


# ── Public API ────────────────────────────────────────────────────────────────

def classify_actor(ticker: str, as_of: str) -> ActorState | None:
    """Classify a single actor. Returns None if no price data available."""
    if ticker in NO_PRICE:
        return None

    benchmark = BENCHMARKS.get(ticker, DEFAULT_BENCH)
    r = relative_return(ticker, as_of, window=5, benchmark=benchmark)
    if r is None:
        return None

    rel        = r["relative_return"]
    stock_ret  = r["stock_return"]
    bench_ret  = r["benchmark_return"]

    corr         = _benchmark_correlation(ticker, benchmark, as_of)
    actor_sigs   = _load_actor_signals(ticker)
    event_count  = _count_recent_events(ticker, as_of)
    # has_conflict = bucket-level signal conflict (LEAN_IN + BE_CAREFUL present)
    # KNOWN_CONFLICTS override is applied inside _classify for structural conflicts
    has_conflict = _has_conflicting_signals(actor_sigs)
    momentum     = _dominant_momentum(actor_sigs)
    weight       = _narrative_weight(event_count, actor_sigs)

    state, explanation, confidence = _classify(
        ticker, rel, stock_ret, bench_ret, corr,
        has_conflict, momentum, event_count, actor_sigs,
    )

    context = _make_context(ticker, state, rel, benchmark, explanation)

    return ActorState(
        actor              = ticker,
        state              = state,
        explanation        = explanation,
        context            = context,
        relative_return_5d = round(rel, 4),
        benchmark          = benchmark,
        confidence         = confidence,
        narrative_momentum = momentum,
        signal_count       = event_count,
        has_conflict       = has_conflict,
        narrative_weight   = weight,
    )


def classify_all(as_of: str, tickers: list[str] | None = None) -> list[ActorState]:
    """Classify all trackable actors (or a supplied list)."""
    if tickers is None:
        tickers = [t for t in ACTOR_ALIASES if t not in NO_PRICE]

    results = []
    for ticker in tickers:
        state = classify_actor(ticker, as_of)
        if state is not None:
            results.append(state)
    return results


def select_homepage_actors(states: list[ActorState], n: int = 5) -> list[ActorState]:
    """
    Pick top n actors ensuring state diversity:
    - At least one CONFIRMED (if available)
    - At least one REPRICING (if available)
    - At least one DIVERGENCE (if available)
    - One DISAGREEMENT if present
    - One MACRO if present and high confidence

    Within each state, pick by narrative_weight descending.
    Exclude low-confidence actors unless no higher-confidence option exists.
    """
    CONF_RANK = {"high": 0, "medium": 1, "low": 2}
    DESIRED_STATES = ["CONFIRMED", "DISAGREEMENT", "DIVERGENCE", "REPRICING", "MACRO", "EARLY"]

    eligible = [s for s in states if s.confidence in ("high", "medium")]
    if not eligible:
        eligible = states  # fallback

    # Best actor per state (highest narrative_weight)
    best_by_state: dict[str, ActorState] = {}
    for state in DESIRED_STATES:
        candidates = sorted(
            [s for s in eligible if s.state == state],
            key=lambda x: (-{"high": 2, "medium": 1, "low": 0}[x.confidence],
                           -x.narrative_weight),
        )
        if candidates:
            best_by_state[state] = candidates[0]

    # Build selection: one per state in priority order until n filled
    selection: list[ActorState] = []
    seen_tickers: set[str] = set()
    for state in DESIRED_STATES:
        if len(selection) >= n:
            break
        if state in best_by_state:
            actor = best_by_state[state]
            if actor.actor not in seen_tickers:
                selection.append(actor)
                seen_tickers.add(actor.actor)

    # Fill remaining slots with next-best by weight
    if len(selection) < n:
        remaining = sorted(
            [s for s in eligible if s.actor not in seen_tickers],
            key=lambda x: (-{"high": 2, "medium": 1, "low": 0}[x.confidence],
                           -x.narrative_weight),
        )
        for s in remaining:
            if len(selection) >= n:
                break
            selection.append(s)

    return selection


def system_snapshot(states: list[ActorState]) -> dict[str, str]:
    """
    Generate a system-level interpretation from state distribution.

    Returns {"summary": "...", "interpretation": "..."}
    """
    from collections import Counter
    counts = Counter(s.state for s in states if s.confidence in ("high", "medium"))
    total  = sum(counts.values()) or 1

    dominant = counts.most_common(1)[0][0] if counts else "MACRO"
    top_two  = [s for s, _ in counts.most_common(2)]

    confirmed_actors   = [s.actor for s in states if s.state == "CONFIRMED"   and s.confidence in ("high","medium")]
    divergence_actors  = [s.actor for s in states if s.state == "DIVERGENCE"  and s.confidence in ("high","medium")]
    repricing_actors   = [s.actor for s in states if s.state == "REPRICING"   and s.confidence in ("high","medium")]
    disagreement_actors= [s.actor for s in states if s.state == "DISAGREEMENT"and s.confidence in ("high","medium")]
    macro_pct          = counts.get("MACRO", 0) / total

    # ── Distribution sentence ─────────────────────────────────────────────────
    if macro_pct > 0.5:
        summary = (
            "Macro pressure dominating — actor-specific signals suppressed across most names."
        )
    elif "DIVERGENCE" in top_two and "REPRICING" in top_two:
        summary = (
            "Market skewed toward divergence and repricing — "
            "narrative strength not translating cleanly into price."
        )
    elif dominant == "DIVERGENCE":
        summary = (
            f"Divergence regime — {len(divergence_actors)} actors showing narrative-price misalignment."
        )
    elif dominant == "REPRICING":
        summary = (
            "Broad repricing underway — narratives intact but price compressing across the board."
        )
    elif dominant == "CONFIRMED" and len(confirmed_actors) >= 2:
        summary = (
            "System in confirmation mode — narratives and price broadly aligned."
        )
    elif "DISAGREEMENT" in counts:
        summary = (
            "Mixed system with active disagreement signals — competing theses unresolved."
        )
    else:
        summary = (
            "Early-stage regime — narratives forming faster than price is reacting."
        )

    # ── Interpretive line ─────────────────────────────────────────────────────
    if confirmed_actors and (divergence_actors or repricing_actors):
        others = divergence_actors + repricing_actors
        interpretation = (
            f"Market is selective — {', '.join(confirmed_actors[:2])} confirming "
            f"while {', '.join(others[:3])} lag."
        )
    elif divergence_actors and macro_pct < 0.4:
        interpretation = (
            f"Price lagging narrative across {', '.join(divergence_actors[:3])} — "
            "timing gap still unresolved."
        )
    elif macro_pct > 0.5:
        interpretation = (
            "Macro pressure suppressing actor-specific signals — wait for divergence to re-emerge."
        )
    elif disagreement_actors:
        interpretation = (
            f"Active disagreement in {', '.join(disagreement_actors)} — "
            "resolution will be a directional signal."
        )
    elif repricing_actors:
        interpretation = (
            f"Repricing concentrated in {', '.join(repricing_actors[:3])} — "
            "thesis intact but timeline compressing."
        )
    else:
        interpretation = "System state unclear — monitor for narrative momentum to confirm direction."

    return {"summary": summary, "interpretation": interpretation}
