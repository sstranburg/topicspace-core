#!/usr/bin/env python3
"""
derive_eligibility_matrix.py

Reads sector_summary.csv (from run_event_studies.py) and derives a new
SECTOR_STATE_ELIGIBLE matrix based on hit rate and sample size thresholds.

Shows:
  1. Full sector × state × horizon matrix with all stats
  2. Which cells pass / fail eligibility at each threshold
  3. Diff vs the old hard-coded matrix
  4. The new SECTOR_STATE_ELIGIBLE dict ready to paste into run_strategy_lab.py

Eligibility criteria:
  n_10d  >= MIN_N        (minimum sample size — cells below this are too thin)
  hit_10d >= MIN_HIT     (hit rate at 10D horizon in percent)

Secondary filter (applied on top of primary):
  avg_10d >= MIN_AVG     (average excess must be meaningfully positive)

Usage:
  source venv/bin/activate && python scripts/derive_eligibility_matrix.py
"""

from pathlib import Path
import pandas as pd
import numpy as np

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "data" / "derived" / "event_studies"

# ── Eligibility thresholds ────────────────────────────────────────────────────

MIN_N   = 5      # minimum n at 10D horizon
MIN_HIT = 55.0   # minimum hit rate at 10D (%)
MIN_AVG = 0.0    # minimum avg excess at 10D (%; 0 = any positive)

# Secondary tighter threshold shown for reference (not used for matrix)
TIGHT_N   = 10
TIGHT_HIT = 60.0

# ── Old matrix (S2 post-fix baseline) ────────────────────────────────────────

OLD_MATRIX: dict[str, set[str]] = {
    "AI Infrastructure":   {"DIVERGENCE", "CONFIRMED", "MACRO", "PRICE-LED"},
    "Semiconductors":      {"CONFIRMED", "DIVERGENCE", "EARLY", "REPRICING",
                            "DISAGREEMENT", "NEG_CONFIRMATION"},
    "AI Platform":         {"DIVERGENCE"},
    "Cloud / Hyperscaler": {"REPRICING", "DIVERGENCE", "MACRO"},
    "Energy / Power":      {"DIVERGENCE", "MACRO"},
    "Growth Software":     set(),
    "Materials":           {"DIVERGENCE"},
    "EV / Consumer":       set(),
    "Consumer Tech":       set(),
}

ALL_STATES = [
    "DIVERGENCE", "REPRICING", "EARLY", "CONFIRMED",
    "MACRO", "NEG_CONFIRMATION", "DISAGREEMENT", "PRICE-LED", "UNCLEAR",
]

ALL_SECTORS = [
    "Semiconductors", "AI Infrastructure", "AI Platform",
    "Cloud / Hyperscaler", "Growth Software", "Energy / Power",
    "Materials", "Consumer Tech", "EV / Consumer",
]


def load_sector_summary() -> pd.DataFrame:
    path = OUT_DIR / "sector_summary.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run run_event_studies.py first")
    return pd.read_csv(path)


def pivot_for_sector(df: pd.DataFrame, sector: str) -> dict[str, dict]:
    """
    Return {state: {h: {n, hit, avg, med}}} for a given sector.
    """
    sub = df[df["sector"] == sector]
    out: dict[str, dict] = {}
    for _, row in sub.iterrows():
        state = row["state"]
        h     = row["horizon"]
        out.setdefault(state, {})[h] = {
            "n":   int(row["n"]),
            "hit": float(row["hit_rate"]),
            "avg": float(row["avg_exc"]),
            "med": float(row["med_exc"]),
        }
    return out


def is_eligible(cell: dict, min_n=MIN_N, min_hit=MIN_HIT, min_avg=MIN_AVG) -> bool:
    h10 = cell.get("10D")
    if h10 is None:
        return False
    return (h10["n"] >= min_n
            and h10["hit"] >= min_hit
            and h10["avg"] >= min_avg)


def fmt(v, fmt_str="+.1f") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "  n/a"
    return f"{v:{fmt_str}}%"


def sep(c="-", w=80) -> str:
    return c * w


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    df = load_sector_summary()
    print(f"Loaded sector_summary.csv  —  {len(df)} rows  "
          f"({df['sector'].nunique()} sectors, {df['state'].nunique()} states)")

    n_total_10d = df[df["horizon"] == "10D"]["n"].sum()
    print(f"Total 10D event-study entries: {n_total_10d:,}\n")

    # ── Build pivot by sector ──────────────────────────────────────────────────
    sector_data: dict[str, dict] = {}
    for sector in ALL_SECTORS:
        sector_data[sector] = pivot_for_sector(df, sector)

    # ── 1. Full matrix with stats ──────────────────────────────────────────────
    print(sep("="))
    print("  1. FULL SECTOR × STATE MATRIX  (10D stats; ✓ = eligible under base criteria)")
    print(f"     Criteria: n≥{MIN_N}, hit≥{MIN_HIT}%, avg≥{MIN_AVG}%")
    print(sep("="))

    new_matrix: dict[str, set[str]] = {s: set() for s in ALL_SECTORS}

    for sector in ALL_SECTORS:
        cells = sector_data.get(sector, {})
        print(f"\n  {sector}")
        print(f"    {'STATE':<22} {'N':>5}  {'HIT':>6}  {'AVG':>7}  {'MED':>7}  "
              f"{'5D-hit':>7}  {'20D-hit':>7}  ELIG")
        print("    " + "-" * 74)
        for state in ALL_STATES:
            cell = cells.get(state, {})
            h10  = cell.get("10D")
            h5   = cell.get("5D")
            h20  = cell.get("20D")
            if h10 is None:
                # No data for this cell
                print(f"    {state:<22} {'—':>5}   {'—':>6}   {'—':>7}   {'—':>7}   {'—':>7}   {'—':>7}   —")
                continue
            elig   = is_eligible(cell)
            tight  = is_eligible(cell, min_n=TIGHT_N, min_hit=TIGHT_HIT)
            marker = "✓✓" if tight else ("✓ " if elig else "  ")
            hit5   = f"{h5['hit']:.0f}%" if h5 else "  n/a"
            hit20  = f"{h20['hit']:.0f}%" if h20 else "  n/a"
            old_flag = "OLD" if state in OLD_MATRIX.get(sector, set()) else "   "
            print(f"    {state:<22} {h10['n']:>5}  {h10['hit']:>5.0f}%  "
                  f"{fmt(h10['avg']):>7}  {fmt(h10['med']):>7}  "
                  f"{hit5:>6}  {hit20:>7}  {marker}  {old_flag}")
            if elig:
                new_matrix[sector].add(state)

    # ── 2. Diff vs old matrix ──────────────────────────────────────────────────
    print(f"\n{sep('=')}")
    print("  2. DIFF vs OLD MATRIX")
    print(sep("="))

    added:   list[tuple[str, str]] = []
    removed: list[tuple[str, str]] = []

    for sector in ALL_SECTORS:
        old = OLD_MATRIX.get(sector, set())
        new = new_matrix[sector]
        for state in new - old:
            added.append((sector, state))
        for state in old - new:
            removed.append((sector, state))

    if added:
        print(f"\n  ADDED ({len(added)} cells):")
        for sector, state in sorted(added):
            h10 = sector_data.get(sector, {}).get(state, {}).get("10D", {})
            n   = h10.get("n", 0)
            hit = h10.get("hit", 0)
            avg = h10.get("avg", 0)
            print(f"    {sector:<26} × {state:<22}  "
                  f"n={n}  hit={hit:.0f}%  avg={avg:+.1f}%")
    else:
        print("\n  ADDED: none")

    if removed:
        print(f"\n  REMOVED ({len(removed)} cells):")
        for sector, state in sorted(removed):
            h10 = sector_data.get(sector, {}).get(state, {}).get("10D", {})
            n   = h10.get("n", 0)
            hit = h10.get("hit", 0)
            avg = h10.get("avg", 0)
            note = f"n={n}  hit={hit:.0f}%  avg={avg:+.1f}%" if n > 0 else "no 10D data"
            print(f"    {sector:<26} × {state:<22}  {note}")
    else:
        print("\n  REMOVED: none")

    # ── 3. Threshold sensitivity: key cells near the boundary ─────────────────
    print(f"\n{sep('=')}")
    print("  3. NEAR-BOUNDARY CELLS  (eligible under relaxed threshold: n≥3, hit≥50%)")
    print(f"     Not in new matrix (base threshold), but potentially worth watching.")
    print(sep("="))

    near_bound = []
    for sector in ALL_SECTORS:
        cells = sector_data.get(sector, {})
        for state in ALL_STATES:
            cell = cells.get(state, {})
            h10  = cell.get("10D")
            if h10 is None:
                continue
            if is_eligible(cell):
                continue    # already in matrix
            if h10["n"] >= 3 and h10["hit"] >= 50.0 and h10["avg"] >= 0.0:
                near_bound.append((sector, state, h10["n"], h10["hit"], h10["avg"]))

    if near_bound:
        print(f"\n  {'SECTOR':<26} {'STATE':<22} {'N':>5}  {'HIT':>6}  {'AVG':>7}")
        print("  " + "-" * 68)
        for sector, state, n, hit, avg in sorted(near_bound, key=lambda x: -x[3]):
            print(f"  {sector:<26} {state:<22} {n:>5}  {hit:>5.0f}%  {avg:>+6.1f}%")
    else:
        print("  None")

    # ── 4. Growth Software deep-dive ───────────────────────────────────────────
    print(f"\n{sep('=')}")
    print("  4. GROWTH SOFTWARE  —  full stats at all horizons")
    print(f"     (Key question: which states are actually positive for this sector?)")
    print(sep("="))

    gs_cells = sector_data.get("Growth Software", {})
    print(f"\n  {'STATE':<22} {'HOR':>4}  {'N':>5}  {'HIT':>6}  {'AVG':>7}  {'MED':>7}")
    print("  " + "-" * 56)
    for state in ALL_STATES:
        cell = gs_cells.get(state, {})
        if not cell:
            continue
        for h in ["5D", "10D", "20D"]:
            hd = cell.get(h)
            if hd is None:
                continue
            marker = " ✓" if is_eligible(cell) and h == "10D" else "  "
            print(f"  {state:<22} {h:>4}  {hd['n']:>5}  {hd['hit']:>5.0f}%  "
                  f"{fmt(hd['avg']):>7}  {fmt(hd['med']):>7}{marker}")

    # ── 5. New matrix as Python dict ───────────────────────────────────────────
    print(f"\n{sep('=')}")
    print("  5. NEW SECTOR_STATE_ELIGIBLE  (paste into run_strategy_lab.py)")
    print(sep("="))
    print("""
SECTOR_STATE_ELIGIBLE: dict[str, set[str]] = {""")
    for sector in ALL_SECTORS:
        states = sorted(new_matrix[sector])
        if not states:
            print(f'    "{sector}":{" " * max(1, 27 - len(sector))}set(),')
        else:
            states_str = ", ".join(f'"{s}"' for s in states)
            print(f'    "{sector}":{" " * max(1, 27 - len(sector))}{{{states_str}}},')
    print("}")

    # ── 6. Tighter matrix (reference only) ────────────────────────────────────
    print(f"\n{sep()}")
    print(f"  6. TIGHTER THRESHOLD MATRIX  (n≥{TIGHT_N}, hit≥{TIGHT_HIT}%  — reference only)")
    print(sep())
    tight_matrix: dict[str, set[str]] = {s: set() for s in ALL_SECTORS}
    for sector in ALL_SECTORS:
        cells = sector_data.get(sector, {})
        for state in ALL_STATES:
            cell = cells.get(state, {})
            if is_eligible(cell, min_n=TIGHT_N, min_hit=TIGHT_HIT):
                tight_matrix[sector].add(state)
        states = sorted(tight_matrix[sector])
        label  = f"{{{', '.join(repr(s) for s in states)}}}" if states else "set()"
        print(f"  {sector:<26} {label}")

    print(f"\n  Base matrix cells:   "
          f"{sum(len(v) for v in new_matrix.values())}")
    print(f"  Tighter matrix cells: "
          f"{sum(len(v) for v in tight_matrix.values())}")
    print(f"  Old matrix cells:    "
          f"{sum(len(v) for v in OLD_MATRIX.values())}")


if __name__ == "__main__":
    main()
