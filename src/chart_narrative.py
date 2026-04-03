"""
Narrative-to-market response chart.

make_narrative_price_chart(
    ticker, benchmark, start_date, end_date,
    event_markers, title, subtitle, state,
    output_path, highlight_region
)

Each event_marker:
    {"date": "2026-03-08", "label": "CEO buy", "tier": "primary"|"secondary"}

State options: DISAGREEMENT | REPRICING | MACRO | DIVERGENCE | EARLY | CONFIRMED
"""

from pathlib import Path
from datetime import date, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from src.price_analysis import load_prices, detect_price_move

CHARTS_DIR = Path("social/charts")
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Palette ──────────────────────────────────────────────────────────────────
BG          = "#0d0d0d"
PANEL       = "#111111"
STOCK_LINE  = "#e8e8e8"
BENCH_LINE  = "#787878"
TEXT_DIM    = "#aaaaaa"
TEXT_MID    = "#cccccc"
TEXT_BRIGHT = "#f0f0f0"
BLUE        = "#2b7fff"
FONT        = "monospace"

# State badge colours  (bg, text)
STATE_COLORS: dict[str, tuple[str, str]] = {
    "DISAGREEMENT": ("#7c3400", "#f97316"),   # orange
    "REPRICING":    ("#0a2a5e", "#2b7fff"),   # blue
    "MACRO":        ("#252525", "#888888"),   # grey
    "DIVERGENCE":   ("#3d0f0f", "#ef4444"),   # red
    "EARLY":        ("#0d2d1e", "#34d399"),   # green
    "CONFIRMED":    ("#0d2d1e", "#22c55e"),   # bright green
}

# Interpretation tags — TopicSpace signature voice
STATE_TAGS: dict[str, str] = {
    "DISAGREEMENT": "⚠  conflicting signals — no clear resolution",
    "REPRICING":    "→  narrative adjusting, not reversing",
    "MACRO":        "⊘  macro overriding actor-specific signals",
    "DIVERGENCE":   "↓  price lagging narrative conviction",
    "EARLY":        "→  price lagging narrative formation",
    "CONFIRMED":    "↑  price validating the narrative",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_window(ticker: str, start: date, end: date) -> pd.DataFrame | None:
    df = load_prices(ticker)
    if df is None:
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.date
    result = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].copy()
    return result.sort_values("timestamp").reset_index(drop=True) if len(result) >= 2 else None


def _normalize(series: pd.Series) -> pd.Series:
    s = series.reset_index(drop=True)
    return (s / s.iloc[0]) * 100


# ── Main ──────────────────────────────────────────────────────────────────────

def make_narrative_price_chart(
    ticker: str,
    benchmark: str,
    start_date: str,
    end_date: str,
    event_markers: list[dict],
    title: str,
    subtitle: str,
    state: str = "MACRO",
    output_path: str | None = None,
    highlight_region: tuple[str, str] | None = None,
) -> Path:
    start = pd.to_datetime(start_date).date()
    end   = pd.to_datetime(end_date).date()

    stock_df = _load_window(ticker, start, end)
    bench_df = _load_window(benchmark, start, end)
    if stock_df is None or bench_df is None:
        raise ValueError(f"No price data for {ticker} or {benchmark} in [{start_date}, {end_date}]")

    shared = set(stock_df["timestamp"]).intersection(set(bench_df["timestamp"]))
    stock_df = stock_df[stock_df["timestamp"].isin(shared)].sort_values("timestamp").reset_index(drop=True)
    bench_df = bench_df[bench_df["timestamp"].isin(shared)].sort_values("timestamp").reset_index(drop=True)

    dates      = pd.to_datetime(stock_df["timestamp"])
    stock_norm = _normalize(stock_df["close"])
    bench_norm = _normalize(bench_df["close"])

    stock_ret = float(stock_df["close"].iloc[-1] / stock_df["close"].iloc[0]) - 1
    bench_ret = float(bench_df["close"].iloc[-1] / bench_df["close"].iloc[0]) - 1
    rel_ret   = stock_ret - bench_ret

    mid_date  = start + timedelta(days=(end - start).days // 2)
    move_info = detect_price_move(ticker, str(mid_date), window=(end - start).days // 2, threshold=0.02)

    badge_bg, badge_fg = STATE_COLORS.get(state, ("#252525", "#888888"))

    # ── Figure ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 5.6))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    # Optional highlight zone (very subtle)
    if highlight_region:
        r0 = pd.to_datetime(highlight_region[0])
        r1 = pd.to_datetime(highlight_region[1])
        ax.axvspan(r0, r1, color=badge_fg, alpha=0.04, zorder=1)
        ax.axvline(r0, color=badge_fg, linewidth=0.5, alpha=0.18, zorder=1)
        ax.axvline(r1, color=badge_fg, linewidth=0.5, alpha=0.18, zorder=1)

    # Relative performance fill band
    above = stock_norm.values >= bench_norm.values
    ax.fill_between(dates, stock_norm, bench_norm,
                    where=above,  color="#00ff7f", alpha=0.18, zorder=2)
    ax.fill_between(dates, stock_norm, bench_norm,
                    where=~above, color="#ff2222", alpha=0.22, zorder=2)

    # Baseline 100
    ax.axhline(100, color="#222222", linewidth=0.6, zorder=1)

    # Benchmark line
    ax.plot(dates, bench_norm, color=BENCH_LINE, linewidth=1.1,
            linestyle="--", alpha=0.8, zorder=3)

    # Stock line
    ax.plot(dates, stock_norm, color=STOCK_LINE, linewidth=2.0,
            solid_capstyle="round", zorder=4)

    # ── Event markers (two-tier) ──────────────────────────────────────────────
    y_max_norm = float(max(stock_norm.max(), bench_norm.max()))
    label_slots: list[tuple[float, float]] = []   # (x_float, y)

    def _slot_y(x_ts: pd.Timestamp) -> float:
        base_y = y_max_norm + 3.0
        x_f = float(x_ts.value)
        for (px, py) in label_slots:
            if abs(x_f - px) < 4e14 and abs(base_y - py) < 5:
                base_y = py + 5
        label_slots.append((x_f, base_y))
        return base_y

    for marker in event_markers:
        m_date  = pd.to_datetime(marker["date"])
        label   = marker["label"]
        primary = marker.get("tier", "primary") == "primary"

        if primary:
            line_alpha, line_w, dot_s  = 0.75, 1.1, 45
            label_color, label_size    = TEXT_BRIGHT, 7.5
            line_style                 = "-"
        else:
            line_alpha, line_w, dot_s  = 0.35, 0.7, 14
            label_color, label_size    = TEXT_DIM, 6.5
            line_style                 = ":"

        ax.axvline(m_date, color=badge_fg, linewidth=line_w,
                   linestyle=line_style, alpha=line_alpha, zorder=5)

        idx = int((dates - m_date).abs().argmin())
        y   = float(stock_norm.iloc[idx])
        ax.scatter(m_date, y, color=badge_fg, s=dot_s,
                   zorder=6, edgecolors="none")

        label_y = _slot_y(m_date)
        ax.text(m_date, label_y, label,
                color=label_color, fontsize=label_size, fontfamily=FONT,
                ha="center", va="bottom", zorder=7,
                bbox=dict(boxstyle="round,pad=0.25", facecolor=BG,
                          edgecolor="none", alpha=0.85))

    # Line end labels
    last_date  = dates.iloc[-1]
    stock_last = float(stock_norm.iloc[-1])
    bench_last = float(bench_norm.iloc[-1])
    if abs(stock_last - bench_last) < 3:
        bench_last -= 3.0

    ax.text(last_date + pd.Timedelta(days=1), stock_last,
            f"  {ticker}", color=STOCK_LINE, fontsize=8,
            fontfamily=FONT, va="center", zorder=7)
    ax.text(last_date + pd.Timedelta(days=1), bench_last,
            f"  {benchmark}", color=BENCH_LINE, fontsize=7,
            fontfamily=FONT, va="center", alpha=0.7, zorder=7)

    # ── Axes ─────────────────────────────────────────────────────────────────
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=1),
                dates.iloc[-1] + pd.Timedelta(days=9))
    y_min_v = float(min(stock_norm.min(), bench_norm.min()))
    y_max_v = float(max(stock_norm.max(), bench_norm.max()))
    y_pad   = (y_max_v - y_min_v) * 0.25
    ax.set_ylim(y_min_v - y_pad, y_max_v + y_pad + 10)

    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(matplotlib.dates.WeekdayLocator(byweekday=0, interval=1))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}"))
    ax.tick_params(axis="x", colors=TEXT_DIM, labelsize=7, length=3)
    ax.tick_params(axis="y", colors=TEXT_DIM, labelsize=7, length=3)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_ylabel("indexed  (start = 100)", color=TEXT_DIM, fontsize=6,
                  fontfamily=FONT, labelpad=8)

    # ── State badge (top-left, inside axes) ───────────────────────────────────
    ax.text(0.012, 0.97, f" {state} ", transform=ax.transAxes,
            color=badge_fg, fontsize=7.5, fontfamily=FONT,
            fontweight="bold", va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.35", facecolor=badge_bg,
                      edgecolor=badge_fg, linewidth=0.6, alpha=0.95),
            zorder=10)

    # ── Titles ────────────────────────────────────────────────────────────────
    fig.text(0.04, 0.97, title,
             color=TEXT_BRIGHT, fontsize=11.5, fontfamily=FONT,
             fontweight="bold", va="top", ha="left")
    fig.text(0.04, 0.905, subtitle,
             color=TEXT_MID, fontsize=7.5, fontfamily=FONT,
             va="top", ha="left", style="italic")

    # ── Metrics box (top-right) ───────────────────────────────────────────────
    metrics_lines = [
        f"{ticker} vs {benchmark}",
        "",
        f"{ticker}:  {stock_ret:+.2%}",
        f"{benchmark}:  {bench_ret:+.2%}",
        f"Rel:  {rel_ret:+.2%}",
    ]
    if move_info:
        d_str = pd.to_datetime(move_info["move_date"]).strftime("%b %d")
        metrics_lines.append(f"Max 1D:  {float(move_info['return_1d']):+.2%}  {d_str}")

    fig.text(0.97, 0.97, "\n".join(metrics_lines),
             color=TEXT_DIM, fontsize=6.5, fontfamily=FONT,
             va="top", ha="right",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#161616",
                       edgecolor="#2a2a2a", alpha=0.9))

    # ── Interpretation tag (bottom-left) ──────────────────────────────────────
    tag = STATE_TAGS.get(state, "")
    if tag:
        _, badge_fg = STATE_COLORS.get(state, ("#252525", "#888888"))
        fig.text(0.04, 0.025, tag,
                 color=badge_fg, fontsize=6.5, fontfamily=FONT,
                 va="bottom", ha="left", alpha=0.85)

    # ── Brand ─────────────────────────────────────────────────────────────────
    fig.text(0.97, 0.025, "TopicSpace",
             color="#333333", fontsize=6, fontfamily=FONT,
             va="bottom", ha="right")

    plt.tight_layout(rect=[0, 0.02, 1, 0.88])

    if output_path is None:
        output_path = CHARTS_DIR / f"{ticker.lower()}_narrative_{start_date}_{end_date}.png"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"  [chart] {output_path}")
    return output_path
