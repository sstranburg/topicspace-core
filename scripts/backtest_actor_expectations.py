"""
Backtest the deterministic actor-expectation engine per ticker.

For each (ticker, date) in the available state history, we:
  1. Apply the deterministic mapping (state + narrative direction → predicted direction)
  2. Look forward 5 / 10 / 20 trading days
  3. Score whether the predicted direction matched the actual forward rel-return

Aggregates per actor:
  - hit rate at each horizon
  - avg forward rel-return when bullish predicted vs bearish predicted
  - which states / read-classes are most predictive for this actor
  - a verdict: WORKS / NOISY / INSUFFICIENT

Output:
  data/derived/actor_predictive_score.json
  stdout summary table
"""

from __future__ import annotations
import argparse
import json
import pathlib
from collections import defaultdict
from typing import Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DERIVED   = REPO_ROOT / "data" / "derived"
ACTORS_JSON = REPO_ROOT.parent / "topicspace-site" / "public" / "actors.json"
HIST_PARQ   = DERIVED / "backtest_history.parquet"
OUT_PATH    = DERIVED / "actor_predictive_score.json"

HORIZONS_D = [5, 10, 20]   # trading-day horizons to score

# ── Deterministic state + direction → predicted direction ──────────────────
# +1 = bullish (expect forward rel to rise)
# -1 = bearish (expect forward rel to fall)
#  0 = mixed/neutral (no directional bet; excluded from hit-rate denominator)

def predicted_direction(state: str, narr_dir: int, flip_bearish: bool = False) -> int:
    """Return +1, -1, or 0 from the engine's deterministic mapping.

    When flip_bearish is True, predictions for narr_dir<0 actors are sign-inverted.
    This tests the hypothesis that the bearish-narrative classification is
    systematically anti-predictive (so flipping should recover the edge).
    """
    if narr_dir > 0:  # bullish-narrative actor (most names)
        if state in ("CONFIRMED", "EARLY", "REPRICING"):
            return +1
        if state == "DISAGREEMENT":
            return +1
        if state == "NEG_CONFIRMATION":
            return -1
        if state in ("DIVERGENCE", "PRICE-LED"):
            return 0
        return 0  # UNCLEAR, MACRO
    else:  # bearish-narrative actor
        base = 0
        if state == "NEG_CONFIRMATION":
            base = -1
        elif state == "CONFIRMED":
            base = -1
        elif state == "DISAGREEMENT":
            base = +1
        elif state in ("DIVERGENCE", "PRICE-LED"):
            base = 0
        return -base if flip_bearish else base


# ── Scoring per actor ───────────────────────────────────────────────────────

def hit(predicted: int, forward_rel_change: float, deadband: float = 0.5) -> Optional[bool]:
    """Return True/False if directional call hit; None for neutral predictions
    or returns within the deadband (treated as too small to score)."""
    if predicted == 0:
        return None
    if abs(forward_rel_change) < deadband:
        return None  # call was directional but the move was noise
    if predicted > 0 and forward_rel_change > 0:
        return True
    if predicted < 0 and forward_rel_change < 0:
        return True
    return False


def score_actor(ticker: str, sub_df, narr_dir: int, flip_bearish: bool = False) -> dict:
    sub_df = sub_df.sort_values("date").reset_index(drop=True)
    states = sub_df["state"].tolist()
    rels   = sub_df["rel"].tolist()
    dates  = sub_df["date"].tolist()

    n = len(sub_df)
    if n == 0:
        return {"ticker": ticker, "verdict": "INSUFFICIENT", "n_observations": 0}

    # Per-row predicted direction
    preds = [predicted_direction(s, narr_dir, flip_bearish=flip_bearish) for s in states]

    # By-state buckets: total observations per state
    by_state: dict[str, dict] = defaultdict(lambda: {
        "n": 0, "n_directional": 0, "hits_5d": 0, "miss_5d": 0,
        "sum_fwd_5d": 0.0, "sum_fwd_10d": 0.0, "sum_fwd_20d": 0.0,
        "n_fwd_5d": 0, "n_fwd_10d": 0, "n_fwd_20d": 0,
    })

    horizon_stats = {h: {
        "directional": 0, "hits": 0, "scored": 0,
        "sum_when_bull": 0.0, "n_when_bull": 0,
        "sum_when_bear": 0.0, "n_when_bear": 0,
    } for h in HORIZONS_D}

    for i in range(n):
        st = states[i]
        pred = preds[i]
        bs = by_state[st]
        bs["n"] += 1
        if pred != 0:
            bs["n_directional"] += 1

        for h in HORIZONS_D:
            if i + h >= n:
                continue
            # `rel` is a centered ±5d return measured at the dated row, so
            # rel[i+h] itself represents a forward window centered at t+h.
            # Use it directly as the forward score (do not diff against rel[i],
            # which would subtract overlapping information).
            fwd = rels[i + h]
            bs[f"sum_fwd_{h}d"] += fwd
            bs[f"n_fwd_{h}d"]   += 1
            if pred == 0:
                continue
            hs = horizon_stats[h]
            hs["directional"] += 1
            if pred > 0:
                hs["sum_when_bull"] += fwd
                hs["n_when_bull"]   += 1
            else:
                hs["sum_when_bear"] += fwd
                hs["n_when_bear"]   += 1
            r = hit(pred, fwd)
            if r is None:
                continue
            hs["scored"] += 1
            if r:
                hs["hits"] += 1
                if h == 5:
                    bs["hits_5d"] += 1
            elif h == 5:
                bs["miss_5d"] += 1

    # Summarize per horizon
    per_horizon = {}
    best_horizon = None
    best_hit_rate = 0.0
    for h, hs in horizon_stats.items():
        hr = (hs["hits"] / hs["scored"]) if hs["scored"] > 0 else None
        per_horizon[f"{h}d"] = {
            "directional_calls": hs["directional"],
            "scored":            hs["scored"],
            "hit_rate":          round(hr, 3) if hr is not None else None,
            "avg_rel_when_bullish": round(hs["sum_when_bull"] / hs["n_when_bull"], 3) if hs["n_when_bull"] else None,
            "avg_rel_when_bearish": round(hs["sum_when_bear"] / hs["n_when_bear"], 3) if hs["n_when_bear"] else None,
        }
        if hr is not None and hr > best_hit_rate:
            best_hit_rate = hr
            best_horizon = f"{h}d"

    # By-state summary
    by_state_out = []
    for st, bs in by_state.items():
        row = {"state": st, "n": bs["n"], "n_directional": bs["n_directional"]}
        for h in HORIZONS_D:
            n_fwd = bs[f"n_fwd_{h}d"]
            row[f"avg_fwd_{h}d"] = round(bs[f"sum_fwd_{h}d"] / n_fwd, 3) if n_fwd > 0 else None
        by_state_out.append(row)
    by_state_out.sort(key=lambda r: -r["n"])

    # Verdict
    total_directional = sum(hs["directional"] for hs in horizon_stats.values())
    verdict = "INSUFFICIENT"
    if total_directional >= 30 and best_horizon and best_hit_rate >= 0.60:
        h_stats = per_horizon[best_horizon]
        bull_ok = h_stats["avg_rel_when_bullish"] is None or h_stats["avg_rel_when_bullish"] > 0
        bear_ok = h_stats["avg_rel_when_bearish"] is None or h_stats["avg_rel_when_bearish"] < 0
        if bull_ok and bear_ok:
            verdict = "WORKS"
        else:
            verdict = "NOISY"
    elif total_directional >= 30:
        verdict = "NOISY"

    # Per-actor reliability flag for downstream consumers (e.g. the actor-
    # expectations page). Looks at the lowest hit rate across horizons to detect
    # systematic inversion.
    horizon_hit_rates = [
        h_stats["hit_rate"] for h_stats in per_horizon.values()
        if h_stats["hit_rate"] is not None
    ]
    if total_directional < 30 or not horizon_hit_rates:
        reliability = "insufficient"
        reliability_summary = (
            f"Backtest has only {total_directional} directional calls; "
            f"insufficient to assess engine reliability for this actor."
        )
    else:
        worst_hit = min(horizon_hit_rates)
        if best_hit_rate >= 0.60:
            reliability = "engine_reliable"
            reliability_summary = (
                f"Engine has been right {int(round(best_hit_rate * 100))}% of the time "
                f"at the {best_horizon} horizon. Trust the directional call."
            )
        elif worst_hit <= 0.40:
            inv = int(round((1 - worst_hit) * 100))
            reliability = "engine_inverted"
            reliability_summary = (
                f"Engine has been wrong {inv}% of the time on this actor "
                f"(flipped hit rate ≈{inv}%). Treat the engine's directional call as a "
                f"contrarian signal — i.e. when the engine says bullish, the market has "
                f"gone the other way."
            )
        else:
            reliability = "engine_unreliable"
            reliability_summary = (
                f"Engine hit rate stays in the 40–60% band — no demonstrable directional "
                f"edge on this actor in either direction."
            )

    return {
        "ticker":              ticker,
        "n_observations":      n,
        "narrative_dir":       int(narr_dir),
        "verdict":             verdict,
        "reliability":         reliability,
        "reliability_summary": reliability_summary,
        "best_horizon":        best_horizon,
        "best_hit_rate":       round(best_hit_rate, 3) if best_horizon else None,
        "by_horizon":          per_horizon,
        "by_state":            by_state_out,
        "window": {"start": dates[0], "end": dates[-1]},
    }


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--deadband", type=float, default=0.5,
                    help="ignore forward moves whose abs rel-change is < this (default 0.5)")
    ap.add_argument("--flip-bearish", action="store_true",
                    help="invert predictions for bearish-narrative actors (narr_dir < 0)")
    args = ap.parse_args()

    import pandas as pd

    actors_data = json.loads(ACTORS_JSON.read_text())
    dir_by_ticker = {a["t"]: a.get("dir", 1) for a in actors_data["actors"]}
    sector_by_ticker = {a["t"]: a.get("sector", "?") for a in actors_data["actors"]}

    df = pd.read_parquet(HIST_PARQ)
    df = df[df["variant"] == "baseline"].copy()
    df["date"] = df["date"].astype(str).str.slice(0, 10)

    tickers = sorted(df["ticker"].unique())
    rows = []
    for t in tickers:
        sub = df[df["ticker"] == t]
        narr_dir = dir_by_ticker.get(t, 1)
        rows.append(score_actor(t, sub, narr_dir, flip_bearish=args.flip_bearish))

    # Add sector to each row for sorting
    for r in rows:
        r["sector"] = sector_by_ticker.get(r["ticker"], "?")

    # Sort: WORKS first (by best_hit_rate desc), then NOISY, then INSUFFICIENT
    verdict_rank = {"WORKS": 0, "NOISY": 1, "INSUFFICIENT": 2}
    rows.sort(key=lambda r: (verdict_rank.get(r["verdict"], 9), -(r.get("best_hit_rate") or 0)))

    out = {
        "as_of": actors_data["date"],
        "deadband": args.deadband,
        "horizons_d": HORIZONS_D,
        "actors": rows,
    }
    payload_text = json.dumps(out, indent=2)
    out_path = pathlib.Path(args.out).resolve()
    out_path.write_text(payload_text)

    # Mirror into topicspace-site/public so the live site can read it on
    # Vercel (no storm-repo access at request time).
    site_public = REPO_ROOT.parent / "topicspace-site" / "public"
    if site_public.is_dir():
        site_target = site_public / out_path.name
        site_target.write_text(payload_text)
        print(f"[wrote] {site_target.relative_to(REPO_ROOT.parent)}")

    # ── Console summary ────────────────────────────────────────────────────
    rel_counter: dict[str, int] = {"engine_reliable": 0, "engine_inverted": 0, "engine_unreliable": 0, "insufficient": 0}
    for r in rows:
        rel_counter[r["reliability"]] = rel_counter.get(r["reliability"], 0) + 1
    print(f"\n  Backtest window per ticker shown; deadband ±{args.deadband}")
    print(f"  Reliability split → reliable {rel_counter['engine_reliable']}, "
          f"inverted {rel_counter['engine_inverted']}, "
          f"unreliable {rel_counter['engine_unreliable']}, "
          f"insufficient {rel_counter['insufficient']}\n")
    print(f"  {'TICKER':<7} {'SECTOR':<22} {'RELIABILITY':<18} {'BEST':<5} {'HIT%':<6} {'#DIR':<6} {'NDS-DIR':<8}")
    print(f"  {'─'*7} {'─'*22} {'─'*18} {'─'*5} {'─'*6} {'─'*6} {'─'*8}")
    rel_rank = {"engine_reliable": 0, "engine_inverted": 1, "engine_unreliable": 2, "insufficient": 3}
    rows.sort(key=lambda r: (rel_rank.get(r["reliability"], 9), -(r.get("best_hit_rate") or 0)))
    for r in rows:
        bhr = r.get("best_hit_rate")
        bhr_str = f"{bhr*100:.0f}%" if bhr is not None else "—"
        bh = r.get("best_horizon") or "—"
        n_dir = sum(r["by_horizon"][h]["directional_calls"] for h in r["by_horizon"])
        nd = "+1" if r["narrative_dir"] > 0 else "-1"
        print(f"  {r['ticker']:<7} {r['sector']:<22} {r['reliability']:<18} {bh:<5} {bhr_str:<6} {n_dir:<6} {nd:<8}")

    print(f"\n[wrote] {out_path.relative_to(REPO_ROOT) if out_path.is_relative_to(REPO_ROOT) else out_path}")


if __name__ == "__main__":
    main()
