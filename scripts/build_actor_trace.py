#!/usr/bin/env python3
"""
build_actor_trace.py

Per-actor full L0-L3 daily trace for the /architecture page. Reframes
the worked example from "follow one cluster through the layers" to
"follow one actor through the stack over time."

Reads:
  data/normalized/tech_ecosystem_filtered.jsonl + backfill    (L0 events)
  data/derived/field_instrumentation.parquet                  (L1 per-day metrics)
  topicspace-site/public/expectations_history/{TICKER}.json   (L2 per-day expectation)
  data/derived/expectation_entities.parquet                   (L3 entity table)
  data/derived/expectation_lifecycle_events.parquet           (L3 lifecycle events)
  data/derived/expectation_versions.parquet                   (L3 per-day attachments)
  data/derived/cluster_labels.json                            (LLM labels for entities' clusters)

Writes:
  data/derived/actor_trace.json
  topicspace-site/public/actor_trace.json

Schema:
  {
    "as_of": "YYYY-MM-DD",
    "ticker": "AAPL",
    "first_date": "...",
    "last_date":  "...",
    "n_days":     int,

    // L0: events/day naming the actor
    "l0": { "days": [ { "date", "n_events", "sample_title" }, ... ] },

    // L1: per-day narrative field metrics for the actor
    "l1": { "days": [ { "date", "cluster_label", "cluster_id_primary",
                        "event_count_7d", "semantic_density_7d",
                        "density_momentum", "novelty_score" }, ... ] },

    // L2: per-day forward expectation
    "l2": { "days": [ { "date", "headline", "direction", "direction_sign",
                        "conviction", "near_term_view" }, ... ] },

    // L3: entities (one per actor + cluster + direction) + their lifecycle
    //     event timeline
    "l3": {
      "entities": [ { "entity_id", "stable_cluster_id", "direction_sign",
                      "label", "first_seen", "last_seen", "n_versions",
                      "status", "peak_conviction", "last_conviction",
                      "last_headline" }, ... ],
      "events":   [ { "entity_id", "date", "event_type",
                      "conviction", "prior_conviction", "delta_conviction",
                      "detail" }, ... ]
    }
  }

Usage:
  source venv/bin/activate && python scripts/build_actor_trace.py
  python scripts/build_actor_trace.py --ticker AMD
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT        = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"

EVENTS_SOURCES = [
    ROOT / "data" / "normalized" / "tech_ecosystem_filtered.jsonl",
    ROOT / "data" / "normalized" / "tech_ecosystem_backfill.jsonl",
]
FIELD_PATH    = ROOT / "data" / "derived" / "field_instrumentation.parquet"
ENT_PATH      = ROOT / "data" / "derived" / "expectation_entities.parquet"
EVT_PATH      = ROOT / "data" / "derived" / "expectation_lifecycle_events.parquet"
VER_PATH      = ROOT / "data" / "derived" / "expectation_versions.parquet"
LABELS_PATH   = ROOT / "data" / "derived" / "cluster_labels.json"
EXPECT_HIST_DIR = SITE_PUBLIC / "expectations_history"

OUT_DERIVED = ROOT / "data" / "derived" / "actor_trace.json"
OUT_SITE    = SITE_PUBLIC / "actor_trace.json"

DEFAULT_TICKER = "AAPL"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", default=DEFAULT_TICKER,
                    help=f"actor to trace (default: {DEFAULT_TICKER})")
    args = ap.parse_args()
    tk = args.ticker.upper()
    print(f"  tracing {tk}")

    # ── L0: events/day naming the actor + best sample title per day ────────
    daily_counts: Counter[str] = Counter()
    daily_sample: dict[str, str] = {}
    seen_ids: set[str] = set()
    for src in EVENTS_SOURCES:
        if not src.exists():
            continue
        with open(src) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                eid = e.get("event_id")
                if eid in seen_ids:
                    continue
                if eid:
                    seen_ids.add(eid)
                if tk not in (e.get("actors") or []):
                    continue
                d = (e.get("timestamp") or "")[:10]
                if not d:
                    continue
                daily_counts[d] += 1
                # First non-empty title becomes the sample for that day
                title = (e.get("title") or "").strip()
                if title and len(title) > 8 and d not in daily_sample:
                    daily_sample[d] = title[:140]

    l0_days = [
        {"date": d, "n_events": int(daily_counts[d]),
         "sample_title": daily_sample.get(d)}
        for d in sorted(daily_counts.keys())
    ]
    print(f"  L0: {sum(daily_counts.values()):,} events over {len(l0_days)} days")

    # ── L1: per-day field metrics from field_instrumentation ───────────────
    field_days: list[dict] = []
    if FIELD_PATH.exists():
        fdf = pd.read_parquet(FIELD_PATH)
        fdf["date"] = fdf["date"].astype(str)
        fsub = fdf[fdf["ticker"] == tk].sort_values("date")
        for _, row in fsub.iterrows():
            field_days.append({
                "date":                row["date"],
                "cluster_label":       row["cluster_label"] or "",
                "cluster_id_primary":  int(row["cluster_id_primary"]) if pd.notna(row["cluster_id_primary"]) else -1,
                "event_count_7d":      int(row["event_count_7d"]),
                "semantic_density_7d": round(float(row["semantic_density_7d"]), 4),
                "density_momentum":    round(float(row["density_momentum"]), 4),
                "novelty_score":       round(float(row["novelty_score"]), 4),
            })
    print(f"  L1: {len(field_days)} days of field metrics")

    # ── L2: per-day expectation from expectations_history/{TICKER}.json ───
    l2_days: list[dict] = []
    hist_path = EXPECT_HIST_DIR / f"{tk}.json"
    if hist_path.exists():
        try:
            h = json.loads(hist_path.read_text())
            for e in h.get("expectations", []):
                if not e.get("date"):
                    continue
                d_raw = (e.get("direction") or "").lower()
                if "bull" in d_raw:
                    sign = 1
                elif "bear" in d_raw:
                    sign = -1
                else:
                    sign = 0
                l2_days.append({
                    "date":           e["date"],
                    "headline":       (e.get("headline") or "")[:160],
                    "direction":      e.get("direction", ""),
                    "direction_sign": sign,
                    "conviction":     round(float(e.get("conviction") or 0.5), 3),
                    "near_term_view": (e.get("near_term_view") or "")[:280],
                })
            l2_days.sort(key=lambda r: r["date"])
        except Exception as ex:
            print(f"  ! L2 read failed: {ex}")
    print(f"  L2: {len(l2_days)} days of expectations")

    # ── L1.narratives: distinct themes the actor was attached to over time ─
    # Derived from expectation_versions (per-(date, ticker, stable_cluster_id))
    # joined with cluster_labels for human-readable names. This gives a
    # coherent "which narratives did this actor participate in" view because
    # stable_cluster_id is F-002-stable across days; the per-day TF-token
    # labels in field_instrumentation are too noisy for that purpose.
    labels_cache = json.loads(LABELS_PATH.read_text()) if LABELS_PATH.exists() else {}

    narratives_out: list[dict] = []
    if VER_PATH.exists():
        ver_df = pd.read_parquet(VER_PATH)
        ver_df["date"] = ver_df["date"].astype(str)
        ver_sub = ver_df[ver_df["ticker"] == tk].copy()
        # Group by stable_cluster_id
        groups = ver_sub.groupby("stable_cluster_id")
        for sid, g in groups:
            lbl = (labels_cache.get(sid) or {}).get("label", "") or ""
            dates = sorted(g["date"].unique().tolist())
            # Per-direction breakdown within this narrative
            dirs = Counter(int(s) for s in g["direction_sign"])
            narratives_out.append({
                "stable_cluster_id": sid,
                "label":             lbl,
                "first_date":        dates[0],
                "last_date":         dates[-1],
                "n_days":            len(dates),
                "dates":             dates,
                "direction_mix": {
                    "bullish": int(dirs.get(1, 0)),
                    "bearish": int(dirs.get(-1, 0)),
                    "neutral": int(dirs.get(0, 0)),
                },
                "avg_conviction":    round(float(g["conviction"].mean()), 3),
            })
        # Sort by n_days desc — most-participated narratives first
        narratives_out.sort(key=lambda r: -r["n_days"])
    print(f"  L1 narratives: {len(narratives_out)} distinct themes the actor attached to")

    # ── L2.snapshots: evenly-spaced expectation snapshots ─────────────────
    # Pick first, last, and ~4 evenly-spaced dates between them so the
    # reader sees the expectation summary at intervals across the corpus.
    snapshots_out: list[dict] = []
    if l2_days:
        N = len(l2_days)
        # Choose ~6 indices: 0, 1/5, 2/5, 3/5, 4/5, last
        idxs = sorted({
            0,
            N // 5,
            (2 * N) // 5,
            (3 * N) // 5,
            (4 * N) // 5,
            N - 1,
        })
        for i in idxs:
            d = l2_days[i]
            why = ("first"    if i == 0
                   else "today" if i == N - 1
                   else "interval")
            snapshots_out.append({
                "date":           d["date"],
                "direction":      d["direction"],
                "direction_sign": d["direction_sign"],
                "conviction":     d["conviction"],
                "headline":       d["headline"],
                "near_term_view": d["near_term_view"],
                "why":            why,
            })
    print(f"  L2 snapshots: {len(snapshots_out)} interval snapshots")

    # ── L3: entities for this actor + their full lifecycle events ─────────

    entities_out: list[dict] = []
    events_out:   list[dict] = []
    if ENT_PATH.exists() and EVT_PATH.exists():
        ent_df = pd.read_parquet(ENT_PATH)
        evt_df = pd.read_parquet(EVT_PATH)
        ent_sub = ent_df[ent_df["ticker"] == tk].copy()
        if len(ent_sub):
            for _, r in ent_sub.iterrows():
                stable = r["stable_cluster_id"]
                lbl = (labels_cache.get(stable) or {}).get("label", "") or ""
                entities_out.append({
                    "entity_id":         r["entity_id"],
                    "stable_cluster_id": stable,
                    "direction_sign":    int(r["direction_sign"]),
                    "label":             lbl,
                    "first_seen":        r["first_seen"],
                    "last_seen":         r["last_seen"],
                    "n_versions":        int(r["n_versions"]),
                    "status":            r["status"],
                    "peak_conviction":   round(float(r["peak_conviction"]), 3),
                    "last_conviction":   round(float(r["last_conviction"]), 3),
                    "last_headline":     (r["last_headline"] or "")[:200],
                })
            ent_ids = set(ent_sub["entity_id"])
            evt_sub = evt_df[evt_df["entity_id"].isin(ent_ids)].sort_values(["date", "entity_id"])
            for _, r in evt_sub.iterrows():
                events_out.append({
                    "entity_id":        r["entity_id"],
                    "date":             r["date"],
                    "event_type":       r["event_type"],
                    "conviction":       (None if pd.isna(r["conviction"]) else round(float(r["conviction"]), 3)),
                    "prior_conviction": (None if pd.isna(r["prior_conviction"]) else round(float(r["prior_conviction"]), 3)),
                    "delta_conviction": (None if pd.isna(r["delta_conviction"]) else round(float(r["delta_conviction"]), 3)),
                    "detail":           (r["detail"] or "")[:200],
                })
    print(f"  L3: {len(entities_out)} entities, {len(events_out)} lifecycle events")

    # ── Time bounds for the trace ──────────────────────────────────────────
    all_dates: set[str] = set()
    all_dates.update(d["date"] for d in l0_days)
    all_dates.update(d["date"] for d in field_days)
    all_dates.update(d["date"] for d in l2_days)
    all_dates.update(d["date"] for d in events_out)
    if not all_dates:
        sys.exit(f"No data for {tk}")
    first_date = min(all_dates)
    last_date  = max(all_dates)

    payload = {
        "as_of":      last_date,
        "ticker":     tk,
        "first_date": first_date,
        "last_date":  last_date,
        "n_days":     (pd.Timestamp(last_date) - pd.Timestamp(first_date)).days + 1,
        "l0": { "days": l0_days },
        "l1": {
            "days":       field_days,
            "narratives": narratives_out,
        },
        "l2": {
            "days":      l2_days,
            "snapshots": snapshots_out,
        },
        "l3": {
            "entities": entities_out,
            "events":   events_out,
        },
    }

    OUT_DERIVED.parent.mkdir(parents=True, exist_ok=True)
    OUT_DERIVED.write_text(json.dumps(payload, indent=2))
    OUT_SITE.write_text(json.dumps(payload, indent=2))

    print(f"  wrote {OUT_DERIVED}")
    print(f"  wrote {OUT_SITE}")
    print()
    print(f"  ─── {tk} TRACE SUMMARY ({first_date} → {last_date}, {payload['n_days']}d) ───")
    print(f"  L0: {sum(d['n_events'] for d in l0_days):,} events, peak {max((d['n_events'] for d in l0_days), default=0)}/day")
    if l2_days:
        last = l2_days[-1]
        print(f"  L2 today: {last['direction']} · conviction {last['conviction']} · '{last['headline'][:80]}'")
    if entities_out:
        active = [e for e in entities_out if e["status"] == "active"]
        persistent = [e for e in active if e["n_versions"] >= 3]
        print(f"  L3: {len(entities_out)} entities ({len(active)} active, {len(persistent)} persistent ≥3v)")
        evt_counts = Counter(e["event_type"] for e in events_out)
        print(f"      events: {dict(evt_counts)}")


if __name__ == "__main__":
    main()
