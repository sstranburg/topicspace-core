#!/usr/bin/env python3
"""Full pipeline: fetch → filter → embed → detect → track → summarise → propagate → pressure → watchlist → visualise → report."""
import sys
import subprocess
import shutil
from pathlib import Path

PYTHON = sys.executable

def run(script, label):
    print(f"\n{'='*60}")
    print(f"▶ {label}")
    print('='*60)
    result = subprocess.run([PYTHON, f"scripts/{script}"], check=True)
    return result

steps = [
    ("fetch_today.py",                  "Fetch latest data"),
    ("fetch_prices.py",                 "Fetch latest prices"),
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
    ("generate_storm_objects.py",       "Build storm objects for frontend"),
    ("generate_thread_objects.py",      "Build thread objects for frontend"),
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

# Copy master_report.html → topicspace-site/public/reports/latest.html
ROOT = Path(__file__).parent.parent
report_src  = ROOT / "master_report.html"
report_dest = ROOT.parent / "topicspace-site" / "public" / "reports" / "latest.html"
if report_src.exists() and report_dest.parent.exists():
    shutil.copy2(report_src, report_dest)
    print(f"  Copied report → {report_dest}")
elif not report_dest.parent.exists():
    print(f"  ⚠ Reports dir not found: {report_dest.parent}")
