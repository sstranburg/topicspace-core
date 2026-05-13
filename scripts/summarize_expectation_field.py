"""
Summarize the expectation field history.

Reads:
  data/derived/expectation_field_history{,_E-001,_E-002}.jsonl
  data/derived/expectation_field_events{,_E-001,_E-002}.jsonl

Emits:
  data/derived/expectation_field_summary.json   (structured)
  stdout report                                  (human-readable)
"""

from __future__ import annotations
import json
import pathlib
import collections
from statistics import mean

DERIVED = pathlib.Path(__file__).resolve().parents[1] / "data" / "derived"

def _discover_scopes() -> list[tuple[str, str, str]]:
    """Discover all per-family scopes from the on-disk history files."""
    scopes: list[tuple[str, str, str]] = [
        ("combined", "expectation_field_history.jsonl", "expectation_field_events.jsonl"),
    ]
    for p in sorted(DERIVED.glob("expectation_field_history_E-*.jsonl")):
        fam = p.stem.split("_")[-1]  # E-001, E-006, etc.
        scopes.append((fam, p.name, f"expectation_field_events_{fam}.jsonl"))
    return scopes


SCOPES = _discover_scopes()


def load_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def metric_stats(history: list[dict], key: str) -> dict:
    vals = [h["metrics"][key] for h in history]
    return {
        "start": vals[0],
        "end":   vals[-1],
        "min":   round(min(vals), 4),
        "max":   round(max(vals), 4),
        "mean":  round(mean(vals), 4),
    }


def summarize_scope(scope: str, hist_path: pathlib.Path, ev_path: pathlib.Path) -> dict:
    history = load_jsonl(hist_path)
    events  = load_jsonl(ev_path)
    if not history:
        return {"scope": scope, "empty": True}

    dates = [h["as_of"] for h in history]

    # cumulative event totals across the window (from snapshot.events_today)
    event_totals = collections.Counter()
    for h in history:
        for k, v in h.get("events_today", {}).items():
            event_totals[k] += v

    # field-level event totals
    field_events_by_kind = collections.Counter(e["kind"] for e in events)

    # family dominance — max share any single family ever held
    fam_max_share = 0.0
    fam_max_family = None
    fam_max_date = None
    for h in history:
        n = h["n_active"]
        if not n:
            continue
        for fam, cnt in h["by_family"].items():
            share = cnt / n
            if share > fam_max_share:
                fam_max_share = share
                fam_max_family = fam
                fam_max_date = h["as_of"]

    return {
        "scope": scope,
        "window": {"start": dates[0], "end": dates[-1], "n_days": len(dates)},
        "metrics": {
            "breadth":              metric_stats(history, "breadth"),
            "family_concentration": metric_stats(history, "family_concentration"),
            "alignment":            metric_stats(history, "alignment"),
            "refinement_pressure":  metric_stats(history, "refinement_pressure"),
            "stress":               metric_stats(history, "stress"),
            "mortality_7d":         metric_stats(history, "mortality_7d"),
            "drift":                metric_stats(history, "drift"),
        },
        "lifecycle_events": dict(event_totals),
        "field_events":     dict(field_events_by_kind),
        "family_dominance": {
            "max_share":  round(fam_max_share, 4),
            "family":     fam_max_family,
            "first_date": fam_max_date,
        },
    }


# ── Stdout reporting ────────────────────────────────────────────────────────

BAR = "─" * 72


def fmt_stat(s: dict, fmt: str = "{:.3f}") -> str:
    return f"start={fmt.format(s['start'])}  end={fmt.format(s['end'])}  min={fmt.format(s['min'])}  max={fmt.format(s['max'])}  mean={fmt.format(s['mean'])}"


def print_scope(summary: dict) -> None:
    s = summary
    print(BAR)
    print(f"scope: {s['scope']}    window: {s['window']['start']} → {s['window']['end']}  ({s['window']['n_days']} days)")
    print(BAR)
    m = s["metrics"]
    print(f"  breadth              {fmt_stat(m['breadth'], '{:.0f}')}")
    print(f"  family_concentration {fmt_stat(m['family_concentration'])}")
    print(f"  alignment            {fmt_stat(m['alignment'])}")
    print(f"  refinement_pressure  {fmt_stat(m['refinement_pressure'])}")
    print(f"  stress               {fmt_stat(m['stress'])}")
    print(f"  mortality_7d         {fmt_stat(m['mortality_7d'], '{:.0f}')}")
    print(f"  drift                {fmt_stat(m['drift'])}")
    print(f"  lifecycle events:    {s['lifecycle_events']}")
    print(f"  field events:        {s['field_events']}")
    fd = s["family_dominance"]
    print(f"  max family share:    {fd['max_share']:.2f}  ({fd['family']}, first reached {fd['first_date']})")


# ── Cross-scope comparison ──────────────────────────────────────────────────

def cross_scope_table(summaries: list[dict]) -> None:
    if not summaries:
        return
    keys = ["breadth", "family_concentration", "alignment", "refinement_pressure", "stress", "mortality_7d", "drift"]
    print(BAR)
    print("cross-scope comparison (start → end, mean)")
    print(BAR)
    header = f"  {'metric':<22}" + "".join(f"{s['scope']:>22}" for s in summaries)
    print(header)
    for k in keys:
        row = f"  {k:<22}"
        for s in summaries:
            m = s["metrics"][k]
            cell = f"{m['start']:.2f}→{m['end']:.2f} ({m['mean']:.2f})"
            row += f"{cell:>22}"
        print(row)


# ── Narrative findings ──────────────────────────────────────────────────────

def derive_findings(summaries: list[dict]) -> list[str]:
    out: list[str] = []
    by_scope = {s["scope"]: s for s in summaries}
    combined = by_scope.get("combined")
    e1 = by_scope.get("E-001")
    e2 = by_scope.get("E-002")

    def trend(stat: dict) -> str:
        delta = stat["end"] - stat["start"]
        if abs(delta) < 0.05:
            return "flat"
        return "rising" if delta > 0 else "falling"

    if combined:
        m = combined["metrics"]
        out.append(f"alignment {trend(m['alignment'])}: start {m['alignment']['start']:.2f} → end {m['alignment']['end']:.2f}  "
                   f"(min {m['alignment']['min']:.2f})")
        out.append(f"refinement_pressure {trend(m['refinement_pressure'])}: start {m['refinement_pressure']['start']:.2f} → end {m['refinement_pressure']['end']:.2f}")
        out.append(f"stress {trend(m['stress'])}: start {m['stress']['start']:.2f} → end {m['stress']['end']:.2f}  (max {m['stress']['max']:.2f})")
        out.append(f"max mortality_7d in combined field: {m['mortality_7d']['max']}")
        churn = combined['field_events'].get('churning', 0)
        stress_days = combined['field_events'].get('stressing', 0)
        out.append(f"field-event totals (combined): churning={churn}, stressing={stress_days}, "
                   f"narrowing={combined['field_events'].get('narrowing', 0)}, "
                   f"fragmenting={combined['field_events'].get('fragmenting', 0)}, "
                   f"consolidating={combined['field_events'].get('consolidating', 0)}, "
                   f"drifting={combined['field_events'].get('drifting', 0)}")

    if e1 and e2:
        e1m = e1["metrics"]; e2m = e2["metrics"]
        out.append(f"per-family alignment at end: E-001 {e1m['alignment']['end']:.2f}  vs  E-002 {e2m['alignment']['end']:.2f}")
        out.append(f"per-family stress at end:    E-001 {e1m['stress']['end']:.2f}  vs  E-002 {e2m['stress']['end']:.2f}")
        out.append(f"per-family mortality (max 7d): E-001 {e1m['mortality_7d']['max']}  vs  E-002 {e2m['mortality_7d']['max']}")
        out.append(f"per-family lifecycle (split/retired/weakened): "
                   f"E-001 {e1['lifecycle_events'].get('split',0)}/{e1['lifecycle_events'].get('retired',0)}/{e1['lifecycle_events'].get('weakened',0)}, "
                   f"E-002 {e2['lifecycle_events'].get('split',0)}/{e2['lifecycle_events'].get('retired',0)}/{e2['lifecycle_events'].get('weakened',0)}")
    return out


def main() -> None:
    summaries: list[dict] = []
    for scope, hist, ev in SCOPES:
        s = summarize_scope(scope, DERIVED / hist, DERIVED / ev)
        summaries.append(s)
        print_scope(s)

    cross_scope_table(summaries)

    print(BAR)
    print("derived findings")
    print(BAR)
    for line in derive_findings(summaries):
        print(f"  • {line}")

    # Write structured summary
    out = {"scopes": summaries}
    out_path = DERIVED / "expectation_field_summary.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(BAR)
    print(f"[wrote] {out_path.relative_to(DERIVED.parent.parent)}")


if __name__ == "__main__":
    main()
