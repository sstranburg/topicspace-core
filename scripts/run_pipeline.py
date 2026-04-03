#!/usr/bin/env python3
"""Full pipeline: fetch → filter → embed → detect → track → summarise → propagate → pressure → watchlist → visualise → report."""
import sys
import subprocess

PYTHON = sys.executable

def run(script, label):
    print(f"\n{'='*60}")
    print(f"▶ {label}")
    print('='*60)
    result = subprocess.run([PYTHON, f"scripts/{script}"], check=True)
    return result

steps = [
    ("fetch_today.py",                  "Fetch latest data"),
    ("filter_events.py",                "Filter events"),
    ("embed_incremental.py",            "Embed new events"),
    ("detect_actor_storms.py",          "Detect actor storms"),
    ("detect_ecosystem_storms.py",      "Detect ecosystem storms"),
    ("track_storms.py",                 "Track storm trajectories"),
    ("track_ecosystem_storms_windowed.py", "Track ecosystem trajectories"),
    ("generate_storm_summaries.py",     "Generate storm summaries"),
    ("generate_ecosystem_summaries.py", "Generate ecosystem summaries"),
    ("detect_storm_propagation.py",     "Detect propagation"),
    ("compute_narrative_evolution.py",  "Compute narrative evolution"),
    ("detect_narrative_pressure.py",    "Detect narrative pressure"),
    ("generate_strategic_watchlist.py", "Generate strategic watchlist"),
    ("build_community_overlay.py",      "Build community overlay"),
    ("clean_narrative_lineages.py",     "Clean narrative lineages (Claude)"),
    ("plot_storm_field_with_state.py",  "Plot ecosystem field"),
    ("plot_per_actor.py",               "Plot per-actor fields"),
    ("plot_watchlist_matrix.py",        "Plot watchlist matrix"),
    ("generate_master_report.py",       "Generate master report"),
    ("generate_leaderboard.py",         "Generate narrative leaderboard"),
    ("render_leaderboard_image.py",     "Render leaderboard social image"),
    ("generate_narrative_charts.py",    "Generate narrative vs price charts"),
]

print("Storm Pipeline")
print(f"Running {len(steps)} steps...\n")

for script, label in steps:
    try:
        run(script, label)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Failed at: {label}")
        sys.exit(1)

print(f"\n{'='*60}")
print("✅ Pipeline complete!")
print("  master_report.html is ready to open in a browser")
print('='*60)
