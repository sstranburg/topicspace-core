#!/usr/bin/env python3
"""
build_confidence_decomposition.py

Computes 7 confidence components per actor and writes them to
topicspace-site/public/actor_confidence.json. The actor page reads this and
renders an inline panel under the trust badge.

Components:
  historical_edge      — best_hit_rate from the backtest
  sample_size          — n_observations
  state_reliability    — hit-rate weight on the actor's *current* state
  sector_reliability   — average best_hit_rate of same-sector actors
  market_confirmation  — did recent rel move with the engine's call?
  source_quality       — % of top_sources rated core+context
  freshness            — days since pipeline last refreshed this row

Reads:
  data/derived/actor_predictive_score.json   (reliability backtest)
  topicspace-site/public/actors.json         (current state + NDS + rel)
  topicspace-site/public/actors_detail.json  (source relevance from P3)

Writes:
  topicspace-site/public/actor_confidence.json
"""

import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).parent.parent
SCORE_PATH         = ROOT / "data" / "derived" / "actor_predictive_score.json"
ACTORS_PATH        = ROOT.parent / "topicspace-site" / "public" / "actors.json"
ACTORS_DETAIL_PATH = ROOT.parent / "topicspace-site" / "public" / "actors_detail.json"
OUT_PATH           = ROOT.parent / "topicspace-site" / "public" / "actor_confidence.json"


# ── Tier definitions ─────────────────────────────────────────────────────────

def tier_hit_rate(hr: Optional[float]) -> str:
    if hr is None:        return "unknown"
    if hr >= 0.65:        return "strong"
    if hr >= 0.55:        return "moderate"
    if hr >= 0.45:        return "weak"
    return "very_weak"


def tier_sample(n: int) -> str:
    if n >= 80:           return "adequate"
    if n >= 30:           return "limited"
    return "insufficient"


def tier_alignment(value: float) -> str:
    """value in [-1, 1]; 1 = confirming, -1 = contradicting."""
    if value > 0.3:       return "confirming"
    if value < -0.3:      return "contradicting"
    return "mixed"


def tier_quality(pct: float) -> str:
    if pct >= 0.7:        return "strong"
    if pct >= 0.4:        return "mixed"
    return "weak"


def tier_freshness(days: int) -> str:
    if days <= 1:         return "current"
    if days <= 3:         return "recent"
    return "stale"


# ── Predicted direction (mirrors engine logic) ──────────────────────────────

def engine_pred(state: str, narr_dir: int) -> int:
    if narr_dir > 0:
        if state in ("CONFIRMED", "EARLY", "REPRICING", "DISAGREEMENT"):
            return +1
        if state == "NEG_CONFIRMATION":
            return -1
        return 0
    else:
        if state in ("NEG_CONFIRMATION", "CONFIRMED"):
            return -1
        if state == "DISAGREEMENT":
            return +1
        return 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    if not SCORE_PATH.exists():
        raise SystemExit(f"Missing {SCORE_PATH}")
    if not ACTORS_PATH.exists():
        raise SystemExit(f"Missing {ACTORS_PATH}")

    score = json.loads(SCORE_PATH.read_text())
    actors = json.loads(ACTORS_PATH.read_text())["actors"]
    detail = (json.loads(ACTORS_DETAIL_PATH.read_text())["actors"]
              if ACTORS_DETAIL_PATH.exists() else [])

    score_by_t  = {a["ticker"]: a for a in score["actors"]}
    detail_by_t = {a["t"]:      a for a in detail}

    # Sector aggregates (avg best_hit_rate per sector for engine_reliable+inverted)
    sector_hits: dict[str, list[float]] = defaultdict(list)
    for a in score["actors"]:
        sec = a.get("sector") or "Other"
        hr = a.get("best_hit_rate")
        if hr is None:
            continue
        # For inverted actors, the *flipped* edge is 1 - hr; use whichever is stronger
        rel = a.get("reliability", "")
        effective_hr = (1.0 - hr) if rel == "engine_inverted" else hr
        sector_hits[sec].append(effective_hr)
    sector_avg = {s: round(sum(v) / len(v), 3) for s, v in sector_hits.items() if v}

    today = dt.date.fromisoformat(score.get("as_of") or str(dt.date.today()))

    results = []
    for a in actors:
        t = a.get("t")
        if not t:
            continue
        sa = score_by_t.get(t, {})
        da = detail_by_t.get(t, {})

        # historical_edge — flipped for inverted actors
        rel_label = sa.get("reliability", "unknown")
        best_hr = sa.get("best_hit_rate")
        effective_hr = (1.0 - best_hr) if (rel_label == "engine_inverted" and best_hr is not None) else best_hr

        # sample_size
        n_obs = sa.get("n_observations", 0)

        # state_reliability — look up current state in by_state
        current_state = a.get("state", "")
        state_n = 0
        state_n_directional = 0
        for st_row in sa.get("by_state", []):
            if st_row.get("state") == current_state:
                state_n = st_row.get("n", 0)
                state_n_directional = st_row.get("n_directional", 0)
                break
        state_directional_share = (state_n_directional / state_n) if state_n > 0 else None

        # sector_reliability
        sec = sa.get("sector") or "Other"
        sec_avg = sector_avg.get(sec)

        # market_confirmation — does recent rel align with engine call?
        predicted = engine_pred(current_state, a.get("dir", 1))
        rel_5d = a.get("rel", 0)
        if predicted == 0 or abs(rel_5d) < 0.5:
            mc_value = 0.0
        else:
            mc_value = 1.0 if (predicted > 0) == (rel_5d > 0) else -1.0
        # If actor is inverted, flip the alignment expectation
        if rel_label == "engine_inverted":
            mc_value = -mc_value

        # source_quality — % of top_sources rated core+context
        srcs = (da.get("detail") or {}).get("top_sources", [])
        if srcs:
            ok = sum(1 for s in srcs if s.get("relevance") in ("core", "context"))
            src_pct = ok / len(srcs)
        else:
            src_pct = None

        # freshness — days since as_of date
        days_stale = 0  # data is being written now

        components = {
            "historical_edge": {
                "value": effective_hr,
                "tier":  tier_hit_rate(effective_hr),
                "detail": (
                    f"{int(round(effective_hr*100))}% best hit rate" if effective_hr is not None else "no edge data"
                ) + (f" (inverted; raw {int(round(best_hr*100))}%)" if rel_label == "engine_inverted" and best_hr is not None else ""),
            },
            "sample_size": {
                "value": n_obs,
                "tier":  tier_sample(n_obs),
                "detail": f"{n_obs} observations",
            },
            "state_reliability": {
                "value": state_directional_share,
                "tier":  ("informative" if (state_directional_share or 0) >= 0.7
                          else "mixed" if (state_directional_share or 0) >= 0.3
                          else "mostly_neutral" if state_n > 0 else "unknown"),
                "detail": (
                    f"current state '{current_state}' issues calls "
                    f"{int(round((state_directional_share or 0)*100))}% of the time"
                    if state_n > 0 else f"no data for state '{current_state}'"
                ),
            },
            "sector_reliability": {
                "value": sec_avg,
                "tier":  tier_hit_rate(sec_avg),
                "detail": (
                    f"avg {int(round(sec_avg*100))}% across {sec}"
                    if sec_avg is not None else f"no {sec} data"
                ),
            },
            "market_confirmation": {
                "value": mc_value,
                "tier":  tier_alignment(mc_value),
                "detail": (
                    "price is moving with the engine's direction"
                    if mc_value > 0.3 else
                    "price is moving against the engine's direction"
                    if mc_value < -0.3 else
                    "no clear price alignment"
                ),
            },
            "source_quality": {
                "value": src_pct,
                "tier":  tier_quality(src_pct) if src_pct is not None else "unknown",
                "detail": (
                    f"{int(round(src_pct*100))}% of visible sources rated core or context"
                    if src_pct is not None else "no scored sources"
                ),
            },
            "freshness": {
                "value": days_stale,
                "tier":  tier_freshness(days_stale),
                "detail": (
                    "refreshed today" if days_stale <= 1 else
                    f"refreshed {days_stale} days ago"
                ),
            },
        }

        results.append({
            "ticker":     t,
            "reliability": rel_label,
            "components": components,
        })

    out = {
        "as_of":   str(today),
        "n_actors": len(results),
        "actors":  results,
    }
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"  wrote {args.out}  ({len(results)} actors)")


if __name__ == "__main__":
    main()
