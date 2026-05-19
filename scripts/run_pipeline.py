#!/usr/bin/env python3
"""Full pipeline: fetch → filter → embed → detect → track → summarise → propagate → pressure → watchlist → visualise → report."""
import sys
import subprocess
import shutil
import base64
import re
from pathlib import Path

PYTHON = sys.executable

def run(script, label, args=None):
    print(f"\n{'='*60}")
    print(f"▶ {label}")
    print('='*60)
    cmd = [PYTHON, f"scripts/{script}"] + list(args or [])
    result = subprocess.run(cmd, check=True)
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
    # generate_actor_expectations.py produces today's per-actor LLM
    # expectations (consumed by /actor pages + archived into
    # expectations_history/ for /replay) and at its tail kicks off the
    # F-006 lifecycle build (build_expectation_lifecycle.py →
    # thesis_trails.json). Placed after narrative pressure / watchlist
    # since the prompt references those numbers; before leaderboard
    # which reads the freshly written actor_expectations.json.
    ("generate_actor_expectations.py", "Generate actor expectations (LLM)",
     ["--all"]),
    ("build_community_overlay.py",      "Build community overlay"),
    ("clean_narrative_lineages.py",     "Clean narrative lineages (Claude)"),
    ("plot_storm_field_with_state.py",  "Plot ecosystem field"),
    ("plot_per_actor.py",               "Plot per-actor fields"),
    ("plot_watchlist_matrix.py",        "Plot watchlist matrix"),
    ("generate_master_report.py",       "Generate master report"),
    ("generate_leaderboard.py",         "Generate narrative leaderboard"),
    ("generate_crypto_leaderboard.py",  "Generate crypto leaderboard"),
    ("render_leaderboard_image.py",     "Render leaderboard social image"),
    ("generate_narrative_charts.py",    "Generate narrative vs price charts"),
    ("generate_storm_objects.py",       "Build storm objects for frontend"),
    ("generate_thread_objects.py",      "Build thread objects for frontend"),
    ("build_event_index.py",            "Build per-actor event index"),
    ("compute_storm_cohesion.py",       "Compute per-actor storm cohesion"),
    ("generate_alerts.py",              "Generate narrative alerts"),
    ("generate_briefing.py",            "Generate daily briefing"),
]

print("Storm Pipeline")
print(f"Running {len(steps)} steps...\n")

for step in steps:
    script, label = step[0], step[1]
    args = step[2] if len(step) > 2 else None
    try:
        run(script, label, args)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Failed at: {label}")
        sys.exit(1)

print(f"\n{'='*60}")
print("✅ Pipeline complete!")
print("  master_report.html is ready to open in a browser")
print('='*60)

# Copy master_report.html → topicspace-site/public/reports/latest.html
# Images are inlined as base64 so the HTML is self-contained when served from /reports/
ROOT = Path(__file__).parent.parent
report_src  = ROOT / "master_report.html"
report_dest = ROOT.parent / "topicspace-site" / "public" / "reports" / "latest.html"
if report_src.exists() and report_dest.parent.exists():
    html = report_src.read_text(encoding='utf-8')

    def _inline_img(m):
        src = m.group(1)
        # Only inline local relative paths (skip data: and http)
        if src.startswith('data:') or src.startswith('http'):
            return m.group(0)
        img_path = report_src.parent / src
        if not img_path.exists():
            return m.group(0)
        ext = img_path.suffix.lstrip('.').lower()
        mime = 'image/svg+xml' if ext == 'svg' else f'image/{ext}'
        b64 = base64.b64encode(img_path.read_bytes()).decode('ascii')
        return f'src="data:{mime};base64,{b64}"'

    html = re.sub(r'src="([^"]+)"', _inline_img, html)
    report_dest.write_text(html, encoding='utf-8')
    print(f"  Copied report (images inlined) → {report_dest}")
elif not report_dest.parent.exists():
    print(f"  ⚠ Reports dir not found: {report_dest.parent}")

# Copy events_by_actor.json → topicspace-site/public/ for the intel feature.
# Read by lib/intel/fields.ts loadRecentEvents() + themeScan().
events_src  = ROOT / "data" / "derived" / "events_by_actor.json"
events_dest = ROOT.parent / "topicspace-site" / "public" / "events_by_actor.json"
if events_src.exists() and events_dest.parent.exists():
    shutil.copyfile(events_src, events_dest)
    print(f"  Copied events index → {events_dest}")
elif not events_src.exists():
    print(f"  ⚠ events_by_actor.json not found at {events_src} (run build_event_index.py)")
