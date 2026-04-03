#!/usr/bin/env python3
"""
Narrative Phase Map — gravity vs velocity scatter plot.

Can be run standalone or called from generate_master_report.py via
generate_phase_map(all_storms, leadership_map, output_dir).
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


ROLE_COLORS = {
    'leader':     '#d62728',   # red
    'amplifier':  '#ff7f0e',   # orange
    'bridge':     '#1f77b4',   # blue
    'receiver':   '#2ca02c',   # green
}
ROLE_COLOR_DEFAULT = '#888888'  # gray / unknown

QUADRANTS = [
    # (x_range, y_range, label, label_xy, ha)
    (0.60, 1.00,  0.0,  2.0, 'Strategic\nExpansion',   (0.80, 1.70), 'center'),
    (0.00, 0.60,  0.0,  2.0, 'Emerging\nSignals',      (0.30, 1.70), 'center'),
    (0.60, 1.00, -1.0,  0.0, 'Cooling but\nImportant', (0.80, -0.80), 'center'),
    (0.00, 0.60, -1.0,  0.0, 'Background',             (0.30, -0.80), 'center'),
]


def _storm_label(storm):
    label = (storm.get('display_headline')
             or storm.get('headline')
             or storm.get('llm_headline')
             or storm.get('storm_id', ''))
    # Shorten: keep first 35 chars
    return label[:35]


def _quadrant_name(x, y):
    if x >= 0.60 and y >= 0.0:
        return 'Strategic Expansion'
    if x < 0.60 and y >= 0.0:
        return 'Emerging Signals'
    if x >= 0.60 and y < 0.0:
        return 'Cooling but Important'
    return 'Background'


def generate_phase_map(all_storms, leadership_map, output_dir):
    """
    Build and save phase_map.png and phase_map.svg.

    Parameters
    ----------
    all_storms     : list of storm dicts (actor + ecosystem, already enriched
                     with gravity_score, velocity_score, velocity_confidence)
    leadership_map : dict  actor -> {role: ...}
    output_dir     : pathlib.Path

    Returns
    -------
    dict with keys png_path, svg_path, plotted_count, quadrant_counts
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    # Filter storms
    plotted = []
    for s in all_storms:
        g = s.get('gravity_score', 0)
        conf = s.get('velocity_confidence', 'low')
        # Include if confidence is not low, OR gravity is high enough to show regardless
        if conf == 'low' and g < 0.70:
            continue
        plotted.append(s)

    # Compute bubble sizes (normalised to 20–400 pt²)
    counts = [max(s.get('event_count', 1), 1) for s in plotted]
    max_count = max(counts) if counts else 1
    sizes = [20 + 380 * (c / max_count) for c in counts]

    # Assign colors from leadership_map (keyed by actor)
    colors = []
    for s in plotted:
        actor = s.get('actor', '')
        role  = leadership_map.get(actor, {}).get('role', 'unknown')
        colors.append(ROLE_COLORS.get(role, ROLE_COLOR_DEFAULT))

    xs = [s.get('gravity_score', 0)   for s in plotted]
    ys = [s.get('velocity_score', 0)  for s in plotted]

    # Quadrant counts
    quadrant_counts = defaultdict(int)
    for x, y in zip(xs, ys):
        quadrant_counts[_quadrant_name(x, y)] += 1

    # ── Plot ──────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor('#0f1117')
    ax.set_facecolor('#0f1117')

    # Quadrant shading
    shade_alpha = 0.06
    ax.axhspan(0, 2,   xmin=0.60, xmax=1.0, color='#d62728', alpha=shade_alpha)
    ax.axhspan(0, 2,   xmin=0.00, xmax=0.60, color='#1f77b4', alpha=shade_alpha)
    ax.axhspan(-1, 0,  xmin=0.60, xmax=1.0, color='#ff7f0e', alpha=shade_alpha)
    ax.axhspan(-1, 0,  xmin=0.00, xmax=0.60, color='#888888', alpha=shade_alpha)

    # Quadrant dividers
    ax.axvline(x=0.60, color='#ffffff', linewidth=0.8, linestyle='--', alpha=0.4)
    ax.axhline(y=0.00, color='#ffffff', linewidth=0.8, linestyle='--', alpha=0.4)

    # Quadrant labels
    for _, _, _, _, qlabel, (lx, ly), ha in QUADRANTS:
        ax.text(lx, ly, qlabel, color='#ffffff', fontsize=9, alpha=0.35,
                ha=ha, va='center', style='italic')

    # Bubbles
    sc = ax.scatter(xs, ys, s=sizes, c=colors, alpha=0.80,
                    edgecolors='#ffffff', linewidths=0.4, zorder=3)

    # Storm labels — all plotted storms, direction-aware offset to reduce overlap.
    CANDIDATE_OFFSETS = [
        ( 6,  6), (-8,  6), ( 6, -10), (-8, -10),
        (13,  3), (-15,  3), (13, -7),  (-15, -7),
        ( 6, 14), (-8,  14), ( 6, -18), (-8, -18),
    ]
    CLUSTER_R_X = 0.08   # data-space proximity thresholds
    CLUSTER_R_Y = 0.20

    label_anchors = []  # (x, y) of already-placed labels

    def _phase_offset(px, py, placed):
        nearby = [(qx, qy) for qx, qy in placed
                  if abs(qx - px) < CLUSTER_R_X and abs(qy - py) < CLUSTER_R_Y]
        if not nearby:
            return CANDIDATE_OFFSETS[0]
        cx_ = sum(q[0] for q in nearby) / len(nearby)
        cy_ = sum(q[1] for q in nearby) / len(nearby)
        dx, dy = px - cx_, py - cy_
        best, best_dot = CANDIDATE_OFFSETS[0], -1e9
        for ox, oy in CANDIDATE_OFFSETS:
            dot = ox * dx + oy * dy
            if dot > best_dot:
                best_dot, best = dot, (ox, oy)
        return best

    for s, x, y in zip(plotted, xs, ys):
        lbl = _storm_label(s)
        if not lbl:
            continue
        ox, oy = _phase_offset(x, y, label_anchors)
        label_anchors.append((x, y))
        ax.annotate(
            lbl, (x, y),
            textcoords='offset points', xytext=(ox, oy),
            fontsize=6.5, color='#cccccc', alpha=0.85,
            clip_on=True,
        )

    # Axes
    ax.set_xlim(0, 1)
    ax.set_ylim(-1, 2)
    ax.set_xlabel('Gravity Score', color='#cccccc', fontsize=11)
    ax.set_ylabel('Velocity Score', color='#cccccc', fontsize=11)
    ax.tick_params(colors='#888888')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333333')

    ax.set_title('Narrative Phase Map — Gravity × Velocity',
                 color='#ffffff', fontsize=13, pad=14)

    # Legend: roles
    legend_handles = [
        mpatches.Patch(color=ROLE_COLORS['leader'],    label='Leader'),
        mpatches.Patch(color=ROLE_COLORS['amplifier'], label='Amplifier'),
        mpatches.Patch(color=ROLE_COLORS['bridge'],    label='Bridge'),
        mpatches.Patch(color=ROLE_COLORS['receiver'],  label='Receiver'),
        mpatches.Patch(color=ROLE_COLOR_DEFAULT,       label='Unknown / Ecosystem'),
    ]
    ax.legend(handles=legend_handles, loc='upper left', fontsize=8,
              facecolor='#1a1d27', edgecolor='#444444', labelcolor='#cccccc')

    plt.tight_layout()

    png_path = output_dir / 'phase_map.png'
    svg_path = output_dir / 'phase_map.svg'
    fig.savefig(png_path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    fig.savefig(svg_path, bbox_inches='tight',          facecolor=fig.get_facecolor())
    plt.close(fig)

    return {
        'png_path': str(png_path),
        'svg_path': str(svg_path),
        'plotted_count': len(plotted),
        'quadrant_counts': dict(quadrant_counts),
    }


# Blue family (actor) and orange family (ecosystem)
_ACTOR_COLOR     = '#4c9be8'   # mid blue
_ECO_COLOR       = '#f5a623'   # amber-orange
_ACTOR_COLOR_LOW = '#2a5a8a'   # muted blue  (low confidence)
_ECO_COLOR_LOW   = '#8a5a10'   # muted amber (low confidence)


def _shorten_label(label, max_words=4):
    """Keep first max_words words, strip trailing noise words."""
    noise = {'narrative', 'report', 'analysis', 'update', 'the', 'a', 'an'}
    words = label.split('[')[0].strip().split()
    kept = [w for w in words if w.lower() not in noise][:max_words]
    return ' '.join(kept) if kept else label[:30]


def _lineage_confidence(rec):
    """Majority-vote velocity_confidence across member storms."""
    counts = defaultdict(int)
    for s in rec.get('storms', []):
        counts[s.get('velocity_confidence', 'low')] += 1
    if not counts:
        return 'low'
    return max(counts, key=counts.__getitem__)


def _lineage_score(rec):
    return 0.7 * rec['lineage_max_gravity'] + 0.3 * min(rec['lineage_max_velocity'], 1.5)


def generate_phase_map_lineages(lineages_sorted, leadership_map, output_dir):
    """
    Narrative Phase Map — lineages only.
    x = lineage_max_gravity, y = lineage_max_velocity, size = event count.
    Actor lineages = blue family, ecosystem lineages = orange family.
    Low-confidence lineages get dashed outline and muted color.
    Top 8 by lineage_score are labeled (2-4 words, offset to reduce overlap).
    Returns dict: png_path, svg_path, plotted_count, quadrant_counts,
                  type_counts, eco_absent.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    plotted = list(lineages_sorted)  # include all lineages
    eco_absent = not any(r.get('lineage_type') == 'ecosystem' for r in plotted)

    png_path = output_dir / 'phase_map_lineages.png'
    svg_path = output_dir / 'phase_map_lineages.svg'

    if not plotted:
        fig, ax = plt.subplots(figsize=(12, 9))
        fig.patch.set_facecolor('#0f1117')
        ax.set_facecolor('#0f1117')
        ax.text(0.5, 0.5, 'No lineages detected in this report window.',
                color='#888888', ha='center', va='center', transform=ax.transAxes, fontsize=12)
        for path in (png_path, svg_path):
            fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        return {'png_path': str(png_path), 'svg_path': str(svg_path),
                'plotted_count': 0, 'quadrant_counts': {}, 'type_counts': {}, 'eco_absent': True}

    xs     = [r['lineage_max_gravity']  for r in plotted]
    ys     = [r['lineage_max_velocity'] for r in plotted]
    counts = [max(r['lineage_event_count'], 1) for r in plotted]
    max_count = max(counts)
    sizes  = [40 + 440 * (c / max_count) for c in counts]

    confidences = [_lineage_confidence(r) for r in plotted]
    face_colors, edge_colors, edge_widths, edge_styles = [], [], [], []
    for rec, conf in zip(plotted, confidences):
        is_eco = rec.get('lineage_type') == 'ecosystem'
        if conf == 'low':
            face_colors.append(_ECO_COLOR_LOW if is_eco else _ACTOR_COLOR_LOW)
            edge_colors.append(_ECO_COLOR if is_eco else _ACTOR_COLOR)
            edge_widths.append(1.2)
            edge_styles.append('dashed')
        else:
            face_colors.append(_ECO_COLOR if is_eco else _ACTOR_COLOR)
            edge_colors.append('#ffffff')
            edge_widths.append(0.5)
            edge_styles.append('solid')

    quadrant_counts = defaultdict(int)
    type_counts     = defaultdict(int)
    for rec, x, y in zip(plotted, xs, ys):
        quadrant_counts[_quadrant_name(x, y)] += 1
        type_counts[rec.get('lineage_type', 'actor')] += 1

    # All lineages get labels (direction-aware offset; highest-score ones placed first)
    scored = sorted(enumerate(plotted), key=lambda t: -_lineage_score(t[1]))
    label_indices = {i for i, _ in scored}

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor('#0f1117')
    ax.set_facecolor('#0f1117')

    shade_alpha = 0.06
    ax.axhspan(0, 2,  xmin=0.60, xmax=1.0, color='#d62728', alpha=shade_alpha)
    ax.axhspan(0, 2,  xmin=0.00, xmax=0.60, color='#1f77b4', alpha=shade_alpha)
    ax.axhspan(-1, 0, xmin=0.60, xmax=1.0, color='#ff7f0e', alpha=shade_alpha)
    ax.axhspan(-1, 0, xmin=0.00, xmax=0.60, color='#888888', alpha=shade_alpha)

    ax.axvline(x=0.60, color='#ffffff', linewidth=0.8, linestyle='--', alpha=0.4)
    ax.axhline(y=0.00, color='#ffffff', linewidth=0.8, linestyle='--', alpha=0.4)

    for _, _, _, _, qlabel, (lx, ly), ha in QUADRANTS:
        ax.text(lx, ly, qlabel, color='#ffffff', fontsize=9, alpha=0.35,
                ha=ha, va='center', style='italic')

    # Draw each bubble individually to support per-point edge styles
    for i, (rec, x, y, sz, fc, ec, ew, es) in enumerate(
        zip(plotted, xs, ys, sizes, face_colors, edge_colors, edge_widths, edge_styles)
    ):
        ax.scatter([x], [y], s=[sz], c=[fc], alpha=0.85,
                   edgecolors=ec, linewidths=ew,
                   linestyle=es, zorder=3)

    # Labels for all lineages — direction-aware, placed highest-score first.
    LIN_CANDIDATE_OFFSETS = [
        ( 7,  7), (-9,  7), ( 7, -11), (-9, -11),
        (15,  3), (-17,  3), (15, -8),  (-17, -8),
        ( 7, 16), (-9,  16), ( 7, -20), (-9, -20),
    ]
    LIN_CLUSTER_R_X, LIN_CLUSTER_R_Y = 0.08, 0.20

    lin_label_anchors = []

    def _lin_offset(px, py, placed):
        nearby = [(qx, qy) for qx, qy in placed
                  if abs(qx - px) < LIN_CLUSTER_R_X and abs(qy - py) < LIN_CLUSTER_R_Y]
        if not nearby:
            return LIN_CANDIDATE_OFFSETS[0]
        cx_ = sum(q[0] for q in nearby) / len(nearby)
        cy_ = sum(q[1] for q in nearby) / len(nearby)
        dx, dy = px - cx_, py - cy_
        best, best_dot = LIN_CANDIDATE_OFFSETS[0], -1e9
        for ox, oy in LIN_CANDIDATE_OFFSETS:
            dot = ox * dx + oy * dy
            if dot > best_dot:
                best_dot, best = dot, (ox, oy)
        return best

    for i, rec in scored:  # already sorted by lineage_score descending
        if i not in label_indices:
            continue
        x, y = xs[i], ys[i]
        conf = confidences[i]
        short = _shorten_label(rec['label'])
        if not short:
            continue
        alpha = 0.65 if conf == 'low' else 0.92
        ox, oy = _lin_offset(x, y, lin_label_anchors)
        lin_label_anchors.append((x, y))
        ax.annotate(
            short, (x, y),
            textcoords='offset points', xytext=(ox, oy),
            fontsize=7.5, color='#cccccc', alpha=alpha,
            clip_on=True,
        )

    ax.set_xlim(0, 1)
    ax.set_ylim(-1, 2)
    ax.set_xlabel('Gravity Score', color='#cccccc', fontsize=11)
    ax.set_ylabel('Velocity Score', color='#cccccc', fontsize=11)
    ax.tick_params(colors='#888888')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333333')
    ax.set_title('Narrative Phase Map — Lineages (Gravity × Velocity)',
                 color='#ffffff', fontsize=13, pad=14)

    legend_handles = [
        mpatches.Patch(color=_ACTOR_COLOR, label='Actor lineage'),
        mpatches.Patch(color=_ECO_COLOR,   label='Ecosystem lineage'),
        mpatches.Patch(facecolor='#444', edgecolor='#aaa', linestyle='--',
                       linewidth=1.2, label='Low confidence'),
    ]
    if eco_absent:
        legend_handles.append(
            mpatches.Patch(color='none', label='(No ecosystem lineages this window)')
        )
    ax.legend(handles=legend_handles, loc='upper left', fontsize=8,
              facecolor='#1a1d27', edgecolor='#444444', labelcolor='#cccccc')

    plt.tight_layout()
    for path in (png_path, svg_path):
        fig.savefig(path, dpi=150 if path.suffix == '.png' else None,
                    bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)

    return {
        'png_path':       str(png_path),
        'svg_path':       str(svg_path),
        'plotted_count':  len(plotted),
        'quadrant_counts': dict(quadrant_counts),
        'type_counts':    dict(type_counts),
        'eco_absent':     eco_absent,
    }


def main():
    base_dir  = Path(__file__).parent.parent
    data_dir  = base_dir / 'data' / 'derived'

    actor_storms = [json.loads(l) for l in open(data_dir / 'actor_storms.jsonl') if l.strip()]
    eco_storms   = [json.loads(l) for l in open(data_dir / 'ecosystem_storms.jsonl') if l.strip()]

    leadership_map = {}
    lp = data_dir / 'narrative_leadership.json'
    if lp.exists():
        for r in json.load(open(lp)):
            leadership_map[r['actor']] = r

    # Minimal enrichment: gravity and velocity must already be on storms
    # (run generate_master_report.py first, or run this after detect_narrative_pressure.py)
    all_storms = actor_storms + eco_storms
    missing = [s['storm_id'] for s in all_storms if 'gravity_score' not in s]
    if missing:
        print(f"WARNING: {len(missing)} storms missing gravity_score — run generate_master_report.py first.")
        sys.exit(1)

    result = generate_phase_map(all_storms, leadership_map, data_dir)

    print(f"\nNarrative Phase Map")
    print(f"  Storms plotted : {result['plotted_count']}")
    print(f"  Quadrant distribution:")
    for q, c in sorted(result['quadrant_counts'].items()):
        print(f"    {q:<25} {c}")
    print(f"  PNG : {result['png_path']}")
    print(f"  SVG : {result['svg_path']}")


if __name__ == '__main__':
    main()
