"""
Build the spatial expectation field.

Each expectation occupies a position in a 2D structural space at each
timestep:
  X = directional bias (bearish ↔ neutral ↔ bullish)
  Y = cohort breadth (narrow ↔ medium ↔ broad)

We discretize to a 3×3 grid and compute per-cell daily aggregates:
  density   — count of expectations in the cell
  pressure  — fraction in weakening status
  born      — new expectations entering the cell that day
  retired   — expectations that retired from the cell that day
  flux_in   — expectations that moved into this cell from another yesterday
  flux_out  — expectations that left this cell to another today

Inputs:
  data/derived/expectation_replay_history_Q-*_*.jsonl   (auto-discovered)
  data/derived/backtest_history.parquet                 (for actor states)

Outputs:
  data/derived/spatial_field_history.jsonl              (one row per day)
  data/derived/spatial_field_summary.json
"""

from __future__ import annotations
import json
import pathlib
import collections
from typing import Iterable

DERIVED = pathlib.Path(__file__).resolve().parents[1] / "data" / "derived"

# ── State → direction mapping (matches replay_expectation_field.py) ────────

STATE_TO_CLASS: dict[str, str] = {
    "CONFIRMED":        "bullish_confirming",
    "EARLY":            "bullish_early",
    "DISAGREEMENT":     "bullish_rejecting",
    "DIVERGENCE":       "divergence_unpaid",
    "PRICE-LED":        "price_led",
    "NEG_CONFIRMATION": "bearish_confirming",
    "REPRICING":        "lagging",
    "UNCLEAR":          "no_follow",
    "MACRO":            "macro",
}

CLASS_TO_DIRECTION: dict[str, float] = {
    "bullish_confirming": +1.0,
    "bullish_early":      +1.0,
    "bullish_rejecting":  +0.5,
    "price_led":          +0.5,
    "bearish_confirming": -1.0,
    "divergence_unpaid":  +0.3,  # narrative-positive but price-negative
    "lagging":             0.0,
    "no_follow":           0.0,
    "macro":               0.0,
}


def state_direction(state: str) -> float:
    return CLASS_TO_DIRECTION.get(STATE_TO_CLASS.get(state, "no_follow"), 0.0)


# ── Bin definitions ─────────────────────────────────────────────────────────

DIRECTION_BINS = [
    ("bearish", -1.01, -0.20),
    ("neutral", -0.20, +0.20),
    ("bullish", +0.20, +1.01),
]

BREADTH_BINS = [
    ("narrow", 1, 3),
    ("medium", 4, 7),
    ("broad",  8, 100),
]


def direction_bin(d: float) -> str:
    for name, lo, hi in DIRECTION_BINS:
        if lo <= d < hi:
            return name
    return "neutral"


def breadth_bin(n: int) -> str:
    for name, lo, hi in BREADTH_BINS:
        if lo <= n <= hi:
            return name
    return "narrow"


def cell_id(direction: str, breadth: str) -> str:
    return f"{direction}__{breadth}"


CELLS: list[str] = [
    cell_id(d, b) for d, *_ in DIRECTION_BINS for b, *_ in BREADTH_BINS
]


# ── Load replay rows ────────────────────────────────────────────────────────

ACTIVE_STATUSES = {"active", "weakening"}


def load_replay_rows() -> list[dict]:
    rows: list[dict] = []
    for f in sorted(DERIVED.glob("expectation_replay_history_Q-*_*.jsonl")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_actor_states() -> dict[str, dict[str, str]]:
    """Returns {ticker: {date: state}}."""
    import pandas as pd
    df = pd.read_parquet(DERIVED / "backtest_history.parquet")
    df = df[df["variant"] == "baseline"].copy()
    df["date"] = df["date"].astype(str).str.slice(0, 10)
    out: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for row in df.itertuples(index=False):
        out[row.ticker][row.date] = row.state
    return dict(out)


# ── Per-row position ────────────────────────────────────────────────────────

def expectation_position(row: dict, actor_states: dict[str, dict[str, str]]) -> tuple[float, int]:
    """Compute (direction_value, cohort_breadth) for this expectation row."""
    actors = row.get("supporting_actors", []) or []
    as_of = row["as_of"]
    if actors:
        dirs = []
        for t in actors:
            s = actor_states.get(t, {}).get(as_of)
            if s is None:
                continue
            dirs.append(state_direction(s))
        direction_val = (sum(dirs) / len(dirs)) if dirs else 0.0
    else:
        direction_val = 0.0

    breadth = (
        row.get("n_supporting", 0)
        + row.get("n_conflicting", 0)
        + row.get("n_neutral", 0)
        + row.get("n_missing", 0)
    )
    if breadth == 0:
        # fall back to cohort hint via supporting_actors only
        breadth = len(actors)
    return direction_val, breadth


# ── Build daily grids ───────────────────────────────────────────────────────

def empty_cell() -> dict:
    return {"density": 0, "weakening": 0, "born": 0, "retired": 0, "flux_in": 0, "flux_out": 0}


HANDLE_RENAME = {
    "Q-001": "E-001", "Q-002": "E-002",
    "Q-006": "E-006", "Q-007": "E-007",
    "Q-008": "E-008", "Q-009": "E-009",
}


def _shorten(text: str, n: int = 130) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def _member_dict(r: dict) -> dict:
    return {
        "id":           r["expectation_id"],
        "family":       HANDLE_RENAME.get(r.get("question_handle", ""), r.get("question_handle", "")),
        "is_parent":    r.get("parent_expectation_id") is None,
        "days_alive":   r.get("days_alive", 0),
        "status":       r.get("status", ""),
        "supporting":   r.get("supporting_actors", []) or [],
        "n_supporting": r.get("n_supporting", 0),
        "statement":    _shorten(r.get("statement", "")),
        "implied_kind": r.get("implied_kind", ""),
    }


def build_grids(rows: list[dict], actor_states: dict[str, dict[str, str]]) -> list[dict]:
    """Returns one record per date with the 3×3 grid populated."""
    # Index active rows by date
    by_day: dict[str, list[dict]] = collections.defaultdict(list)
    retire_by_day: dict[str, set[str]] = collections.defaultdict(set)
    for r in rows:
        if r.get("status") in ACTIVE_STATUSES:
            by_day[r["as_of"]].append(r)
        if r.get("event") == "died":
            retire_by_day[r["as_of"]].add(r["expectation_id"])

    all_dates = sorted(by_day.keys())
    prior_cell_by_id: dict[str, str] = {}
    daily_records: list[dict] = []

    for d in all_dates:
        grid = {c: empty_cell() for c in CELLS}
        # Members per cell on this date
        members_by_cell: dict[str, list[dict]] = collections.defaultdict(list)
        current_cell_by_id: dict[str, str] = {}

        for r in by_day[d]:
            dir_val, breadth = expectation_position(r, actor_states)
            c = cell_id(direction_bin(dir_val), breadth_bin(breadth))
            current_cell_by_id[r["expectation_id"]] = c
            grid[c]["density"] += 1
            if r.get("status") == "weakening":
                grid[c]["weakening"] += 1
            if r.get("days_alive", -1) == 0:
                grid[c]["born"] += 1
            members_by_cell[c].append(_member_dict(r))

        # retirements on this date — credit them to whichever cell they were in yesterday
        for eid in retire_by_day.get(d, ()):
            prior = prior_cell_by_id.get(eid)
            if prior:
                grid[prior]["retired"] += 1

        # flux: compare each id's cell today vs yesterday
        for eid, cell_today in current_cell_by_id.items():
            cell_prior = prior_cell_by_id.get(eid)
            if cell_prior and cell_prior != cell_today:
                grid[cell_today]["flux_in"]  += 1
                grid[cell_prior]["flux_out"] += 1

        # derived pressure per cell
        for c in CELLS:
            den = grid[c]["density"]
            grid[c]["pressure"] = round(grid[c]["weakening"] / den, 4) if den else 0.0

        daily_records.append({
            "as_of": d,
            "totals": {
                "density":  sum(grid[c]["density"]  for c in CELLS),
                "weakening": sum(grid[c]["weakening"] for c in CELLS),
                "born":     sum(grid[c]["born"]     for c in CELLS),
                "retired":  sum(grid[c]["retired"]  for c in CELLS),
                "flux":     sum(grid[c]["flux_in"]  for c in CELLS),
            },
            "grid": grid,
            "members": {c: members_by_cell.get(c, []) for c in CELLS},
        })

        prior_cell_by_id = current_cell_by_id

    return daily_records


# ── Summary ────────────────────────────────────────────────────────────────

def summarize(daily_records: list[dict]) -> dict:
    cell_density_sum: collections.Counter = collections.Counter()
    cell_pressure_sum: dict[str, float] = collections.defaultdict(float)
    cell_pressure_n: dict[str, int] = collections.defaultdict(int)
    cell_born: collections.Counter = collections.Counter()
    cell_retired: collections.Counter = collections.Counter()
    cell_flux_in: collections.Counter = collections.Counter()
    cell_flux_out: collections.Counter = collections.Counter()
    # Per-cell occupant tracking: cell -> {expectation_id: {days, family, statement, is_parent, ever_retired}}
    occupants: dict[str, dict[str, dict]] = collections.defaultdict(dict)

    total_days = len(daily_records)
    for rec in daily_records:
        for c, vals in rec["grid"].items():
            cell_density_sum[c] += vals["density"]
            if vals["density"] > 0:
                cell_pressure_sum[c] += vals["pressure"]
                cell_pressure_n[c]   += 1
            cell_born[c]    += vals["born"]
            cell_retired[c] += vals["retired"]
            cell_flux_in[c]  += vals["flux_in"]
            cell_flux_out[c] += vals["flux_out"]
        for c, members in (rec.get("members") or {}).items():
            for m in members:
                eid = m["id"]
                slot = occupants[c].setdefault(eid, {
                    "id":         eid,
                    "family":     m["family"],
                    "is_parent":  m["is_parent"],
                    "statement":  m["statement"],
                    "implied_kind": m["implied_kind"],
                    "days_in_cell": 0,
                    "last_status": m["status"],
                })
                slot["days_in_cell"] += 1
                slot["last_status"]   = m["status"]
                slot["statement"]     = m["statement"]   # keep most-recent compressed text

    rows = []
    for c in CELLS:
        occ_list = sorted(
            occupants.get(c, {}).values(),
            key=lambda o: -o["days_in_cell"],
        )
        rows.append({
            "cell": c,
            "mean_density":  round(cell_density_sum[c] / total_days, 3) if total_days else 0,
            "days_occupied": cell_pressure_n[c],
            "mean_pressure_when_occupied": round(cell_pressure_sum[c] / cell_pressure_n[c], 3) if cell_pressure_n[c] else 0,
            "total_born":    cell_born[c],
            "total_retired": cell_retired[c],
            "total_flux_in": cell_flux_in[c],
            "total_flux_out": cell_flux_out[c],
            "occupants":     occ_list,
        })

    return {
        "window": {
            "start": daily_records[0]["as_of"] if daily_records else None,
            "end":   daily_records[-1]["as_of"] if daily_records else None,
            "n_days": total_days,
        },
        "direction_bins": [{"name": n, "lo": lo, "hi": hi} for n, lo, hi in DIRECTION_BINS],
        "breadth_bins":   [{"name": n, "lo": lo, "hi": hi} for n, lo, hi in BREADTH_BINS],
        "cells": rows,
    }


# ── Write ──────────────────────────────────────────────────────────────────

def write_jsonl(path: pathlib.Path, rows: Iterable[dict]) -> None:
    with path.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")


def main() -> None:
    rows = load_replay_rows()
    states = load_actor_states()
    print(f"loaded {len(rows)} replay rows; {len(states)} tickers with state history")

    daily = build_grids(rows, states)
    write_jsonl(DERIVED / "spatial_field_history.jsonl", daily)
    print(f"[wrote] data/derived/spatial_field_history.jsonl  ({len(daily)} rows)")

    summary = summarize(daily)
    (DERIVED / "spatial_field_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[wrote] data/derived/spatial_field_summary.json")

    # Brief console digest
    print()
    print("by-cell summary (mean density · days occupied · mean pressure · births · retirements · flux_in/out):")
    for row in sorted(summary["cells"], key=lambda r: -r["mean_density"]):
        print(
            f"  {row['cell']:25s}  "
            f"density={row['mean_density']:>4.1f}  "
            f"occ={row['days_occupied']:>3d}  "
            f"press={row['mean_pressure_when_occupied']:>4.2f}  "
            f"born={row['total_born']:>3d}  "
            f"retired={row['total_retired']:>3d}  "
            f"flux={row['total_flux_in']:>2d}/{row['total_flux_out']:>2d}"
        )


if __name__ == "__main__":
    main()
