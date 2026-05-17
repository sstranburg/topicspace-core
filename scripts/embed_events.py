#!/usr/bin/env python3
"""
embed_events.py

Embeds every event in tech_ecosystem.jsonl into a semantic vector space
using OpenAI text-embedding-3-small. Idempotent — only events without a
cached embedding are sent. Output is a parquet file with one row per
event_id keyed by `event_id`.

Reads:
  data/normalized/tech_ecosystem.jsonl

Writes/updates:
  data/derived/event_embeddings.parquet
    columns: event_id, embedding (list[float]), model, embedded_at

Usage:
  source venv/bin/activate && python scripts/embed_events.py
  python scripts/embed_events.py --batch 100 --max 1000   # cap for testing
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).parent.parent
# Match build_backtest_history.py — use filtered production + backfill so
# the field corpus aligns with narr's corpus exactly.
DEFAULT_SOURCES = [
    ROOT / "data" / "normalized" / "tech_ecosystem_filtered.jsonl",
    ROOT / "data" / "normalized" / "tech_ecosystem_backfill.jsonl",
]
# Fallback if filtered isn't available (e.g. older clones)
LEGACY_SOURCE   = ROOT / "data" / "normalized" / "tech_ecosystem.jsonl"
EMB_PATH        = ROOT / "data" / "derived" / "event_embeddings.parquet"

MODEL = "text-embedding-3-small"
DIM   = 1536
BATCH_SIZE_DEFAULT = 100
MAX_INPUT_CHARS = 4000   # truncate very long texts before embedding


def event_text(rec: dict) -> str:
    """Compose the embedding input for an event."""
    title = (rec.get("title") or "").strip()
    text  = (rec.get("text") or "").strip()
    parts = [title]
    if text and text not in title:
        parts.append(text[:1500])
    s = " · ".join(p for p in parts if p)
    if len(s) > MAX_INPUT_CHARS:
        s = s[:MAX_INPUT_CHARS]
    return s


def load_cached_ids() -> set[str]:
    if not EMB_PATH.exists():
        return set()
    df = pd.read_parquet(EMB_PATH, columns=["event_id"])
    return set(df["event_id"].tolist())


def append_embeddings(rows: list[dict]) -> None:
    if not rows:
        return
    new_df = pd.DataFrame(rows)
    if EMB_PATH.exists():
        old = pd.read_parquet(EMB_PATH)
        new_df = pd.concat([old, new_df], ignore_index=True)
        new_df = new_df.drop_duplicates(subset="event_id", keep="last")
    EMB_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_df.to_parquet(EMB_PATH, index=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=int, default=BATCH_SIZE_DEFAULT,
                    help="number of events per OpenAI call (default 100)")
    ap.add_argument("--max", type=int, default=None,
                    help="cap how many new events to embed this run (testing)")
    args = ap.parse_args()

    # Build list of source files to scan
    sources = [p for p in DEFAULT_SOURCES if p.exists()]
    if not sources and LEGACY_SOURCE.exists():
        sources = [LEGACY_SOURCE]
    if not sources:
        sys.exit(f"No source files found in {DEFAULT_SOURCES[0].parent}")
    print(f"  reading from: {', '.join(p.name for p in sources)}")

    cached = load_cached_ids()
    print(f"  cached so far: {len(cached):,}")

    to_embed: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for src_path in sources:
        with src_path.open() as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                eid = rec.get("event_id")
                if not eid or eid in cached or eid in seen_ids:
                    continue
                seen_ids.add(eid)
                txt = event_text(rec)
                if not txt:
                    continue
                to_embed.append((eid, txt))
                if args.max and len(to_embed) >= args.max:
                    break
        if args.max and len(to_embed) >= args.max:
            break

    print(f"  to embed: {len(to_embed):,}")
    if not to_embed:
        print("  nothing to do")
        return

    # OpenAI client
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
    rows_buffer: list[dict] = []
    BATCH = max(1, args.batch)
    t0 = time.time()
    n_done = 0
    n_failed = 0

    def flush():
        nonlocal rows_buffer
        if rows_buffer:
            append_embeddings(rows_buffer)
            rows_buffer = []

    for i in range(0, len(to_embed), BATCH):
        chunk = to_embed[i : i + BATCH]
        ids   = [c[0] for c in chunk]
        texts = [c[1] for c in chunk]
        try:
            resp = client.embeddings.create(model=MODEL, input=texts)
            for eid, e in zip(ids, resp.data):
                rows_buffer.append({
                    "event_id":   eid,
                    "embedding":  np.array(e.embedding, dtype=np.float32),
                    "model":      MODEL,
                    "embedded_at": now,
                })
            n_done += len(chunk)
        except Exception as e:
            n_failed += len(chunk)
            print(f"  ! batch {i}-{i+len(chunk)} failed: {e}")
            # tiny backoff
            time.sleep(1.0)
            continue

        # Periodically flush to disk (every 1000 events) so partial progress is saved
        if n_done % 1000 < BATCH:
            flush()
            elapsed = time.time() - t0
            rate = n_done / max(1, elapsed)
            eta = (len(to_embed) - n_done) / rate / 60 if rate > 0 else 0
            print(f"  {n_done:,}/{len(to_embed):,}  ({elapsed:.0f}s elapsed · {rate:.0f}/s · ETA {eta:.1f}min)")

    flush()
    elapsed = time.time() - t0
    print(f"\n  done: {n_done:,} embedded · {n_failed} failed · {elapsed/60:.1f}min")
    print(f"  wrote {EMB_PATH}")


if __name__ == "__main__":
    main()
