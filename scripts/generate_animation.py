"""
Generate 3-frame animation: expansion → fragmentation → system-wide cooling.

Frames:
  T-2  (Mar 20) — Everything still rising
  T-1  (Mar 21) — Fragmentation begins
  T    (Mar 22) — Cooling across the system / PLTR only exception

Output: animation.mp4 + animation.gif in data/derived/map_frames/
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import cairosvg
from PIL import Image, ImageDraw, ImageFont

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT  = Path(__file__).parent.parent
OUT   = ROOT / "data/derived/map_frames"
OUT.mkdir(parents=True, exist_ok=True)

# ── Canvas ─────────────────────────────────────────────────────────────────────
CW, CH    = 1080, 1920          # portrait
BG        = (10, 15, 30)        # dark navy
TEXT_PRI  = (226, 232, 240)     # slate-200
TEXT_MUT  = (100, 116, 139)     # slate-500

# ── SVG map dimensions ─────────────────────────────────────────────────────────
# Scale SVG (560×440) to fill canvas width with margin
MAP_W = 1000
MAP_H = int(440 * MAP_W / 560)
MAP_X = (CW - MAP_W) // 2       # centered horizontally
MAP_Y = 420                     # vertical position on canvas


# ── Dark-theme SVG builder ─────────────────────────────────────────────────────
def _svg(actors, date_label, pltr_highlight=False):
    """
    Build a dark-background SVG frame.
    actors: list of (name, sub, cx, cy, nx, ny, anchor, color, role)
    """
    W, H   = 560, 440
    PL, PT = 55, 24
    PR, PB = 20, 60
    IW     = W - PL - PR     # 485
    IH     = H - PT - PB     # 356
    midX   = PL + IW / 2
    midY   = PT + IH / 2

    bg       = "#0a0f1e"
    q_hi     = "#111827"   # upper-right highlight quad
    q_norm   = "#0d1321"   # other quads
    ax_col   = "#1e293b"
    ax_dash  = "#1e293b"
    lbl_col  = "#334155"
    txt_main = "#cbd5e1"
    txt_sub  = "#475569"

    lines = [
        f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'style="font-family:system-ui,sans-serif;background:{bg}">',

        # Quadrant fills
        f'<rect x="{PL}" y="{PT}" width="{IW/2}" height="{IH/2}" fill="{q_norm}"/>',
        f'<rect x="{midX}" y="{PT}" width="{IW/2}" height="{IH/2}" fill="{q_hi}"/>',
        f'<rect x="{PL}" y="{midY}" width="{IW/2}" height="{IH/2}" fill="{q_norm}"/>',
        f'<rect x="{midX}" y="{midY}" width="{IW/2}" height="{IH/2}" fill="{q_norm}"/>',

        # Grid lines
        f'<line x1="{midX}" y1="{PT}" x2="{midX}" y2="{PT+IH}" '
        f'stroke="{ax_dash}" stroke-width="1" stroke-dasharray="3 4"/>',
        f'<line x1="{PL}" y1="{midY}" x2="{PL+IW}" y2="{midY}" '
        f'stroke="{ax_dash}" stroke-width="1" stroke-dasharray="3 4"/>',

        # Axis borders
        f'<line x1="{PL}" y1="{PT+IH}" x2="{PL+IW}" y2="{PT+IH}" '
        f'stroke="{ax_col}" stroke-width="1"/>',
        f'<line x1="{PL}" y1="{PT}" x2="{PL}" y2="{PT+IH}" '
        f'stroke="{ax_col}" stroke-width="1"/>',

        # Axis labels
        f'<text x="{PL+IW/2}" y="{H-4}" text-anchor="middle" '
        f'font-size="8.5" fill="{lbl_col}" letter-spacing="0.1em">'
        f'NARRATIVE MOMENTUM (ATTENTION) →</text>',
        f'<text x="13" y="{midY}" text-anchor="middle" '
        f'font-size="8.5" fill="{lbl_col}" letter-spacing="0.1em" '
        f'transform="rotate(-90,13,{midY})">'
        f'NARRATIVE VELOCITY (CHANGE) →</text>',

        # Date stamp
        f'<text x="{PL}" y="{PT-8}" font-size="9" fill="{txt_sub}" '
        f'font-weight="600" letter-spacing="0.08em">{date_label}</text>',
    ]

    for name, sub, cx, cy, nx, ny, anchor, color, role in actors:
        is_pltr_hl = pltr_highlight and name == "PLTR"
        r = 7.5 if is_pltr_hl else 4.5
        dot_color = "#4ade80" if is_pltr_hl else color
        if is_pltr_hl:
            # Soft glow ring behind the dot
            lines.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="13" '
                f'fill="#4ade80" opacity="0.15"/>'
            )
            lines.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="10" '
                f'fill="#4ade80" opacity="0.10"/>'
            )
        lines.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{dot_color}"/>'
        )
        # Name
        lines.append(
            f'<text x="{nx}" y="{ny}" text-anchor="{anchor}" '
            f'font-size="9" fill="{txt_main}" font-weight="600">{name}</text>'
        )
        # Sub-label (e.g. "(OpenAI + Anthropic)")
        if sub:
            lines.append(
                f'<text x="{nx}" y="{ny+11}" text-anchor="{anchor}" '
                f'font-size="7.5" fill="{txt_sub}">{sub}</text>'
            )
            lines.append(
                f'<text x="{nx}" y="{ny+22}" text-anchor="{anchor}" '
                f'font-size="7.5" fill="{txt_sub}" font-style="italic">{role}</text>'
            )
        else:
            lines.append(
                f'<text x="{nx}" y="{ny+11}" text-anchor="{anchor}" '
                f'font-size="7.5" fill="{txt_sub}" font-style="italic">{role}</text>'
            )

    lines.append("</svg>")
    return "\n".join(lines)


# ── Actor definitions ──────────────────────────────────────────────────────────
# Each tuple: (name, sub_label, cx, cy, nx, ny, anchor, color, role)
# cx/cy = dot position, nx/ny = text position

FRAME_ACTORS = [
    # T-2 (Mar 20): broad expansion — everything accelerating
    [
        ("NVIDIA",      None, 404.2, 88.1,  397.0,  81.0, "end",   "#fcd34d", "accelerating"),
        ("Amazon",      None, 307.2, 123.7, 315.0, 114.0, "start", "#c4b5fd", "accelerating"),
        ("Model layer", "(OpenAI + Anthropic)", 152.0, 130.8, 159.0, 121.0, "start", "#fca5a5", "accelerating"),
        ("Meta",        None, 273.2, 155.7, 266.0, 163.0, "end",   "#93c5fd", "rising"),
        ("ARM",         None, 103.5, 184.2, 111.0, 179.0, "start", "#86efac", "emerging"),
    ],
    # T-1 (Mar 21): fragmentation — leaders split, model layer fading
    [
        ("Meta",        None, 336.3,  77.4, 343.0,  67.0, "start", "#93c5fd", "accelerating"),
        ("ARM",         None, 355.7, 137.9, 363.0, 128.0, "start", "#86efac", "emerging"),
        ("NVIDIA",      None, 404.2, 194.9, 397.0, 185.0, "end",   "#fcd34d", "bifurcated"),
        ("Amazon",      None, 287.8, 248.3, 295.0, 238.0, "start", "#c4b5fd", "stable anchor"),
        ("Model layer", "(OpenAI + Anthropic)",  93.8, 358.6,  101.0, 349.0, "start", "#fca5a5", "declining"),
    ],
    # T (Mar 22): broad cooling — PLTR only positive signal
    [
        ("PLTR",        None, 273.25,  95.2, 280.0,  86.0, "start", "#86efac", "emerging"),
        ("Meta",        None, 321.75, 244.9, 330.0, 235.0, "start", "#fcd34d", "bridge — fading"),
        ("Intel",       None, 258.70, 280.3, 252.0, 293.0, "end",   "#fcd34d", "bridge — fading"),
        ("NVIDIA",      None, 404.20, 301.7, 397.0, 292.0, "end",   "#fca5a5", "weakening"),
        ("Model layer", "(OpenAI + Anthropic)",  84.10, 365.8,  91.0, 353.0, "start", "#fca5a5", "declining"),
    ],
]

FRAME_DATES = ["T-2 · Mar 20", "T-1 · Mar 21", "T  (today) · Mar 22"]


# ── Font loader ────────────────────────────────────────────────────────────────
def load_font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNSText.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── Compose final frame ────────────────────────────────────────────────────────
def compose_frame(svg_bytes: bytes, headline: str, is_last_content: bool,
                  timestamp: str = "") -> Image.Image:
    """
    Render SVG → PNG, paste onto 1080×1920 dark canvas, add overlay text.
    timestamp: short date string shown bottom-left (e.g. "Mar 20")
    """
    # Render SVG to PNG bytes at MAP_W × MAP_H
    png_bytes = cairosvg.svg2png(
        bytestring=svg_bytes,
        output_width=MAP_W,
        output_height=MAP_H,
    )
    import io
    map_img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    # Dark canvas
    canvas = Image.new("RGB", (CW, CH), BG)
    canvas.paste(map_img.convert("RGB"), (MAP_X, MAP_Y))

    draw = ImageDraw.Draw(canvas)

    # ── Wordmark top-left ────────────────────────────────────────────────────
    brand_font = load_font(22)
    draw.text((54, 72), "topicspace", font=brand_font, fill=(51, 65, 85))

    # ── Timestamp — bottom-left, small and muted ─────────────────────────────
    if timestamp:
        ts_font = load_font(26)
        draw.text((54, CH - 80), timestamp, font=ts_font, fill=(51, 65, 85))

    # ── Headline ─────────────────────────────────────────────────────────────
    hl_y = MAP_Y + MAP_H + 72
    if is_last_content:
        # Two-line final frame
        line1 = headline                     # "Everything is cooling — except one"
        line2 = "PLTR is still rising"

        hl_font  = load_font(52, bold=True)
        sub_font = load_font(38, bold=True)

        b1 = draw.textbbox((0, 0), line1, font=hl_font)
        tx1 = (CW - (b1[2] - b1[0])) // 2
        draw.text((tx1, hl_y), line1, font=hl_font, fill=TEXT_PRI)

        b2 = draw.textbbox((0, 0), line2, font=sub_font)
        tx2 = (CW - (b2[2] - b2[0])) // 2
        draw.text((tx2, hl_y + (b1[3] - b1[1]) + 20), line2,
                  font=sub_font, fill=(74, 222, 128))   # green to match PLTR dot
    else:
        hl_font = load_font(52, bold=True)
        bbox = draw.textbbox((0, 0), headline, font=hl_font)
        tx = (CW - (bbox[2] - bbox[0])) // 2
        draw.text((tx, hl_y), headline, font=hl_font, fill=TEXT_PRI)

    return canvas


def caption_frame(text: str) -> Image.Image:
    """Solid dark frame with centered text — used as tail card."""
    canvas = Image.new("RGB", (CW, CH), BG)
    draw = ImageDraw.Draw(canvas)
    font = load_font(64, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((CW - tw) // 2, (CH - th) // 2), text, font=font, fill=TEXT_PRI)

    sub_font = load_font(28)
    sub = "topicspace.com"
    sb = draw.textbbox((0, 0), sub, font=sub_font)
    draw.text(((CW - (sb[2]-sb[0])) // 2, (CH - th) // 2 + th + 30),
              sub, font=sub_font, fill=(51, 65, 85))
    return canvas


def crossfade(a: Image.Image, b: Image.Image, steps: int) -> list[Image.Image]:
    frames = []
    ra, rb = a.convert("RGBA"), b.convert("RGBA")
    for i in range(1, steps + 1):
        t = i / (steps + 1)
        frames.append(Image.blend(ra, rb, alpha=t).convert("RGB"))
    return frames


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    OVERLAYS = [
        "Everything still rising",
        "Fragmentation begins",
        "Everything is cooling — except one",
    ]
    TIMESTAMPS = ["Mar 20", "Mar 21", "Mar 22"]

    FPS        = 25
    HOLD_SEC   = 1.8
    FADE_SEC   = 0.4
    CAP_SEC    = 1.5
    HOLD       = int(HOLD_SEC * FPS)   # 45
    FADE       = int(FADE_SEC * FPS)   # 10
    CAP        = int(CAP_SEC  * FPS)   # 37

    print("Building SVG frames...")
    content_frames = []
    for i, (actors, date_label, headline, ts) in enumerate(
        zip(FRAME_ACTORS, FRAME_DATES, OVERLAYS, TIMESTAMPS)
    ):
        pltr_hl = (i == 2)
        svg_str = _svg(actors, date_label, pltr_highlight=pltr_hl)
        frame = compose_frame(svg_str.encode(), headline,
                              is_last_content=(i == 2), timestamp=ts)
        content_frames.append(frame)
        # Save individual PNG
        out_name = ["frame_t2.png", "frame_t1.png", "frame_t0.png"][i]
        frame.save(OUT / out_name)
        print(f"  {out_name} saved")

    cap = caption_frame("One signal remains")
    cap.save(OUT / "frame_caption.png")
    print("  frame_caption.png saved")

    # Build sequence
    sequence: list[Image.Image] = []
    for i, frame in enumerate(content_frames):
        sequence.extend([frame] * HOLD)
        if i < len(content_frames) - 1:
            sequence.extend(crossfade(frame, content_frames[i + 1], FADE))
    # Fade content → caption
    sequence.extend(crossfade(content_frames[-1], cap, FADE))
    sequence.extend([cap] * CAP)
    # Fade caption out (to black) for clean loop
    black = Image.new("RGB", (CW, CH), (0, 0, 0))
    sequence.extend(crossfade(cap, black, FADE))

    total_s = len(sequence) / FPS
    print(f"Sequence: {len(sequence)} frames @ {FPS}fps = {total_s:.1f}s")

    # ── GIF (downscaled to 540×960 for file size) ───────────────────────────
    gif_path = OUT / "animation.gif"
    GIF_W, GIF_H = 540, 960
    gif_frames = [
        f.resize((GIF_W, GIF_H), Image.LANCZOS)
         .quantize(colors=128, method=Image.Quantize.MEDIANCUT)
        for f in sequence
    ]
    gif_frames[0].save(
        gif_path, save_all=True, append_images=gif_frames[1:],
        duration=int(1000 / FPS), loop=0, optimize=False,
    )
    print(f"GIF: {gif_path}  ({gif_path.stat().st_size // 1024} KB)")

    # ── MP4 ─────────────────────────────────────────────────────────────────
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        tmp = Path(tempfile.mkdtemp())
        for i, f in enumerate(sequence):
            f.save(tmp / f"f{i:05d}.png")
        mp4_path = OUT / "animation.mp4"
        cmd = [
            ffmpeg_bin, "-y",
            "-framerate", str(FPS),
            "-i", str(tmp / "f%05d.png"),
            "-vf", f"scale={CW}:{CH}:flags=lanczos",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(mp4_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)
        if r.returncode == 0:
            print(f"MP4: {mp4_path}  ({mp4_path.stat().st_size // 1024} KB)")
        else:
            print("ffmpeg error:", r.stderr[-400:])
    else:
        print("ffmpeg not found — skipping MP4")

    print("Done.")


if __name__ == "__main__":
    main()
