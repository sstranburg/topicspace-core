#!/usr/bin/env python3
"""
generate_compass.py — Compass-format signal output.

Converts storm + transcript signals into 4 decision sections:
  1. PAY ATTENTION        positive momentum, density holding, reinforced
  2. IGNORE FOR NOW       declining, no recovery, breakdown
  3. TREAT WITH CAUTION   sustained divergence, alignment_gap > threshold
  4. WATCH NEXT           reversals, new formations, narrowing divergence

Usage:
  python scripts/generate_compass.py
  python scripts/generate_compass.py --json
  python scripts/generate_compass.py --out compass.txt
  python scripts/generate_compass.py --gap-threshold 0.4
"""

import json
import sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent.parent
TRAJ_FILE = BASE / 'data' / 'derived' / 'storm_trajectories.jsonl'
SIG_DIR = BASE / 'data' / 'derived' / 'transcript_signals'

DIVERGE_GAP_THRESHOLD = 0.35
MAX_PER_SECTION = 5


# ── data loading ──────────────────────────────────────────────────────────────

def load_trajectories() -> dict:
    """Load best trajectory record per actor (most windows = most complete)."""
    by_actor: dict = {}
    with open(TRAJ_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            actor = rec.get('actor')
            if not actor:
                continue
            if actor not in by_actor or rec.get('window_count', 0) > by_actor[actor].get('window_count', 0):
                by_actor[actor] = rec
    return by_actor


def load_all_signals() -> dict:
    """Load most recent transcript signal per actor."""
    by_actor: dict = {}
    for actor in sorted(set(p.stem.split('_')[0] for p in SIG_DIR.glob('*.json'))):
        paths = sorted(SIG_DIR.glob(f'{actor}_*.json'))
        if paths:
            by_actor[actor] = json.loads(paths[-1].read_text())
    return by_actor


# ── one-liner builders ────────────────────────────────────────────────────────

def _attention_liner(traj: dict, sig: dict | None) -> str:
    state = traj.get('state', '?')
    mom = traj.get('latest_momentum', 0)
    density = traj.get('latest_density', 0)
    prev = traj.get('previous_density') or density
    cs = (sig or {}).get('cross_signal', {})
    classification = cs.get('classification', '')
    persistence = cs.get('persistence', '')

    density_tag = '↑' if density > prev else '→'
    parts = [f"{state}  ·  momentum +{mom}  ·  density {density} ({density_tag})"]
    if classification in ('Reinforced', 'Formation'):
        pers = 'Sustained' if 'Sustained' in persistence else 'Early'
        parts.append(f"{classification} ({pers})")
    return '  ·  '.join(parts)


def _ignore_liner(traj: dict, sig: dict | None) -> str:
    state = traj.get('state', '?')
    accel = traj.get('latest_acceleration', 0)
    peak_ratio = traj.get('peak_ratio', 1.0)
    cs = (sig or {}).get('cross_signal', {})
    classification = cs.get('classification', '')

    tag = 'Breakdown confirmed' if classification == 'Breakdown' else f"density {int(peak_ratio * 100)}% of peak"
    return f"{state}  ·  acceleration {accel:+d}  ·  {tag}"


def _misleading_liner(traj: dict, sig: dict) -> str:
    cs = sig.get('cross_signal', {})
    persistence = cs.get('persistence', '')
    gap = cs.get('alignment_gap', 0.0)
    int_s = cs.get('internal_strength')
    ext_s = cs.get('external_strength')
    pers = 'Sustained' if 'Sustained' in persistence else 'Early'
    if int_s is not None and ext_s is not None:
        detail = f"internal {int_s:.2f} vs ecosystem {ext_s:.2f}"
    else:
        detail = "score data incomplete"
    return f"{pers} Diverging  ·  gap +{gap:.2f}  ·  {detail}"


def _watch_liner(traj: dict, sig: dict | None, reason: str) -> str:
    mom = traj.get('latest_momentum', 0)
    accel = traj.get('latest_acceleration', 0)
    density = traj.get('latest_density', 0)
    prev = traj.get('previous_density') or density
    state = traj.get('state', '?')
    cs = (sig or {}).get('cross_signal', {})
    gap = cs.get('alignment_gap')

    if reason == 'reversal':
        return f"momentum still negative but acceleration {accel:+d}  ·  deceleration of decline"
    elif reason == 'density_recovery':
        return f"density recovering {prev} → {density}  ·  momentum may follow"
    elif reason == 'formation':
        return f"new {state} state  ·  momentum +{mom}  ·  watch for confirmation"
    elif reason == 'narrowing':
        return f"divergence narrowing  ·  gap {gap:.2f}  ·  ecosystem may be catching up"
    return f"{state}  ·  transition signal pending"


# ── classification ────────────────────────────────────────────────────────────

def classify_actors(trajs: dict, sigs: dict) -> dict:
    """
    Assign each actor to exactly one compass section.
    Priority order: MISLEADING → ATTENTION → IGNORE → WATCH
    """
    assigned: set = set()
    sections: dict = {
        'attention': [],
        'ignore': [],
        'misleading': [],
        'watch': [],
    }

    # 1. MISLEADING — sustained divergence above gap threshold
    divergers = []
    for actor, sig in sigs.items():
        cs = sig.get('cross_signal', {})
        if cs.get('classification') != 'Diverging':
            continue
        gap = cs.get('alignment_gap', 0.0)
        if 'Sustained' in cs.get('persistence', '') and gap >= DIVERGE_GAP_THRESHOLD:
            divergers.append((-gap, actor))
    divergers.sort()
    for _, actor in divergers[:MAX_PER_SECTION]:
        traj = trajs.get(actor, {})
        sig = sigs[actor]
        sections['misleading'].append((actor, _misleading_liner(traj, sig)))
        assigned.add(actor)

    # 2. PAY ATTENTION — positive momentum, density holding, reinforced
    attention_cands = []
    for actor, traj in trajs.items():
        if actor in assigned:
            continue
        mom = traj.get('latest_momentum', 0)
        density = traj.get('latest_density', 0)
        prev = traj.get('previous_density') or density
        sig = sigs.get(actor)
        cs = (sig or {}).get('cross_signal', {})
        classification = cs.get('classification', '')

        if mom <= 0:
            continue
        if prev and density < prev * 0.7:      # density collapsing despite positive mom
            continue

        score = mom
        if density >= prev:
            score += 2
        if classification == 'Reinforced':
            score += 3
        elif classification == 'Formation':
            score += 1

        attention_cands.append((-score, actor))
    attention_cands.sort()
    for _, actor in attention_cands[:MAX_PER_SECTION]:
        traj = trajs[actor]
        sections['attention'].append((actor, _attention_liner(traj, sigs.get(actor))))
        assigned.add(actor)

    # 3. IGNORE — declining with no recovery signal
    ignore_cands = []
    for actor, traj in trajs.items():
        if actor in assigned:
            continue
        mom = traj.get('latest_momentum', 0)
        accel = traj.get('latest_acceleration', 0)
        state = traj.get('state', '')
        sig = sigs.get(actor)
        cs = (sig or {}).get('cross_signal', {})
        classification = cs.get('classification', '')

        # Reversal candidates stay out of IGNORE (go to WATCH instead)
        if mom < 0 and accel > 0:
            continue

        is_declining = (
            (mom < 0 and accel <= 0)
            or state == 'collapse'
            or classification == 'Breakdown'
        )
        if not is_declining:
            continue

        ignore_cands.append((accel, mom, actor))
    ignore_cands.sort()
    for _, _, actor in ignore_cands[:MAX_PER_SECTION]:
        traj = trajs[actor]
        sections['ignore'].append((actor, _ignore_liner(traj, sigs.get(actor))))
        assigned.add(actor)

    # 4. WATCH NEXT — reversals, formations, narrowing divergence
    watch_cands = []
    for actor, traj in trajs.items():
        if actor in assigned:
            continue
        mom = traj.get('latest_momentum', 0)
        accel = traj.get('latest_acceleration', 0)
        density = traj.get('latest_density', 0)
        prev = traj.get('previous_density') or density
        state = traj.get('state', '')
        sig = sigs.get(actor)
        cs = (sig or {}).get('cross_signal', {})
        classification = cs.get('classification', '')
        gap = cs.get('alignment_gap', 1.0)

        score = 0
        reason = None

        if mom < 0 and accel > 0:
            score = abs(accel) + 3
            reason = 'reversal'
        elif density > prev and mom <= 0:
            score = (density - prev) + 1
            reason = 'density_recovery'
        elif state in ('emerging', 'growing') and mom > 0:
            score = mom + 1
            reason = 'formation'
        elif classification == 'Diverging' and gap < DIVERGE_GAP_THRESHOLD + 0.15:
            score = 1
            reason = 'narrowing'

        if reason:
            watch_cands.append((-score, reason, actor))
    watch_cands.sort()
    for _, reason, actor in watch_cands[:MAX_PER_SECTION]:
        traj = trajs[actor]
        sections['watch'].append((actor, _watch_liner(traj, sigs.get(actor), reason)))
        assigned.add(actor)

    return sections


# ── rendering ─────────────────────────────────────────────────────────────────

def render_text(sections: dict, date: str) -> str:
    w = 64
    lines = [
        '╔' + '═' * w + '╗',
        '║' + f'  TOPICSPACE COMPASS  ·  {date}'.ljust(w) + '║',
        '╚' + '═' * w + '╝',
        '',
    ]

    defs = [
        ('attention',  '1  PAY ATTENTION'),
        ('ignore',     '2  IGNORE FOR NOW'),
        ('misleading', '3  TREAT WITH CAUTION'),
        ('watch',      '4  WATCH NEXT'),
    ]

    for key, header in defs:
        items = sections[key]
        lines.append(header)
        lines.append('─' * len(header))
        if not items:
            lines.append('   (none)')
        else:
            for actor, liner in items:
                lines.append(f'   {actor:<8}  {liner}')
        lines.append('')

    return '\n'.join(lines)


def render_json(sections: dict, date: str) -> str:
    return json.dumps({
        'date': date,
        'compass': {
            k: [{'actor': a, 'signal': s} for a, s in v]
            for k, v in sections.items()
        }
    }, indent=2)


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    import argparse
    global DIVERGE_GAP_THRESHOLD

    parser = argparse.ArgumentParser(description='Generate Compass-format signal output')
    parser.add_argument('--json', action='store_true', help='Output JSON instead of text')
    parser.add_argument('--out', help='Write output to file instead of stdout')
    parser.add_argument('--gap-threshold', type=float, default=DIVERGE_GAP_THRESHOLD,
                        help=f'Alignment gap threshold for CAUTION section (default {DIVERGE_GAP_THRESHOLD})')
    args = parser.parse_args()
    DIVERGE_GAP_THRESHOLD = args.gap_threshold

    trajs = load_trajectories()
    sigs = load_all_signals()

    date_str = datetime.today().strftime('%Y-%m-%d')
    sections = classify_actors(trajs, sigs)

    output = render_json(sections, date_str) if args.json else render_text(sections, date_str)

    if args.out:
        Path(args.out).write_text(output)
        print(f'Written to {args.out}')
    else:
        print(output)


if __name__ == '__main__':
    main()
