#!/usr/bin/env python3
"""
Plot Pressure × Leadership matrix.
x-axis: pressure score, y-axis: leadership importance, bubble size: event count, color: role.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


ROLE_COLORS = {
    'leader': '#dc2626',
    'amplifier': '#1f5eff',
    'bridge': '#7e22ce',
    'receiver': '#6b7280',
    'unknown': '#cbd5e1',
}

ROLE_ORDER = {'leader': 4, 'bridge': 3, 'amplifier': 2, 'receiver': 1, 'unknown': 0}


def load_jsonl(path):
    items = []
    if not path.exists():
        return items
    with open(path) as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def main():
    data_dir = Path(__file__).parent.parent / 'data' / 'derived'
    out_path = data_dir / 'pressure_leadership_matrix.png'

    watchlist = load_jsonl(data_dir / 'strategic_watchlist.jsonl')
    leadership_list = json.loads((data_dir / 'narrative_leadership.json').read_text()) if (data_dir / 'narrative_leadership.json').exists() else []
    leadership_map = {r['actor']: r for r in leadership_list}

    # Dedupe: keep highest strategic_score per actor
    best_per_actor = {}
    for r in watchlist:
        actor = r['actor']
        if actor not in best_per_actor or r['strategic_score'] > best_per_actor[actor]['strategic_score']:
            best_per_actor[actor] = r

    # Also aggregate total events per actor
    actor_total_events = defaultdict(int)
    for r in watchlist:
        actor_total_events[r['actor']] += r['event_count']

    points = []
    for actor, rec in best_per_actor.items():
        lead = leadership_map.get(actor, {})
        role = rec['role']

        # Y-axis: leadership importance = role's top score, or ROLE_WEIGHT for unknowns
        if lead:
            y = max(lead.get('leader_score', 0), lead.get('amplifier_score', 0),
                    lead.get('bridge_score', 0), lead.get('receiver_score', 0))
        else:
            y = {'leader': 0.8, 'amplifier': 0.6, 'bridge': 0.7, 'receiver': 0.5, 'unknown': 0.3}.get(role, 0.3)

        points.append({
            'actor': actor,
            'x': rec['pressure_score'],
            'y': y,
            'events': actor_total_events[actor],
            'role': role,
            'strategic': rec['strategic_score'],
            'category': rec['watch_category'],
            'label': rec['label'],
        })

    # Plot
    fig, ax = plt.subplots(figsize=(8.0, 5.5))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('#fafbfc')

    # Quadrant shading
    ax.axvspan(0.5, 1.05, ymin=0.5, ymax=1.0, alpha=0.06, color='#1f5eff', zorder=0)
    ax.axhline(y=0.5, color='#d9e0e7', linewidth=0.8, linestyle='--', zorder=1)
    ax.axvline(x=0.5, color='#d9e0e7', linewidth=0.8, linestyle='--', zorder=1)

    # Quadrant labels
    ax.text(0.75, 0.97, 'STRATEGIC PRIORITY', transform=ax.transAxes,
            ha='center', va='top', fontsize=8, color='#1f5eff', alpha=0.5, weight='bold')
    ax.text(0.25, 0.97, 'INFLUENTIAL\nLOW PRESSURE', transform=ax.transAxes,
            ha='center', va='top', fontsize=7, color='#94a3b8', alpha=0.7)
    ax.text(0.75, 0.05, 'PRESSURE WITHOUT\nINFLUENCE', transform=ax.transAxes,
            ha='center', va='bottom', fontsize=7, color='#94a3b8', alpha=0.7)
    ax.text(0.25, 0.05, 'LOW VALUE', transform=ax.transAxes,
            ha='center', va='bottom', fontsize=7, color='#94a3b8', alpha=0.5)

    # Bubble sizing: sqrt scale, min 40, max 600
    event_vals = [p['events'] for p in points]
    max_events = max(event_vals) if event_vals else 1
    for p in points:
        p['size'] = max(40, min(600, 40 + 560 * np.sqrt(p['events'] / max_events)))

    # Draw bubbles (lower z-order for larger bubbles)
    for p in sorted(points, key=lambda p: -p['size']):
        color = ROLE_COLORS.get(p['role'], '#94a3b8')
        edge = '#ffffff' if p['category'] == 'priority_watch' else color
        lw = 2.0 if p['category'] == 'priority_watch' else 0.8
        ax.scatter(p['x'], p['y'], s=p['size'], c=color, alpha=0.75,
                   edgecolors=edge, linewidths=lw, zorder=3)

    # Labels — only for top strategic items or distinct actors
    labeled = set()
    for p in sorted(points, key=lambda p: -p['strategic']):
        actor = p['actor']
        if actor.startswith('eco_'):
            display = p['label'][:20] if p['label'] != 'Unnamed' else actor
        else:
            display = actor

        if display in labeled:
            continue
        labeled.add(display)

        # Offset to avoid overlap
        offset_y = 0.025
        if p['y'] > 0.9:
            offset_y = -0.035
        ax.annotate(display, (p['x'], p['y']),
                    xytext=(6, 8 if offset_y > 0 else -12), textcoords='offset points',
                    fontsize=8, fontweight='bold' if p['category'] == 'priority_watch' else 'normal',
                    color='#1b1f24', zorder=5)

    # Legend
    legend_handles = [mpatches.Patch(color=ROLE_COLORS[r], label=r.title()) for r in ['leader', 'amplifier', 'bridge', 'receiver']]
    ax.legend(handles=legend_handles, loc='lower left', fontsize=8, framealpha=0.9,
              edgecolor='#d9e0e7', title='Role', title_fontsize=8)

    ax.set_xlabel('Narrative Pressure', fontsize=10, labelpad=8)
    ax.set_ylabel('Leadership Importance', fontsize=10, labelpad=8)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(0.0, 1.05)
    ax.set_title('Pressure × Leadership Matrix', fontsize=13, fontweight='bold', pad=12)

    # Size legend
    size_examples = [10, 50, 150]
    for i, ev in enumerate(size_examples):
        sz = max(40, min(600, 40 + 560 * np.sqrt(ev / max_events)))
        ax.scatter([], [], s=sz, c='#d9e0e7', edgecolors='#94a3b8', linewidths=0.5,
                   label=f'{ev} events')
    ax2 = ax.legend(loc='lower right', fontsize=7, framealpha=0.9, edgecolor='#d9e0e7',
                     title='Event count', title_fontsize=7, scatterpoints=1,
                     handles=ax.get_legend_handles_labels()[0][-3:])
    ax.add_artist(ax.legend(handles=legend_handles, loc='lower left', fontsize=8,
                            framealpha=0.9, edgecolor='#d9e0e7', title='Role', title_fontsize=8))

    plt.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches='tight', facecolor='white')
    plt.close()

    print(f"✓ Matrix saved: {out_path}")
    print(f"  Points plotted: {len(points)}")
    for p in sorted(points, key=lambda p: -p['strategic'])[:5]:
        q = 'top-right' if p['x'] > 0.5 and p['y'] > 0.5 else 'top-left' if p['y'] > 0.5 else 'bottom-right' if p['x'] > 0.5 else 'bottom-left'
        actor_display = p['actor'] if not p['actor'].startswith('eco_') else p['label'][:30]
        print(f"  {actor_display:30s} pressure={p['x']:.2f} leadership={p['y']:.2f} events={p['events']:4d} role={p['role']:10s} quadrant={q}")


if __name__ == '__main__':
    main()
