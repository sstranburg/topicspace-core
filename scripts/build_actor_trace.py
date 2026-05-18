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
  Per-ticker:
    data/derived/actor_trace/{TICKER}.json
    topicspace-site/public/actor_trace/{TICKER}.json

  Default-ticker compatibility shim (kept until older pages migrate):
    data/derived/actor_trace.json
    topicspace-site/public/actor_trace.json

Schema is unchanged from prior versions; see below.

Usage:
  source venv/bin/activate && python scripts/build_actor_trace.py
  python scripts/build_actor_trace.py --ticker AMD
  python scripts/build_actor_trace.py --all
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

# Per-ticker output dirs
OUT_DERIVED_DIR = ROOT / "data" / "derived" / "actor_trace"
OUT_SITE_DIR    = SITE_PUBLIC / "actor_trace"

# Compatibility shim — keep the top-level file pointing at the default ticker
# until older pages migrate. Once nothing reads it, drop.
COMPAT_DERIVED = ROOT / "data" / "derived" / "actor_trace.json"
COMPAT_SITE    = SITE_PUBLIC / "actor_trace.json"

DEFAULT_TICKER = "NVDA"


# ─── L0 events per actor ────────────────────────────────────────────────────

def load_events_index() -> dict[str, dict[str, dict]]:
    """Returns { ticker: { date: {n_events, sample_title} } }, dedup by event_id."""
    by_ticker: dict[str, dict[str, dict]] = {}
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
                d = (e.get("timestamp") or "")[:10]
                if not d:
                    continue
                title = (e.get("title") or "").strip()
                actors = e.get("actors") or []
                for tk in actors:
                    day = by_ticker.setdefault(tk, {}).setdefault(
                        d, {"n_events": 0, "sample_title": None}
                    )
                    day["n_events"] += 1
                    if title and len(title) > 8 and not day["sample_title"]:
                        day["sample_title"] = title[:140]
    return by_ticker


# ─── Build one actor's trace payload ─────────────────────────────────────────

def build_payload(
    tk: str,
    l0_index:     dict[str, dict[str, dict]],
    field_df:     pd.DataFrame | None,
    ent_df:       pd.DataFrame | None,
    evt_df:       pd.DataFrame | None,
    ver_df:       pd.DataFrame | None,
    labels_cache: dict,
) -> dict | None:
    """Returns the trace payload for one ticker, or None if there's no data."""

    # L0
    l0_for_tk = l0_index.get(tk, {})
    l0_days = [
        {"date": d, "n_events": int(v["n_events"]), "sample_title": v["sample_title"]}
        for d, v in sorted(l0_for_tk.items())
    ]

    # L1
    field_days: list[dict] = []
    if field_df is not None:
        fsub = field_df[field_df["ticker"] == tk].sort_values("date")
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

    # L2
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
            print(f"    ! L2 read failed for {tk}: {ex}")

    # L1 narratives — distinct stable_cluster_ids this actor attached to
    narratives_out: list[dict] = []
    if ver_df is not None:
        ver_sub = ver_df[ver_df["ticker"] == tk]
        for sid, g in ver_sub.groupby("stable_cluster_id"):
            lbl = (labels_cache.get(sid) or {}).get("label", "") or ""
            dates = sorted(g["date"].unique().tolist())
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
        narratives_out.sort(key=lambda r: -r["n_days"])

    # L2 snapshots — evenly spaced
    snapshots_out: list[dict] = []
    if l2_days:
        N = len(l2_days)
        idxs = sorted({0, N // 5, (2 * N) // 5, (3 * N) // 5, (4 * N) // 5, N - 1})
        for i in idxs:
            d = l2_days[i]
            why = "first" if i == 0 else "today" if i == N - 1 else "interval"
            snapshots_out.append({
                "date":           d["date"],
                "direction":      d["direction"],
                "direction_sign": d["direction_sign"],
                "conviction":     d["conviction"],
                "headline":       d["headline"],
                "near_term_view": d["near_term_view"],
                "why":            why,
            })

    # L3 entities + events
    entities_out: list[dict] = []
    events_out:   list[dict] = []
    if ent_df is not None and evt_df is not None:
        ent_sub = ent_df[ent_df["ticker"] == tk]
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

    # Time bounds
    all_dates: set[str] = set()
    all_dates.update(d["date"] for d in l0_days)
    all_dates.update(d["date"] for d in field_days)
    all_dates.update(d["date"] for d in l2_days)
    all_dates.update(d["date"] for d in events_out)
    if not all_dates:
        return None
    first_date = min(all_dates)
    last_date  = max(all_dates)

    return {
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


def write_payload(tk: str, payload: dict, is_default: bool) -> None:
    """Write per-ticker file + maintain the top-level compat file for default."""
    OUT_DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    OUT_SITE_DIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload, indent=2)
    (OUT_DERIVED_DIR / f"{tk}.json").write_text(blob)
    (OUT_SITE_DIR    / f"{tk}.json").write_text(blob)
    if is_default:
        COMPAT_DERIVED.write_text(blob)
        COMPAT_SITE.write_text(blob)


def print_summary(tk: str, payload: dict) -> None:
    l0_days = payload["l0"]["days"]
    l2_days = payload["l2"]["days"]
    entities = payload["l3"]["entities"]
    events = payload["l3"]["events"]
    n_l0 = sum(d["n_events"] for d in l0_days)
    print(f"  {tk}  L0:{n_l0:>6,}ev/{len(l0_days):>3}d  "
          f"L1:{len(payload['l1']['days']):>3}d  "
          f"L2:{len(l2_days):>3}d  "
          f"L3:{len(entities):>3}ent/{len(events):>3}evt  "
          f"narr:{len(payload['l1']['narratives']):>2}")


def list_tickers(field_df: pd.DataFrame) -> list[str]:
    """Source of truth for the actor cohort: tickers in field_instrumentation."""
    return sorted(field_df["ticker"].unique().tolist())


# ─── main ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", default=DEFAULT_TICKER,
                    help=f"actor to trace (default: {DEFAULT_TICKER})")
    ap.add_argument("--all", action="store_true",
                    help="trace every actor in field_instrumentation; emit per-ticker files")
    args = ap.parse_args()

    print("  loading shared artifacts…")
    field_df     = pd.read_parquet(FIELD_PATH) if FIELD_PATH.exists() else None
    if field_df is not None:
        field_df["date"] = field_df["date"].astype(str)
    ent_df       = pd.read_parquet(ENT_PATH) if ENT_PATH.exists() else None
    evt_df       = pd.read_parquet(EVT_PATH) if EVT_PATH.exists() else None
    ver_df       = pd.read_parquet(VER_PATH) if VER_PATH.exists() else None
    if ver_df is not None:
        ver_df["date"] = ver_df["date"].astype(str)
    labels_cache = json.loads(LABELS_PATH.read_text()) if LABELS_PATH.exists() else {}

    print("  scanning L0 corpus…")
    l0_index = load_events_index()
    print(f"    L0 index: {len(l0_index)} tickers")

    if args.all:
        if field_df is None:
            sys.exit("--all requires field_instrumentation.parquet (cohort source of truth)")
        tickers = list_tickers(field_df)
        print(f"  tracing {len(tickers)} actors…")
        written = 0
        for tk in tickers:
            payload = build_payload(tk, l0_index, field_df, ent_df, evt_df, ver_df, labels_cache)
            if payload is None:
                print(f"  ! no data for {tk}, skipping")
                continue
            write_payload(tk, payload, is_default=(tk == DEFAULT_TICKER))
            print_summary(tk, payload)
            written += 1
        print(f"\n  wrote {written} per-ticker traces → {OUT_SITE_DIR}")
        if (OUT_SITE_DIR / f"{DEFAULT_TICKER}.json").exists():
            print(f"  compat shim: {COMPAT_SITE} mirrors {DEFAULT_TICKER}.json")
    else:
        tk = args.ticker.upper()
        print(f"  tracing {tk}")
        payload = build_payload(tk, l0_index, field_df, ent_df, evt_df, ver_df, labels_cache)
        if payload is None:
            sys.exit(f"No data for {tk}")
        write_payload(tk, payload, is_default=(tk == DEFAULT_TICKER))
        print_summary(tk, payload)
        print(f"\n  wrote {OUT_SITE_DIR / f'{tk}.json'}")


if __name__ == "__main__":
    main()
