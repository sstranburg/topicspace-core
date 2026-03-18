"""
Narrative momentum scoring.

Computes a 0–100 score from 5 components:
  0.30  pressure_level      — current signal strength
  0.30  pressure_trend      — direction of signal (most important)
  0.20  event_acceleration  — coverage ramping?
  0.10  spread_trend        — actor spread expanding?
  0.10  coherence_trend     — getting clearer, not just louder?

Minus a noise penalty (0–20) for low-coherence/market-noise storms.

Each component is normalized to 0–100 before weighting so the final
score is also 0–100.
"""

from __future__ import annotations
from typing import Optional

__all__ = [
    "compute_narrative_momentum",
    "compute_narrative_momentum_full",
    "classify_momentum",
    "classify_narrative_state",
    "compute_lead_score",
    "classify_lead",
    "momentum_explanation",
    "momentum_debug_row",
]


# ── Math helpers ───────────────────────────────────────────────────────────────

def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _slope(values: list[float]) -> float:
    """Ordinary-least-squares slope over evenly-spaced observations."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    den = sum((i - mean_x) ** 2 for i in range(n))
    return num / den if den else 0.0


def _pick_signal(history: list[dict]) -> tuple[list[float], str]:
    """
    Return (signal_values, label) from history.
    Prefers gravity (per-window) → pressure → event_count.
    """
    has_g = sum(1 for h in history if h.get("gravity")  is not None)
    has_p = sum(1 for h in history if h.get("pressure") is not None)
    n = len(history)
    if has_g >= n / 2:
        return ([h["gravity"]  for h in history if h.get("gravity")  is not None], "gravity")
    if has_p >= n / 2:
        return ([h["pressure"] for h in history if h.get("pressure") is not None], "pressure")
    return ([h.get("event_count", 0) for h in history], "events")


# ── Component scorers ──────────────────────────────────────────────────────────

def score_pressure_level(history: list[dict]) -> float:
    """Latest 1–2 windows' signal, normalized to 0–100."""
    ordered = sorted(history, key=lambda h: h.get("date", ""))
    recent  = ordered[-2:]
    sig, _  = _pick_signal(recent)
    if not sig:
        return 0.0
    latest = sig[-1]
    # gravity/pressure in 0–1; events need normalising differently
    if latest <= 1.0:
        return _clamp(latest * 100)
    # event_count fallback: cap at 200 events → 100 pts
    return _clamp(latest / 2.0)


def score_pressure_trend(history: list[dict]) -> float:
    """
    Slope of signal over all windows, centered at 50.
    Sharply rising → 90–100, flat → ~50, falling → 0–30.
    """
    ordered = sorted(history, key=lambda h: h.get("date", ""))
    sig, _  = _pick_signal(ordered)
    if len(sig) < 2:
        return 50.0
    s = _slope(sig)
    # For gravity/pressure (0–1 scale): slope of +0.02/window → +10 pts
    # For events (0–200 scale): scale down first
    if max(sig, default=0) > 1:
        s = s / 100.0
    return _clamp(50.0 + s * 500.0)


def score_spread_trend(history: list[dict]) -> float:
    """
    Change in actor_count across windows, centered at 50.
    +4 actors → ~100, no change → 50, shrinking → <50.
    """
    ordered = sorted(history, key=lambda h: h.get("date", ""))
    counts  = [h.get("actor_count", 1) for h in ordered]
    if len(counts) < 2:
        return 50.0
    delta = counts[-1] - counts[0]
    return _clamp(50.0 + delta * 12.5)


def score_event_acceleration(history: list[dict]) -> float:
    """
    Latest event count vs mean of prior windows.
    ratio 2.0 → 100, ratio 1.0 → 50, ratio 0.5 → 25.
    """
    ordered = sorted(history, key=lambda h: h.get("date", ""))
    events  = [h.get("event_count", 0) for h in ordered]
    if len(events) < 2:
        return 50.0
    latest    = events[-1]
    prev_mean = sum(events[:-1]) / len(events[:-1])
    if prev_mean == 0:
        return 50.0 if latest == 0 else 75.0
    return _clamp((latest / prev_mean) * 50.0)


def score_coherence_trend(history: list[dict]) -> float:
    """
    Slope of coherence over windows, centered at 50.
    Improving → >50, degrading → <50.
    """
    ordered = sorted(history, key=lambda h: h.get("date", ""))
    vals    = [h["coherence"] for h in ordered if h.get("coherence") is not None]
    if len(vals) < 2:
        return 50.0
    s = _slope(vals)
    return _clamp(50.0 + s * 500.0)


def score_noise_penalty(storm: dict) -> float:
    """
    0–20 penalty for low-coherence / churn / market-noise storms.
    Applied as a subtraction from the final score.
    """
    penalty    = 0.0
    coherence  = storm.get("coherence") or 0.0
    drift      = storm.get("drift",     0.0) or 0.0
    shift_type = storm.get("shift_type", "")
    if coherence < 0.35 and drift > 0.20:
        penalty += 10.0
    if "market_noise" in str(shift_type):
        penalty += 10.0
    return penalty


# ── Lead indicator ─────────────────────────────────────────────────────────────

def compute_lead_score(storm: dict, history: list[dict]) -> float:
    """
    Leading indicator: identifies narratives that are early but about to explode.
    Weights direction and acceleration over current level.

    lead_score = 0.4 * pressure_trend + 0.3 * event_acceleration
               + 0.2 * spread_trend   - 0.1 * noise_penalty
    """
    if not history:
        return 0.0
    pt  = score_pressure_trend(history)
    ea  = score_event_acceleration(history)
    st  = score_spread_trend(history)
    np_ = score_noise_penalty(storm)
    return round(_clamp(0.4 * pt + 0.3 * ea + 0.2 * st - 0.1 * np_), 1)


def classify_lead(score: float) -> str:
    """Interpret lead score as a watch-level."""
    if score >= 75:
        return "Imminent"
    if score >= 60:
        return "Watch"
    if score >= 45:
        return "Early"
    return "Quiet"


# ── Main scorer ────────────────────────────────────────────────────────────────

def compute_narrative_momentum_full(storm: dict, history: list[dict]) -> dict:
    """
    Compute momentum score, components, and delta.
    Returns a dict with keys:
      score, components, delta, momentum_class
    """
    if not history:
        components = {
            "pressure_level": 0.0, "pressure_trend": 50.0,
            "spread_trend": 50.0, "event_acceleration": 50.0,
            "coherence_trend": 50.0, "noise_penalty": 0.0,
        }
        return {"score": 0.0, "components": components, "delta": 0.0,
                "momentum_class": "Cooling"}

    pl  = score_pressure_level(history)
    pt  = score_pressure_trend(history)
    st  = score_spread_trend(history)
    ea  = score_event_acceleration(history)
    ct  = score_coherence_trend(history)
    np_ = score_noise_penalty(storm)

    raw = 0.30 * pl + 0.30 * pt + 0.10 * st + 0.20 * ea + 0.10 * ct
    score = round(_clamp(raw - np_), 1)

    # Delta: score with all history vs score with history[:-1]
    if len(history) >= 2:
        prev_history = history[:-1]
        pl2 = score_pressure_level(prev_history)
        pt2 = score_pressure_trend(prev_history)
        st2 = score_spread_trend(prev_history)
        ea2 = score_event_acceleration(prev_history)
        ct2 = score_coherence_trend(prev_history)
        raw2 = 0.30 * pl2 + 0.30 * pt2 + 0.10 * st2 + 0.20 * ea2 + 0.10 * ct2
        prev_score = round(_clamp(raw2 - np_), 1)
        delta = round(score - prev_score, 1)
    else:
        delta = 0.0

    components = {
        "pressure_level":     round(pl,  1),
        "pressure_trend":     round(pt,  1),
        "spread_trend":       round(st,  1),
        "event_acceleration": round(ea,  1),
        "coherence_trend":    round(ct,  1),
        "noise_penalty":      round(np_, 1),
    }

    lead = compute_lead_score(storm, history)
    drift = storm.get("drift", 0.0) or 0.0
    ns_label, ns_interp = classify_narrative_state(drift, delta)

    return {
        "score":                score,
        "components":           components,
        "delta":                delta,
        "momentum_class":       classify_momentum(score, delta),
        "lead_score":           lead,
        "lead_class":           classify_lead(lead),
        "narrative_state":      ns_label,
        "narrative_state_interp": ns_interp,
    }


def compute_narrative_momentum(storm: dict, history: list[dict]) -> float:
    """Convenience wrapper — returns score only."""
    return compute_narrative_momentum_full(storm, history)["score"]


def classify_narrative_state(drift: float, momentum_delta: float) -> tuple[str, str]:
    """
    Composite signal: drift level × momentum direction.

    Returns (label, interpretation) using a 3×3 matrix:

      drift_high (>0.20) × momentum rising  → "Emerging shift"
      drift_high          × momentum falling → "Narrative breakdown"
      drift_high          × momentum flat    → "Turbulent"
      drift_mid (0.08–0.20) × rising         → "Evolving"
      drift_mid             × falling        → "Fading"
      drift_mid             × flat           → "Drifting"
      drift_low (<0.08)   × rising           → "Strengthening"
      drift_low           × falling          → "Cooling"
      drift_low           × flat             → "Stable"
    """
    drift_high = drift > 0.20
    drift_mid  = 0.08 <= drift <= 0.20
    # flat = within ±5 pts
    rising  = momentum_delta > 5
    falling = momentum_delta < -5

    if drift_high:
        if rising:
            return ("Emerging shift",     "High drift + rising momentum: narrative is pivoting and accelerating")
        if falling:
            return ("Narrative breakdown","High drift + falling momentum: narrative losing coherence and traction")
        return     ("Turbulent",          "High drift, momentum flat: narrative in flux, direction unclear")
    if drift_mid:
        if rising:
            return ("Evolving",           "Moderate drift + rising momentum: gradual thematic shift building")
        if falling:
            return ("Fading",             "Moderate drift + falling momentum: narrative evolving away from peak")
        return     ("Drifting",           "Moderate drift, momentum stable: slow background shift")
    # drift_low
    if rising:
        return     ("Strengthening",      "Low drift + rising momentum: coherent narrative gaining traction")
    if falling:
        return     ("Cooling",            "Low drift + falling momentum: stable narrative losing steam")
    return         ("Stable",            "Low drift, momentum flat: narrative holding steady")


def classify_momentum(score: float, delta: float = 0.0) -> str:
    if delta <= -10:
        return "Cooling"
    if score >= 80:
        return "Surging"
    if score >= 65:
        return "Expanding"
    if score >= 50:
        return "Building"
    if score >= 35:
        return "Stable"
    return "Cooling"


def momentum_explanation(storm: dict, history: list[dict]) -> str:
    """
    One-line human-readable summary of what is driving the momentum score.
    """
    if not history:
        return "no history"

    ordered   = sorted(history, key=lambda h: h.get("date", ""))
    sig, sig_label = _pick_signal(ordered)
    parts: list[str] = []

    # Current signal level
    if sig:
        latest = sig[-1]
        level  = latest if latest <= 1.0 else latest / 200.0
        if level >= 0.65:
            parts.append(f"{sig_label} high")
        elif level >= 0.40:
            parts.append(f"{sig_label} moderate")
        else:
            parts.append(f"{sig_label} low")
        # Trend direction
        if len(sig) >= 2:
            s = _slope(sig)
            threshold = 0.005 if max(sig) <= 1.0 else 0.5
            if s > threshold:
                parts.append(f"{sig_label} rising")
            elif s < -threshold:
                parts.append(f"{sig_label} falling")

    # Actor spread
    counts = [h.get("actor_count", 1) for h in ordered]
    if len(counts) >= 2:
        delta = counts[-1] - counts[0]
        if delta >= 2:
            parts.append(f"actor spread +{delta}")
        elif delta <= -2:
            parts.append(f"actor spread shrinking")

    # Coherence
    coh = [h["coherence"] for h in ordered if h.get("coherence") is not None]
    if coh:
        c = coh[-1]
        if c >= 0.60:
            parts.append("coherence stable")
        elif c < 0.35:
            parts.append("coherence mixed")

    # Noise flags
    if "market_noise" in str(storm.get("shift_type", "")):
        parts.append("market noise detected")

    return ", ".join(parts) if parts else "stable"


def momentum_debug_row(storm: dict, history: list[dict]) -> dict:
    """Return a flat dict of all component scores for debug printing."""
    full = compute_narrative_momentum_full(storm, history)
    c = full["components"]
    return {
        "label":              storm.get("display_headline", storm.get("storm_id", "?"))[:55],
        "pressure_level":     c["pressure_level"],
        "pressure_trend":     c["pressure_trend"],
        "spread_trend":       c["spread_trend"],
        "event_acceleration": c["event_acceleration"],
        "coherence_trend":    c["coherence_trend"],
        "noise_penalty":      c["noise_penalty"],
        "momentum_score":     full["score"],
        "momentum_class":     full["momentum_class"],
        "momentum_delta":     full["delta"],
        "lead_score":         full["lead_score"],
        "lead_class":         full["lead_class"],
    }
