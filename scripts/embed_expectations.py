#!/usr/bin/env python3
"""
embed_expectations.py  —  F-005 part 1

Embeds the headline + near_term_view of every (live + historical)
expectation into the same semantic space as events. Output sidecar
parquet keyed by (date, ticker). Idempotent.

Reads:
  topicspace-site/public/actor_expectations.json     (today's live exps)
  topicspace-site/public/expectations_history/*.json (backfilled history)

Writes:
  data/derived/expectation_embeddings.parquet
    columns: date, ticker, embedding (1536-d), model, input_hash, embedded_at

Usage:
  source venv/bin/activate && python scripts/embed_expectations.py
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).parent.parent
SITE_PUBLIC = ROOT.parent / "topicspace-site" / "public"
EXPS_TODAY  = SITE_PUBLIC / "actor_expectations.json"
EXPS_HISTORY_DIR = SITE_PUBLIC / "expectations_history"
OUT_PATH    = ROOT / "data" / "derived" / "expectation_embeddings.parquet"

MODEL = "text-embedding-3-small"
BATCH = 100
MAX_INPUT_CHARS = 4000


def exp_text(e: dict) -> str:
    """Compose the embedding input for an expectation."""
    parts = [(e.get("headline") or "").strip()]
    ntv = (e.get("near_term_view") or "").strip()
    if ntv:
        parts.append(ntv[:1500])
    s = " · ".join(p for p in parts if p)
    return s[:MAX_INPUT_CHARS]


def input_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load_existing() -> pd.DataFrame:
    if not OUT_PATH.exists():
        return pd.DataFrame(columns=["date", "ticker", "embedding", "model", "input_hash", "embedded_at"])
    return pd.read_parquet(OUT_PATH)


def write_existing(df: pd.DataFrame):
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)


def gather_expectations() -> list[dict]:
    """Combine today's live expectations + all per-ticker history files
    into a deduplicated list of {date, ticker, headline, near_term_view, ...}"""
    seen: set[tuple[str, str]] = set()  # (date, ticker)
    out = []

    # Today's live expectations
    today_iso = str(dt.date.today())
    if EXPS_TODAY.exists():
        try:
            today_data = json.loads(EXPS_TODAY.read_text())
            for e in today_data.get("expectations", []):
                date = today_iso
                tk = e.get("ticker")
                if not tk:
                    continue
                key = (date, tk)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "date": date, "ticker": tk,
                    "headline": e.get("headline", ""),
                    "near_term_view": e.get("near_term_view", ""),
                })
        except Exception as e:
            print(f"  ! could not parse {EXPS_TODAY}: {e}")

    # Historical per-ticker files
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
                key = (date, tk)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "date": date, "ticker": tk,
                    "headline": e.get("headline", ""),
                    "near_term_view": e.get("near_term_view", ""),
                })

    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=None,
                    help="cap new embeddings (for testing)")
    args = ap.parse_args()

    existing = load_existing()
    existing_keys = set(zip(existing["date"].astype(str).tolist(),
                            existing["ticker"].tolist()))
    existing_hashes = dict(zip(
        zip(existing["date"].astype(str).tolist(), existing["ticker"].tolist()),
        existing["input_hash"].tolist(),
    ))
    print(f"  cached so far: {len(existing):,}")

    all_exps = gather_expectations()
    print(f"  expectations in input: {len(all_exps):,}")

    to_embed: list[dict] = []
    for e in all_exps:
        text = exp_text(e)
        if not text:
            continue
        h = input_hash(text)
        key = (str(e["date"]), e["ticker"])
        # Skip if already embedded with same input hash
        if key in existing_keys and existing_hashes.get(key) == h:
            continue
        to_embed.append({**e, "text": text, "hash": h})
        if args.max and len(to_embed) >= args.max:
            break

    print(f"  to embed: {len(to_embed):,}")
    if not to_embed:
        print("  nothing to do")
        return

    try:
        from openai import OpenAI
        from dotenv import load_dotenv
        load_dotenv()
        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("OPENAI_API_KEY not set")
        client = OpenAI()
    except ImportError:
        sys.exit("openai package not available")

    now = dt.datetime.now().isoformat(timespec="seconds")
    new_rows: list[dict] = []
    t0 = time.time()

    for i in range(0, len(to_embed), BATCH):
        chunk = to_embed[i : i + BATCH]
        texts = [c["text"] for c in chunk]
        try:
            resp = client.embeddings.create(model=MODEL, input=texts)
            for c, e in zip(chunk, resp.data):
                new_rows.append({
                    "date":        str(c["date"]),
                    "ticker":      c["ticker"],
                    "embedding":   np.array(e.embedding, dtype=np.float32),
                    "model":       MODEL,
                    "input_hash":  c["hash"],
                    "embedded_at": now,
                })
        except Exception as e:
            print(f"  ! batch {i}: {e}")
            time.sleep(1.0)
            continue

    if new_rows:
        if len(existing) > 0:
            # Replace any row with matching (date, ticker, but different hash)
            new_df = pd.DataFrame(new_rows)
            keys_to_drop = set(zip(new_df["date"].astype(str).tolist(),
                                   new_df["ticker"].tolist()))
            existing_keep_mask = ~existing.apply(
                lambda r: (str(r["date"]), r["ticker"]) in keys_to_drop, axis=1
            )
            merged = pd.concat([existing[existing_keep_mask], new_df], ignore_index=True)
        else:
            merged = pd.DataFrame(new_rows)
        write_existing(merged)

    elapsed = time.time() - t0
    print(f"\n  done: {len(new_rows):,} embedded · {elapsed:.0f}s")
    print(f"  wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
