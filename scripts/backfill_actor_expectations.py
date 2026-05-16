#!/usr/bin/env python3
"""
backfill_actor_expectations.py

Generates retrospective forward expectations for every (date, ticker) in the
backtest history, using only data available as of that date. Output is
per-ticker JSON files in topicspace-site/public/expectations_history/.

Why this works: the live generate_actor_expectations.py prompt uses only
structural data (state, NDS, rel, trajectory, peer context, hand-curated
anchors). All of that can be reconstructed for any historical date. The
LLM is told explicitly that this is a retrospective analysis at the given
date so it doesn't fabricate forward-looking news.

Usage:
  source venv/bin/activate && python scripts/backfill_actor_expectations.py
  python scripts/backfill_actor_expectations.py --tickers NVDA,CRM  --max-dates 5
  python scripts/backfill_actor_expectations.py --workers 10
  python scripts/backfill_actor_expectations.py --force   # re-generate even if cached
"""

from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pandas as pd


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ACTORS_JSON = REPO_ROOT.parent / "topicspace-site" / "public" / "actors.json"
HIST_PARQ   = REPO_ROOT / "data" / "derived" / "backtest_history.parquet"
OUT_DIR     = REPO_ROOT.parent / "topicspace-site" / "public" / "expectations_history"

MODEL = "gpt-4o-mini"
MAX_TOKENS = 800
TEMPERATURE = 0.6

# Reuse the live anchors so backfilled expectations engage with the same
# company-specific levers. These don't change over time, so applying today's
# anchors to historical dates is fine.
sys.path.insert(0, str(REPO_ROOT))
from scripts.generate_actor_expectations import (  # noqa: E402
    ACTOR_ANCHORS, compute_field_context,
)

# State → plain read (mirror generate_leaderboard.py)
STATE_READS = {
    "CONFIRMED":        "price confirming narrative",
    "EARLY":            "price starting to follow",
    "REPRICING":        "price lagging narrative",
    "DIVERGENCE":       "story not being paid",
    "NEG_CONFIRMATION": "selloff confirming narrative",
    "DISAGREEMENT":     "price rejecting negative narrative",
    "MACRO":            "moving with tape",
    "PRICE-LED":        "price ahead of story",
    "UNCLEAR":          "no follow-through",
}
READ_OVERRIDES = {"INTC": "price confirming negative story"}


def state_read(ticker: str, state: str) -> str:
    return READ_OVERRIDES.get(ticker) or STATE_READS.get(state, "no clean read")


SYSTEM_PROMPT = textwrap.dedent("""
You generate a RETROSPECTIVE forward expectation for one tracked actor, as of a
specific historical date. The prompt you receive contains ONLY the structural
data available on that date — narrative pressure, narrative dislocation score,
relative return vs benchmark, state classifications, and 30-day trajectory.

CRITICAL: you do not have access to news text. Do not invent specific news
events, earnings results, or product launches. Reason from the structural
state alone, plus the hand-curated anchor block. The forward expectation
should reflect what the system would have surfaced as the 1–6 month outlook
on that date, using the same structural reasoning the live system uses.

Return ONE compact JSON object:
{
  "ticker":           "<TICKER>",
  "headline":         "<6-12 word characterization. Vary structure across days.>",
  "direction":        "<bullish_continuation | bearish_continuation | mixed_rotational | inflection_pending | neutral_macro>",
  "conviction":       <number 0.0-1.0 — your real confidence; do not default to 0.5>,
  "near_term_view":   "<1-2 sentences. The 1-2 month path given the structural picture as of this date.>",
  "fork_conditions":  ["<short>", ...]
}

Output JSON only, no preamble.
""").strip()


# ── Reconstruct historical actor snapshots ─────────────────────────────────

def build_as_of_actors(hist_df, on_date: str, sectors: dict[str, str],
                       narratives: dict[str, str]) -> list[dict]:
    """Return a list of actor dicts as of `on_date`, in the same shape the
    live prompt builder expects."""
    sub = hist_df[hist_df["date"] == on_date]
    out = []
    for _, r in sub.iterrows():
        t = r["ticker"]
        state = r["state"]
        out.append({
            "t":         t,
            "state":     state,
            "narr":      int(r["narr"]),
            "nds":       round(float(r["nds"]), 1),
            "rel":       round(float(r["rel"]), 2),
            "dir":       int(r["direction"]),
            "read":      state_read(t, state),
            "sector":    sectors.get(t, "?"),
            "narrative": narratives.get(t, ""),
        })
    return out


def build_context(ticker: str, on_date: str, actors_today_static: dict[str, dict],
                  hist_df: pd.DataFrame, sectors: dict[str, str],
                  narratives: dict[str, str]) -> Optional[str]:
    """Compose the retrospective context block. Returns None if the actor
    has no row on this date."""
    sub_t = hist_df[(hist_df["ticker"] == ticker) & (hist_df["date"] <= on_date)]
    if sub_t.empty:
        return None
    sub_t = sub_t.sort_values("date").tail(30)
    today_row = sub_t.iloc[-1]
    if today_row["date"] != on_date:
        return None  # no row on this exact date

    sector = sectors.get(ticker, "?")
    narrative = narratives.get(ticker, "")

    # 30-day trajectory ending on on_date
    traj_lines = []
    for row in sub_t.itertuples(index=False):
        traj_lines.append(
            f"  {row.date}  state={row.state:18s} narr={row.narr:>3d}  nds={row.nds:+6.1f}  rel={row.rel:+6.2f}"
        )
    trajectory = "\n".join(traj_lines)

    # Build as-of actors list for field context + peer context
    actors_as_of = build_as_of_actors(hist_df, on_date, sectors, narratives)
    actors_data = {"date": on_date, "actors": actors_as_of}
    field_ctx = compute_field_context(actors_data)

    # Peer context — same-sector actors on this date
    peers = [a for a in actors_as_of if a["sector"] == sector and a["t"] != ticker]
    peer_lines = []
    for p in sorted(peers, key=lambda x: -abs(x.get("nds", 0)))[:8]:
        peer_lines.append(
            f"  {p['t']:5s} state={p['state']:18s} NDS={p['nds']:+6.1f}  rel={p['rel']:+5.1f}%  {p['read']}"
        )
    peer_context = "\n".join(peer_lines) if peer_lines else "  (no peers in this sector)"

    # Prior state + days in state
    if len(sub_t) >= 2:
        prior_state = sub_t.iloc[-2]["state"]
    else:
        prior_state = "(no prior)"

    # Anchors
    if ticker in ACTOR_ANCHORS:
        anchors = ACTOR_ANCHORS[ticker]
    elif narrative:
        anchors = (f"{narrative}. No hand-curated anchors registered for this actor; "
                   f"lean on the trajectory and peer context.")
    else:
        anchors = "(no specific anchors registered for this actor)"

    return textwrap.dedent(f"""
    FIELD CONTEXT (cross-actor patterns visible in the corpus as of {on_date}):
    {field_ctx}

    NOTE: Apply field context only when it fits THIS actor's own data.

    ─────────────────────────────────────────────────────────────────

    ACTOR: {ticker}
    AS OF: {on_date}   <-- THIS IS THE HISTORICAL DATE; reason as if this is "today"
    SECTOR: {sector}
    NARRATIVE: {narrative}

    ACTOR-SPECIFIC ANCHORS (the levers the forecast should engage with):
    {anchors}

    CURRENT STATE: {today_row['state']}
    READ CLASS:    {state_read(ticker, today_row['state'])}
    NDS:           {today_row['nds']:+.1f}
    REL:           {today_row['rel']:+.2f}%
    NARR:          {today_row['narr']}
    PRIOR STATE:   {prior_state}

    30-DAY TRAJECTORY (state, narr, nds, rel — most recent line is "today"):
{trajectory}

    PEER CONTEXT (same sector, top by |NDS|):
{peer_context}
    """).strip()


# ── LLM call (with retry) ───────────────────────────────────────────────────

_print_lock = threading.Lock()


def call_llm(system: str, user: str, client) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    return json.loads(resp.choices[0].message.content)


def generate_one(client, ticker: str, on_date: str, context: str) -> Optional[dict]:
    user_msg = f"Generate the retrospective forward expectation for {ticker} as of {on_date}.\n\nCONTEXT:\n{context}"
    try:
        out = call_llm(SYSTEM_PROMPT, user_msg, client)
        # Normalize
        out["ticker"] = ticker
        out["date"]   = on_date
        # Truncate noisy fields
        for k in ("headline", "near_term_view"):
            if isinstance(out.get(k), str) and len(out[k]) > 400:
                out[k] = out[k][:400]
        if "fork_conditions" not in out:
            out["fork_conditions"] = []
        return out
    except Exception as e:
        with _print_lock:
            print(f"  ! {ticker} {on_date}: {e}")
        return None


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", help="comma-separated ticker list (default: all)")
    ap.add_argument("--max-dates", type=int, default=None,
                    help="only backfill the last N dates per ticker (for testing)")
    ap.add_argument("--workers", type=int, default=8,
                    help="number of concurrent LLM calls (default 8)")
    ap.add_argument("--force", action="store_true",
                    help="re-generate even if a cached entry exists")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not ACTORS_JSON.exists():
        sys.exit(f"Missing {ACTORS_JSON}")
    if not HIST_PARQ.exists():
        sys.exit(f"Missing {HIST_PARQ}")

    # Load OpenAI client
    try:
        from openai import OpenAI
        from dotenv import load_dotenv
        load_dotenv()
        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("OPENAI_API_KEY not set")
        client = OpenAI()
    except ImportError:
        sys.exit("openai package not available")

    actors_today = json.loads(ACTORS_JSON.read_text())["actors"]
    sectors    = {a["t"]: a.get("sector", "?") for a in actors_today}
    narratives = {a["t"]: a.get("narrative", "") for a in actors_today}

    df = pd.read_parquet(HIST_PARQ).copy()
    df = df[df["variant"] == "baseline"].copy()
    df["date"] = df["date"].astype(str).str.slice(0, 10)
    df = df.sort_values(["ticker", "date"])

    all_tickers = sorted(df["ticker"].unique())
    if args.tickers:
        wanted = [t.strip() for t in args.tickers.split(",")]
        tickers = [t for t in all_tickers if t in wanted]
    else:
        tickers = all_tickers
    print(f"  backfill {len(tickers)} tickers from {df['date'].min()} → {df['date'].max()}")

    # Plan all (ticker, date) jobs, skipping cached
    jobs: list[tuple[str, str]] = []
    cached_per_ticker: dict[str, dict] = {}

    for ticker in tickers:
        path = OUT_DIR / f"{ticker}.json"
        existing = {}
        if path.exists() and not args.force:
            try:
                data = json.loads(path.read_text())
                for e in data.get("expectations", []):
                    existing[e["date"]] = e
            except Exception:
                pass
        cached_per_ticker[ticker] = existing

        dates_for_ticker = sorted(df[df["ticker"] == ticker]["date"].unique())
        if args.max_dates:
            dates_for_ticker = dates_for_ticker[-args.max_dates:]
        for d in dates_for_ticker:
            if d not in existing:
                jobs.append((ticker, d))

    total = len(jobs)
    print(f"  {total} (ticker,date) pairs to generate "
          f"({sum(len(v) for v in cached_per_ticker.values())} already cached)")
    if total == 0:
        print("  nothing to do")
        return

    # Run in parallel
    t0 = time.time()
    new_results: list[dict] = []
    completed = 0

    def worker(t_d):
        ticker, on_date = t_d
        ctx = build_context(ticker, on_date, {}, df, sectors, narratives)
        if ctx is None:
            return None
        return generate_one(client, ticker, on_date, ctx)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(worker, j): j for j in jobs}
        for fut in as_completed(futures):
            completed += 1
            result = fut.result()
            if result:
                new_results.append(result)
            if completed % 25 == 0 or completed == total:
                elapsed = time.time() - t0
                rate = completed / max(1, elapsed)
                eta_min = (total - completed) / rate / 60 if rate > 0 else 0
                with _print_lock:
                    print(f"  {completed}/{total}  ({elapsed:.0f}s elapsed · "
                          f"{rate:.1f}/s · ETA {eta_min:.0f}min)")

    # Merge new results into per-ticker files
    by_ticker: dict[str, list[dict]] = {t: [] for t in tickers}
    for t, existing in cached_per_ticker.items():
        for d, e in existing.items():
            by_ticker[t].append(e)
    for r in new_results:
        by_ticker[r["ticker"]].append(r)

    for t, entries in by_ticker.items():
        entries = sorted(entries, key=lambda e: e["date"])
        out_path = OUT_DIR / f"{t}.json"
        out_path.write_text(json.dumps({
            "ticker":       t,
            "n":            len(entries),
            "expectations": entries,
        }, separators=(",", ":")))

    elapsed = time.time() - t0
    print(f"\n  wrote {len(by_ticker)} per-ticker files in {OUT_DIR}")
    print(f"  total elapsed: {elapsed/60:.1f}min  ·  generated {len(new_results)} new entries")


if __name__ == "__main__":
    main()
