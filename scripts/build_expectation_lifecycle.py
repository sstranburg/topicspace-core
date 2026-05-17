#!/usr/bin/env python3
"""
build_expectation_lifecycle.py  —  F-006 V1

Builds the L3 expectation lifecycle layer on top of F-002 (stable clusters)
and F-005 (expectation attachment).

V1 lifecycle fingerprint:  entity_id = hash(ticker + stable_cluster_id + direction_sign)
Each (ticker, cluster, direction) is a persistent ENTITY with:
  - versions: per-date snapshots while the actor's daily expectation maps to
    that (cluster, direction)
  - lifecycle events: born / strengthened / weakened / contradicted / retired

V1 scope (per user spec):
  - born, strengthened, weakened, contradicted, retired
  - no split/merge UI yet
  - thesis_trail emitted per actor into actors_detail.json

Writes:
  data/derived/expectation_entities.parquet
  data/derived/expectation_versions.parquet
  data/derived/expectation_lifecycle_events.parquet
  data/derived/thesis_trails.json                 (per-ticker, for site)

Usage:
  source venv/bin/activate && python scripts/build_expectation_lifecycle.py
"""

import datetime as dt
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"

EVENT_EMB_PATH = ROOT / "data" / "derived" / "event_embeddings.parquet"
EXP_EMB_PATH   = ROOT / "data" / "derived" / "expectation_embeddings.parquet"
MEMBERS_PATH   = ROOT / "data" / "derived" / "cluster_members.parquet"
LABELS_PATH    = ROOT / "data" / "derived" / "cluster_labels.json"
CLAIM_SENT_PATH = ROOT / "data" / "derived" / "claim_sentences.json"

EXPS_TODAY        = SITE_PUBLIC / "actor_expectations.json"
EXPS_HISTORY_DIR  = SITE_PUBLIC / "expectations_history"

OUT_ENTITIES   = ROOT / "data" / "derived" / "expectation_entities.parquet"
OUT_VERSIONS   = ROOT / "data" / "derived" / "expectation_versions.parquet"
OUT_EVENTS     = ROOT / "data" / "derived" / "expectation_lifecycle_events.parquet"
OUT_TRAILS     = ROOT / "data" / "derived" / "thesis_trails.json"
OUT_TRAILS_SITE = SITE_PUBLIC / "thesis_trails.json"

# Classification thresholds — calibrate over time
DELTA_THRESHOLD     = 0.10   # conviction shift to qualify as strengthened/weakened
RETIRED_GAP_DAYS    = 7      # days absent from coverage to mark retired
SIM_FLOOR           = 0.10   # below this, treat attachment as unreliable (skip)
TRAIL_MIN_VERSIONS  = 3      # filter thesis_trail: only entities seen ≥3 days
TRAIL_KEEP_TYPES    = {"strengthened", "weakened", "contradicted"}  # always keep these


# ─── helpers ───────────────────────────────────────────────────────────────

def direction_sign(d: str) -> int:
    if not d:
        return 0
    s = d.lower()
    if "bull" in s:
        return +1
    if "bear" in s:
        return -1
    return 0


def entity_hash(ticker: str, stable_cluster_id: str, direction_sign: int) -> str:
    s = f"{ticker}::{stable_cluster_id}::{direction_sign}"
    return "ent-" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def l2_normalize(arr: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(arr, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return arr / n


# ─── attach expectations to clusters ───────────────────────────────────────

def build_attachments(
    exp_emb_df: pd.DataFrame,
    event_mat: np.ndarray,
    members_df: pd.DataFrame,
    exp_meta: dict[tuple[str, str], dict],
) -> pd.DataFrame:
    """
    Returns a DataFrame of (date, ticker, stable_cluster_id, direction, direction_sign,
                            conviction, headline, near_term_view, sim, input_hash).
    """
    eid_to_idx = {eid: i for i, eid in enumerate(
        pd.read_parquet(EVENT_EMB_PATH, columns=["event_id"])["event_id"].tolist()
    )}
    members_df = members_df.copy()
    members_df["emb_idx"] = members_df["event_id"].map(eid_to_idx)
    members_df = members_df.dropna(subset=["emb_idx"]).copy()
    members_df["emb_idx"] = members_df["emb_idx"].astype(int)

    exp_dates = set(exp_emb_df["date"].unique())
    mem_dates = set(members_df["date"].unique())
    valid_dates = sorted(exp_dates & mem_dates)
    print(f"  attaching expectations across {len(valid_dates)} dates")

    rows: list[dict] = []
    for d in valid_dates:
        exps_d = exp_emb_df[exp_emb_df["date"] == d]
        if len(exps_d) == 0:
            continue
        members_d = members_df[members_df["date"] == d]
        if len(members_d) == 0:
            continue

        # Per-day cluster centroids
        day_clusters: dict[int, dict] = {}
        for cluster_id, group in members_d.groupby("day_cluster_id"):
            emb_idx_arr = group["emb_idx"].values
            stable_id = group["stable_cluster_id"].iloc[0]
            centroid = l2_normalize(
                event_mat[emb_idx_arr].mean(axis=0, keepdims=True)
            )[0]
            day_clusters[int(cluster_id)] = {
                "stable_id": stable_id,
                "centroid":  centroid,
            }
        cluster_keys = sorted(day_clusters.keys())
        if not cluster_keys:
            continue
        centroid_mat = np.stack([day_clusters[k]["centroid"] for k in cluster_keys])

        # Attach each expectation to nearest cluster
        exp_mat = np.stack(exps_d["embedding"].apply(
            lambda x: np.asarray(x, dtype=np.float32)
        ).tolist())
        exp_mat = l2_normalize(exp_mat)
        sims = exp_mat @ centroid_mat.T
        best_clusters = sims.argmax(axis=1)
        best_sims = sims.max(axis=1)

        d_iso = pd.Timestamp(d).date().isoformat()
        for i, (_, row) in enumerate(exps_d.iterrows()):
            sim = float(best_sims[i])
            if sim < SIM_FLOOR:
                continue
            ck = cluster_keys[int(best_clusters[i])]
            stable_id = day_clusters[ck]["stable_id"]
            tk = row["ticker"]
            meta = exp_meta.get((d_iso, tk), {})
            d_raw = meta.get("direction", "")
            rows.append({
                "date":              d_iso,
                "ticker":            tk,
                "stable_cluster_id": stable_id,
                "direction":         d_raw,
                "direction_sign":    direction_sign(d_raw),
                "conviction":        float(meta.get("conviction", 0.5) or 0.5),
                "headline":          meta.get("headline", "") or "",
                "near_term_view":    meta.get("near_term", "") or "",
                "sim":               round(sim, 4),
                "input_hash":        row.get("input_hash", ""),
            })

    return pd.DataFrame(rows)


# ─── lifecycle classification ──────────────────────────────────────────────

def classify_lifecycle(
    attachments: pd.DataFrame,
    as_of_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (entities, versions, events) DataFrames."""
    if attachments.empty:
        return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    # Add entity_id
    attachments = attachments.copy()
    attachments["entity_id"] = [
        entity_hash(r.ticker, r.stable_cluster_id, r.direction_sign)
        for r in attachments.itertuples(index=False)
    ]
    attachments = attachments.sort_values(["entity_id", "date"]).reset_index(drop=True)

    # Versions: one per (entity_id, date)
    versions = attachments[[
        "entity_id", "date", "ticker", "stable_cluster_id",
        "direction", "direction_sign", "conviction",
        "headline", "near_term_view", "sim", "input_hash",
    ]].copy()

    # Events
    events: list[dict] = []

    # Per-entity timeline → born, strengthened, weakened
    for entity_id, grp in attachments.groupby("entity_id"):
        grp = grp.sort_values("date").reset_index(drop=True)
        prev_conv = None
        for i, row in grp.iterrows():
            if i == 0:
                events.append({
                    "entity_id":       entity_id,
                    "date":            row["date"],
                    "event_type":      "born",
                    "prior_conviction": None,
                    "conviction":      row["conviction"],
                    "delta_conviction": None,
                    "detail":          (row["headline"] or "")[:200],
                })
            else:
                delta = row["conviction"] - prev_conv
                if delta > DELTA_THRESHOLD:
                    events.append({
                        "entity_id":        entity_id,
                        "date":             row["date"],
                        "event_type":       "strengthened",
                        "prior_conviction": prev_conv,
                        "conviction":       row["conviction"],
                        "delta_conviction": round(delta, 3),
                        "detail":           (row["headline"] or "")[:200],
                    })
                elif delta < -DELTA_THRESHOLD:
                    events.append({
                        "entity_id":        entity_id,
                        "date":             row["date"],
                        "event_type":       "weakened",
                        "prior_conviction": prev_conv,
                        "conviction":       row["conviction"],
                        "delta_conviction": round(delta, 3),
                        "detail":           (row["headline"] or "")[:200],
                    })
            prev_conv = row["conviction"]

    # Contradicted: on a date when actor produces opposite-direction expectation
    # mapping to the same (cluster) — emit on the original entity.
    # Group by (ticker, stable_cluster_id) → look at direction_sign per date
    grouped = attachments.groupby(["ticker", "stable_cluster_id"])
    for (tk, cluster), grp in grouped:
        grp = grp.sort_values("date").reset_index(drop=True)
        # Per direction_sign, last-active date
        active: dict[int, str] = {}  # direction_sign -> last_date
        for _, row in grp.iterrows():
            current_sign = row["direction_sign"]
            current_date = row["date"]
            # If a different non-zero sign was active recently, contradict it
            for prior_sign, prior_date in list(active.items()):
                if prior_sign == current_sign:
                    continue
                # Only contradict signed (not neutral) by signed (not neutral)
                if prior_sign == 0 or current_sign == 0:
                    continue
                if prior_sign * current_sign < 0:
                    prior_entity = entity_hash(tk, cluster, prior_sign)
                    events.append({
                        "entity_id":        prior_entity,
                        "date":             current_date,
                        "event_type":       "contradicted",
                        "prior_conviction": None,
                        "conviction":       None,
                        "delta_conviction": None,
                        "detail":           (
                            f"contradicted by opposing expectation "
                            f"({row['direction'] or 'opposite'})"
                        )[:200],
                    })
                    # Once contradicted, drop prior sign from active set
                    active.pop(prior_sign, None)
            active[current_sign] = current_date

    # Retired: per entity, if last_seen < as_of_date - RETIRED_GAP_DAYS, emit retired
    as_of_dt = dt.date.fromisoformat(as_of_date)
    last_seen_per_entity = attachments.groupby("entity_id")["date"].max()
    retired_threshold = as_of_dt - dt.timedelta(days=RETIRED_GAP_DAYS)
    for entity_id, last_seen in last_seen_per_entity.items():
        last_dt = dt.date.fromisoformat(last_seen)
        if last_dt <= retired_threshold:
            retired_date = (last_dt + dt.timedelta(days=RETIRED_GAP_DAYS + 1)).isoformat()
            # Don't emit a retired date past as_of
            if retired_date > as_of_date:
                retired_date = as_of_date
            events.append({
                "entity_id":        entity_id,
                "date":             retired_date,
                "event_type":       "retired",
                "prior_conviction": None,
                "conviction":       None,
                "delta_conviction": None,
                "detail":           f"absent for >{RETIRED_GAP_DAYS} days since {last_seen}",
            })

    events_df = pd.DataFrame(events).sort_values(["entity_id", "date", "event_type"])

    # Entities summary
    entity_rows: list[dict] = []
    for entity_id, grp in attachments.groupby("entity_id"):
        grp_sorted = grp.sort_values("date")
        last_row = grp_sorted.iloc[-1]
        first_seen = grp_sorted["date"].min()
        last_seen = grp_sorted["date"].max()
        # Status: retired if absent past threshold; contradicted if any
        # contradicted event exists; active otherwise
        ent_events = events_df[events_df["entity_id"] == entity_id]
        if (ent_events["event_type"] == "retired").any():
            status = "retired"
        elif (ent_events["event_type"] == "contradicted").any():
            status = "contradicted"
        else:
            status = "active"
        entity_rows.append({
            "entity_id":         entity_id,
            "ticker":            last_row["ticker"],
            "stable_cluster_id": last_row["stable_cluster_id"],
            "direction_sign":    int(last_row["direction_sign"]),
            "first_seen":        first_seen,
            "last_seen":         last_seen,
            "n_versions":        int(len(grp_sorted)),
            "status":            status,
            "peak_conviction":   float(grp_sorted["conviction"].max()),
            "mean_conviction":   float(grp_sorted["conviction"].mean()),
            "last_conviction":   float(last_row["conviction"]),
            "last_headline":     (last_row["headline"] or "")[:200],
            "last_direction":    last_row["direction"],
        })
    entities_df = pd.DataFrame(entity_rows)

    return entities_df, versions, events_df


# ─── thesis trail per actor ───────────────────────────────────────────────

def build_thesis_trails(
    entities_df: pd.DataFrame,
    events_df: pd.DataFrame,
    labels_cache: dict,
    claim_sentence_cache: dict,
) -> dict:
    """
    Returns { ticker: { trail: [...], n_entities, n_active, ... } }
    Each trail entry = a lifecycle event with theme label + claim sentence
    if available. Trails are chronological, capped per actor.
    """
    if entities_df.empty or events_df.empty:
        return {}

    # Build a quick lookup: entity_id -> (ticker, cluster, sign)
    ent_lookup = entities_df.set_index("entity_id").to_dict("index")

    # Latest claim sentence per (cluster_id, dominant_direction)
    # The cache key format is "{stable_id}::{member_hash}". We just want the
    # most recently cached sentence per cluster + direction match.
    sentence_by_cluster_dir: dict[tuple[str, str], str] = {}
    for key, rec in claim_sentence_cache.items():
        cluster = rec.get("stable_cluster_id", "")
        dom = rec.get("dominant_direction", "")
        first_seen = rec.get("first_seen_date", "")
        # Pick the most recent first_seen
        existing = sentence_by_cluster_dir.get((cluster, dom))
        if existing is None or first_seen > existing[1]:
            sentence_by_cluster_dir[(cluster, dom)] = (rec.get("sentence", ""), first_seen)

    def sentence_for(cluster: str, sign: int) -> str:
        dom = {1: "bullish", -1: "bearish", 0: "mixed"}.get(sign, "")
        rec = sentence_by_cluster_dir.get((cluster, dom))
        return rec[0] if rec else ""

    def label_for(cluster: str) -> str:
        return labels_cache.get(cluster, {}).get("label", "") or ""

    # Group events by ticker via entity_id → ticker
    # Filter: only include events from entities with n_versions ≥ TRAIL_MIN_VERSIONS,
    # OR events of strengthened/weakened/contradicted type (always meaningful).
    # This avoids surfacing single-day born/retired churn in the actor-facing UI.
    trails: dict[str, dict] = defaultdict(lambda: {"trail": []})
    for _, ev in events_df.iterrows():
        ent = ent_lookup.get(ev["entity_id"])
        if not ent:
            continue
        n_versions = int(ent.get("n_versions", 0))
        if n_versions < TRAIL_MIN_VERSIONS and ev["event_type"] not in TRAIL_KEEP_TYPES:
            continue
        ticker = ent["ticker"]
        cluster = ent["stable_cluster_id"]
        sign = int(ent["direction_sign"])
        trails[ticker]["trail"].append({
            "date":              ev["date"],
            "event_type":        ev["event_type"],
            "entity_id":         ev["entity_id"],
            "stable_cluster_id": cluster,
            "direction_sign":    sign,
            "label":             label_for(cluster),
            "claim_sentence":    sentence_for(cluster, sign),
            "conviction":        (None if pd.isna(ev["conviction"]) else float(ev["conviction"])),
            "delta_conviction":  (None if pd.isna(ev["delta_conviction"]) else float(ev["delta_conviction"])),
            "detail":            ev["detail"] or "",
        })

    # Sort each trail chronologically; cap to 30 most recent
    for ticker, payload in trails.items():
        payload["trail"].sort(key=lambda x: x["date"])
        payload["trail"] = payload["trail"][-30:]
        # Quick stats
        ent_for_ticker = entities_df[entities_df["ticker"] == ticker]
        payload["n_entities"] = int(len(ent_for_ticker))
        payload["n_active"]   = int((ent_for_ticker["status"] == "active").sum())
        payload["active_claims"] = [
            {
                "entity_id":         r["entity_id"],
                "stable_cluster_id": r["stable_cluster_id"],
                "direction_sign":    int(r["direction_sign"]),
                "label":             label_for(r["stable_cluster_id"]),
                "claim_sentence":    sentence_for(r["stable_cluster_id"], int(r["direction_sign"])),
                "last_conviction":   float(r["last_conviction"]),
                "n_versions":        int(r["n_versions"]),
                "first_seen":        r["first_seen"],
                "last_seen":         r["last_seen"],
            }
            for _, r in ent_for_ticker.iterrows()
            if r["status"] == "active" and int(r["n_versions"]) >= TRAIL_MIN_VERSIONS
        ]
        payload["active_claims"].sort(key=lambda x: (-x["n_versions"], -x["last_conviction"]))

    return dict(trails)


# ─── main ─────────────────────────────────────────────────────────────────

def main():
    print("  loading artifacts…")
    if not EXP_EMB_PATH.exists():
        sys.exit(f"Missing {EXP_EMB_PATH}")
    if not MEMBERS_PATH.exists():
        sys.exit(f"Missing {MEMBERS_PATH}")
    if not EVENT_EMB_PATH.exists():
        sys.exit(f"Missing {EVENT_EMB_PATH}")

    exp_emb_df = pd.read_parquet(EXP_EMB_PATH)
    exp_emb_df["date"] = pd.to_datetime(exp_emb_df["date"])
    print(f"    expectation embeddings: {len(exp_emb_df):,}")

    event_emb_df = pd.read_parquet(EVENT_EMB_PATH)
    event_mat = np.stack(event_emb_df["embedding"].apply(
        lambda x: np.asarray(x, dtype=np.float32)
    ).tolist())
    event_mat = l2_normalize(event_mat)
    print(f"    event embeddings: {event_mat.shape}")

    members_df = pd.read_parquet(MEMBERS_PATH)
    members_df["date"] = pd.to_datetime(members_df["date"])
    print(f"    cluster members: {len(members_df):,}")

    labels_cache = {}
    if LABELS_PATH.exists():
        labels_cache = json.loads(LABELS_PATH.read_text())
    claim_sentence_cache = {}
    if CLAIM_SENT_PATH.exists():
        claim_sentence_cache = json.loads(CLAIM_SENT_PATH.read_text())

    # Expectation metadata (direction + conviction + headline + near_term)
    exp_meta: dict[tuple[str, str], dict] = {}
    today_iso = str(dt.date.today())
    if EXPS_TODAY.exists():
        td = json.loads(EXPS_TODAY.read_text())
        for e in td.get("expectations", []):
            tk = e.get("ticker")
            if tk:
                exp_meta[(today_iso, tk)] = {
                    "headline":    e.get("headline", ""),
                    "direction":   e.get("direction", ""),
                    "conviction":  float(e.get("conviction", 0.5) or 0.5),
                    "near_term":   e.get("near_term_view", ""),
                }
    if EXPS_HISTORY_DIR.is_dir():
        for f in EXPS_HISTORY_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue
            for e in data.get("expectations", []):
                date = e.get("date")
                tk = e.get("ticker")
                if not date or not tk:
                    continue
                exp_meta[(date, tk)] = {
                    "headline":    e.get("headline", ""),
                    "direction":   e.get("direction", ""),
                    "conviction":  float(e.get("conviction", 0.5) or 0.5),
                    "near_term":   e.get("near_term_view", ""),
                }
    print(f"    expectation metadata: {len(exp_meta):,}")

    # ── Attach ─────────────────────────────────────────────────────────────
    attachments = build_attachments(exp_emb_df, event_mat, members_df, exp_meta)
    print(f"  attachments: {len(attachments):,}")

    # ── Classify ───────────────────────────────────────────────────────────
    as_of = attachments["date"].max()
    print(f"  as_of: {as_of}")
    entities, versions, events = classify_lifecycle(attachments, as_of)
    print(f"  entities: {len(entities):,}  (active: {(entities['status'] == 'active').sum()}, "
          f"contradicted: {(entities['status'] == 'contradicted').sum()}, "
          f"retired: {(entities['status'] == 'retired').sum()})")
    print(f"  versions: {len(versions):,}")
    print(f"  events: {len(events):,}")
    if not events.empty:
        for et, n in events["event_type"].value_counts().items():
            print(f"    {et:>14}: {n}")

    # ── Thesis trails ──────────────────────────────────────────────────────
    trails = build_thesis_trails(entities, events, labels_cache, claim_sentence_cache)
    print(f"  thesis trails: {len(trails)} tickers")

    # ── Write ──────────────────────────────────────────────────────────────
    OUT_ENTITIES.parent.mkdir(parents=True, exist_ok=True)
    entities.to_parquet(OUT_ENTITIES, index=False)
    versions.to_parquet(OUT_VERSIONS, index=False)
    events.to_parquet(OUT_EVENTS, index=False)
    print(f"  wrote {OUT_ENTITIES} ({len(entities):,} rows)")
    print(f"  wrote {OUT_VERSIONS} ({len(versions):,} rows)")
    print(f"  wrote {OUT_EVENTS} ({len(events):,} rows)")

    trails_payload = {
        "as_of":  as_of,
        "tickers": trails,
    }
    OUT_TRAILS.write_text(json.dumps(trails_payload, indent=2))
    OUT_TRAILS_SITE.write_text(json.dumps(trails_payload, indent=2))
    print(f"  wrote {OUT_TRAILS} ({len(trails)} tickers)")
    print(f"  wrote {OUT_TRAILS_SITE}")

    # ── Diagnostic ─────────────────────────────────────────────────────────
    print()
    print("  ─── SAMPLE THESIS TRAILS (top 5 by active entities) ───")
    by_active = sorted(trails.items(), key=lambda x: -x[1]["n_active"])[:5]
    for ticker, payload in by_active:
        print(f"  {ticker}  ({payload['n_entities']} entities, {payload['n_active']} active)")
        for ac in payload["active_claims"][:2]:
            label = ac["label"] or ac["stable_cluster_id"][-8:]
            sign = {-1: "↓", 0: "─", 1: "↑"}[ac["direction_sign"]]
            print(f"    {sign}  [{label[:50]}]  conv={ac['last_conviction']:.2f}")


if __name__ == "__main__":
    main()
