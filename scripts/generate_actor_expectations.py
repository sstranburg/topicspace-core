"""
Generate non-deterministic forward expectations per actor.

Pilot mode runs on a small set of tickers to test prompt quality before
scaling to all actors. For each ticker:
  - Load current state from actors.json
  - Build a 30-day state-trajectory snippet from backtest_history.parquet
  - Add peer context (other actors in same sector and their states)
  - Call the LLM with an anti-house-style prompt
  - Write the structured expectation to JSON

Usage:
  python scripts/generate_actor_expectations.py --pilot
  python scripts/generate_actor_expectations.py --tickers NVDA,CRM,ANET
"""

from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys
import textwrap
from typing import Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DERIVED   = REPO_ROOT / "data" / "derived"
ACTORS_JSON = REPO_ROOT.parent / "topicspace-site" / "public" / "actors.json"
HIST_PARQ   = DERIVED / "backtest_history.parquet"
OUT_PATH    = DERIVED / "actor_expectations.json"

PILOT_TICKERS = ["NVDA", "CRM", "ANET", "MU", "VRT", "CEG"]

MODEL = "gpt-4o-2024-08-06"
MAX_TOKENS = 1500

# Per-actor anchors — hand-curated 1-3 sentence blocks naming the company-specific
# items the LLM should engage with. Prevents the model from falling back on
# cluster-level theses when same-sector peers look similar on the surface.
ACTOR_ANCHORS: dict[str, str] = {
    "NVDA": "Blackwell ramp economics and pricing power vs custom silicon (TPU, Trainium, MTIA). "
            "Hyperscaler capex discipline. China data-center revenue exposure under export controls.",
    "CRM":  "Agentforce monetization curve (is it adding to seat economics or cannibalizing them). "
            "Competitive pressure from agent-native platforms (OpenAI Atlas, Anthropic agents, vertical SaaS rivals). "
            "Slack/MuleSoft cross-sell vs incremental AI capex.",
    "ANET": "Hyperscaler AI networking spend share (vs Broadcom Tomahawk-based whitebox alternatives). "
            "400G/800G/1.6T cycle timing. Customer concentration in Microsoft and Meta.",
    "MU":   "HBM3e/HBM4 supply tightness and ASP trajectory. "
            "Memory cycle inflection vs lagging consumer/PC DRAM. "
            "Capex discipline and inventory normalization.",
    "VRT":  "Liquid-cooling backlog conversion. "
            "Datacenter power equipment supply (switchgear, UPS) demand pull vs lead-time normalization. "
            "AI-vs-traditional data-center mix.",
    "CEG":  "Hyperscaler nuclear PPA pipeline (Three Mile Island restart, Microsoft offtake, new deals). "
            "Capacity-market price floors. Regulatory clearance pace for behind-the-meter deals.",

    "MSFT": "Copilot enterprise adoption velocity and revenue contribution. "
            "OpenAI commercial relationship economics (revenue share, capacity priority). "
            "Azure AI capacity vs compute supply. Magnitude of AI capex relative to free cash flow.",
    "GOOGL":"AI Overviews / Gemini erosion-or-defense of core search ad revenue. "
            "TPU competitive economics vs NVDA. Waymo geographic and unit-economics ramp. "
            "DOJ remedies in the search antitrust case.",
    "AMZN": "Trainium/Inferentia adoption inside AWS (cost-per-token shift away from H100). "
            "Anthropic strategic relationship. AWS growth reacceleration vs structural deceleration. "
            "Retail margin trajectory. Kuiper satellite capex.",
    "META": "Reality Labs sustained losses against ad-business cash generation. "
            "Llama open-source strategy as moat vs cost center. MTIA custom silicon ramp. "
            "Threads / WhatsApp monetization. Ad attribution recovery post-ATT.",
    "ORCL": "OCI growth rate vs hyperscaler trio. Stargate JV with OpenAI (datacenter buildout commitments). "
            "Cerner healthcare integration tail. RPO bookings translation into revenue.",
}

SYSTEM_PROMPT = textwrap.dedent("""
You generate a non-deterministic FORWARD EXPECTATION for one tracked actor (ticker).
The expectation is a forward-looking analytical claim: what is likely to happen next
for this actor, why, and what conditions would change the path.

You receive a structured context block containing:
  - FIELD CONTEXT: the cross-actor rotation patterns and structural conditions
    currently visible in the broader corpus. Use these as anchors when they bear
    on this actor; ignore them when they do not.
  - ACTOR-SPECIFIC CONTEXT: current behavior state, 30-day state and
    narrative-score trajectory, conviction signals, peer context, and narrative tag.

Return ONE JSON object with this exact schema:
{
  "ticker":           "<TICKER>",
  "headline":         "<6-12 word characterization specific to THIS actor — not a label
                       restatement. Vary structure across writeups: do NOT default to
                       'X amid Y' or 'X awaiting Y' patterns.>",
  "direction":        "<one of: bullish_continuation | bearish_continuation | mixed_rotational | inflection_pending | neutral_macro>",
  "conviction":       <number 0.0-1.0 — your real confidence; do not default to 0.5>,
  "near_term_view":   "<1-3 sentences. The 1-2 month path. Reference THIS actor's specific
                       trajectory, not generic patterns. Lead with what is most useful
                       — not always the same structural opener.>",
  "medium_term_view": "<1-3 sentences. The 3-6 month horizon. Can be brief or even
                       skipped if there is no meaningful medium-term fork.>",
  "fork_conditions":  ["<specific event, threshold, or catalyst>", ...],
  "asymmetric_risk":  {
    "bull": "<the under-priced bull scenario, specific to this actor>",
    "bear": "<the under-priced bear scenario, specific to this actor>"
  },
  "themes":           ["<short theme tag>", ...],
  "horizon":          "<choose based on when the fork resolves — vary across actors. Use
                       '2-4 weeks' for imminent catalysts, '1-3 months' for near-term
                       forks, '3-6 months' for slower setups, '6-12 months' for cycle
                       resets. Do NOT default to '1-3 months' or '3-6 months' habit.>",
  "watching":         ["<specific data point or event to watch next>", ...]
}

CRITICAL RULES (these are anti-generic guardrails):

1. SPECIFICITY: every field must be specific to this actor. If the writeup would still
   be true with the ticker swapped, you have failed. Use the actor's narrative, sector
   peers, trajectory, the FIELD CONTEXT, and especially the ACTOR-SPECIFIC ANCHORS in
   the prose.

2. ANCHOR GROUNDING: the writeup MUST engage with at least one of the actor-specific
   anchors provided in the context. The anchors are the company-specific items the
   forecast hinges on. A writeup that ignores them is failing the specificity rule
   no matter how detailed the rest sounds.

3. FAITHFULNESS OVER FIELD CONTEXT: the field context describes patterns across the
   corpus. Do NOT apply a field-level pattern that contradicts this actor's own data.
   If the field says "narrative is strong but price-flat across many names" but this
   actor's NDS is negative or its state is MACRO/UNCLEAR, the field pattern does not
   apply to this actor. In that case, say so explicitly — the differentiator IS that
   this actor sits outside the dominant pattern. Trust the actor's numbers over the
   corpus mood.

4. DO NOT RESTATE THE READ CLASS as the prediction. The read tells you the current
   behavior; the expectation must describe what comes NEXT and WHY.

5. USE FIELD CONTEXT when it genuinely explains this actor. If field context says
   hardware has bifurcated and this actor is one of the names being rotated away from,
   that is the central story — not a peripheral one. But always check that the
   pattern fits before importing it.

6. NAMED RISKS, NOT FILLERS: asymmetric risks must be concretely named.
   Bad: "earnings could surprise either way"
   Good for NVDA: "Blackwell ramp underdelivers / hyperscaler capex prints below
   consensus"
   Good for CRM: "agentforce monetization fails / OpenAI Atlas browser cannibalizes
   workflow software"

7. FORBIDDEN PHRASES: "potential catalyst", "remains to be seen", "market sentiment",
   "investor focus", "could move higher/lower", "watch for developments", "key level".

8. FORBIDDEN OPENERS (sentence starts — pick something else):
   - "Over the next 3-6 months..."
   - "Over the next 1-3 months..."
   - "Over the next [N] months..."
   - "If [TICKER] can..."
   - "[TICKER] is likely to..."
   - "Looking ahead..."
   - "In the near term..."
   - "Despite..." as a stock opener
   Vary your sentence openers. The asymmetric risk, the fork condition, or the most
   counter-intuitive observation is often a better lead than the most-likely path.

9. CONVICTION RANGE: be willing to write 0.2 (low) or 0.8 (high). 0.5 means you
   genuinely cannot lean. Do not default-lazy to 0.5.

10. HORIZON: choose based on when the fork resolves, not as a habit. An actor with
    an imminent earnings print is a 2-4 week story; a slow capex cycle is a 6-12 month
    story. Vary the horizon to match.

11. NO MAGNITUDE INVENTION: do not invent specific price targets or percentage moves.
    Speak in direction, conviction, and conditions, not numbers you do not have.

12. HEADLINE VARIETY: do not write every headline as "X amid Y" or "X awaiting Y".
    Try declarative claims, contrasts, or named patterns. A good headline is a label
    you would actually use to describe this actor in conversation.

Output JSON only, no preamble.
""").strip()


def compute_field_context(actors_data: dict) -> str:
    """Auto-generate 2–3 sentences describing dominant rotation patterns and structural
    conditions across the corpus. Deterministic — no LLM."""
    import collections as _c
    actors = actors_data["actors"]
    by_sector: dict[str, list] = _c.defaultdict(list)
    for a in actors:
        by_sector[a.get("sector", "?")].append(a)

    lines: list[str] = []

    # 1) Hardware-complex rotation: commodity HW (memory/CPU/server) leading vs
    #    AI-infrastructure narrative names lagging. This is the dominant move
    #    in the current corpus and matters for every hardware-adjacent actor.
    hw_leaders = [
        a for a in actors
        if a.get("sector", "") in ("Semiconductors", "AI Infrastructure")
        and a.get("rel", 0) > 10
    ]
    ai_infra_laggards = [
        a for a in actors
        if a.get("sector", "") == "AI Infrastructure"
        and a.get("nds", 0) > 30
        and a.get("rel", 0) < -5
    ]
    if len(hw_leaders) >= 4 and len(ai_infra_laggards) >= 2:
        lead_names = ", ".join(a["t"] for a in sorted(hw_leaders, key=lambda x: -x.get("rel", 0))[:5])
        lag_names  = ", ".join(a["t"] for a in sorted(ai_infra_laggards, key=lambda x: -x.get("nds", 0))[:4])
        lines.append(
            f"Hardware-complex leadership has rotated to commodity names ({lead_names} leading on price), "
            f"while AI-infrastructure narrative leaders ({lag_names}) sit narrative-positive but price-negative — "
            f"the rotation away from the original AI-poster cohort is the dominant hardware move."
        )

    # 2) Cross-sector "story not being paid" divergence cluster
    divergence_actors = [a for a in actors if a.get("read", "") == "story not being paid"]
    if len(divergence_actors) >= 5:
        top = ", ".join(a["t"] for a in sorted(divergence_actors, key=lambda x: -x.get("nds", 0))[:5])
        lines.append(
            f"A 'story not being paid' divergence cluster of {len(divergence_actors)} names "
            f"(strongest: {top}) shows positive narrative consistently failing to lift price across sectors."
        )

    # 3) Software / AI Platform under sustained negative-confirming pressure
    sw_actors = [a for a in actors if a.get("sector", "") in ("Growth Software", "AI Platform")]
    sw_strained = [a for a in sw_actors if a.get("rel", 0) < -5]
    if len(sw_strained) >= 4 and len(sw_actors) > 0 and len(sw_strained) / len(sw_actors) >= 0.5:
        names = ", ".join(a["t"] for a in sorted(sw_strained, key=lambda x: x.get("rel", 0))[:5])
        lines.append(
            f"Software cohort is broadly under price pressure ({names} most affected) — "
            f"the 'AI eats software margins / AI disruption' framing dominates this segment."
        )

    return " ".join(lines[:3]) if lines else "(no dominant cross-actor patterns detected)"


def load_actors_json() -> dict:
    return json.loads(ACTORS_JSON.read_text())


def load_state_history():
    import pandas as pd
    df = pd.read_parquet(HIST_PARQ)
    df = df[df["variant"] == "baseline"].copy()
    df["date"] = df["date"].astype(str).str.slice(0, 10)
    return df.sort_values(["ticker", "date"])


def build_context(ticker: str, actors_data: dict, hist_df) -> str:
    """Compose the context block fed to the LLM."""
    actor = next((a for a in actors_data["actors"] if a["t"] == ticker), None)
    if actor is None:
        raise ValueError(f"actor not found: {ticker}")

    as_of = actors_data["date"]
    sector = actor.get("sector", "?")
    narrative_tag = actor.get("narrative", "")

    # 30-day trajectory
    sub = hist_df[hist_df["ticker"] == ticker].tail(30)
    traj_lines = []
    for row in sub.itertuples(index=False):
        traj_lines.append(
            f"  {row.date}  state={row.state:18s} narr={row.narr:>3d}  nds={row.nds:+6.1f}  rel={row.rel:+6.2f}"
        )
    trajectory = "\n".join(traj_lines)

    # Peer context — other actors in the same sector
    peers = [a for a in actors_data["actors"] if a.get("sector") == sector and a["t"] != ticker]
    peer_lines = []
    for p in sorted(peers, key=lambda x: -abs(x.get("nds", 0)))[:8]:
        peer_lines.append(
            f"  {p['t']:5s} state={p.get('state',''):18s} NDS={p.get('nds',0):+6.1f}  rel={p.get('rel',0):+5.1f}%  {p.get('read','')}"
        )
    peer_context = "\n".join(peer_lines) if peer_lines else "  (no peers in this sector)"

    field_ctx = compute_field_context(actors_data)
    # Anchors: hand-curated when available; otherwise fall back to the actor's
    # one-line narrative tag from actors.json so the LLM still has something
    # company-specific to engage with.
    if ticker in ACTOR_ANCHORS:
        anchors = ACTOR_ANCHORS[ticker]
    elif narrative_tag:
        anchors = (
            f"{narrative_tag}. "
            f"No hand-curated anchors registered; lean on the trajectory and peer context."
        )
    else:
        anchors = "(no specific anchors registered for this actor)"

    return textwrap.dedent(f"""
    FIELD CONTEXT (cross-actor patterns currently visible in the corpus):
    {field_ctx}

    NOTE: Apply field context only when it fits THIS actor's own data. If this
    actor's NDS, state, or trajectory contradict the field pattern, the pattern does
    not apply — say so explicitly.

    ─────────────────────────────────────────────────────────────────

    ACTOR: {ticker}
    AS OF: {as_of}
    SECTOR: {sector}
    NARRATIVE: {actor.get('narrative','')}

    ACTOR-SPECIFIC ANCHORS (the company-specific items the forecast must engage with):
    {anchors}

    CURRENT STATE: {actor.get('state','')}
    READ CLASS:    {actor.get('read','')}
    NDS (narrative dislocation score): {actor.get('nds',0):+.1f}  (signed gap: positive = narrative leading price; negative = price leading narrative)
    REL (rel return vs broad tape):  {actor.get('rel',0):+.1f}%
    DAYS IN STATE: {actor.get('days_in_state',0)}
    PRIOR STATE:   {actor.get('prior_state','')}

    30-DAY TRAJECTORY (state, narrative score, NDS, rel):
{trajectory}

    PEER CONTEXT (same sector, top by |NDS|):
{peer_context}
    """).strip()


def call_llm(system: str, user: str, max_tokens: int) -> dict:
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.6,
        response_format={"type": "json_object"},
    )
    txt = resp.choices[0].message.content or "{}"
    return json.loads(txt)


def generate_for_ticker(ticker: str, actors_data: dict, hist_df, dry: bool = False) -> dict:
    ctx = build_context(ticker, actors_data, hist_df)
    if dry:
        print("─" * 72)
        print(f"DRY RUN · {ticker}")
        print("─" * 72)
        print(ctx)
        return {"ticker": ticker, "dry_run_context": ctx}
    obj = call_llm(SYSTEM_PROMPT, ctx, MAX_TOKENS)
    obj["ticker"] = ticker  # ensure
    obj["as_of"]  = actors_data["date"]
    return obj


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    ap.add_argument("--pilot", action="store_true", help=f"run pilot set: {','.join(PILOT_TICKERS)}")
    ap.add_argument("--all",   action="store_true", help="run over every tracked actor in actors.json")
    ap.add_argument("--tickers", help="comma-separated tickers (overrides --pilot/--all)")
    ap.add_argument("--dry-run", action="store_true", help="print prompts without calling LLM")
    ap.add_argument("--out", default=str(OUT_PATH), help=f"output path (default {OUT_PATH})")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    actors_data = load_actors_json()
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.pilot:
        tickers = PILOT_TICKERS
    elif args.all:
        tickers = sorted({a["t"] for a in actors_data["actors"]})
    else:
        sys.exit("specify --pilot, --all, or --tickers")

    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        sys.exit("missing OPENAI_API_KEY")

    hist_df = load_state_history()

    out_rows = []
    for t in tickers:
        print(f"generating expectation for {t}…")
        try:
            row = generate_for_ticker(t, actors_data, hist_df, dry=args.dry_run)
            out_rows.append(row)
        except Exception as e:
            print(f"  [error] {e}")

    if args.dry_run:
        # Dry-run rows are just context dumps — never write them to disk,
        # since they would otherwise overwrite real LLM-generated content.
        print(f"[dry-run] generated context for {len(out_rows)} tickers; nothing written")
        return

    payload = {"as_of": actors_data["date"], "expectations": out_rows}
    payload_text = json.dumps(payload, indent=2)

    out_path = pathlib.Path(args.out).resolve()
    out_path.write_text(payload_text)
    try:
        display = out_path.relative_to(REPO_ROOT)
    except ValueError:
        display = out_path
    print(f"[wrote] {display}  ({len(out_rows)} expectations)")

    # Mirror into the topicspace-site public/ directory so the homepage and lab
    # page can read the freshest data on Vercel (which has no access to the
    # storm repo at request time).
    site_public = REPO_ROOT.parent / "topicspace-site" / "public"
    if site_public.is_dir():
        site_target = site_public / out_path.name
        site_target.write_text(payload_text)
        print(f"[wrote] {site_target.relative_to(REPO_ROOT.parent)}")

    # ── Source provenance — connect sources back to the forward view ────────
    print("\n  scoring source provenance against forward views…")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(pathlib.Path(__file__).parent / "score_source_provenance.py")],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                ls = line.strip()
                if ls.startswith(("supports", "neutral", "contradicts", "(")):
                    print(f"    {ls}")
        else:
            print(f"  provenance scoring failed (exit {result.returncode})")
            if result.stderr:
                print(f"    stderr: {result.stderr[:300]}")
    except Exception as e:
        print(f"  provenance scoring failed: {e}")


if __name__ == "__main__":
    main()
