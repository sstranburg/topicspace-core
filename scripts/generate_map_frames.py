"""
Generate 3 static SVG map frames for animation:
  T-2 = Mar 19  (system-wide acceleration, NVDA dominant)
  T-1 = Mar 20  (mixed signals, first cracks)
  T   = Mar 21  (fragmentation — current live map)

Coordinate system matches NarrativeMap.tsx exactly:
  W=560, H=440, PL=55, PT=24, IW=485, IH=356
  cx(m) = 55 + m*485
  cy(v) = 24 + (1-v)*356
"""

import os

W, H = 560, 440
PL, PT, IW, IH = 55, 24, 485, 356

def cx(m): return PL + m * IW
def cy(v): return PT + (1 - v) * IH

AXIS_BOTTOM = PT + IH      # 380
MID_X = cx(0.5)            # 297.5
MID_Y = cy(0.5)            # 202

# Actor colors — fixed across all frames so viewers can track movement
COLORS = {
    "META":  "#93c5fd",   # blue
    "ARM":   "#86efac",   # green
    "NVDA":  "#fcd34d",   # yellow
    "AMZN":  "#c4b5fd",   # violet (distinguish from NVDA)
    "MODEL": "#fca5a5",   # red
}

# Each frame: list of (id, name, sub, role, m, v, nx, ny, anchor)
# Positions are narrative-interpretive, informed by 48h event windows:
#   Mar 19: META +33%, NVDA +192%, ARM +500%, AMZN +240%, MODEL(avg) +730%
#   Mar 20: META -11%, NVDA +13%,  ARM +650%, AMZN +43%,  MODEL(avg) +320%
#   Mar 21: META  -8%, NVDA -36%,  ARM +225%, AMZN -23%,  MODEL(avg) -16%

FRAMES = [
    {
        "date":      "Mar 19",
        "label":     "T-2",
        "headline":  "Broad acceleration — everything rising together",
        "actors": [
            # NVDA dominant — high momentum, strong velocity
            dict(id="NVDA", name="NVIDIA",      sub=None,
                 role="accelerating",    m=0.72, v=0.82,
                 nx=397, ny=81,   anchor="end"),
            # AMZN rising strongly
            dict(id="AMZN", name="Amazon",      sub=None,
                 role="accelerating",    m=0.52, v=0.72,
                 nx=315, ny=114,  anchor="start"),
            # Model layer rising fast (OPENAI+ANTHRO both surging)
            dict(id="MODEL", name="Model layer", sub="(OpenAI + Anthropic)",
                 role="accelerating",    m=0.20, v=0.70,
                 nx=159, ny=121,  anchor="start"),
            # META rising, smaller relative signal
            dict(id="META", name="Meta",         sub=None,
                 role="rising",          m=0.45, v=0.63,
                 nx=266, ny=163,  anchor="end"),
            # ARM just beginning to emerge
            dict(id="ARM",  name="ARM",          sub=None,
                 role="emerging",        m=0.10, v=0.55,
                 nx=101, ny=179,  anchor="start"),
        ],
    },
    {
        "date":      "Mar 20",
        "label":     "T-1",
        "headline":  "First cracks — NVIDIA slowing, system starting to split",
        "actors": [
            # NVDA still high volume but velocity dropping
            dict(id="NVDA", name="NVIDIA",      sub=None,
                 role="slowing",         m=0.72, v=0.63,
                 nx=397, ny=138,  anchor="end"),
            # AMZN still positive but moderating
            dict(id="AMZN", name="Amazon",      sub=None,
                 role="stable",          m=0.50, v=0.57,
                 nx=305, ny=179,  anchor="start"),
            # Model layer still rising
            dict(id="MODEL", name="Model layer", sub="(OpenAI + Anthropic)",
                 role="rising",          m=0.20, v=0.67,
                 nx=159, ny=128,  anchor="start"),
            # META flattening — first dip
            dict(id="META", name="Meta",         sub=None,
                 role="flattening",      m=0.50, v=0.48,
                 nx=305, ny=222,  anchor="start"),
            # ARM emerging strongly
            dict(id="ARM",  name="ARM",          sub=None,
                 role="emerging",        m=0.22, v=0.73,
                 nx=169, ny=113,  anchor="start"),
        ],
    },
    {
        "date":      "Mar 21",
        "label":     "T  (today)",
        "headline":  "Fragmentation — no clear leader is holding",
        "actors": [
            # Current live map — exact values from NarrativeMap.tsx
            dict(id="META", name="Meta",         sub=None,
                 role="accelerating",    m=0.58, v=0.85,
                 nx=343, ny=67,   anchor="start"),
            dict(id="ARM",  name="ARM",          sub=None,
                 role="emerging",        m=0.62, v=0.68,
                 nx=363, ny=128,  anchor="start"),
            dict(id="NVDA", name="NVIDIA",       sub=None,
                 role="bifurcated",      m=0.72, v=0.52,
                 nx=397, ny=185,  anchor="end"),
            dict(id="AMZN", name="Amazon",       sub=None,
                 role="stable anchor",   m=0.48, v=0.37,
                 nx=295, ny=238,  anchor="start"),
            dict(id="MODEL", name="Model layer", sub="(OpenAI + Anthropic)",
                 role="declining",       m=0.08, v=0.06,
                 nx=101, ny=349,  anchor="start"),
        ],
    },
]


def render_frame(frame: dict) -> str:
    actors = frame["actors"]
    date   = frame["date"]
    label  = frame["label"]
    head   = frame["headline"]

    lines = []
    lines.append(f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
                 f'xmlns="http://www.w3.org/2000/svg" '
                 f'style="font-family: system-ui, sans-serif; background: white;">')

    # ── Quadrant fills ──────────────────────────────────────────────────────────
    hw, hh = IW / 2, IH / 2
    lines.append(f'<rect x="{PL}"    y="{PT}"    width="{hw}" height="{hh}" fill="#f9fafb"/>')
    lines.append(f'<rect x="{MID_X}" y="{PT}"    width="{hw}" height="{hh}" fill="#eff6ff"/>')
    lines.append(f'<rect x="{PL}"    y="{MID_Y}" width="{hw}" height="{hh}" fill="#f9fafb"/>')
    lines.append(f'<rect x="{MID_X}" y="{MID_Y}" width="{hw}" height="{hh}" fill="#f9fafb"/>')

    # ── Dividers ────────────────────────────────────────────────────────────────
    lines.append(f'<line x1="{MID_X}" y1="{PT}"          x2="{MID_X}"    y2="{AXIS_BOTTOM}" '
                 f'stroke="#e8eaed" stroke-width="1" stroke-dasharray="3 4"/>')
    lines.append(f'<line x1="{PL}"    y1="{MID_Y}"        x2="{PL + IW}" y2="{MID_Y}" '
                 f'stroke="#e8eaed" stroke-width="1" stroke-dasharray="3 4"/>')

    # ── Axes ────────────────────────────────────────────────────────────────────
    lines.append(f'<line x1="{PL}" y1="{AXIS_BOTTOM}" x2="{PL + IW}" y2="{AXIS_BOTTOM}" '
                 f'stroke="#e5e7eb" stroke-width="1"/>')
    lines.append(f'<line x1="{PL}" y1="{PT}" x2="{PL}" y2="{AXIS_BOTTOM}" '
                 f'stroke="#e5e7eb" stroke-width="1"/>')

    # ── Axis labels ─────────────────────────────────────────────────────────────
    lines.append(f'<text x="{PL + IW / 2}" y="{H - 10}" text-anchor="middle" '
                 f'font-size="8.5" fill="#c4c4c4" letter-spacing="0.1em">'
                 f'NARRATIVE MOMENTUM (ATTENTION) →</text>')
    lines.append(f'<text x="13" y="{PT + IH / 2}" text-anchor="middle" '
                 f'font-size="8.5" fill="#c4c4c4" letter-spacing="0.1em" '
                 f'transform="rotate(-90, 13, {PT + IH / 2})">'
                 f'NARRATIVE VELOCITY (CHANGE) →</text>')

    # ── Actors ──────────────────────────────────────────────────────────────────
    for a in actors:
        x     = cx(a["m"])
        y     = cy(a["v"])
        color = COLORS[a["id"]]
        nx, ny = a["nx"], a["ny"]
        anch  = a["anchor"]
        has_sub = bool(a["sub"])

        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}"/>')
        lines.append(f'<text x="{nx}" y="{ny}" text-anchor="{anch}" '
                     f'font-size="9" fill="#4b5563" font-weight="600">{a["name"]}</text>')
        if has_sub:
            lines.append(f'<text x="{nx}" y="{ny + 11}" text-anchor="{anch}" '
                         f'font-size="7.5" fill="#b0b8c4">{a["sub"]}</text>')
        role_y = ny + (22 if has_sub else 11)
        lines.append(f'<text x="{nx}" y="{role_y}" text-anchor="{anch}" '
                     f'font-size="7.5" fill="#b0b8c4" font-style="italic">{a["role"]}</text>')

    # ── Frame label + headline ───────────────────────────────────────────────────
    lines.append(f'<text x="{PL}" y="{PT - 8}" font-size="9" fill="#9ca3af" '
                 f'font-weight="600" letter-spacing="0.08em">{label} · {date}</text>')
    # Headline below the map (in the PB zone)
    lines.append(f'<text x="{PL}" y="{AXIS_BOTTOM + 24}" font-size="10" fill="#374151" '
                 f'font-weight="600">{head}</text>')

    lines.append('</svg>')
    return "\n".join(lines)


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "../data/derived/map_frames")
    os.makedirs(out_dir, exist_ok=True)

    names = ["frame_t2_mar19.svg", "frame_t1_mar20.svg", "frame_t0_mar21.svg"]
    for frame, name in zip(FRAMES, names):
        svg = render_frame(frame)
        path = os.path.join(out_dir, name)
        with open(path, "w") as f:
            f.write(svg)
        print(f"Wrote {path}")

    print("\nDone. 3 frames in data/derived/map_frames/")


if __name__ == "__main__":
    main()
