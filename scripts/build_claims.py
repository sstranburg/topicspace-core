#!/usr/bin/env python3
"""
build_claims.py  —  F-005 part 2

Attaches each expectation to its nearest stable_cluster_id from F-002's
cluster lineage, then computes claim-space statistics per (date, theme).

For each (date, theme) with member expectations:
  - member_actors (with their direction + conviction)
  - direction_distribution
  - dominant_direction
  - alignment_score   (max bucket share)
  - conflict_score    (entropy of direction distribution)
  - avg_conviction
  - crowding_score    (n_members × avg_conviction × alignment)
  - state_distribution (mix of actor states for the theme members)
  - representative_headlines (top 3 by conviction)

Reads:
  data/derived/expectation_embeddings.parquet
  data/derived/event_embeddings.parquet
  data/derived/cluster_members.parquet
  data/derived/cluster_lineage.parquet
  data/derived/cluster_labels.json
  topicspace-site/public/actor_expectations.json
  topicspace-site/public/expectations_history/*.json
  topicspace-site/public/actors.json   (today's state per actor)

Writes:
  data/derived/claims_daily.parquet              (full history if --all)
  topicspace-site/public/claims.json             (latest snapshot)

Usage:
  source venv/bin/activate && python scripts/build_claims.py
  python scripts/build_claims.py --all       # historical too (slower)
"""

import argparse
import datetime as dt
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


ROOT = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"

EVENT_EMB_PATH = ROOT / "data" / "derived" / "event_embeddings.parquet"
EXP_EMB_PATH   = ROOT / "data" / "derived" / "expectation_embeddings.parquet"
MEMBERS_PATH   = ROOT / "data" / "derived" / "cluster_members.parquet"
LINEAGE_PATH   = ROOT / "data" / "derived" / "cluster_lineage.parquet"
LABELS_PATH    = ROOT / "data" / "derived" / "cluster_labels.json"
CLAIM_SENT_CACHE = ROOT / "data" / "derived" / "claim_sentences.json"

EXPS_TODAY  = SITE_PUBLIC / "actor_expectations.json"
EXPS_HISTORY_DIR = SITE_PUBLIC / "expectations_history"
ACTORS_JSON = SITE_PUBLIC / "actors.json"

OUT_PARQ = ROOT / "data" / "derived" / "claims_daily.parquet"
OUT_JSON = SITE_PUBLIC / "claims.json"


# ── Claim sentence generation ─────────────────────────────────────────────

CLAIM_SENTENCE_SYSTEM = (
    "You synthesize a single-sentence FORWARD-LOOKING PREDICTION (12-25 words) "
    "representing the collective view of a cluster of expectations about "
    "specific tickers. This is a CLAIM ABOUT WHAT WILL HAPPEN — NOT a "
    "description of what is currently happening.\n"
    "\n"
    "REQUIRED form:\n"
    "  - Use forward-tense verbs: 'will', 'is likely to', 'should', 'are set to', "
    "    'expect ... to', 'remain under', 'continue to', 'keep'.\n"
    "  - Express a directional thrust over the near-to-medium term (next few "
    "    weeks to a couple of quarters).\n"
    "  - Include the mechanism / driver behind the prediction.\n"
    "\n"
    "FORBIDDEN:\n"
    "  - Present-continuous observational framings like 'are facing', 'is failing', "
    "    'are struggling', 'is driving' as the main verb. These describe state, "
    "    not prediction.\n"
    "  - Hedging adverbs ('perhaps', 'might', 'could maybe').\n"
    "  - Listing tickers in the sentence.\n"
    "  - Generic phrases like 'investment strategies', 'market dynamics', "
    "    'sector pressures'.\n"
    "\n"
    "Target style (note the forward-tense verbs):\n"
    "  - 'AI-linked growth names will remain under price pressure as the market "
    "    keeps re-pricing them lower against narrative strength.'\n"
    "  - 'Custom-silicon vendors should keep absorbing pressure on merchant-GPU "
    "    pricing without confirmation from buyers.'\n"
    "  - 'Data-center power demand will continue to anchor nuclear and gas "
    "    operators while utility multiples lag the build-out cycle.'\n"
    "  - 'Semiconductor multiples are likely to compress further as AI capex "
    "    growth fails to broaden beyond the top hyperscalers.'\n"
    "\n"
    "Return ONLY the sentence, no quotes, no preamble."
)


def member_hash(member_tickers: list[str], dominant_direction: str) -> str:
    import hashlib
    s = "|".join(sorted(member_tickers)) + "::" + dominant_direction
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def gen_claim_sentence(
    members: list[dict],
    dominant_direction: str,
    label: str,
    client,
) -> Optional[str]:
    """One-shot LLM call. members is a list of {ticker, direction, conviction, headline}."""
    if client is None or not members:
        return None
    top = sorted(members, key=lambda m: -m["conviction"])[:5]
    bullet_lines = []
    for m in top:
        h = (m.get("headline") or "")[:120]
        d = m.get("direction", "").replace("_", " ")
        c = m.get("conviction", 0.5)
        bullet_lines.append(f"- {m['ticker']} ({d}, {c:.2f}): \"{h}\"")
    user = (
        f"Topical label: {label}\n"
        f"Dominant direction: {dominant_direction}\n"
        f"Top member expectations:\n" + "\n".join(bullet_lines)
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CLAIM_SENTENCE_SYSTEM},
                {"role": "user",   "content": user},
            ],
            temperature=0.4,
            max_tokens=80,
        )
        text = resp.choices[0].message.content.strip().strip('"').strip("'")
        return text[:280] if text else None
    except Exception as e:
        print(f"  ! claim sentence failed: {e}")
        return None

# Direction normalization
def direction_sign(d: str) -> int:
    if not d:
        return 0
    s = d.lower()
    if "bull" in s:
        return +1
    if "bear" in s:
        return -1
    return 0


def alignment_and_conflict(signs: list[int]) -> tuple[float, float, str]:
    """Returns (alignment, conflict, dominant_direction)."""
    if not signs:
        return 0.0, 0.0, "neutral"
    c = Counter(signs)
    total = len(signs)
    max_bucket = max(c.values())
    alignment = max_bucket / total
    # Entropy
    conflict = 0.0
    for n in c.values():
        p = n / total
        if p > 0:
            conflict -= p * math.log2(p)
    # Normalize entropy to [0, 1] given 3 buckets max
    conflict /= math.log2(3) if conflict > 0 else 1
    dominant_sign = max(c.items(), key=lambda x: x[1])[0]
    dom = {1: "bullish", -1: "bearish", 0: "mixed"}[dominant_sign]
    return alignment, conflict, dom


def l2_normalize(arr: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(arr, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return arr / n


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true",
                    help="build claims for every date in the history (default: latest only)")
    args = ap.parse_args()

    # Load all the artifacts
    print("  loading artifacts…")
    if not EXP_EMB_PATH.exists():
        sys.exit(f"Missing {EXP_EMB_PATH}")
    if not MEMBERS_PATH.exists():
        sys.exit(f"Missing {MEMBERS_PATH}")
    if not LINEAGE_PATH.exists():
        sys.exit(f"Missing {LINEAGE_PATH}")

    exp_emb_df = pd.read_parquet(EXP_EMB_PATH)
    exp_emb_df["date"] = pd.to_datetime(exp_emb_df["date"])
    print(f"    expectation embeddings: {len(exp_emb_df):,}")

    event_emb_df = pd.read_parquet(EVENT_EMB_PATH)
    eid_to_idx = {eid: i for i, eid in enumerate(event_emb_df["event_id"].tolist())}
    event_mat = np.stack(event_emb_df["embedding"].apply(
        lambda x: np.asarray(x, dtype=np.float32)
    ).tolist())
    event_mat = l2_normalize(event_mat)
    print(f"    event embeddings: {event_mat.shape}")

    members_df = pd.read_parquet(MEMBERS_PATH)
    members_df["date"] = pd.to_datetime(members_df["date"])
    print(f"    cluster members: {len(members_df):,}")

    lineage_df = pd.read_parquet(LINEAGE_PATH)
    lineage_df["date"] = pd.to_datetime(lineage_df["date"])

    # Build a (date_iso, stable_cluster_id) → lifecycle lookup so each theme
    # can be tagged with its F-002 lineage event on the as-of date.
    lineage_lookup: dict[tuple[str, str], str] = {}
    for _, lrow in lineage_df.iterrows():
        d_iso = pd.Timestamp(lrow["date"]).date().isoformat()
        lineage_lookup[(d_iso, lrow["stable_cluster_id"])] = lrow["lifecycle"]

    labels_cache = {}
    if LABELS_PATH.exists():
        labels_cache = json.loads(LABELS_PATH.read_text())

    # Claim sentence cache — keyed by (stable_cluster_id, member_hash)
    claim_sentence_cache: dict[str, dict] = {}
    if CLAIM_SENT_CACHE.exists():
        try:
            claim_sentence_cache = json.loads(CLAIM_SENT_CACHE.read_text())
        except Exception:
            pass

    # Lazy OpenAI client for claim sentences
    llm_client = None
    try:
        from openai import OpenAI
        from dotenv import load_dotenv
        load_dotenv()
        if os.environ.get("OPENAI_API_KEY"):
            llm_client = OpenAI()
    except ImportError:
        pass

    # Load expectation metadata for direction + conviction + state lookup
    exp_meta: dict[tuple[str, str], dict] = {}  # (date_iso, ticker) -> meta

    # Today's
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
    # Historical
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

    # Per-actor state today (for state_distribution on latest)
    actor_state_today: dict[str, str] = {}
    if ACTORS_JSON.exists():
        ad = json.loads(ACTORS_JSON.read_text())
        for a in ad.get("actors", []):
            tk = a.get("t")
            if tk:
                actor_state_today[tk] = a.get("state", "")

    # Pre-build event_id → emb_idx + per (date, day_cluster) member event_ids
    members_df["emb_idx"] = members_df["event_id"].map(eid_to_idx)
    members_df = members_df.dropna(subset=["emb_idx"]).copy()
    members_df["emb_idx"] = members_df["emb_idx"].astype(int)

    # Determine dates to process — only dates with BOTH expectations and clusters
    exp_dates = set(exp_emb_df["date"].unique())
    mem_dates = set(members_df["date"].unique())
    valid_dates = sorted(exp_dates & mem_dates)
    if args.all:
        target_dates = valid_dates
    else:
        target_dates = [valid_dates[-1]] if valid_dates else []
    print(f"  processing {len(target_dates)} date(s) "
          f"(exp dates: {len(exp_dates)}, member dates: {len(mem_dates)}, "
          f"intersect: {len(valid_dates)})")
    if not target_dates:
        sys.exit("No dates with both expectations and cluster members")

    # ── Build claim rows ────────────────────────────────────────────────────
    out_rows: list[dict] = []
    latest_payload = None

    for d in target_dates:
        # Get expectations for this date
        exps_d = exp_emb_df[exp_emb_df["date"] == d]
        if len(exps_d) == 0:
            continue

        # Build day_cluster centroids from members
        members_d = members_df[members_df["date"] == d]
        if len(members_d) == 0:
            # No clusters that day; skip
            continue

        day_clusters: dict[int, dict] = {}
        for cluster_id, group in members_d.groupby("day_cluster_id"):
            emb_idx_arr = group["emb_idx"].values
            stable_id = group["stable_cluster_id"].iloc[0]
            centroid = l2_normalize(event_mat[emb_idx_arr].mean(axis=0, keepdims=True))[0]
            day_clusters[int(cluster_id)] = {
                "stable_id": stable_id,
                "centroid":  centroid,
                "n_events":  len(group),
            }

        # Build matrix of centroids for fast matching
        cluster_keys = sorted(day_clusters.keys())
        if not cluster_keys:
            continue
        centroid_mat = np.stack([day_clusters[k]["centroid"] for k in cluster_keys])

        # Attach each expectation to nearest cluster
        exp_emb_mat = np.stack(exps_d["embedding"].apply(
            lambda x: np.asarray(x, dtype=np.float32)
        ).tolist())
        exp_emb_mat = l2_normalize(exp_emb_mat)
        sims = exp_emb_mat @ centroid_mat.T  # (n_exps, n_clusters)
        best_clusters = sims.argmax(axis=1)
        best_sims = sims.max(axis=1)

        # Aggregate per stable_cluster_id
        d_iso = pd.Timestamp(d).date().isoformat()
        per_theme: dict[str, dict] = defaultdict(lambda: {
            "members": [],   # list of (ticker, direction, conviction, headline, sim)
        })
        for i, (_, row) in enumerate(exps_d.iterrows()):
            ck = cluster_keys[int(best_clusters[i])]
            stable_id = day_clusters[ck]["stable_id"]
            tk = row["ticker"]
            meta = exp_meta.get((d_iso, tk), {})
            per_theme[stable_id]["members"].append({
                "ticker":     tk,
                "direction":  meta.get("direction", ""),
                "conviction": meta.get("conviction", 0.5),
                "headline":   meta.get("headline", ""),
                "sim":        float(best_sims[i]),
            })

        # Build claim rows
        for stable_id, info in per_theme.items():
            members = info["members"]
            signs = [direction_sign(m["direction"]) for m in members]
            alignment, conflict, dominant = alignment_and_conflict(signs)
            avg_conv = float(np.mean([m["conviction"] for m in members]))
            crowding = len(members) * avg_conv * alignment

            # State distribution (for latest date only)
            state_dist = Counter()
            if d_iso == today_iso or args.all is False:
                for m in members:
                    s = actor_state_today.get(m["ticker"], "")
                    if s:
                        state_dist[s] += 1

            # Top representative headlines (by conviction)
            top_members = sorted(members, key=lambda x: -x["conviction"])[:3]
            rep_headlines = [
                {"ticker": m["ticker"], "direction": m["direction"],
                 "conviction": m["conviction"], "headline": m["headline"][:140]}
                for m in top_members
            ]

            label = labels_cache.get(stable_id, {}).get("label", "")

            # Claim sentence — generated/cached by (stable_id, member_hash)
            member_tickers_sorted = sorted({m["ticker"] for m in members})
            mh = member_hash(member_tickers_sorted, dominant)
            cache_key = f"{stable_id}::{mh}"
            existing = claim_sentence_cache.get(cache_key)
            if existing and existing.get("sentence"):
                claim_sentence = existing["sentence"]
            else:
                claim_sentence = gen_claim_sentence(
                    members, dominant, label, llm_client
                )
                if claim_sentence:
                    claim_sentence_cache[cache_key] = {
                        "sentence":           claim_sentence,
                        "stable_cluster_id":  stable_id,
                        "member_hash":        mh,
                        "members":            member_tickers_sorted,
                        "dominant_direction": dominant,
                        "first_seen_date":    d_iso,
                    }

            # Lineage event on this date from F-002 (persisted / merge_target /
            # split_target / born / drift). Tells the reader whether this theme
            # is a fresh formation or a continuing one.
            lifecycle_event = lineage_lookup.get((d_iso, stable_id), "")

            out_rows.append({
                "date":                d_iso,
                "stable_cluster_id":   stable_id,
                "label":                label,
                "claim_sentence":       claim_sentence or "",
                "lifecycle_event":      lifecycle_event,
                "n_members":            len(members),
                "member_tickers":       member_tickers_sorted,
                "avg_conviction":       round(avg_conv, 3),
                "alignment_score":      round(alignment, 3),
                "conflict_score":       round(conflict, 3),
                "dominant_direction":   dominant,
                "crowding_score":       round(crowding, 3),
                "direction_dist":       {str(k): v for k, v in dict(Counter(signs)).items()},
                "state_dist":           dict(state_dist),
                "rep_headlines":        rep_headlines,
            })

        # Build latest payload (compact JSON for the site)
        if d == target_dates[-1]:
            latest_payload = {
                "as_of": d_iso,
                "themes": sorted(
                    [{
                        "stable_cluster_id":   r["stable_cluster_id"],
                        "label":                r["label"],
                        "claim_sentence":       r["claim_sentence"],
                        "lifecycle_event":      r["lifecycle_event"],
                        "n_members":            r["n_members"],
                        "member_tickers":       r["member_tickers"],
                        "avg_conviction":       r["avg_conviction"],
                        "alignment_score":      r["alignment_score"],
                        "conflict_score":       r["conflict_score"],
                        "dominant_direction":   r["dominant_direction"],
                        "crowding_score":       r["crowding_score"],
                        "direction_dist": {
                            "bullish": r["direction_dist"].get("1", 0),
                            "bearish": r["direction_dist"].get("-1", 0),
                            "neutral": r["direction_dist"].get("0", 0),
                        },
                        "state_dist":           r["state_dist"],
                        "rep_headlines":        r["rep_headlines"],
                    } for r in [r for r in out_rows if r["date"] == d_iso]],
                    key=lambda x: -x["crowding_score"],
                ),
            }

    # ── Write outputs ───────────────────────────────────────────────────────
    if out_rows:
        OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(out_rows)
        if args.all:
            df.to_parquet(OUT_PARQ, index=False)
            print(f"\n  wrote {OUT_PARQ} ({len(df):,} rows)")
        else:
            # Latest only — overwrite a "latest_only" parquet for diagnostic
            df.to_parquet(OUT_PARQ.with_suffix(".latest.parquet"), index=False)
            print(f"\n  wrote {OUT_PARQ.with_suffix('.latest.parquet')} ({len(df):,} rows)")

    if latest_payload:
        OUT_JSON.write_text(json.dumps(latest_payload, indent=2))
        print(f"  wrote {OUT_JSON} ({len(latest_payload['themes'])} themes @ {latest_payload['as_of']})")

    # Persist claim sentence cache
    CLAIM_SENT_CACHE.write_text(json.dumps(claim_sentence_cache, indent=2))
    print(f"  wrote {CLAIM_SENT_CACHE} ({len(claim_sentence_cache)} cached sentences)")

    if latest_payload:
        print()
        print(f"  ─── TOP THEMES BY CROWDING @ {latest_payload['as_of']} ─────────────")
        for t in latest_payload["themes"][:10]:
            tickers = ", ".join(t["member_tickers"][:5])
            extra = f" (+{len(t['member_tickers'])-5})" if len(t["member_tickers"]) > 5 else ""
            print(f"  [{t['n_members']:>2}m] {t['label'][:60]:<60} {t['dominant_direction']:<8} {tickers}{extra}")
            cs = t.get("claim_sentence", "")
            if cs:
                print(f"        ↳ {cs[:120]}")


if __name__ == "__main__":
    main()
