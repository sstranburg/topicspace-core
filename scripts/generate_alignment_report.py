#!/usr/bin/env python3
"""
Narrative Alignment Report — TopicSpace

Reads all transcript signal JSONs, computes internal/external narrative
strength scores, and produces a cross-actor alignment research table.

Usage:
    python scripts/generate_alignment_report.py
    python scripts/generate_alignment_report.py --actors META MSFT NVDA
    python scripts/generate_alignment_report.py --out alignment_report.md
"""

import argparse
import json
import pathlib
import sys
import textwrap
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

BASE_DIR  = pathlib.Path(__file__).parent.parent
SIG_DIR   = BASE_DIR / 'data' / 'derived' / 'transcript_signals'

# ── Re-use scoring from extract_transcript_signals ───────────────────────────
_TONE_SCORE: dict[str, float] = {
    'confident': 1.00, 'optimistic': 0.85,
    'neutral':   0.50,
    'cautious':  0.30, 'defensive': 0.15, 'uncertain': 0.15,
}
_PRESSURE_SCORE: dict[str, float] = {'low': 1.0, 'medium': 0.5, 'high': 0.0}


def _compute_internal_strength(signals: dict) -> float:
    tone    = (signals.get('management_tone') or 'neutral').lower()
    tone_s  = _TONE_SCORE.get(tone, 0.50)

    fwd      = signals.get('forward_signals', [])
    n_raises = sum(1 for f in fwd if f.get('direction') == 'raise')
    n_cuts   = sum(1 for f in fwd if f.get('direction') == 'cut')
    guidance_s = min(1.0, max(0.0, 0.5 + 0.15 * n_raises - 0.25 * n_cuts))

    themes  = signals.get('themes', [])
    n_pos   = sum(1 for t in themes if t.get('tone') == 'positive')
    n_neg   = sum(1 for t in themes if t.get('tone') in ('negative', 'cautious'))
    theme_s = min(1.0, max(0.0, (n_pos - 0.5 * n_neg) / max(len(themes), 1)))

    pressure   = (signals.get('analyst_pressure') or 'medium').lower()
    pressure_s = _PRESSURE_SCORE.get(pressure, 0.5)

    return round(
        0.35 * tone_s + 0.30 * guidance_s + 0.20 * theme_s + 0.15 * pressure_s,
        3,
    )


def _compute_external_strength(eco: dict) -> float:
    peak_ratio = float(eco.get('peak_ratio', 0) or 0)
    accel      = float(eco.get('acceleration', 0) or 0)
    accel_s    = min(1.0, max(0.0, (accel + 200) / 400))
    consec     = int(eco.get('consec_decline', 0) or 0)
    persist_s  = max(0.0, 1.0 - 0.25 * consec)
    density    = min(int(eco.get('density', 0) or 0), 50) / 50
    return round(
        0.35 * peak_ratio + 0.30 * accel_s + 0.20 * persist_s + 0.15 * density,
        3,
    )


# ── Persistence logic ─────────────────────────────────────────────────────────
def _persistence_label(history: list[dict]) -> str:
    """Given actor history sorted oldest→newest, return persistence for latest."""
    if len(history) < 2:
        return 'Early'
    current = history[-1]['classification']
    matching = sum(1 for h in history[:-1] if h['classification'] == current)
    if matching >= 1:
        return f'Sustained ({matching + 1}+ periods)'
    return 'Early'


# ── Watch interpretation ──────────────────────────────────────────────────────
def _next_watch(classification: str, persistence: str, gap: float, eco: dict) -> str:
    sustained = persistence.startswith('Sustained')
    c = classification

    if c == 'Diverging':
        if sustained:
            if gap > 0.5:
                return 'Watch for guidance cut or forced capex moderation'
            return 'Watch management tone for first sign of ecosystem acknowledgment'
        return 'Watch next quarter — confirm or correct divergence'

    if c == 'Reinforced':
        if gap < 0.1:
            return 'Watch for ecosystem saturation or peak narrative density'
        return 'Watch for demand pull-forward or capacity ceiling signals'

    if c == 'Formation':
        return 'Watch management tone shift — ecosystem recovery may not yet be priced in'

    if c == 'Breakdown':
        return 'Watch for capitulation in guidance or strategic pivot language'

    return 'Watch next period for signal resolution'


# ── Load all signals ──────────────────────────────────────────────────────────
def load_all(actors: list[str] | None = None) -> dict[str, list[dict]]:
    """Return {actor: [record, ...]} sorted oldest→newest."""
    by_actor: dict[str, list[dict]] = defaultdict(list)

    for path in sorted(SIG_DIR.glob('*.json')):
        # stem format: {ACTOR}_{DATE}
        parts = path.stem.split('_', 1)
        if len(parts) != 2:
            continue
        ticker, date = parts
        if actors and ticker not in actors:
            continue

        try:
            data = json.loads(path.read_text())
        except Exception:
            continue

        xs      = data.get('cross_signal', {})
        eco     = xs.get('ecosystem') or {}
        int_s   = xs.get('internal_strength') or _compute_internal_strength(data)
        ext_s   = xs.get('external_strength') or _compute_external_strength(eco)
        gap     = xs.get('alignment_gap')
        if gap is None:
            gap = round(int_s - ext_s, 3)

        by_actor[ticker].append({
            'actor':             ticker,
            'date':              date,
            'tone':              data.get('management_tone', '?'),
            'pressure':          data.get('analyst_pressure', '?'),
            'confidence':        data.get('confidence_score', 0.0),
            'classification':    xs.get('classification', 'Unknown'),
            'internal_strength': int_s,
            'external_strength': ext_s,
            'alignment_gap':     gap,
            'eco':               eco,
            'insight':           xs.get('insight', ''),
        })

    # Sort each actor's records by date
    for ticker in by_actor:
        by_actor[ticker].sort(key=lambda r: r['date'])

    return dict(by_actor)


# ── Outcome classification ────────────────────────────────────────────────────
def _classify_outcome(cur_cls: str, nxt_cls: str,
                      d_int: float, d_ext: float) -> str:
    """Name the transition between two consecutive alignment states."""
    if cur_cls == nxt_cls == 'Reinforced':
        return 'Reinforcement continues'
    if cur_cls == nxt_cls == 'Diverging':
        return 'Continued divergence'
    if cur_cls == nxt_cls == 'Breakdown':
        return 'Breakdown deepens'
    if cur_cls == nxt_cls == 'Formation':
        return 'Formation progressing'

    if cur_cls == 'Diverging' and nxt_cls == 'Reinforced':
        return 'Re-acceleration (external recovered)'
    if cur_cls == 'Reinforced' and nxt_cls == 'Diverging':
        return 'Divergence onset'
    if nxt_cls == 'Breakdown':
        return 'Breakdown (internal weakened)'
    if cur_cls == 'Breakdown' and nxt_cls == 'Formation':
        return 'Recovery signal (eco strengthening)'
    if cur_cls == 'Formation' and nxt_cls == 'Reinforced':
        return 'Formation resolved'

    return f'{cur_cls} → {nxt_cls}'


def _build_transitions(by_actor: dict[str, list[dict]]) -> list[dict]:
    """Return one dict per consecutive period pair, sorted by actor then date."""
    rows = []
    for ticker, history in sorted(by_actor.items()):
        for i in range(len(history) - 1):
            cur = history[i]
            nxt = history[i + 1]
            d_int = round(nxt['internal_strength'] - cur['internal_strength'], 3)
            d_ext = round(nxt['external_strength'] - cur['external_strength'], 3)
            outcome = _classify_outcome(
                cur['classification'], nxt['classification'], d_int, d_ext
            )
            rows.append({
                'actor':       ticker,
                'period':      cur['date'],
                'state':       cur['classification'],
                'persistence': _persistence_label(history[:i + 1]),
                'next_period': nxt['date'],
                'next_state':  nxt['classification'],
                'd_int':       d_int,
                'd_ext':       d_ext,
                'outcome':     outcome,
            })
    return rows


# ── Formatting helpers ────────────────────────────────────────────────────────
def _bar(val: float, width: int = 10) -> str:
    filled = round(val * width)
    return '█' * filled + '░' * (width - filled)


def _gap_arrow(gap: float) -> str:
    if gap > 0.3:  return '↑↑ company leads'
    if gap > 0.1:  return '↑  company ahead'
    if gap > -0.1: return '↔  aligned'
    if gap > -0.3: return '↓  ecosystem leads'
    return             '↓↓ ecosystem far ahead'


# ── Report generation ─────────────────────────────────────────────────────────
def generate_report(by_actor: dict[str, list[dict]]) -> str:
    lines: list[str] = []

    lines.append('═' * 72)
    lines.append('NARRATIVE ALIGNMENT REPORT — TopicSpace')
    lines.append('═' * 72)
    lines.append('')

    # ── Research Table ────────────────────────────────────────────────────────
    lines.append('CROSS-ACTOR ALIGNMENT TABLE  (most recent period per actor)')
    lines.append('─' * 72)
    col = '{:<6}  {:>5}  {:>5}  {:>8}  {:>5}  {:<26}  {}'
    lines.append(col.format('ACTOR', 'INT', 'EXT', 'GAP', 'CONF', 'ALIGNMENT STATE', 'PERSISTENCE'))
    lines.append('─' * 72)

    all_records = []
    for ticker, history in sorted(by_actor.items()):
        latest   = history[-1]
        persist  = _persistence_label(history)
        cls      = latest['classification']
        gap      = latest['alignment_gap']
        state    = f'{cls}'
        lines.append(col.format(
            ticker,
            f"{latest['internal_strength']:.2f}",
            f"{latest['external_strength']:.2f}",
            f"{gap:+.2f}",
            f"{latest['confidence']:.2f}",
            state,
            persist,
        ))
        all_records.append((ticker, history, latest, persist))

    lines.append('─' * 72)
    lines.append('INT = internal narrative strength  EXT = external/ecosystem strength')
    lines.append('GAP = INT − EXT  (positive = company outpacing ecosystem)')
    lines.append('')

    # ── Per-actor detail blocks ───────────────────────────────────────────────
    lines.append('')
    lines.append('PER-ACTOR DETAIL')
    lines.append('═' * 72)

    for ticker, history, latest, persist in all_records:
        cls      = latest['classification']
        gap      = latest['alignment_gap']
        eco      = latest['eco']
        watch    = _next_watch(cls, persist, gap, eco)

        lines.append('')
        lines.append(f'▌ {ticker}  —  {cls}  ({persist})')
        lines.append('─' * 40)

        # Period history strip
        if len(history) > 1:
            strip = '  '.join(
                f"{r['date']}:{r['classification'][0]}"
                for r in history
            )
            lines.append(f'  History:   {strip}')

        lines.append(f"  Internal:  {_bar(latest['internal_strength'])}  {latest['internal_strength']:.2f}  ({latest['tone']}, pressure={latest['pressure']})")
        lines.append(f"  External:  {_bar(latest['external_strength'])}  {latest['external_strength']:.2f}  (eco={eco.get('state','?')}, accel={eco.get('acceleration',0):+d}, peak={eco.get('peak_ratio',0):.0%})")
        lines.append(f'  Gap:       {gap:+.2f}  {_gap_arrow(gap)}')
        lines.append(f'  Confidence:{latest["confidence"]:.2f}')
        lines.append('')
        lines.append('  Interpretation:')
        for l in textwrap.wrap(latest['insight'], width=66):
            lines.append(f'    {l}')
        lines.append('')
        lines.append(f'  Watch next:  {watch}')

    # ── Outcome Tracking ──────────────────────────────────────────────────────
    transitions = _build_transitions(by_actor)
    if transitions:
        lines.append('')
        lines.append('')
        lines.append('OUTCOME TRACKING  (period-over-period transitions)')
        lines.append('─' * 72)
        tcol = '{:<6}  {:<11}  {:<12}  {:<11}  {:<12}  {:>5}  {:>5}  {}'
        lines.append(tcol.format(
            'ACTOR', 'PERIOD', 'STATE', 'NEXT PERIOD', 'NEXT STATE',
            'ΔINT', 'ΔEXT', 'OUTCOME',
        ))
        lines.append('─' * 72)
        for t in transitions:
            lines.append(tcol.format(
                t['actor'],
                t['period'],
                t['state'],
                t['next_period'],
                t['next_state'],
                f"{t['d_int']:+.2f}",
                f"{t['d_ext']:+.2f}",
                t['outcome'],
            ))
        lines.append('─' * 72)

        # Pattern summary — count outcomes
        from collections import Counter
        counts = Counter(t['outcome'] for t in transitions)
        lines.append('')
        lines.append('Pattern summary:')
        for outcome, n in counts.most_common():
            lines.append(f'  {n:2d}×  {outcome}')

    lines.append('')
    lines.append('═' * 72)
    return '\n'.join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description='Generate narrative alignment report')
    parser.add_argument('--actors', nargs='+', metavar='TICKER',
                        help='Filter to specific actors (default: all)')
    parser.add_argument('--out', metavar='FILE',
                        help='Write report to file instead of stdout')
    args = parser.parse_args()

    if not SIG_DIR.exists():
        print(f'No signal directory found at {SIG_DIR}', file=sys.stderr)
        sys.exit(1)

    by_actor = load_all(actors=args.actors)
    if not by_actor:
        print('No signal files found.', file=sys.stderr)
        sys.exit(1)

    report = generate_report(by_actor)

    if args.out:
        pathlib.Path(args.out).write_text(report)
        print(f'Report written to {args.out}')
    else:
        print(report)


if __name__ == '__main__':
    main()
