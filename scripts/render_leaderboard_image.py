#!/usr/bin/env python3
"""
render_leaderboard_image.py

Renders a social-ready PNG of the narrative leaderboard.
1200×675 (16:9) — sized for Twitter/LinkedIn cards.

Usage:
  venv/bin/python scripts/render_leaderboard_image.py
  venv/bin/python scripts/render_leaderboard_image.py --out social/leaderboard-card.png
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import pandas as pd

ROOT = Path(__file__).parent.parent
PRICES_DIR    = ROOT / "data" / "derived" / "prices"
PRESSURE_FILE = ROOT / "data" / "derived" / "narrative_pressure.jsonl"
AI_SIGNALS    = ROOT.parent / "topicspace-site" / "public" / "signals" / "ai" / "latest.json"
DEFAULT_OUT   = ROOT / "social" / "narrative-leaderboard.png"

# ── palette (matches site dark theme) ────────────────────────────────────────
BG        = "#0d0d0f"
SURFACE   = "#111116"
BORDER    = "#1a1a24"
BORDER2   = "#22222e"
TEXT      = "#eeeef2"
MUTED     = "#dcdce8"
DIM       = "#b8b8d0"
VERY_DIM  = "#8888b8"

STATE_COLOR = {
    "CONFIRMED":    "#22c55e",
    "EARLY":        "#34d399",
    "REPRICING":    "#2b7fff",
    "DIVERGENCE":   "#ef4444",
    "DISAGREEMENT": "#f97316",
    "MACRO":        "#888888",
    "UNCLEAR":      "#8080a0",
}

# Reuse scoring logic from generate_leaderboard
sys.path.insert(0, str(ROOT / "scripts"))
from generate_leaderboard import (
    load_pressure, load_leadership, load_ai_signal_buckets,
    load_rel_returns, build_actors,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out_path = Path(args.out)

    # ── data ─────────────────────────────────────────────────────────────────
    pressure   = load_pressure()
    leadership = load_leadership()
    buckets    = load_ai_signal_buckets()
    rel        = load_rel_returns()
    rows       = build_actors(pressure, leadership, buckets, rel)

    # Top 12 by narrative score for the card
    rows = rows[:12]

    today = date.today().strftime("%b %-d, %Y").upper()

    # ── figure ───────────────────────────────────────────────────────────────
    ROW_H_FIXED = 0.30        # inches per row
    HEADER_H    = 1.68        # space above column headers
    FOOTER_H    = 0.22        # space below last row (footer + bottom margin)
    W = 12
    H = HEADER_H + len(rows) * ROW_H_FIXED + FOOTER_H
    fig = plt.figure(figsize=(W, H), facecolor=BG)
    ax  = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    # ── header ───────────────────────────────────────────────────────────────
    ax.text(0.36, H - 0.30, "N A R R A T I V E   V S   M A R K E T",
            fontsize=7.5, color=VERY_DIM, fontweight="bold",
            ha="left", va="top", fontfamily="Helvetica Neue")
    ax.text(0.36, H - 0.58, "Who's getting paid — and who isn't",
            fontsize=14, color=TEXT, fontweight="bold",
            ha="left", va="top", fontfamily="Helvetica Neue")

    # date + wordmark on same line, right-aligned
    ax.text(W - 0.32, H - 0.30, "TOPICSPACE",
            fontsize=7.5, color=VERY_DIM, fontweight="bold",
            ha="right", va="top", fontfamily="Helvetica Neue", alpha=0.7)
    ax.text(W - 0.32, H - 0.50, today,
            fontsize=7.5, color=VERY_DIM, fontweight="bold",
            ha="right", va="top", fontfamily="Helvetica Neue", alpha=0.8)

    # ── summary metrics strip ─────────────────────────────────────────────────
    all_rows = build_actors(load_pressure(), load_leadership(),
                            load_ai_signal_buckets(), load_rel_returns())
    n_confirmed  = sum(1 for r in all_rows if r["state"] in ("CONFIRMED", "EARLY"))
    n_diverging  = sum(1 for r in all_rows if r["state"] == "DIVERGENCE")
    n_conflict   = sum(1 for r in all_rows if r["state"] == "DISAGREEMENT")
    strong_narr  = [r for r in all_rows if r["narr"] >= 65]
    n_narr_neg   = sum(1 for r in strong_narr if r["rel"] < 0)
    n_narr_total = len(strong_narr)

    ax.axhline(H - 1.00, xmin=0.03, xmax=0.97, color=BORDER2, linewidth=0.5)

    METRIC_Y  = H - 1.16
    METRIC_Y2 = H - 1.30
    metrics = [
        (f"{n_confirmed}",               "confirming or early",    STATE_COLOR["EARLY"],        0.36),
        (f"{n_narr_neg}/{n_narr_total}", "strong narrative, down", STATE_COLOR["REPRICING"],    3.40),
        (f"{n_diverging}",               "diverging",              STATE_COLOR["DIVERGENCE"],   6.90),
        (f"{n_conflict}",                "in conflict",            STATE_COLOR["DISAGREEMENT"], 9.80),
    ]
    for val, label, col, x in metrics:
        ax.text(x, METRIC_Y,  val,   fontsize=13, color=col, fontweight="bold",
                ha="left", va="bottom", fontfamily="Helvetica Neue")
        ax.text(x, METRIC_Y2, label, fontsize=6.5, color=VERY_DIM,
                ha="left", va="top", fontfamily="Helvetica Neue")

    ax.axhline(H - 1.44, xmin=0.03, xmax=0.97, color=BORDER2, linewidth=0.5)

    # ── column headers ────────────────────────────────────────────────────────
    COL_X = {"ticker": 0.32, "bar": 1.22, "narr": 2.98,
              "rel": 3.82, "state": 5.12, "story": 6.50}
    HDR_Y = H - 1.68

    header_items = [
        ("ticker", "TICKER"),
        ("bar",    "NARRATIVE"),
        ("narr",   ""),
        ("rel",    "5D REL"),
        ("state",  "STATE"),
        ("story",  "STORY"),
    ]
    for col, label in header_items:
        ax.text(COL_X[col], HDR_Y, label, fontsize=6.5,
                color=VERY_DIM, fontweight="bold", ha="left", va="bottom",
                fontfamily="Helvetica Neue")

    # thin header rule
    ax.axhline(HDR_Y - 0.06, xmin=0.03, xmax=0.97,
               color=BORDER2, linewidth=0.6)

    # ── rows ─────────────────────────────────────────────────────────────────
    FOOTER_LINE = 0.11               # footer rule y-position
    ROW_H    = ROW_H_FIXED
    ROW_BASE = HDR_Y - 0.06

    for i, r in enumerate(rows):
        y_top    = ROW_BASE - i * ROW_H
        y_mid    = y_top - ROW_H * 0.52
        y_bottom = y_top - ROW_H

        # alternating row tint
        if i % 2 == 0:
            rect = FancyBboxPatch((0.28, y_bottom + 0.01),
                                  W - 0.56, ROW_H - 0.02,
                                  boxstyle="square,pad=0",
                                  fc="#ffffff06", ec="none", zorder=0)
            ax.add_patch(rect)

        state_col = STATE_COLOR.get(r["state"], DIM)

        # ticker
        ax.text(COL_X["ticker"], y_mid, r["t"],
                fontsize=9.5, color=state_col, fontweight="bold",
                ha="left", va="center", fontfamily="Helvetica Neue")

        # narrative bar
        bar_x  = COL_X["bar"]
        bar_w  = 1.50
        bar_h  = 0.06
        bar_y  = y_mid - bar_h / 2
        fill_w = bar_w * r["narr"] / 100

        ax.add_patch(FancyBboxPatch((bar_x, bar_y), bar_w, bar_h,
                     boxstyle="square,pad=0", fc=BORDER2, ec="none", zorder=1))
        if fill_w > 0:
            ax.add_patch(FancyBboxPatch((bar_x, bar_y), fill_w, bar_h,
                         boxstyle="square,pad=0", fc=state_col, ec="none",
                         alpha=0.85, zorder=2))

        # narr value
        ax.text(COL_X["narr"], y_mid, str(r["narr"]),
                fontsize=8, color=MUTED, ha="left", va="center",
                fontfamily="Courier New")

        # 5D relative return
        ret_val = r["rel"]
        ret_str = f"{ret_val:+.1f}%"
        ret_col = STATE_COLOR["CONFIRMED"] if ret_val > 0.5 else (
                  STATE_COLOR["DIVERGENCE"] if ret_val < -0.5 else MUTED)
        ax.text(COL_X["rel"], y_mid, ret_str,
                fontsize=8.5, color=ret_col, fontweight="bold",
                ha="left", va="center",
                fontfamily="Courier New")

        # state
        ax.text(COL_X["state"], y_mid, r["state"],
                fontsize=6.8, color=state_col, fontweight="bold",
                ha="left", va="center", fontfamily="Helvetica Neue")

        # story description (last — runs to right edge)
        story_text = r.get("narrative", "")
        ax.text(COL_X["story"], y_mid, story_text,
                fontsize=7.5, color=MUTED, ha="left", va="center",
                fontfamily="Helvetica Neue")

        # row separator
        ax.axhline(y_bottom, xmin=0.03, xmax=0.97,
                   color=BORDER, linewidth=0.4, alpha=0.6)

    # ── footer ───────────────────────────────────────────────────────────────
    ax.axhline(FOOTER_LINE, xmin=0.03, xmax=0.97, color=BORDER2, linewidth=0.5)
    ax.text(0.36, 0.02, "topicspace.com",
            fontsize=7, color=VERY_DIM, ha="left", va="bottom",
            fontfamily="Helvetica Neue")

    # state legend bottom-right
    legend_x = W - 0.32
    legend_items = [
        ("CONFIRMED", STATE_COLOR["CONFIRMED"]),
        ("EARLY",     STATE_COLOR["EARLY"]),
        ("REPRICING", STATE_COLOR["REPRICING"]),
        ("DIVERGENCE",STATE_COLOR["DIVERGENCE"]),
    ]
    for j, (lbl, col) in enumerate(reversed(legend_items)):
        ax.text(legend_x - j * 1.38, 0.02, f"● {lbl}",
                fontsize=6.5, color=col, ha="right", va="bottom",
                fontfamily="Helvetica Neue")

    # ── save ─────────────────────────────────────────────────────────────────
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=100, bbox_inches=None, pad_inches=0,
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"Saved → {out_path}  ({out_path.stat().st_size // 1024}K)")


if __name__ == "__main__":
    main()
