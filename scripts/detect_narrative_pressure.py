#!/usr/bin/env python3
"""
Detect narrative pressure across actor and ecosystem storms.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from narrative_pressure import compute_pressure_score, interpret_pressure, compute_velocity


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
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data' / 'derived'

    actor_storms = load_jsonl(data_dir / 'actor_storms.jsonl')
    actor_summaries = load_jsonl(data_dir / 'actor_storm_summaries.jsonl')
    eco_storms = load_jsonl(data_dir / 'ecosystem_storms.jsonl')
    trajectories = load_jsonl(data_dir / 'storm_trajectories.jsonl')

    # Build event_id -> timestamp lookup from normalized events
    norm_events = load_jsonl(base_dir / 'data' / 'normalized' / 'tech_ecosystem_filtered.jsonl')
    event_ts_map = {e.get('event_id', ''): e.get('timestamp', '') for e in norm_events}

    # Shared reference time for report_latest anchor mode
    from datetime import datetime
    def _parse_ts(ts):
        ts = ts.rstrip('Z').replace('+00:00Z', '+00:00')
        if not ts.endswith('+00:00'):
            ts += '+00:00'
        return datetime.fromisoformat(ts)
    all_ts = [_parse_ts(ts) for ts in event_ts_map.values() if ts]
    report_reference_time = max(all_ts) if all_ts else None

    # Leadership for leader_actor flag
    leader_actors = set()
    leadership_path = data_dir / 'narrative_leadership.json'
    if leadership_path.exists():
        with open(leadership_path) as f:
            for r in json.load(f):
                if r.get('role') == 'leader':
                    leader_actors.add(r['actor'])

    # Merge summaries
    summary_map = {s['storm_id']: s for s in actor_summaries}
    for storm in actor_storms:
        if storm['storm_id'] in summary_map:
            storm.update(summary_map[storm['storm_id']])

    # Enrich with trajectory metrics
    for storm in actor_storms:
        matching_traj = None
        for traj in trajectories:
            if traj['actor'] == storm['actor']:
                if matching_traj is None or traj['total_events'] > matching_traj.get('total_events', 0):
                    matching_traj = traj
        if matching_traj:
            storm['momentum'] = matching_traj.get('latest_momentum', 0)
            storm['acceleration'] = matching_traj.get('latest_acceleration', 0)
            storm['peak_ratio'] = matching_traj.get('peak_ratio', 0)

    # Compute pressure
    results = []
    state_modifier_counts = Counter()

    for storm in actor_storms:
        p = compute_pressure_score(storm, storm_type='actor')
        p['pressure_interpretation'] = interpret_pressure(storm, p)
        p['storm_id'] = storm['storm_id']
        p['label'] = storm.get('display_headline', storm.get('headline', 'Unnamed'))
        p['actor'] = storm.get('actor', 'unknown')
        p['state'] = storm.get('state', 'unknown')
        p['event_count'] = storm.get('event_count', 0)
        p['leader_actor'] = storm.get('actor', '') in leader_actors
        timestamps = [event_ts_map[eid] for eid in storm.get('event_ids', []) if eid in event_ts_map]
        p.update(compute_velocity(storm, timestamps, storm_type='actor'))
        results.append(p)
        state_modifier_counts[storm.get('state', 'unknown')] += 1

    for storm in eco_storms:
        p = compute_pressure_score(storm, storm_type='ecosystem')
        p['pressure_interpretation'] = interpret_pressure(storm, p)
        p['storm_id'] = storm['storm_id']
        p['label'] = storm.get('display_headline', storm.get('headline', 'Unnamed'))
        p['actor'] = 'ecosystem'
        p['state'] = storm.get('state', 'unknown')
        p['event_count'] = storm.get('event_count', 0)
        p['leader_actor'] = False
        timestamps = [event_ts_map[eid] for eid in storm.get('event_ids', []) if eid in event_ts_map]
        p.update(compute_velocity(storm, timestamps, storm_type='ecosystem',
                                  anchor_mode='report_latest',
                                  report_reference_time=report_reference_time))
        results.append(p)
        state_modifier_counts[storm.get('state', 'unknown')] += 1

    # Save
    output_path = data_dir / 'narrative_pressure.jsonl'
    with open(output_path, 'w') as f:
        for r in results:
            f.write(json.dumps(r) + '\n')

    # Diagnostics
    high = [r for r in results if r['pressure_level'] == 'high']
    building = [r for r in results if r['pressure_level'] == 'building']
    low = [r for r in results if r['pressure_level'] == 'low']

    buckets = [0] * 5
    for r in results:
        s = r['pressure_score']
        if s < 0.20: buckets[0] += 1
        elif s < 0.40: buckets[1] += 1
        elif s < 0.60: buckets[2] += 1
        elif s < 0.80: buckets[3] += 1
        else: buckets[4] += 1

    print("Narrative Pressure Tuning Diagnostics")
    print("-------------------------------------")
    print(f"Storms analyzed: {len(results)}")

    print("\nPressure buckets:")
    for i, (lo, hi) in enumerate([(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1)]):
        print(f"  {lo:.2f}–{hi:.2f}: {buckets[i]}")

    print(f"\nLevels:")
    print(f"  High: {len(high)}")
    print(f"  Building: {len(building)}")
    print(f"  Low: {len(low)}")

    print(f"\nState modifiers applied:")
    for state in ['emerging', 'growing', 'volatile', 'peaking', 'stable', 'fading']:
        print(f"  {state}: {state_modifier_counts.get(state, 0)} storms")

    print("\nTop 10 pressure storms:")
    for i, r in enumerate(sorted(results, key=lambda x: x['pressure_score'], reverse=True)[:10], 1):
        print(f"  {i:2d}. {r['storm_id']:35s} | {r['label'][:45]:45s} | {r['state']:10s} | {r['pressure_score']:.3f} | {r['pressure_level']}")

    print(f"\nTop high-pressure narratives:")
    for i, r in enumerate(sorted(high, key=lambda x: x['pressure_score'], reverse=True)[:5], 1):
        print(f"  {i}. {r['label'][:60]} ({r['actor']}) score={r['pressure_score']:.3f}")

    print(f"\nTop building-pressure narratives:")
    for i, r in enumerate(sorted(building, key=lambda x: x['pressure_score'], reverse=True)[:5], 1):
        print(f"  {i}. {r['label'][:60]} ({r['actor']}) score={r['pressure_score']:.3f}")

    print(f"\nSaved to {output_path}")

    print("\nVelocity Validation Log")
    print("-----------------------")
    print(f"  {'storm_id':<35} {'type':<10} {'window':<6} {'anchor':<14} {'prev':>6} {'last':>6} {'score':>7} {'state':<14} {'confidence'}")
    for r in sorted(results, key=lambda x: x.get('velocity_score', 0), reverse=True):
        stype = 'ecosystem' if r['storm_id'].startswith('eco_') else 'actor'
        ref_ts = r.get('velocity_reference_time', '')[:10]
        anchor = f"{r.get('velocity_anchor_mode', '?')}({ref_ts})"
        print(f"  {r['storm_id']:<35} {stype:<10} {r.get('velocity_window', '?'):<6} {anchor:<30} "
              f"{r.get('events_prev_48h', 0):>6} {r.get('events_last_48h', 0):>6} "
              f"{r.get('velocity_score', 0):>7.3f} {r.get('velocity_state', 'N/A'):<14} {r.get('velocity_confidence', 'N/A')}")

    # Velocity calibration summary
    actor_results = [r for r in results if not r['storm_id'].startswith('eco_')]
    eco_results   = [r for r in results if r['storm_id'].startswith('eco_')]

    def _velocity_summary(group, label):
        n = len(group)
        if n == 0:
            print(f"\n  {label}: no storms")
            return
        scores = [r.get('velocity_score', 0) for r in group]
        scores_sorted = sorted(scores)
        avg = sum(scores) / n
        mid = n // 2
        median = scores_sorted[mid] if n % 2 else (scores_sorted[mid - 1] + scores_sorted[mid]) / 2

        state_counts = Counter(r.get('velocity_state', 'unknown') for r in group)
        conf_counts  = Counter(r.get('velocity_confidence', 'unknown') for r in group)
        prev_zero    = sum(1 for r in group if r.get('events_prev_48h', 0) == 0 and r.get('events_last_48h', 0) > 0)

        print(f"\n  {label} ({n} storms)")
        print(f"    avg velocity_score : {avg:.3f}")
        print(f"    median             : {median:.3f}")
        print(f"    prev=0 & last>0    : {prev_zero}")
        print(f"    state breakdown:")
        for state in ('accelerating', 'stable', 'declining'):
            c = state_counts.get(state, 0)
            print(f"      {state:<14} {c:>3}  ({100*c/n:.0f}%)")
        print(f"    confidence breakdown:")
        for conf in ('high', 'medium', 'low'):
            c = conf_counts.get(conf, 0)
            print(f"      {conf:<8} {c:>3}  ({100*c/n:.0f}%)")

        accel   = sorted([r for r in group if r.get('velocity_state') == 'accelerating'],
                         key=lambda r: -r.get('velocity_score', 0))
        decline = sorted([r for r in group if r.get('velocity_state') == 'declining'],
                         key=lambda r: r.get('velocity_score', 0))
        print(f"    top 5 accelerating:")
        for r in accel[:5]:
            print(f"      {r['storm_id']:<35} score={r.get('velocity_score',0):>7.3f}  conf={r.get('velocity_confidence','?')}")
        print(f"    top 5 declining:")
        for r in decline[:5]:
            print(f"      {r['storm_id']:<35} score={r.get('velocity_score',0):>7.3f}  conf={r.get('velocity_confidence','?')}")

    def _crosstab(group, label):
        states = ('accelerating', 'stable', 'declining')
        confs  = ('high', 'medium', 'low')
        print(f"\n  Cross-tab: {label}")
        print(f"    {'state':<14} {'high':>6} {'medium':>8} {'low':>6}")
        for state in states:
            row = {c: sum(1 for r in group
                          if r.get('velocity_state') == state
                          and r.get('velocity_confidence') == c)
                   for c in confs}
            print(f"    {state:<14} {row['high']:>6} {row['medium']:>8} {row['low']:>6}")

    print("\n" + "="*60)
    print("VELOCITY CALIBRATION SUMMARY")
    print("="*60)
    _velocity_summary(actor_results, 'Actor storms')
    _velocity_summary(eco_results,   'Ecosystem storms')
    print("\n  Cross-tabs (state × confidence)")
    _crosstab(actor_results, 'actor storms')
    _crosstab(eco_results,   'ecosystem storms')

    # Ecosystem anchor comparison diagnostic
    print("\n" + "="*60)
    print("ECOSYSTEM VELOCITY ANCHOR COMPARISON")
    print("  storm_latest vs report_latest for ecosystem storms")
    print("="*60)

    sl_col = f"{'prev':>6} {'last':>6} {'score':>7} {'state':<14}"
    rl_col = f"{'prev':>6} {'last':>6} {'score':>7} {'state':<14}"
    print(f"  {'storm_id':<35}  [storm_latest] {sl_col}  [report_latest] {rl_col}  {'conf'}")

    state_changes = 0
    accel_to_other = 0
    score_deltas = []

    for storm in eco_storms:
        eid_list = storm.get('event_ids', [])
        timestamps = [event_ts_map[eid] for eid in eid_list if eid in event_ts_map]

        sl = compute_velocity(storm, timestamps, storm_type='ecosystem',
                              anchor_mode='storm_latest')
        rl = compute_velocity(storm, timestamps, storm_type='ecosystem',
                              anchor_mode='report_latest',
                              report_reference_time=report_reference_time)

        changed = sl['velocity_state'] != rl['velocity_state']
        if changed:
            state_changes += 1
            if sl['velocity_state'] == 'accelerating':
                accel_to_other += 1

        score_deltas.append(abs(sl['velocity_score'] - rl['velocity_score']))

        marker = ' *' if changed else '  '
        print(f"  {storm['storm_id']:<35}{marker}"
              f"  {sl['events_prev_48h']:>6} {sl['events_last_48h']:>6} "
              f"{sl['velocity_score']:>7.3f} {sl['velocity_state']:<14}"
              f"  {rl['events_prev_48h']:>6} {rl['events_last_48h']:>6} "
              f"{rl['velocity_score']:>7.3f} {rl['velocity_state']:<14}"
              f"  {rl['velocity_confidence']}")

    avg_delta = sum(score_deltas) / len(score_deltas) if score_deltas else 0.0
    print(f"\n  Storms changing velocity_state : {state_changes} / {len(eco_storms)}")
    print(f"  accelerating → other           : {accel_to_other}")
    print(f"  avg |score delta|              : {avg_delta:.3f}")

    # Window expansion diagnostic: 7d vs 14d for ecosystem storms (report_latest anchor)
    print("\n" + "="*60)
    print("ECOSYSTEM WINDOW EXPANSION: 7d → 14d (report_latest)")
    print("="*60)
    print(f"  {'storm_id':<35}  {'score_7d':>8} {'state_7d':<14} {'conf_7d':<8}"
          f"  {'score_14d':>9} {'state_14d':<14} {'conf_14d'}")

    n_score_changed = 0
    n_state_changed = 0
    n_conf_changed  = 0

    for storm in eco_storms:
        timestamps = [event_ts_map[eid] for eid in storm.get('event_ids', []) if eid in event_ts_map]

        # Temporarily override window by patching timedelta directly
        from datetime import timedelta
        def _vel(window_days):
            """Compute velocity with a specific window size, report_latest anchor."""
            from datetime import datetime
            def parse_ts(ts):
                ts = ts.rstrip('Z').replace('+00:00Z', '+00:00')
                if not ts.endswith('+00:00'):
                    ts += '+00:00'
                return datetime.fromisoformat(ts)
            parsed = []
            for ts in timestamps:
                try:
                    parsed.append(parse_ts(ts))
                except (ValueError, AttributeError):
                    pass
            if not parsed:
                return {'velocity_score': 0.0, 'velocity_state': 'stable',
                        'velocity_confidence': 'low', 'events_last_48h': 0, 'events_prev_48h': 0}
            window   = timedelta(days=window_days)
            ref_time = report_reference_time
            last  = sum(1 for t in parsed if t > ref_time - window)
            prev  = sum(1 for t in parsed if ref_time - 2*window < t <= ref_time - window)
            if last == 0 and prev == 0:
                score, state = 0.0, 'stable'
            elif prev == 0:
                score, state = 1.0, 'accelerating'
            else:
                score = round((last - prev) / prev, 4)
                state = 'accelerating' if score > 0.50 else ('declining' if score < -0.20 else 'stable')
            total = last + prev
            if prev == 0 and last > 0:
                conf = 'high' if last >= 6 else 'low'
            elif total >= 6 and prev >= 2:
                conf = 'high'
            elif total >= 4:
                conf = 'medium'
            else:
                conf = 'low'
            return {'velocity_score': score, 'velocity_state': state,
                    'velocity_confidence': conf, 'events_last_48h': last, 'events_prev_48h': prev}

        v7  = _vel(7)
        v14 = _vel(14)

        score_changed = v7['velocity_score'] != v14['velocity_score']
        state_changed = v7['velocity_state'] != v14['velocity_state']
        conf_changed  = v7['velocity_confidence'] != v14['velocity_confidence']
        if score_changed: n_score_changed += 1
        if state_changed: n_state_changed += 1
        if conf_changed:  n_conf_changed  += 1

        marker = ' *' if state_changed else '  '
        print(f"  {storm['storm_id']:<35}{marker}"
              f"  {v7['velocity_score']:>8.3f} {v7['velocity_state']:<14} {v7['velocity_confidence']:<8}"
              f"  {v14['velocity_score']:>9.3f} {v14['velocity_state']:<14} {v14['velocity_confidence']}")

    print(f"\n  score changed  : {n_score_changed} / {len(eco_storms)}")
    print(f"  state changed  : {n_state_changed} / {len(eco_storms)}")
    print(f"  conf changed   : {n_conf_changed} / {len(eco_storms)}")


if __name__ == '__main__':
    main()
