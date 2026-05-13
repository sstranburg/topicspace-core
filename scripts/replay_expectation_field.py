#!/usr/bin/env python3
"""
replay_expectation_field.py — narrow expectation-field replay backtest.

Tests the original idea directly: not "did the system fire candidates?",
but "if topicspace had been running on day T0, what expectation would it
have held, and how would that expectation have evolved over time?"

For ONE expectation family (default: Q-001 hardware-software gap):
  1. Generate initial expectation E0 at T0 via LLM, with STRUCTURED anchors
  2. Walk forward N trading days
  3. Each day, deterministically update active expectations using only the
     structural anchors (no LLM)
  4. Detect lifecycle events: stable | strengthened | weakened | split | died
  5. On split, make one LLM call to articulate the child expectation
  6. Append a per-day trajectory row for each active expectation

LLM cadence:
  - T0:        1 call (initial expectation with structured anchors)
  - Per split: 1 call (articulate child expectation)
  - Daily:     0 calls (pure structural update)

Outputs:
  data/derived/expectation_replay_history.jsonl    one row per (expectation, day)
  data/derived/expectation_replay_summary.json     aggregates + lineage

Usage:
  python scripts/replay_expectation_field.py
  python scripts/replay_expectation_field.py --t0 2025-11-19 --days 60
  python scripts/replay_expectation_field.py --family Q-001
  python scripts/replay_expectation_field.py --dry-run     # show T0 prompt; no LLM
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REPO_ROOT  = Path(__file__).resolve().parent.parent
SEED_FILE  = REPO_ROOT / "config" / "tracked_questions.yaml"
HIST_PARQ  = REPO_ROOT / "data"   / "derived" / "backtest_history.parquet"
# Per-(family, T0) output paths so multiple replays coexist
def _t0_compact(t0: str) -> str:
    return t0.replace("-", "")
def out_traj_path(family: str, t0: str) -> Path:
    return REPO_ROOT / "data" / "derived" / f"expectation_replay_history_{family}_{_t0_compact(t0)}.jsonl"
def out_summ_path(family: str, t0: str) -> Path:
    return REPO_ROOT / "data" / "derived" / f"expectation_replay_summary_{family}_{_t0_compact(t0)}.json"

# Reuse field-state vocabulary so the replay speaks the same language as live
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import build_question_field_states as bqfs       # noqa: E402
import generate_derived_questions  as gdq        # noqa: E402


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_T0       = "2025-11-19"
DEFAULT_DAYS     = 60
DEFAULT_FAMILY   = "Q-001"

# Lifecycle rule thresholds. Deliberately simple — meant to be inspectable
# and easy to tune, not optimized.
WEAKENING_SHARE        = 0.50    # supporting_share below this → weakened
DEATH_SHARE            = 0.33    # below this for K consecutive days → died
DEATH_CONSECUTIVE_DAYS = 3
STRENGTHENING_DELTA    = 0.10    # rise ≥ this vs 5d MA → strengthened
STABILITY_TOLERANCE    = 0.05    # |delta| ≤ this → stable
SPLIT_MIN_GROUP_SIZE   = 3       # min cohort members per side of split
SPLIT_FINGERPRINT_TTL  = 30      # trading days — don't refire same conceptual split
SPLIT_DEDUP_BY_LABEL   = True    # if True, fingerprint = split-off topic label
                                  # (not class pair). Coarser, but matches how a
                                  # human reviewer thinks: "chip split happened
                                  # already; same chip split tomorrow isn't news"
LOOKBACK_BD            = 5       # business days for state-flip context


MODEL              = "gpt-4o"
T0_MAX_OUTPUT_TOK  = 900
SPLIT_MAX_OUT_TOK  = 600
TEMPERATURE        = 0.2

STATE_TO_CANONICAL_READ = {
    "CONFIRMED":        "price confirming narrative",
    "EARLY":            "price starting to follow",
    "DISAGREEMENT":     "price rejecting negative narrative",
    "DIVERGENCE":       "story not being paid",
    "PRICE-LED":        "price ahead of story",
    "NEG_CONFIRMATION": "selloff confirming narrative",
    "REPRICING":        "price lagging narrative",
    "UNCLEAR":          "no follow-through",
    "MACRO":            "moving with tape",
}

# Map structural read-class → coarse directional bucket. The expectation's
# supporting_cohort is keyed by this coarse direction so daily updates don't
# need to chase exact read-class equivalence.
READ_CLASS_TO_DIRECTION = {
    "bullish_confirming":  "bullish",
    "bullish_early":       "bullish",
    "bullish_rejecting":   "bullish",
    "price_led":           "bullish",
    "bearish_confirming":  "bearish",
    "divergence_unpaid":   "neutral",
    "lagging":             "neutral",
    "no_follow":           "neutral",
    "macro":               "neutral",
}


# ── I/O ──────────────────────────────────────────────────────────────────────

def load_question(family: str) -> dict:
    import yaml
    seeds = yaml.safe_load(SEED_FILE.read_text()) or []
    for s in seeds:
        if s["id"] == family:
            return {
                "question_id":   s["id"],
                "title":         s["title"].strip(),
                "prompt":        s.get("prompt", "").strip(),
                "cohort":        list(s.get("cohort") or s.get("entities", [])),
                "themes":        list(s.get("themes", [])),
            }
    sys.exit(f"unknown family: {family}")


def load_history():
    """Returns (sorted_dates, ticker_states) where:
       - sorted_dates: list of all distinct trading dates ascending
       - ticker_states: dict[ticker] -> dict[date] -> state."""
    import pandas as pd
    df = pd.read_parquet(HIST_PARQ)
    df = df[df["variant"] == "baseline"].copy()
    df["date"] = df["date"].astype(str).str.slice(0, 10)
    df = df.sort_values(["date", "ticker"])

    ticker_states: dict[str, dict[str, str]] = defaultdict(dict)
    for row in df.itertuples(index=False):
        ticker_states[row.ticker][row.date] = row.state

    sorted_dates = sorted(df["date"].unique())
    return sorted_dates, dict(ticker_states)


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def write_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


# ── Field-state-as-of-date helpers ───────────────────────────────────────────

def state_at(ticker_states: dict, ticker: str, target_date: str) -> str | None:
    """Get ticker's state on the most recent date ≤ target_date."""
    series = ticker_states.get(ticker, {})
    if target_date in series:
        return series[target_date]
    # Fall back to nearest prior trading day in this series
    prior = sorted(d for d in series if d <= target_date)
    if not prior:
        return None
    return series[prior[-1]]


def direction_for_ticker(ticker_states: dict, ticker: str, target_date: str) -> str | None:
    """Map ticker's state at target_date to bullish/bearish/neutral, or None
       if absent."""
    s = state_at(ticker_states, ticker, target_date)
    if not s:
        return None
    cls = bqfs.state_to_class(s)
    return READ_CLASS_TO_DIRECTION.get(cls, "neutral")


def cohort_field_snapshot(cohort: list[str], date: str, ticker_states: dict) -> dict:
    """Return a structural snapshot of the cohort at `date`."""
    in_snap: list[str] = []
    by_dir: dict[str, list[str]] = defaultdict(list)
    by_read_class: dict[str, list[str]] = defaultdict(list)
    actor_states: dict[str, str] = {}

    for t in cohort:
        s = state_at(ticker_states, t, date)
        if s is None:
            continue
        in_snap.append(t)
        actor_states[t] = s
        cls = bqfs.state_to_class(s)
        by_read_class[cls].append(t)
        d = READ_CLASS_TO_DIRECTION.get(cls, "neutral")
        by_dir[d].append(t)

    return {
        "as_of":              date,
        "cohort_in_snapshot": in_snap,
        "by_direction":       dict(by_dir),
        "by_read_class":      dict(by_read_class),
        "actor_states":       actor_states,
    }


# ── T0 expectation generation (LLM) ──────────────────────────────────────────

T0_SYSTEM_PROMPT = """You generate the initial topicspace expectation for a tracked research question, at time T0.

You receive: the question's prompt, and a STRUCTURED FIELD SNAPSHOT at T0 (each cohort member's state and coarse direction: bullish, bearish, or neutral).

Your job: produce an initial expectation object that the system will track forward in time. The deterministic replay layer will check this expectation's structural anchors against the field state on every subsequent day, so the anchors must be precise and complete.

Return a JSON object with these exact keys:
{
  "statement":         "1-2 sentences. PREDICTION-FIRST. The first sentence MUST be a declarative forward claim about what will happen next (e.g. 'the hardware/software gap will persist...', 'the divergence will not resolve downward...'). The optional second sentence may add specificity, but never lead with description of the current snapshot.",
  "implied_kind":      "one of: directional_bullish | directional_bearish | split | convergent | divergent",
  "supporting_cohort": { "TICKER": "bullish" | "bearish" | "neutral", ... }    // MUST contain an entry for every cohort member listed in the snapshot
  "confidence":        "high" | "medium" | "low",
  "weakening_conditions_text": "1-2 sentences in plain English",
  "watch_next_text":   "1-2 sentences in plain English"
}

Rules:
- statement must LEAD with the forward claim. Do NOT open with "The current field snapshot suggests…", "The field implies…", or any other description of the present. Open with the prediction itself.
- supporting_cohort must include EVERY ticker from the snapshot.
- The expected direction for each ticker should be the CURRENT direction in the snapshot — your expectation is "this current configuration persists, or shifts in a specific way you describe in the statement."
- If your statement is bullish on hardware, the supporting tickers should mostly be bullish in the snapshot, and the conflicting (bearish) ones should remain or grow bearish.
- Forbidden words: "regime", "we recommend", "buy", "sell", "predict that", "definitely", "certainly".
- Output JSON only.
"""


def _format_snapshot_for_prompt(snap: dict) -> str:
    parts = []
    parts.append(f"FIELD SNAPSHOT at {snap['as_of']}  ({len(snap['cohort_in_snapshot'])} cohort members)")
    for direction in ("bullish", "bearish", "neutral"):
        members = snap["by_direction"].get(direction, [])
        if not members:
            continue
        parts.append(f"  {direction}: {', '.join(sorted(members))}")
    parts.append("")
    parts.append("State detail per actor:")
    for t in sorted(snap["actor_states"]):
        st = snap["actor_states"][t]
        cls = bqfs.state_to_class(st)
        rdl = bqfs.READ_CLASS_LABEL.get(cls, cls)
        d = READ_CLASS_TO_DIRECTION.get(cls, "neutral")
        parts.append(f"  {t:6s} state={st:18s} read_class={rdl:20s} direction={d}")
    return "\n".join(parts)


def call_openai(system: str, user: str, max_tokens: int) -> tuple[dict, dict]:
    from openai import OpenAI
    client = OpenAI()
    t0 = time.time()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=TEMPERATURE,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    elapsed_ms = int((time.time() - t0) * 1000)
    text = resp.choices[0].message.content or "{}"
    parsed = json.loads(text)
    return parsed, {
        "model":             MODEL,
        "prompt_tokens":     getattr(resp.usage, "prompt_tokens", None),
        "completion_tokens": getattr(resp.usage, "completion_tokens", None),
        "latency_ms":        elapsed_ms,
    }


def generate_t0_expectation(question: dict, snap: dict, dry_run: bool) -> dict:
    user_prompt = (
        f"QUESTION\n"
        f"  id:     {question['question_id']}\n"
        f"  title:  {question['title']}\n"
        f"  themes: {', '.join(question['themes'])}\n\n"
        f"PROMPT BODY\n  {question['prompt']}\n\n"
        f"{_format_snapshot_for_prompt(snap)}\n\n"
        f"Generate the initial expectation. Return JSON."
    )
    if dry_run:
        print("─" * 76)
        print("DRY-RUN T0 PROMPT")
        print("─" * 76)
        print(user_prompt)
        return {"_dry_run": True}

    parsed, meta = call_openai(T0_SYSTEM_PROMPT, user_prompt, T0_MAX_OUTPUT_TOK)
    sc = parsed.get("supporting_cohort", {}) or {}
    # Validate: every cohort member in snap must be in supporting_cohort
    missing = set(snap["cohort_in_snapshot"]) - set(sc.keys())
    extra   = set(sc.keys()) - set(snap["cohort_in_snapshot"])
    if missing or extra:
        # Repair: snap them deterministically using snapshot directions
        for t in missing:
            cls = bqfs.state_to_class(snap["actor_states"][t])
            sc[t] = READ_CLASS_TO_DIRECTION.get(cls, "neutral")
        for t in extra:
            sc.pop(t, None)
        parsed["supporting_cohort"] = sc
        parsed["_anchor_repaired"] = True

    eid = f"E-{question['question_id']}-{snap['as_of'].replace('-', '')}-001"
    return {
        "expectation_id":           eid,
        "question_handle":          question["question_id"],
        "parent_expectation_id":    None,
        "born_at":                  snap["as_of"],

        # LLM-produced
        "statement":                parsed.get("statement", "(missing)"),
        "implied_kind":             parsed.get("implied_kind", "directional_bullish"),
        "confidence_initial":       parsed.get("confidence", "medium"),
        "weakening_conditions":     parsed.get("weakening_conditions_text", ""),
        "watch_next":               parsed.get("watch_next_text", ""),

        # Structured anchor — the bridge to deterministic replay
        "supporting_cohort":        dict(parsed["supporting_cohort"]),
        "anchor_repaired":          parsed.get("_anchor_repaired", False),

        "generation_metadata":      meta,
    }


# ── Daily deterministic update ───────────────────────────────────────────────

def update_expectation_today(exp: dict, ticker_states: dict, today: str) -> dict:
    """Pure-function: given an expectation and today's data, compute today's
    structural state. Returns a dict of derived metrics."""
    supporting = exp["supporting_cohort"]
    n_total = len(supporting)
    supporting_actors: list[str] = []
    conflicting_actors: list[str] = []
    neutral_actors:    list[str] = []
    missing_actors:    list[str] = []

    for ticker, expected_dir in supporting.items():
        cur = direction_for_ticker(ticker_states, ticker, today)
        if cur is None:
            missing_actors.append(ticker)
            continue
        if cur == expected_dir:
            supporting_actors.append(ticker)
        elif cur == "neutral" or expected_dir == "neutral":
            neutral_actors.append(ticker)
        else:
            # bullish vs bearish: directly conflicting
            conflicting_actors.append(ticker)

    n_in_snap = n_total - len(missing_actors)
    supporting_share = (
        len(supporting_actors) / n_in_snap if n_in_snap else 0.0
    )
    return {
        "supporting_actors":   sorted(supporting_actors),
        "conflicting_actors":  sorted(conflicting_actors),
        "neutral_actors":      sorted(neutral_actors),
        "missing_actors":      sorted(missing_actors),
        "supporting_share":    round(supporting_share, 3),
        "n_in_snapshot":       n_in_snap,
    }


# ── Lifecycle event detection ────────────────────────────────────────────────

def detect_event(
    exp: dict,
    today_metrics: dict,
    today_snap: dict,
    share_history: deque,
    recent_split_fps: dict[str, str],
    today: str,
    sorted_dates: list[str],
) -> tuple[str, str | None]:
    """Return (event, detail). event ∈ {stable, strengthened, weakened, split, died}.
       Split detection uses the same logic as cluster_split trigger."""
    share = today_metrics["supporting_share"]
    ma_recent = mean(share_history) if share_history else share

    # ── Death (highest priority)
    # Death = supporting_share < DEATH_SHARE for N consecutive days
    if share < DEATH_SHARE:
        consec = 1
        for s in reversed(share_history):
            if s < DEATH_SHARE:
                consec += 1
            else:
                break
        if consec >= DEATH_CONSECUTIVE_DAYS:
            return "died", (
                f"supporting_share {share:.0%} < {DEATH_SHARE:.0%} "
                f"for {consec} consecutive days"
            )

    # ── Split
    # Cluster_split: ≥2 distinct read-classes among supporting cohort, each
    # with ≥SPLIT_MIN_GROUP_SIZE members and direction mismatch.
    cohort = list(exp["supporting_cohort"].keys())
    by_class: dict[str, list[str]] = defaultdict(list)
    for t in cohort:
        st = today_snap["actor_states"].get(t)
        if not st:
            continue
        by_class[bqfs.state_to_class(st)].append(t)
    big = [(cls, m) for cls, m in by_class.items() if len(m) >= SPLIT_MIN_GROUP_SIZE]
    # Look for distinct directional buckets
    dirs_with_big_group = {
        READ_CLASS_TO_DIRECTION.get(cls, "neutral") for cls, _ in big
    }
    if len(big) >= 2 and len(dirs_with_big_group) >= 2:
        big_sorted = sorted(big, key=lambda kv: -len(kv[1]))
        primary = big_sorted[0]
        split_off = big_sorted[1]
        # SEMANTIC fingerprint: primary read-class + split-off topic label.
        # Avoids the membership-churn problem where a "chip split-off" rotates
        # individual actors day-to-day but represents the same conceptual
        # split. Mirrors the fix made in the live trigger system.
        splitoff_label = bqfs.cohort_label(split_off[1])
        fp = (
            splitoff_label
            if SPLIT_DEDUP_BY_LABEL
            else f"{primary[0]}|{split_off[0]}|{splitoff_label}"
        )
        last = recent_split_fps.get(fp)
        if last:
            try:
                days_since = sorted_dates.index(today) - sorted_dates.index(last)
                if days_since < SPLIT_FINGERPRINT_TTL:
                    # Suppress the split — return stable instead
                    return "stable", None
            except ValueError:
                pass
        return "split", (
            f"sub-cohort split detected — primary {primary[0]} ({len(primary[1])}) "
            f"vs split-off {split_off[0]} ({len(split_off[1])}, label={splitoff_label})  [fp={fp}]"
        )

    # ── Weakened
    if share < WEAKENING_SHARE:
        return "weakened", f"supporting_share {share:.0%} < {WEAKENING_SHARE:.0%}"

    # ── Strengthened
    if share - ma_recent >= STRENGTHENING_DELTA and share >= 0.66:
        return "strengthened", (
            f"supporting_share {share:.0%} rose ≥ "
            f"{STRENGTHENING_DELTA:.0%} vs 5d MA ({ma_recent:.0%})"
        )

    return "stable", None


# ── Split-event LLM call ─────────────────────────────────────────────────────

SPLIT_SYSTEM_PROMPT = """You articulate a CHILD expectation that has split off from an existing topicspace expectation.

You receive: the parent expectation, today's field snapshot, and the detected split (which sub-cohort is breaking off from the parent's frame).

Your job: produce the child expectation. The child describes a NEW, NARROWER expectation about the split-off sub-cohort.

Return a JSON object with these keys:
{
  "statement":                "1-2 sentences. What does the field imply about the SPLIT-OFF sub-cohort, distinct from the parent's frame?",
  "supporting_cohort":        { "TICKER": "bullish"|"bearish"|"neutral", ... },     // include every ticker in the split-off sub-cohort
  "weakening_conditions_text":"1-2 sentences",
  "watch_next_text":          "1-2 sentences"
}

Rules:
- supporting_cohort must include every ticker listed in the split-off sub-cohort.
- The child should be specific about WHAT THE SPLIT-OFF GROUP is doing, in a way distinct from the parent's broader claim.
- Forbidden words: "regime", "we recommend", "buy", "sell", "predict that", "definitely", "certainly".
- Output JSON only.
"""


def generate_split_child(parent: dict, today_snap: dict, today: str, splitoff_members: list[str]) -> dict:
    splitoff_dirs = {
        t: READ_CLASS_TO_DIRECTION.get(bqfs.state_to_class(today_snap["actor_states"][t]), "neutral")
        for t in splitoff_members
    }
    user_prompt = (
        f"PARENT EXPECTATION ({parent['expectation_id']})\n"
        f"  statement: {parent['statement']}\n"
        f"  born_at:   {parent['born_at']}\n"
        f"  cohort:    {', '.join(sorted(parent['supporting_cohort'].keys()))}\n\n"
        f"SPLIT EVENT at {today}\n"
        f"  split-off sub-cohort: {', '.join(sorted(splitoff_members))}\n"
        f"  split-off direction map: "
        f"{json.dumps(splitoff_dirs)}\n\n"
        f"Articulate the child expectation for the split-off sub-cohort."
    )
    parsed, meta = call_openai(SPLIT_SYSTEM_PROMPT, user_prompt, SPLIT_MAX_OUT_TOK)

    # Enforce coverage of the split-off set
    sc = parsed.get("supporting_cohort", {}) or {}
    for t in splitoff_members:
        if t not in sc:
            sc[t] = splitoff_dirs[t]
    parsed["supporting_cohort"] = sc

    child_id = f"{parent['expectation_id']}-c{today.replace('-', '')[-4:]}"
    return {
        "expectation_id":        child_id,
        "question_handle":       parent["question_handle"],
        "parent_expectation_id": parent["expectation_id"],
        "born_at":               today,
        "statement":             parsed.get("statement", "(missing)"),
        "implied_kind":          "split_off",
        "confidence_initial":    "medium",
        "weakening_conditions":  parsed.get("weakening_conditions_text", ""),
        "watch_next":            parsed.get("watch_next_text", ""),
        "supporting_cohort":     dict(parsed["supporting_cohort"]),
        "generation_metadata":   meta,
    }


# ── Replay driver ────────────────────────────────────────────────────────────

def replay(question: dict, t0: str, days: int, dry_run: bool):
    sorted_dates, ticker_states = load_history()
    if t0 not in sorted_dates:
        # Find nearest later trading day
        later = [d for d in sorted_dates if d >= t0]
        if not later:
            sys.exit(f"T0 {t0} is past available history")
        t0 = later[0]
        print(f"  T0 snapped to next trading day: {t0}")

    t0_idx = sorted_dates.index(t0)
    replay_dates = sorted_dates[t0_idx : t0_idx + days + 1]
    if not replay_dates:
        sys.exit("empty replay window")
    print(f"  replay window: {replay_dates[0]} → {replay_dates[-1]} "
          f"({len(replay_dates)} trading days)")

    # T0 snapshot + initial expectation
    t0_snap = cohort_field_snapshot(question["cohort"], replay_dates[0], ticker_states)
    print(f"  T0 cohort: {len(t0_snap['cohort_in_snapshot'])} of {len(question['cohort'])} in snapshot")

    e0 = generate_t0_expectation(question, t0_snap, dry_run)
    if dry_run:
        return [], {"_dry_run": True}

    print(f"  T0 expectation: {e0['expectation_id']}")
    print(f"    statement: {e0['statement']}")
    print(f"    kind:      {e0['implied_kind']}    confidence: {e0['confidence_initial']}")
    if e0.get("anchor_repaired"):
        print(f"    (anchor repaired — LLM missed some cohort members)")

    # State held during replay
    active: dict[str, dict] = {e0["expectation_id"]: e0}        # id → expectation object
    share_history: dict[str, deque] = {                          # id → recent supporting_share values
        e0["expectation_id"]: deque(maxlen=LOOKBACK_BD)
    }
    # Per-expectation map of split fingerprint → last fire date, for TTL dedup
    split_fps: dict[str, dict[str, str]] = defaultdict(dict)
    trajectory: list[dict] = []
    lineage: list[dict] = []      # records of birth events
    lineage.append({
        "expectation_id": e0["expectation_id"],
        "parent_id":      None,
        "born_at":        e0["born_at"],
        "kind":           "initial",
        "statement":      e0["statement"],
    })

    for d in replay_dates:
        today_snap = cohort_field_snapshot(question["cohort"], d, ticker_states)
        new_children: list[dict] = []

        for eid, exp in list(active.items()):
            metrics = update_expectation_today(exp, ticker_states, d)
            event, detail = detect_event(
                exp, metrics, today_snap, share_history[eid],
                split_fps[eid], d, sorted_dates,
            )

            # Snapshot row BEFORE applying the event so we capture the moment
            row = {
                "as_of":              d,
                "expectation_id":     eid,
                "question_handle":    exp["question_handle"],
                "parent_expectation_id": exp.get("parent_expectation_id"),
                "born_at":            exp["born_at"],
                "days_alive":         sorted_dates.index(d) - sorted_dates.index(exp["born_at"]),
                "statement":          exp["statement"],
                "implied_kind":       exp["implied_kind"],
                "supporting_share":   metrics["supporting_share"],
                "n_supporting":       len(metrics["supporting_actors"]),
                "n_conflicting":      len(metrics["conflicting_actors"]),
                "n_neutral":          len(metrics["neutral_actors"]),
                "n_missing":          len(metrics["missing_actors"]),
                "supporting_actors":  metrics["supporting_actors"],
                "conflicting_actors": metrics["conflicting_actors"],
                "event":              event,
                "event_detail":       detail,
                "status":             exp.get("status", "active"),
            }
            trajectory.append(row)
            share_history[eid].append(metrics["supporting_share"])

            # Apply lifecycle transitions
            if event == "died":
                exp["status"] = "dead"
                exp["died_at"] = d
                # Will remove from active at end of this iteration
            elif event == "weakened":
                exp["status"] = "weakening"
            elif event == "strengthened":
                exp["status"] = "active"
            elif event == "split":
                # Identify split-off sub-cohort = the SECOND-largest big group
                # (the one that's breaking off from the dominant frame)
                cohort = list(exp["supporting_cohort"].keys())
                by_class: dict[str, list[str]] = defaultdict(list)
                for t in cohort:
                    st = today_snap["actor_states"].get(t)
                    if not st:
                        continue
                    by_class[bqfs.state_to_class(st)].append(t)
                big = sorted(
                    [(cls, m) for cls, m in by_class.items()
                     if len(m) >= SPLIT_MIN_GROUP_SIZE],
                    key=lambda kv: -len(kv[1])
                )
                splitoff_members = big[1][1] if len(big) >= 2 else []
                # Record SEMANTIC fingerprint so we don't refire this same
                # conceptual split for TTL window — even if member set rotates.
                if len(big) >= 2:
                    splitoff_label = bqfs.cohort_label(big[1][1])
                    fp = (
                        splitoff_label
                        if SPLIT_DEDUP_BY_LABEL
                        else f"{big[0][0]}|{big[1][0]}|{splitoff_label}"
                    )
                    split_fps[eid][fp] = d
                if splitoff_members and not dry_run:
                    print(f"    [split] {d}  {eid} → spawning child for {splitoff_members}")
                    child = generate_split_child(exp, today_snap, d, splitoff_members)
                    new_children.append(child)
                    lineage.append({
                        "expectation_id": child["expectation_id"],
                        "parent_id":      eid,
                        "born_at":        d,
                        "kind":           "split_child",
                        "statement":      child["statement"],
                    })
                exp["status"] = "active"   # parent stays alive after split

        # Remove dead expectations
        active = {eid: exp for eid, exp in active.items()
                  if exp.get("status") != "dead"}
        # Add new children
        for child in new_children:
            active[child["expectation_id"]] = child
            share_history[child["expectation_id"]] = deque(maxlen=LOOKBACK_BD)

    summary = summarise(trajectory, lineage, replay_dates)
    return trajectory, lineage, summary


# ── Summary ──────────────────────────────────────────────────────────────────

def summarise(trajectory: list[dict], lineage: list[dict], replay_dates: list[str]) -> dict:
    """Aggregate the replay into the headline metrics."""
    if not trajectory:
        return {"empty": True}

    by_exp: dict[str, list[dict]] = defaultdict(list)
    for r in trajectory:
        by_exp[r["expectation_id"]].append(r)

    per_exp = []
    for eid, rows in by_exp.items():
        rows_sorted = sorted(rows, key=lambda x: x["as_of"])
        events = [r["event"] for r in rows_sorted]
        from collections import Counter
        ev_counts = Counter(events)
        died = "died" in ev_counts
        split = "split" in ev_counts
        weakened = "weakened" in ev_counts
        per_exp.append({
            "expectation_id":   eid,
            "born_at":          rows_sorted[0]["born_at"],
            "first_seen":       rows_sorted[0]["as_of"],
            "last_seen":        rows_sorted[-1]["as_of"],
            "days_observed":    len(rows_sorted),
            "final_status":     "dead" if died else ("weakening" if weakened and not split else "active"),
            "ever_split":       split,
            "ever_weakened":    weakened,
            "ever_strengthened": "strengthened" in ev_counts,
            "ever_died":        died,
            "mean_supporting_share": round(
                mean(r["supporting_share"] for r in rows_sorted), 3),
            "min_supporting_share":  round(
                min(r["supporting_share"] for r in rows_sorted), 3),
            "max_supporting_share":  round(
                max(r["supporting_share"] for r in rows_sorted), 3),
            "event_counts":     dict(ev_counts),
            "statement":        rows_sorted[0]["statement"],
        })

    return {
        "as_of":                datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "replay_start":         replay_dates[0],
        "replay_end":           replay_dates[-1],
        "trading_days":         len(replay_dates),
        "n_expectations_born":  len(by_exp),
        "n_trajectory_rows":    len(trajectory),
        "per_expectation":      per_exp,
        "lineage":              lineage,
    }


def print_summary(summary: dict) -> None:
    print()
    print("=" * 78)
    print("EXPECTATION-FIELD REPLAY SUMMARY")
    print("=" * 78)
    print(f"  window:                {summary['replay_start']} → {summary['replay_end']}  "
          f"({summary['trading_days']} trading days)")
    print(f"  expectations born:     {summary['n_expectations_born']}")
    print(f"  trajectory rows:       {summary['n_trajectory_rows']}")
    print()
    print("PER EXPECTATION")
    print("─" * 78)
    for e in summary["per_expectation"]:
        print(f"\n  {e['expectation_id']}  ({e['final_status']})")
        print(f"    born_at:      {e['born_at']}  ·  observed {e['days_observed']} days")
        print(f"    supporting_share: mean {e['mean_supporting_share']:.0%}  "
              f"min {e['min_supporting_share']:.0%}  max {e['max_supporting_share']:.0%}")
        ev = e["event_counts"]
        ev_str = "  ".join(f"{k}={v}" for k, v in sorted(ev.items(), key=lambda kv: -kv[1]))
        print(f"    events:       {ev_str}")
        st = e["statement"]
        print(f"    statement:    {st[:140]}{'…' if len(st) > 140 else ''}")
    print()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    ap.add_argument("--t0",     default=DEFAULT_T0,
                    help=f"replay start date (default {DEFAULT_T0})")
    ap.add_argument("--days",   type=int, default=DEFAULT_DAYS,
                    help=f"replay window in trading days (default {DEFAULT_DAYS})")
    ap.add_argument("--family", default=DEFAULT_FAMILY,
                    help=f"question family / handle (default {DEFAULT_FAMILY})")
    ap.add_argument("--dry-run", action="store_true",
                    help="show T0 prompt only; do not call the model")
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY") and not args.dry_run:
        sys.exit("missing OPENAI_API_KEY (export, set in .env, or use --dry-run)")

    question = load_question(args.family)
    print(f"replaying expectation field for {args.family} — {question['title']}")

    result = replay(question, args.t0, args.days, args.dry_run)
    if args.dry_run:
        return

    trajectory, lineage, summary = result
    traj_path = out_traj_path(args.family, args.t0)
    summ_path = out_summ_path(args.family, args.t0)
    write_jsonl(trajectory, traj_path)
    write_json(summary,     summ_path)
    print(f"\nwrote {traj_path.relative_to(REPO_ROOT)}  ({len(trajectory)} rows)")
    print(f"wrote {summ_path.relative_to(REPO_ROOT)}")
    print_summary(summary)


if __name__ == "__main__":
    main()
