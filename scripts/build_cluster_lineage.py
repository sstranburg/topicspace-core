#!/usr/bin/env python3
"""
build_cluster_lineage.py  —  F-002

Builds stable theme identities by matching daily cluster centroids across
consecutive days. Produces:

  data/derived/cluster_lineage.parquet
      One row per (date, day_cluster_id). Carries:
        - stable_cluster_id (persistent across days)
        - centroid_hash (for the lineage matcher)
        - n_events, n_actors
        - parent_stable_ids (yesterday's clusters this one came from)
        - lifecycle: born | persisted | drift | merge_target | split_source
                     | split_target | retired
        - drift_from_prior (cosine distance vs prior matched cluster)

  data/derived/cluster_members.parquet
      One row per (date, day_cluster_id, event_id) — full membership.

  data/derived/cluster_actor_membership.parquet
      One row per (date, ticker, stable_cluster_id) where ticker has
      events_in_cluster > 0. Includes flag for "primary cluster of the day."

  data/derived/cluster_events.parquet
      One row per lifecycle event (born / merge / split / retired / large_drift).
      Used by L3 later for the "thesis trail" timeline.

  data/derived/cluster_labels.json
      { stable_cluster_id: { label, last_labeled_at, last_labeled_top_titles } }
      LLM-labeled; cached; only relabeled when membership shifts ≥40% or
      label is missing.

Reads:
  data/normalized/tech_ecosystem_filtered.jsonl + tech_ecosystem_backfill.jsonl
  data/derived/event_embeddings.parquet
  data/derived/backtest_history.parquet  (for the trading-date grid)

Usage:
  source venv/bin/activate && python scripts/build_cluster_lineage.py
  python scripts/build_cluster_lineage.py --tail 30        # last 30 dates only
  python scripts/build_cluster_lineage.py --no-llm-labels  # skip LLM labeling
"""

from __future__ import annotations
import argparse
import json
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


ROOT = Path(__file__).parent.parent
DEFAULT_SOURCES = [
    ROOT / "data" / "normalized" / "tech_ecosystem_filtered.jsonl",
    ROOT / "data" / "normalized" / "tech_ecosystem_backfill.jsonl",
]
LEGACY_SOURCE = ROOT / "data" / "normalized" / "tech_ecosystem.jsonl"
EMB_PATH  = ROOT / "data" / "derived" / "event_embeddings.parquet"
HIST_PATH = ROOT / "data" / "derived" / "backtest_history.parquet"

OUT_LINEAGE  = ROOT / "data" / "derived" / "cluster_lineage.parquet"
OUT_MEMBERS  = ROOT / "data" / "derived" / "cluster_members.parquet"
OUT_AMEMBER  = ROOT / "data" / "derived" / "cluster_actor_membership.parquet"
OUT_EVENTS   = ROOT / "data" / "derived" / "cluster_events.parquet"
OUT_LABELS   = ROOT / "data" / "derived" / "cluster_labels.json"

CLUSTER_WINDOW_DAYS = 30
K_MIN, K_MAX = 8, 25                # adaptive k = clip(n_events // 50, K_MIN, K_MAX)
MATCH_PERSIST_SIM    = 0.85         # ≥ this → clean persistence
MATCH_DRIFT_SIM      = 0.50         # 0.50-0.85 → persist with drift
LARGE_DRIFT_THRESHOLD = 0.30        # drift_from_prior ≥ this → log as event
MEMBERSHIP_RELABEL_THRESHOLD = 0.40 # if member-set churn ≥ this, relabel

DEGENERATE_TEXT_LEN = 30


def l2_normalize(arr: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(arr, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return arr / n


# ── Cheap token labeler (fallback when LLM unavailable) ────────────────────

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")
_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "into", "over",
    "after", "before", "what", "when", "where", "how", "why",
    "company", "stock", "shares", "stocks", "market", "report",
    "news", "update", "today", "more", "less",
}


def top_tokens(titles: list[str], k: int = 3) -> str:
    c: Counter = Counter()
    for t in titles:
        for tok in _TOKEN_RE.findall((t or "").lower()):
            if len(tok) >= 4 and tok not in _STOP:
                c[tok] += 1
    return " / ".join(w for w, _ in c.most_common(k)) if c else ""


# ── LLM labeler ────────────────────────────────────────────────────────────

LLM_LABEL_SYSTEM = (
    "You assign a short label (3-7 words, no punctuation) to a cluster of "
    "tech/finance news headlines. The label should capture the THEME — what "
    "is this cluster about? — not a list of tickers. Examples: 'AI capex "
    "tailwind in semis', 'Agentic software pressures incumbent SaaS', "
    "'Hyperscaler power-deal cycle'. Respond with ONLY the label, no quotes, "
    "no preamble."
)


def llm_label_cluster(titles: list[str], client) -> Optional[str]:
    sample = "\n".join(f"- {t}" for t in titles[:20])
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": LLM_LABEL_SYSTEM},
                {"role": "user",   "content": f"Cluster headlines:\n{sample}"},
            ],
            temperature=0.2,
            max_tokens=30,
        )
        label = resp.choices[0].message.content.strip().strip('"').strip("'")
        return label[:80] if label else None
    except Exception as e:
        print(f"  ! llm label failed: {e}")
        return None


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tail", type=int, default=None,
                    help="only build for the last N trading dates")
    ap.add_argument("--no-llm-labels", action="store_true",
                    help="skip LLM labeling; use TFIDF token labels only")
    args = ap.parse_args()

    sources = [p for p in DEFAULT_SOURCES if p.exists()]
    if not sources and LEGACY_SOURCE.exists():
        sources = [LEGACY_SOURCE]
    if not sources:
        sys.exit(f"No corpus source files found")
    if not EMB_PATH.exists():
        sys.exit(f"Missing {EMB_PATH}")
    if not HIST_PATH.exists():
        sys.exit(f"Missing {HIST_PATH}")

    # ── Load events ────────────────────────────────────────────────────────
    print(f"  loading events from: {', '.join(p.name for p in sources)}")
    seen: set[str] = set()
    rows = []
    for src_path in sources:
        with src_path.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                eid = r.get("event_id")
                if not eid or eid in seen or not r.get("timestamp"):
                    continue
                seen.add(eid)
                title = (r.get("title") or "")[:200]
                text  = (r.get("text") or "")
                combined_len = len(title) + len(text)
                rows.append({
                    "event_id": eid,
                    "date":     r["timestamp"][:10],
                    "title":    title,
                    "actors":   r.get("actors") or [],
                    "degenerate": combined_len < DEGENERATE_TEXT_LEN,
                })
    events_df = pd.DataFrame(rows)
    events_df["date"] = pd.to_datetime(events_df["date"])
    events_df = events_df.sort_values("date").reset_index(drop=True)
    print(f"    {len(events_df):,} events loaded")

    # ── Load embeddings ────────────────────────────────────────────────────
    emb_df = pd.read_parquet(EMB_PATH)
    eid_to_idx = {eid: i for i, eid in enumerate(emb_df["event_id"].tolist())}
    emb_mat = np.stack(emb_df["embedding"].apply(
        lambda x: np.asarray(x, dtype=np.float32)
    ).tolist())
    emb_mat = l2_normalize(emb_mat)
    print(f"    embeddings: {emb_mat.shape}")

    events_df = events_df[events_df["event_id"].isin(eid_to_idx)].copy()
    events_df["emb_idx"] = events_df["event_id"].map(eid_to_idx)
    print(f"    events with embeddings: {len(events_df):,}")

    # ── Trading-date grid ──────────────────────────────────────────────────
    hist = pd.read_parquet(HIST_PATH).copy()
    hist["date"] = pd.to_datetime(hist["date"])
    if "variant" in hist.columns:
        hist = hist[hist["variant"] == hist["variant"].mode().iloc[0]].copy()
    trading_dates = sorted(hist["date"].unique())
    if args.tail:
        trading_dates = trading_dates[-args.tail:]
    print(f"  building lineage over {len(trading_dates)} trading dates")

    # ── Load existing labels cache ────────────────────────────────────────
    if OUT_LABELS.exists():
        try:
            labels_cache = json.loads(OUT_LABELS.read_text())
        except Exception:
            labels_cache = {}
    else:
        labels_cache = {}

    # LLM client (lazy)
    client = None
    if not args.no_llm_labels:
        try:
            from openai import OpenAI
            from dotenv import load_dotenv
            load_dotenv()
            if os.environ.get("OPENAI_API_KEY"):
                client = OpenAI()
        except ImportError:
            print("  (openai not available; using TFIDF labels)")

    # ── Main loop ─────────────────────────────────────────────────────────
    from sklearn.cluster import MiniBatchKMeans

    # Per-day artifacts
    lineage_rows: list[dict] = []
    members_rows: list[dict] = []
    actor_member_rows: list[dict] = []
    event_rows: list[dict] = []   # lifecycle events

    # State carried across days: yesterday's stable_id → (centroid, members_set, n_events)
    prior_clusters: dict[str, dict] = {}

    dates_arr = events_df["date"].values

    for d_idx, d in enumerate(trading_dates):
        d_np   = np.datetime64(d)
        lo     = d_np - np.timedelta64(CLUSTER_WINDOW_DAYS, "D")
        mask   = (dates_arr >= lo) & (dates_arr <= d_np) & (~events_df["degenerate"].values)
        sub    = events_df[mask]
        if len(sub) < K_MIN * 5:
            continue
        sub_emb_idx = sub["emb_idx"].values
        sub_emb = emb_mat[sub_emb_idx]
        n = len(sub)
        k = max(K_MIN, min(K_MAX, n // 50))

        # Cluster
        km = MiniBatchKMeans(n_clusters=k, n_init=3, random_state=42, batch_size=512)
        km.fit(sub_emb)
        labels = km.labels_
        # Note: km.cluster_centers_ are NOT normalized; renormalize for cosine
        centroids = l2_normalize(km.cluster_centers_.astype(np.float32))

        # Per-cluster: member event_ids + member actors + centroid
        today_clusters: dict[int, dict] = {}
        for ci in range(k):
            member_mask = labels == ci
            if not member_mask.any():
                continue
            member_idx_in_sub = np.where(member_mask)[0]
            member_eids = sub.iloc[member_idx_in_sub]["event_id"].tolist()
            member_titles = sub.iloc[member_idx_in_sub]["title"].tolist()
            # Member actors (with counts)
            actor_counter: Counter = Counter()
            for actors in sub.iloc[member_idx_in_sub]["actors"]:
                for a in actors:
                    actor_counter[a] += 1
            today_clusters[ci] = {
                "centroid":     centroids[ci],
                "member_eids":  set(member_eids),
                "member_titles": member_titles,
                "actor_counts": actor_counter,
                "n_events":     int(member_mask.sum()),
                "n_actors":     len(actor_counter),
            }

        # ── Match against yesterday's clusters ───────────────────────────
        # Build similarity matrix between today's centroids and yesterday's
        prior_ids = list(prior_clusters.keys())
        if prior_ids:
            prior_centroids = np.stack([prior_clusters[sid]["centroid"] for sid in prior_ids])
            today_centroids_arr = np.stack([
                today_clusters[ci]["centroid"] for ci in sorted(today_clusters)
            ])
            sims = today_centroids_arr @ prior_centroids.T  # (n_today, n_prior)
        else:
            sims = None

        today_keys = sorted(today_clusters.keys())
        today_stable: dict[int, str] = {}  # day_cluster_id → stable_id
        today_lifecycle: dict[int, dict] = {}  # day_cluster_id → {kind, parents, drift}

        # For each today cluster, find best prior match
        used_prior: set[str] = set()
        if sims is not None:
            # Greedy match in descending similarity
            pairs = []
            for ti, ci in enumerate(today_keys):
                best_pi = int(np.argmax(sims[ti]))
                pairs.append((sims[ti][best_pi], ti, ci, prior_ids[best_pi]))
            pairs.sort(key=lambda x: -x[0])

            # Track which prior clusters get claimed multiple times (= merge)
            prior_claims: dict[str, list[int]] = defaultdict(list)
            for sim, ti, ci, prior_sid in pairs:
                prior_claims[prior_sid].append(ci)

            for sim, ti, ci, prior_sid in pairs:
                if ci in today_stable:
                    continue
                if sim >= MATCH_PERSIST_SIM and prior_sid not in used_prior:
                    today_stable[ci] = prior_sid
                    used_prior.add(prior_sid)
                    today_lifecycle[ci] = {
                        "kind": "persisted", "parents": [prior_sid],
                        "drift": float(1.0 - sim),
                    }
                elif sim >= MATCH_DRIFT_SIM and prior_sid not in used_prior:
                    today_stable[ci] = prior_sid
                    used_prior.add(prior_sid)
                    today_lifecycle[ci] = {
                        "kind": "drift", "parents": [prior_sid],
                        "drift": float(1.0 - sim),
                    }

            # Detect merge: any prior that had multiple today clusters claiming it
            for prior_sid, claimants in prior_claims.items():
                # Only the one we already matched is "primary"; the others are merge_targets
                primary = next((c for c in claimants if today_stable.get(c) == prior_sid), None)
                if primary is None or len(claimants) <= 1:
                    continue
                # Mark this primary as merge_target with multiple parents (from claimants)
                if today_lifecycle[primary]["kind"] in ("persisted", "drift"):
                    parent_ids = []
                    for cc in claimants:
                        ti2 = today_keys.index(cc)
                        # Each claimant's best prior is prior_sid; alternates are next-best
                        # For simplicity record only the shared parent here
                        parent_ids.append(prior_sid)
                    # Already in parents; mark kind
                    today_lifecycle[primary]["kind"] = "merge_target"
                    # The other claimants are "born" (or split-target) — handled below

            # Detect split: a prior that we matched today → check if multiple today clusters
            # had this prior as best match
            for prior_sid in prior_ids:
                claimants = prior_claims.get(prior_sid, [])
                if len(claimants) >= 2:
                    # Mark each claimant beyond the primary as a split_target
                    for cc in claimants:
                        if today_stable.get(cc) == prior_sid:
                            continue
                        # This claimant wanted prior_sid but didn't get it (already used)
                        # Treat as split_target
                        today_lifecycle.setdefault(cc, {
                            "kind": "split_target", "parents": [prior_sid], "drift": None,
                        })

        # Any today cluster still without a stable_id → born
        for ci in today_keys:
            if ci in today_stable:
                continue
            new_sid = f"theme-{uuid.uuid4().hex[:8]}"
            today_stable[ci] = new_sid
            today_lifecycle.setdefault(ci, {"kind": "born", "parents": [], "drift": None})

        # Detect retired: prior clusters not claimed at all
        for prior_sid in prior_ids:
            if prior_sid not in used_prior:
                # No one matched this prior strongly → retired
                event_rows.append({
                    "date":       pd.Timestamp(d).date().isoformat(),
                    "stable_id":  prior_sid,
                    "kind":       "retired",
                    "parents":    [],
                    "drift":      None,
                    "n_events":   prior_clusters[prior_sid]["n_events"],
                    "n_actors":   prior_clusters[prior_sid]["n_actors"],
                })

        # ── Emit lineage + members + actor membership + events ──────────
        d_iso = pd.Timestamp(d).date().isoformat()
        next_state: dict[str, dict] = {}

        for ci in today_keys:
            sid = today_stable[ci]
            tc = today_clusters[ci]
            lc = today_lifecycle[ci]

            lineage_rows.append({
                "date":              d_iso,
                "day_cluster_id":    int(ci),
                "stable_cluster_id": sid,
                "n_events":          tc["n_events"],
                "n_actors":          tc["n_actors"],
                "lifecycle":         lc["kind"],
                "parent_stable_ids": lc["parents"],
                "drift_from_prior":  lc["drift"],
            })

            # Lifecycle event row (for the timeline / thesis trail later)
            if lc["kind"] in ("born", "merge_target", "split_target"):
                event_rows.append({
                    "date":      d_iso,
                    "stable_id": sid,
                    "kind":      lc["kind"],
                    "parents":   lc["parents"],
                    "drift":     lc["drift"],
                    "n_events":  tc["n_events"],
                    "n_actors":  tc["n_actors"],
                })
            elif lc["kind"] == "drift" and lc["drift"] is not None and lc["drift"] >= LARGE_DRIFT_THRESHOLD:
                event_rows.append({
                    "date":      d_iso,
                    "stable_id": sid,
                    "kind":      "large_drift",
                    "parents":   lc["parents"],
                    "drift":     lc["drift"],
                    "n_events":  tc["n_events"],
                    "n_actors":  tc["n_actors"],
                })

            # Member event rows
            for eid in tc["member_eids"]:
                members_rows.append({
                    "date":              d_iso,
                    "day_cluster_id":    int(ci),
                    "stable_cluster_id": sid,
                    "event_id":          eid,
                })

            # Actor membership rows
            for actor, n_ev in tc["actor_counts"].items():
                actor_member_rows.append({
                    "date":              d_iso,
                    "ticker":            actor,
                    "stable_cluster_id": sid,
                    "events_in_cluster": int(n_ev),
                })

            # Carry to next day
            next_state[sid] = {
                "centroid":     tc["centroid"],
                "member_eids":  tc["member_eids"],
                "n_events":     tc["n_events"],
                "n_actors":     tc["n_actors"],
                "titles":       tc["member_titles"],
                "actors":       set(tc["actor_counts"]),
            }

            # Cluster label management
            existing = labels_cache.get(sid)
            need_relabel = False
            if existing is None:
                need_relabel = True
            else:
                # Compute member-set churn
                prior_titles = set(existing.get("last_labeled_top_titles", []))
                cur_titles = set(tc["member_titles"][:20])
                if prior_titles:
                    churn = len(cur_titles.symmetric_difference(prior_titles)) / max(1, len(cur_titles | prior_titles))
                    if churn >= MEMBERSHIP_RELABEL_THRESHOLD:
                        need_relabel = True
                else:
                    need_relabel = True

            if need_relabel:
                token_label = top_tokens(tc["member_titles"], 3)
                if client is not None:
                    llm_label = llm_label_cluster(tc["member_titles"], client)
                    final_label = llm_label or token_label
                else:
                    final_label = token_label
                labels_cache[sid] = {
                    "label":                     final_label,
                    "token_label":               token_label,
                    "last_labeled_at":           d_iso,
                    "last_labeled_top_titles":   tc["member_titles"][:20],
                }

        prior_clusters = next_state

        if (d_idx + 1) % 20 == 0 or d_idx == len(trading_dates) - 1:
            n_alive = len(next_state)
            print(f"  {d_idx+1}/{len(trading_dates)}  alive clusters: {n_alive}  lineage rows so far: {len(lineage_rows):,}")

    # ── Add primary-cluster flag to actor membership ────────────────────
    am_df = pd.DataFrame(actor_member_rows)
    if len(am_df) > 0:
        # Per (date, ticker): the cluster with max events_in_cluster is "primary"
        am_df["rank"] = am_df.groupby(["date", "ticker"])["events_in_cluster"].rank(
            method="first", ascending=False
        )
        am_df["is_primary"] = (am_df["rank"] == 1).astype(int)
        am_df = am_df.drop(columns=["rank"])

    # ── Write outputs ───────────────────────────────────────────────────
    OUT_LINEAGE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(lineage_rows).to_parquet(OUT_LINEAGE, index=False)
    pd.DataFrame(members_rows).to_parquet(OUT_MEMBERS, index=False)
    am_df.to_parquet(OUT_AMEMBER, index=False)
    pd.DataFrame(event_rows).to_parquet(OUT_EVENTS, index=False)
    OUT_LABELS.write_text(json.dumps(labels_cache, indent=2))

    print(f"\n  wrote {OUT_LINEAGE} ({len(lineage_rows):,} rows)")
    print(f"  wrote {OUT_MEMBERS} ({len(members_rows):,} rows)")
    print(f"  wrote {OUT_AMEMBER} ({len(am_df):,} rows)")
    print(f"  wrote {OUT_EVENTS}  ({len(event_rows):,} rows)")
    print(f"  wrote {OUT_LABELS}  ({len(labels_cache):,} cached labels)")

    # ── Summary ────────────────────────────────────────────────────────
    lin = pd.DataFrame(lineage_rows)
    if len(lin) > 0:
        kind_counts = lin["lifecycle"].value_counts().to_dict()
        n_unique_stable = lin["stable_cluster_id"].nunique()
        print(f"\n  ─── LINEAGE SUMMARY ─────────────────────────")
        print(f"  unique stable clusters: {n_unique_stable}")
        for kind, n in sorted(kind_counts.items(), key=lambda x: -x[1]):
            print(f"  {kind:<15} {n:>5}")
        if len(event_rows):
            print(f"\n  lifecycle events: {len(event_rows)}")
            for kind, n in Counter(e["kind"] for e in event_rows).most_common():
                print(f"  {kind:<15} {n:>5}")


if __name__ == "__main__":
    main()
