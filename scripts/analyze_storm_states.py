#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sue/Documents/git/storm')

import json
from collections import defaultdict, Counter

print("="*70)
print("STORM LIFECYCLE ANALYSIS")
print("="*70)

# Load trajectories
print("\nLoading trajectories...")
trajectories = []
with open("data/derived/storm_trajectories.jsonl", 'r') as f:
    for line in f:
        trajectories.append(json.loads(line))

print(f"Loaded {len(trajectories)} trajectories")

# Analyze state distribution
print("\n" + "="*70)
print("STATE DISTRIBUTION")
print("="*70)

state_counts = Counter(t['state'] for t in trajectories)
for state in sorted(state_counts.keys()):
    count = state_counts[state]
    pct = 100 * count / len(trajectories)
    print(f"{state:12s}: {count:2d} ({pct:5.1f}%)")

# Analyze state transitions
print("\n" + "="*70)
print("STATE TRANSITIONS")
print("="*70)

transitions = []
for traj in trajectories:
    history = traj['state_history']
    for i in range(len(history) - 1):
        transitions.append((history[i], history[i+1]))

transition_counts = Counter(transitions)
print(f"\nTotal transitions observed: {len(transitions)}")
print(f"\nTop 10 transitions:")
for (from_state, to_state), count in transition_counts.most_common(10):
    print(f"  {from_state:12s} → {to_state:12s}: {count:3d}")

# Analyze lifecycle patterns
print("\n" + "="*70)
print("LIFECYCLE PATTERNS")
print("="*70)

lifecycle_patterns = defaultdict(list)
for traj in trajectories:
    history = traj['state_history']
    pattern = ' → '.join(history)
    lifecycle_patterns[pattern].append(traj['trajectory_id'])

print(f"\nUnique lifecycle patterns: {len(lifecycle_patterns)}")
print(f"\nTop 10 most common patterns:")
sorted_patterns = sorted(lifecycle_patterns.items(), key=lambda x: len(x[1]), reverse=True)
for i, (pattern, traj_ids) in enumerate(sorted_patterns[:10], 1):
    print(f"\n{i}. {pattern}")
    print(f"   Count: {len(traj_ids)}")
    print(f"   Trajectories: {', '.join(traj_ids[:3])}{'...' if len(traj_ids) > 3 else ''}")

# Analyze trajectories by actor
print("\n" + "="*70)
print("STATE BY ACTOR")
print("="*70)

actor_states = defaultdict(list)
for traj in trajectories:
    actor_states[traj['actor']].append(traj['state'])

for actor in sorted(actor_states.keys()):
    states = actor_states[actor]
    state_dist = Counter(states)
    print(f"\n{actor}:")
    for state, count in sorted(state_dist.items()):
        print(f"  {state}: {count}")

# Analyze peak ratios
print("\n" + "="*70)
print("PEAK RATIO ANALYSIS")
print("="*70)

peak_ratios = [(t['trajectory_id'], t['peak_ratio'], t['state']) for t in trajectories]
peak_ratios.sort(key=lambda x: x[1])

print(f"\nLowest peak ratios (potential fading storms):")
for traj_id, ratio, state in peak_ratios[:5]:
    print(f"  {traj_id:20s}: {ratio:.2f} (state: {state})")

print(f"\nHighest peak ratios (at or near peak):")
for traj_id, ratio, state in peak_ratios[-5:]:
    print(f"  {traj_id:20s}: {ratio:.2f} (state: {state})")

# Analyze acceleration
print("\n" + "="*70)
print("ACCELERATION ANALYSIS")
print("="*70)

acceleration_data = [(t['trajectory_id'], t.get('latest_acceleration'), t['state'], t['latest_momentum']) 
                     for t in trajectories if t.get('latest_acceleration') is not None]
acceleration_data.sort(key=lambda x: x[1], reverse=True)

print(f"\nTop positive acceleration (strengthening):")
for traj_id, accel, state, momentum in acceleration_data[:5]:
    print(f"  {traj_id:20s}: {accel:+4d} (momentum: {momentum:+4d}, state: {state})")

print(f"\nTop negative acceleration (weakening):")
for traj_id, accel, state, momentum in acceleration_data[-5:]:
    print(f"  {traj_id:20s}: {accel:+4d} (momentum: {momentum:+4d}, state: {state})")

# Analyze state reasons
print("\n" + "="*70)
print("STATE REASONS")
print("="*70)

reason_counts = Counter(t['state_reason'] for t in trajectories)
for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {reason:25s}: {count:2d}")

# Generate lifecycle report
print("\n" + "="*70)
print("GENERATING LIFECYCLE REPORT")
print("="*70)

with open("STORM_LIFECYCLE_REPORT.md", 'w') as f:
    f.write("# Storm Lifecycle Analysis Report\n\n")
    f.write(f"Generated from {len(trajectories)} trajectories\n\n")
    
    f.write("## State Distribution\n\n")
    for state in sorted(state_counts.keys()):
        count = state_counts[state]
        pct = 100 * count / len(trajectories)
        f.write(f"- **{state}**: {count} ({pct:.1f}%)\n")
    
    f.write("\n## State Transitions\n\n")
    f.write(f"Total transitions observed: {len(transitions)}\n\n")
    f.write("### Transition Frequency Table\n\n")
    f.write("| From State | To State | Count |\n")
    f.write("|------------|----------|-------|\n")
    for (from_state, to_state), count in transition_counts.most_common(15):
        f.write(f"| {from_state} | {to_state} | {count} |\n")
    
    f.write("\n## Lifecycle Patterns\n\n")
    f.write(f"Unique patterns: {len(lifecycle_patterns)}\n\n")
    for i, (pattern, traj_ids) in enumerate(sorted_patterns[:15], 1):
        f.write(f"\n### Pattern {i}: {pattern}\n\n")
        f.write(f"**Count**: {len(traj_ids)}\n\n")
        f.write(f"**Trajectories**: {', '.join(traj_ids)}\n")
    
    f.write("\n## Example Trajectories\n\n")
    for traj in trajectories[:5]:
        f.write(f"\n### {traj['trajectory_id']}\n\n")
        f.write(f"- **Actor**: {traj['actor']}\n")
        f.write(f"- **Current State**: {traj['state']} ({traj['state_reason']})\n")
        f.write(f"- **Windows**: {traj['window_count']}\n")
        f.write(f"- **Total Events**: {traj['total_events']}\n")
        f.write(f"- **Peak Ratio**: {traj['peak_ratio']:.2f}\n")
        f.write(f"- **Max Density**: {traj['max_density_seen']}\n")
        f.write(f"- **State History**: {' → '.join(traj['state_history'])}\n")
    
    f.write("\n## Peak Ratio Analysis\n\n")
    f.write("### Lowest Peak Ratios (Fading)\n\n")
    for traj_id, ratio, state in peak_ratios[:10]:
        f.write(f"- **{traj_id}**: {ratio:.2f} (state: {state})\n")
    
    f.write("\n### Highest Peak Ratios (At Peak)\n\n")
    for traj_id, ratio, state in peak_ratios[-10:]:
        f.write(f"- **{traj_id}**: {ratio:.2f} (state: {state})\n")
    
    f.write("\n## Acceleration Analysis\n\n")
    if acceleration_data:
        f.write("### Top Positive Acceleration (Strengthening)\n\n")
        for traj_id, accel, state, momentum in acceleration_data[:5]:
            f.write(f"- **{traj_id}**: {accel:+d} (momentum: {momentum:+d}, state: {state})\n")
        
        f.write("\n### Top Negative Acceleration (Weakening)\n\n")
        for traj_id, accel, state, momentum in acceleration_data[-5:]:
            f.write(f"- **{traj_id}**: {accel:+d} (momentum: {momentum:+d}, state: {state})\n")
    
    f.write("\n## State Reasons\n\n")
    for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
        f.write(f"- **{reason}**: {count}\n")

print("✅ Report written to STORM_LIFECYCLE_REPORT.md")

print("\n" + "="*70)
print("ANALYSIS COMPLETE")
print("="*70)

print(f"\nTrajectories analyzed: {len(trajectories)}")
print(f"\nState distribution:")
for state in sorted(state_counts.keys()):
    print(f"  {state}: {state_counts[state]}")

# Load near-emerging storms
try:
    with open("data/derived/near_emerging_storms.jsonl", 'r') as f:
        near_emerging = [json.loads(line) for line in f]
    print(f"\nNear-emerging storms: {len(near_emerging)}")
except FileNotFoundError:
    print(f"\nNear-emerging storms: 0 (file not found)")

print(f"\nArtifacts written:")
print(f"  data/derived/storm_trajectories.jsonl")
print(f"  data/derived/near_emerging_storms.jsonl")
print(f"  STORM_LIFECYCLE_REPORT.md")
