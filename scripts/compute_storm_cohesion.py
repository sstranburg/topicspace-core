#!/usr/bin/env python3
"""
compute_storm_cohesion.py

For each tracked actor, compute storm-direction cohesion:
- n_storms: total active storms touching the actor
- by_state: count per state ("growing", "stable", "fading", "volatile", ...)
- dominant_direction: the state with the most storms
- agreement_pct: percentage of storms in the dominant direction (0-100)
- cohesion_strength: HIGH (>=80%), MEDIUM (50-80%), LOW (<50%, "mixed")

Reads:
  data/derived/actor_storm_summaries.jsonl

Writes:
  data/derived/storm_cohesion.json
  topicspace-site/public/storm_cohesion.json  (copy for intel field layer)

Why this exists:
  Pressure score alone doesn't distinguish "PLTR with 19 growing storms" from
  "ZETA with 5 mixed storms" — both might score similarly on loudness. The
  directional homogeneity across storms (every storm pulling the same way)
  is rare and analytically useful — used by the intel feature to cite
  cohesion as a signal.
"""

import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
STORMS_FILE = ROOT / "data" / "derived" / "actor_storm_summaries.jsonl"
OUTPUT      = ROOT / "data" / "derived" / "storm_cohesion.json"
SITE_COPY   = ROOT.parent / "topicspace-site" / "public" / "storm_cohesion.json"


def cohesion_strength(agreement_pct: float) -> str:
    if agreement_pct >= 80.0:
        return "HIGH"
    if agreement_pct >= 50.0:
        return "MEDIUM"
    return "LOW"


def main() -> None:
    if not STORMS_FILE.exists():
        print(f"ERROR: {STORMS_FILE} not found — run generate_storm_summaries.py first.")
        return

    by_actor: dict[str, list[str]] = defaultdict(list)
    for line in STORMS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        state = r.get("state")
        if not state:
            continue
        for a in r.get("actors", []):
            by_actor[a].append(state)

    cohesion = {}
    for ticker, states in sorted(by_actor.items()):
        n = len(states)
        if n == 0:
            continue
        counts = Counter(states)
        dominant_direction, dominant_n = counts.most_common(1)[0]
        agreement_pct = round(100.0 * dominant_n / n, 1)
        cohesion[ticker] = {
            "n_storms":           n,
            "by_state":           dict(counts),
            "dominant_direction": dominant_direction,
            "agreement_pct":      agreement_pct,
            "cohesion_strength":  cohesion_strength(agreement_pct),
        }

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "actor_count":  len(cohesion),
        "actors":       cohesion,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(out, indent=2))
    print(f"✓ Wrote {OUTPUT}")
    print(f"  {len(cohesion)} actors with storms")

    # Site copy for intel field layer (lib/intel/fields.ts)
    if SITE_COPY.parent.exists():
        shutil.copyfile(OUTPUT, SITE_COPY)
        print(f"✓ Copied to {SITE_COPY}")
    else:
        print(f"⚠ Site dir not found at {SITE_COPY.parent} — skipped copy")

    # Print a summary of the most extreme cohesion cases
    extreme_high  = [(t, v) for t, v in cohesion.items() if v["agreement_pct"] >= 90 and v["n_storms"] >= 5]
    extreme_low   = [(t, v) for t, v in cohesion.items() if v["agreement_pct"] < 50 and v["n_storms"] >= 5]
    extreme_high.sort(key=lambda x: -x[1]["n_storms"])
    extreme_low.sort(key=lambda x: -x[1]["n_storms"])

    if extreme_high:
        print("\nHIGH cohesion (>=90%, n>=5):")
        for t, v in extreme_high[:8]:
            print(f"  {t:<6} {v['n_storms']:>3} storms · {v['dominant_direction']:<10} · {v['agreement_pct']:.0f}%")
    if extreme_low:
        print("\nLOW cohesion (<50%, n>=5):")
        for t, v in extreme_low[:8]:
            print(f"  {t:<6} {v['n_storms']:>3} storms · split by_state={v['by_state']}")


if __name__ == "__main__":
    main()
