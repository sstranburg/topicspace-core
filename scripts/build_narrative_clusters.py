#!/usr/bin/env python3
"""
build_narrative_clusters.py

Per-cluster event-level snapshot for the /architecture L1 "narrative
constellations" visualization. Each cluster is a storm: a coherent
group of events, with the actors who appear in them as anchors.

Reads:
  data/derived/cluster_lineage.parquet     (per-cluster n_events, n_actors, lifecycle)
  data/derived/cluster_members.parquet     (event_id → stable_cluster_id, per day)
  data/derived/cluster_labels.json         (LLM-generated cluster labels)
  data/normalized/tech_ecosystem_filtered.jsonl + backfill (event_id → actors, title)

Writes:
  data/derived/narrative_clusters.json
  topicspace-site/public/narrative_clusters.json

Output schema:
  {
    "as_of": "YYYY-MM-DD",
    "n_clusters": 25,
    "total_events_today": ...,
    "clusters": [
      {
        "stable_cluster_id": "theme-...",
        "label": "...",
        "lifecycle": "persisted" | "merge_target" | "split_target" | "drift" | "born",
        "n_events": 1383,
        "n_actors": 44,
        "actors": ["AAPL", "NVDA", ...],          // actors with ≥1 event in cluster today
        "actor_counts": {"AAPL": 12, "NVDA": 23},  // event count per actor (top 8)
        "sample_titles": ["...", "...", "..."]    // up to 3 representative titles
      },
      ...
    ]
  }

Usage:
  source venv/bin/activate && python scripts/build_narrative_clusters.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT        = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"

LINEAGE_PATH = ROOT / "data" / "derived" / "cluster_lineage.parquet"
MEMBERS_PATH = ROOT / "data" / "derived" / "cluster_members.parquet"
LABELS_PATH  = ROOT / "data" / "derived" / "cluster_labels.json"
SOURCES      = [
    ROOT / "data" / "normalized" / "tech_ecosystem_filtered.jsonl",
    ROOT / "data" / "normalized" / "tech_ecosystem_backfill.jsonl",
]

OUT_DERIVED = ROOT / "data" / "derived" / "narrative_clusters.json"
OUT_SITE    = SITE_PUBLIC / "narrative_clusters.json"


def main():
    if not LINEAGE_PATH.exists():
        sys.exit(f"Missing {LINEAGE_PATH}")
    if not MEMBERS_PATH.exists():
        sys.exit(f"Missing {MEMBERS_PATH}")

    lineage = pd.read_parquet(LINEAGE_PATH)
    lineage["date"] = lineage["date"].astype(str)
    as_of  = lineage["date"].max()
    today_lineage = lineage[lineage["date"] == as_of].copy()
    print(f"  as_of: {as_of} · {len(today_lineage)} clusters")

    members = pd.read_parquet(MEMBERS_PATH)
    members["date"] = members["date"].astype(str)
    today_members = members[members["date"] == as_of].copy()
    print(f"  today members: {len(today_members):,} rows")

    labels_cache = {}
    if LABELS_PATH.exists():
        labels_cache = json.loads(LABELS_PATH.read_text())

    # Build event_id → (actors[], title) lookup from the JSONL sources.
    # Both files dedup by event_id (filtered + backfill can overlap).
    today_event_ids = set(today_members["event_id"])
    event_meta: dict[str, dict] = {}
    for src in SOURCES:
        if not src.exists():
            print(f"  ! skipping (missing): {src}")
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
                if not eid or eid not in today_event_ids:
                    continue
                if eid in event_meta:
                    continue
                event_meta[eid] = {
                    "actors": e.get("actors", []) or [],
                    "title":  e.get("title", "") or "",
                }
    print(f"  event metadata for {len(event_meta):,} / {len(today_event_ids):,} events")

    # Join: members → event_meta → per-cluster aggregates
    today_members["actors"] = today_members["event_id"].map(
        lambda eid: event_meta.get(eid, {}).get("actors", [])
    )
    today_members["title"] = today_members["event_id"].map(
        lambda eid: event_meta.get(eid, {}).get("title", "")
    )

    clusters_out: list[dict] = []
    for _, lrow in today_lineage.sort_values("n_events", ascending=False).iterrows():
        sid   = lrow["stable_cluster_id"]
        label = labels_cache.get(sid, {}).get("label") or ""
        grp = today_members[today_members["stable_cluster_id"] == sid]
        # Flatten actor counts
        ac: Counter = Counter()
        for actor_list in grp["actors"]:
            for a in actor_list:
                ac[a] += 1
        # Sample titles — prefer ones with non-empty text
        titles = [t for t in grp["title"].tolist() if t and len(t) > 8]
        # Deduplicate first; take first 3 by appearance order
        seen = set()
        sample_titles: list[str] = []
        for t in titles:
            key = t.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            sample_titles.append(t.strip()[:140])
            if len(sample_titles) >= 3:
                break

        top_actors = [a for a, _ in ac.most_common(40)]
        actor_counts_top = dict(ac.most_common(8))

        clusters_out.append({
            "stable_cluster_id":  sid,
            "label":              label,
            "lifecycle":          lrow["lifecycle"],
            "n_events":           int(lrow["n_events"]),
            "n_actors":           int(lrow["n_actors"]),
            "actors":             top_actors,
            "actor_counts":       actor_counts_top,
            "sample_titles":      sample_titles,
        })

    payload = {
        "as_of":              as_of,
        "n_clusters":         len(clusters_out),
        "total_events_today": int(today_lineage["n_events"].sum()),
        "clusters":           clusters_out,
    }

    OUT_DERIVED.parent.mkdir(parents=True, exist_ok=True)
    OUT_DERIVED.write_text(json.dumps(payload, indent=2))
    OUT_SITE.write_text(json.dumps(payload, indent=2))

    print(f"  wrote {OUT_DERIVED}")
    print(f"  wrote {OUT_SITE}")
    print()
    print(f"  ─── TOP CLUSTERS BY EVENT COUNT @ {as_of} ───")
    for c in clusters_out[:6]:
        actors_top = ", ".join(c["actors"][:5])
        extra = f" (+{len(c['actors'])-5})" if len(c["actors"]) > 5 else ""
        print(f"  [{c['n_events']:>4}ev {c['n_actors']:>2}a] {(c['label'] or c['stable_cluster_id'])[:55]:<55}  {actors_top}{extra}")


if __name__ == "__main__":
    main()
