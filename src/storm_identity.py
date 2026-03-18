"""
Storm identity model.

Core abstractions:
  StormWindow   — a single detected cluster (one time slice from the pipeline)
  Storm         — a persistent narrative entity, formed by merging windows

Identity key: (lineage_id, actor, phase_key)
  Stable across runs. Two windows belong to the same Storm iff they share a
  candidate key AND pass the merge rule (time proximity + semantic similarity).

Usage:
  windows = [StormWindow(...) for raw in pipeline_output]
  storms  = build_storms_from_windows(windows)
  for s in storms:
      s.display_headline = make_storm_display_name(s)
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Optional


# ── Phase ontology ─────────────────────────────────────────────────────────────
# Keys are machine-stable identifiers. Display labels are human-readable.
# Aliases are matched case-insensitively (exact, then substring).

PHASE_ONTOLOGY: dict[str, dict] = {
    "capacity_constraints": {
        "display": "Capacity Constraints",
        "aliases": [
            "Emerging Capacity Constraints",
            "Supply Constraints",
            "Capacity Constraint",
            "Supply Constraint",
            "Demand Pressure",
        ],
    },
    "partnership_expansion": {
        "display": "Partnership Expansion",
        "aliases": [
            "Partnership Formation",
            "Strategic Partnerships",
            "Strategic Partnership",
            "Collaborative Framework",
            "Strategic Alliance",
            "Strategic Alliances",
            "Collaborative Expansion",
            "Partnership Expansion",
        ],
    },
    "market_volatility": {
        "display": "Market Volatility",
        "aliases": [
            "Market Volatility and Competition",
            "Volatility Recognition",
            "Competitive Pressure",
            "Competitive Landscape",
            "Competitive Landscape Challenges",
            "Market Reassessment",
            "Volatile Market Reactions",
            "Market Volatility",
        ],
    },
    "capital_deployment": {
        "display": "Capital Deployment",
        "aliases": [
            "Strategic Infrastructure Investments",
            "Investment Acceleration",
            "Investment Sentiment Shift",
            "Strategic Investment Focus",
            "Investment Focus in Taiwan",
            "Infrastructure Expansion Initiatives",
            "Capital Deployment",
            "Investment Acceleration",
        ],
    },
    "infrastructure_expansion": {
        "display": "Infrastructure Expansion",
        "aliases": [
            "Infrastructure Expansion",
            "Infrastructure Investments",
            "Infrastructure Buildout",
            "Infrastructure Build",
            "Revenue Growth Anticipation",
        ],
    },
    "leadership_transition": {
        "display": "Leadership Transition",
        "aliases": [
            "Leadership Emergence",
            "Strategic Transition Focus",
            "Leadership Transition Dynamics",
            "Leadership Transition",
        ],
    },
    "recovery_momentum": {
        "display": "Recovery Momentum",
        "aliases": [
            "Initial Rebound Sentiment",
            "Growing Recovery Optimism",
            "Consolidated Rebound Outlook",
            "Rebound Potential",
            "Rebound Outlook",
            "Rebound Sentiment",
            "Growth Optimism",
            "Recovery Optimism",
            "Recovery Momentum",
        ],
    },
    "demand_surge": {
        "display": "Demand Surge",
        "aliases": [
            "Emerging Demand",
            "Demand Surge",
            "Demand Acceleration",
            "Demand",
        ],
    },
    "market_positioning": {
        "display": "Market Positioning",
        "aliases": [
            "Strategic Positioning",
            "Market Positioning",
            "Technological Commitment",
            "Operational Integration",
        ],
    },
    "financial_performance": {
        "display": "Financial Performance",
        "aliases": [
            "Earnings Growth",
            "Revenue Surge",
            "Comparative Performance Insights",
            "Oracle Revenue Surge",
            "Micron Stability Surge",
        ],
    },
    "narrative_contraction": {
        "display": "Narrative Contraction",
        "aliases": [
            "Sales Forecast Reassessment",
            "Infrastructure Viability Doubts",
            "Super Micro",
        ],
    },
}

# Build lookup tables once at import time
_ALIAS_TO_KEY: dict[str, str] = {}
for _key, _meta in PHASE_ONTOLOGY.items():
    _ALIAS_TO_KEY[_meta["display"].lower()] = _key
    for _alias in _meta["aliases"]:
        _ALIAS_TO_KEY[_alias.lower()] = _key


def canonicalize_phase_key(label: str) -> str:
    """
    Map a raw or normalized phase label to a stable phase key.
    Order: exact match → substring match → slugify fallback.
    """
    norm = label.strip().lower()
    if norm in _ALIAS_TO_KEY:
        return _ALIAS_TO_KEY[norm]
    # Substring: label contains alias or alias contains label
    for alias, key in _ALIAS_TO_KEY.items():
        if alias in norm or norm in alias:
            return key
    return re.sub(r'[^a-z0-9]+', '_', norm).strip('_') or 'unknown'


def phase_display(phase_key: str) -> str:
    return PHASE_ONTOLOGY.get(phase_key, {}).get(
        "display", phase_key.replace("_", " ").title()
    )


# ── Actor display names ─────────────────────────────────────────────────────────

ACTOR_DISPLAY: dict[str, str] = {
    "NVDA": "NVIDIA", "GOOGL": "Google", "META": "Meta",
    "MSFT": "Microsoft", "AMZN": "Amazon", "ADBE": "Adobe",
    "INTC": "Intel", "AMD": "AMD", "TSM": "TSMC",
    "ARM": "Arm", "AVGO": "Broadcom", "TSLA": "Tesla",
    "ORCL": "Oracle", "DELL": "Dell", "CRM": "Salesforce",
    "MU": "Micron", "SMCI": "Super Micro", "NBIS": "Nebius",
    "CRWV": "CoreWeave",
}


def actor_display(actor_id: str) -> str:
    return ACTOR_DISPLAY.get(actor_id, actor_id)


# ── Data models ─────────────────────────────────────────────────────────────────

@dataclass
class StormWindow:
    window_id:  str
    lineage_id: str
    phase_key:  str
    actor:      str
    actor_ids:  list
    start_date: str
    end_date:   str
    centroid:   Optional[list]  = None
    top_terms:  list            = field(default_factory=list)
    event_count: int            = 0
    coherence:  Optional[float] = None
    gravity:    Optional[float] = None


@dataclass
class Storm:
    storm_id:    str
    lineage_id:  str
    phase_key:   str
    actor:       str
    actor_ids:   set
    start_date:  str
    end_date:    str
    window_ids:          list           = field(default_factory=list)
    event_count:         int            = 0
    max_gravity:         Optional[float] = None
    mean_coherence:      Optional[float] = None
    display_headline:    Optional[str]  = None
    representative_id:   Optional[str]  = None
    merge_confidences:   list           = field(default_factory=list)
    history:             list           = field(default_factory=list)
    # internal centroid accumulator — not serialised directly
    _centroid_sum:   Optional[list] = field(default=None, compare=False, repr=False)
    _centroid_n:     int            = field(default=0,    compare=False, repr=False)
    _max_ev_window:  int            = field(default=0,    compare=False, repr=False)

    @property
    def centroid(self) -> Optional[list]:
        if not self._centroid_sum or self._centroid_n == 0:
            return None
        return [v / self._centroid_n for v in self._centroid_sum]

    def absorb(self, w: StormWindow, confidence: float = 1.0) -> None:
        self.actor_ids = self.actor_ids | set(w.actor_ids)
        self.start_date = min(self.start_date, w.start_date)
        self.end_date   = max(self.end_date,   w.end_date)
        self.window_ids.append(w.window_id)
        self.event_count += w.event_count
        if w.gravity is not None:
            self.max_gravity = max(self.max_gravity or 0.0, w.gravity)
        if w.coherence is not None:
            n = len(self.window_ids)
            self.mean_coherence = (((self.mean_coherence or 0.0) * (n - 1)) + w.coherence) / n
        if w.centroid is not None:
            if self._centroid_sum is None:
                self._centroid_sum = list(w.centroid)
            else:
                self._centroid_sum = [a + b for a, b in zip(self._centroid_sum, w.centroid)]
            self._centroid_n += 1
        if w.event_count >= self._max_ev_window:
            self._max_ev_window = w.event_count
            self.representative_id = w.window_id
        self.merge_confidences.append(round(confidence, 3))
        self.history.append({
            "date":        w.start_date,
            "event_count": w.event_count,
            "coherence":   w.coherence,
            "gravity":     w.gravity,
        })


# ── Trend classification ───────────────────────────────────────────────────────

def classify_trend(history: list) -> tuple[str, str]:
    """
    Classify a storm's trajectory from its ordered per-window history.

    Each entry: {date, event_count, coherence?, gravity?, pressure?}
    Uses pressure when available on ≥ half the entries, else gravity.

    Returns (label, explanation) where label ∈
      'expanding' | 'building' | 'cooling' | 'unstable' | 'stable'
    """
    if not history or len(history) < 2:
        return ("stable", "Insufficient history.")

    ordered = sorted(history, key=lambda h: h.get("date", ""))
    n = len(ordered)

    # Prefer gravity (per-window) → pressure → event_count as fallback
    # Pressure is often actor-level (flat across windows) so gravity is more informative.
    has_gravity  = sum(1 for h in ordered if h.get("gravity")  is not None)
    has_pressure = sum(1 for h in ordered if h.get("pressure") is not None)
    if has_gravity >= n / 2:
        sig_key, signals = "gravity",  [h["gravity"]  for h in ordered if h.get("gravity")  is not None]
    elif has_pressure >= n / 2:
        sig_key, signals = "pressure", [h["pressure"] for h in ordered if h.get("pressure") is not None]
    else:
        sig_key, signals = "events",   [h["event_count"] for h in ordered]
    sig_label = sig_key

    if len(signals) < 2:
        return ("stable", "Insufficient signal data.")

    mid = max(1, len(signals) // 2)
    early_mean = sum(signals[:mid]) / mid
    late_mean  = sum(signals[mid:]) / max(len(signals) - mid, 1)

    events  = [h["event_count"] for h in ordered]
    mid_ev  = max(1, len(events) // 2)
    early_ev = sum(events[:mid_ev]) / mid_ev
    late_ev  = sum(events[mid_ev:]) / max(len(events) - mid_ev, 1)

    mean_s = sum(signals) / len(signals)
    if mean_s > 0 and len(signals) >= 3:
        variance = sum((x - mean_s) ** 2 for x in signals) / len(signals)
        cv = variance ** 0.5 / mean_s
    else:
        cv = 0.0

    rising_sig    = late_mean > early_mean * 1.10
    falling_sig   = late_mean < early_mean * 0.90
    rising_events = late_ev   > early_ev   * 1.10

    if rising_sig and rising_events:
        return ("expanding",
                f"{sig_label} rising, actor spread increasing "
                f"({early_mean:.2f} → {late_mean:.2f})")
    if rising_sig:
        return ("building",
                f"{sig_label} rising ({early_mean:.2f} → {late_mean:.2f})")
    if falling_sig:
        return ("cooling",
                f"{sig_label} falling ({early_mean:.2f} → {late_mean:.2f})")
    if cv >= 0.40 and len(signals) >= 3:
        return ("unstable",
                f"high {sig_label} volatility (CV={cv:.2f})")
    return ("stable",
            f"{sig_label} flat ({early_mean:.2f} → {late_mean:.2f})")


# ── Similarity helpers ─────────────────────────────────────────────────────────

def _cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _days_gap(end: str, start: str) -> int:
    try:
        return max(0, (_date.fromisoformat(start) - _date.fromisoformat(end)).days)
    except Exception:
        return 0


def _semantic_similarity(window: StormWindow, storm: Storm) -> float:
    c_storm = storm.centroid
    if window.centroid and c_storm:
        return _cosine(window.centroid, c_storm)
    # Fallback: term Jaccard (no penalisation — just no boost)
    return _jaccard(set(window.top_terms), set(window.top_terms[:0]))  # 0.0 → skip threshold


# ── Merge rule ─────────────────────────────────────────────────────────────────

def merge_confidence_score(
    window: StormWindow,
    storm:  Storm,
    max_gap_days: int = 7,
) -> float:
    gap          = _days_gap(storm.end_date, window.start_date)
    time_score   = max(0.0, 1.0 - gap / max(max_gap_days, 1))
    actor_score  = _jaccard(set(window.actor_ids), storm.actor_ids)
    c_storm = storm.centroid
    sem_score = _cosine(window.centroid, c_storm) if (window.centroid and c_storm) else 0.5
    return round(0.25 * time_score + 0.25 * actor_score + 0.50 * sem_score, 3)


def should_merge(
    window: StormWindow,
    storm:  Storm,
    max_gap_days:            int   = 7,
    min_actor_overlap:       float = 0.2,
    min_semantic_similarity: float = 0.78,
) -> bool:
    # Candidate key — caller already filters by these, but be explicit
    if window.lineage_id != storm.lineage_id: return False
    if window.actor       != storm.actor:      return False
    if window.phase_key   != storm.phase_key:  return False

    if _days_gap(storm.end_date, window.start_date) > max_gap_days:
        return False

    if _jaccard(set(window.actor_ids), storm.actor_ids) < min_actor_overlap:
        return False

    c_storm = storm.centroid
    if window.centroid and c_storm:
        if _cosine(window.centroid, c_storm) < min_semantic_similarity:
            return False

    return True


# ── Storm builder ──────────────────────────────────────────────────────────────

def make_storm_id(lineage_id: str, actor: str, phase_key: str,
                  start_date: str, end_date: str) -> str:
    """Deterministic, human-readable storm ID. Stable once dates are final."""
    raw = f"{lineage_id}|{actor}|{phase_key}|{start_date}|{end_date}"
    return "s_" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def build_storms_from_windows(
    windows: list[StormWindow],
    max_gap_days:            int   = 7,
    min_actor_overlap:       float = 0.2,
    min_semantic_similarity: float = 0.78,
) -> list[Storm]:
    """
    Merge windows into Storm entities using a greedy chronological scan.

    For each window (sorted by lineage, actor, phase, date):
      - Try to extend the most recent open Storm with the same candidate key
      - If should_merge passes → absorb; otherwise open a new Storm
    """
    sorted_windows = sorted(
        windows,
        key=lambda w: (w.lineage_id, w.actor, w.phase_key, w.start_date, w.window_id),
    )

    # open_storms: candidate_key → most recently updated Storm
    open_storms: dict[tuple, Storm] = {}
    all_storms:  list[Storm]        = []

    for w in sorted_windows:
        key = (w.lineage_id, w.actor, w.phase_key)
        existing = open_storms.get(key)

        if existing is not None and should_merge(
            w, existing, max_gap_days, min_actor_overlap, min_semantic_similarity
        ):
            conf = merge_confidence_score(w, existing, max_gap_days)
            existing.absorb(w, conf)
        else:
            # Open a new Storm (provisional ID — finalised after all windows merged)
            new_storm = Storm(
                storm_id    = "",           # filled below
                lineage_id  = w.lineage_id,
                phase_key   = w.phase_key,
                actor       = w.actor,
                actor_ids   = set(w.actor_ids),
                start_date  = w.start_date,
                end_date    = w.end_date,
            )
            new_storm.absorb(w, confidence=1.0)
            open_storms[key] = new_storm
            all_storms.append(new_storm)

    # Assign deterministic IDs now that dates are final
    for s in all_storms:
        s.storm_id = make_storm_id(s.lineage_id, s.actor, s.phase_key,
                                   s.start_date, s.end_date)

    return all_storms


# ── Display naming ─────────────────────────────────────────────────────────────

def make_storm_display_name(storm: Storm) -> str:
    """ACTOR — Phase  (no date — unique within lineage by construction)."""
    return f"{actor_display(storm.actor)} — {phase_display(storm.phase_key)}"


# ── Debug helper ───────────────────────────────────────────────────────────────

def debug_storm_identity(storms: list[Storm],
                         windows_by_id: dict[str, StormWindow]) -> None:
    for s in storms:
        print("=" * 72)
        print(f"{s.storm_id}  {s.display_headline or make_storm_display_name(s)}")
        print(f"  phase: {s.phase_key}  actor: {s.actor}")
        print(f"  date:  {s.start_date} → {s.end_date}")
        print(f"  events:{s.event_count}  windows:{len(s.window_ids)}"
              f"  gravity:{s.max_gravity:.3f}" if s.max_gravity else
              f"  events:{s.event_count}  windows:{len(s.window_ids)}")
        if s.merge_confidences:
            print(f"  conf:  {s.merge_confidences}")
        for wid in s.window_ids:
            w = windows_by_id.get(wid)
            if w:
                print(f"    {wid:<28} {w.start_date}  ev={w.event_count}"
                      f"  [{' '.join(w.top_terms[:4])}]")
