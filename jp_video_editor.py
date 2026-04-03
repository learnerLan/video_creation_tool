#!/usr/bin/env python3
"""
Japanese Learning Video Editor
================================
Creates a 2-part learning video from Japanese drama/anime clips:
  Part 1: Original video with subtitle area covered (blacked out)
  Part 2: Original video with N3+ vocabulary & grammar annotations overlaid

Usage:
    python jp_video_editor.py input.mp4 --config config.json
    python jp_video_editor.py input.mp4 --config config.json --output output.mp4 --duration 60

Dependencies (install first):
    pip install imageio-ffmpeg pillow numpy
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


# ─────────────────────────────────────────────
# FFmpeg helpers
# ─────────────────────────────────────────────

def get_ffmpeg_paths():
    """Return (ffmpeg_exe, ffprobe_exe) paths. Prefers bundled imageio-ffmpeg."""
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        # ffprobe lives next to ffmpeg in the imageio bundle
        ffprobe_exe = ffmpeg_exe.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
        if not os.path.exists(ffprobe_exe):
            ffprobe_exe = "ffprobe"
        return ffmpeg_exe, ffprobe_exe
    except ImportError:
        return "ffmpeg", "ffprobe"


def get_video_info(ffprobe_exe, video_path):
    """Return (width, height, duration_sec, fps) for the first video stream."""
    cmd = [
        ffprobe_exe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            stream = data.get("streams", [{}])[0]
            fmt = data.get("format", {})
            width = int(stream.get("width", 1920))
            height = int(stream.get("height", 1080))
            duration = float(fmt.get("duration", 120))
            fps_str = stream.get("r_frame_rate", "24/1")
            num, den = fps_str.split("/")
            fps = float(num) / float(den)
            return width, height, duration, fps
    except FileNotFoundError:
        pass  # ffprobe not available, fall back to ffmpeg -i

    # Fallback: parse ffmpeg -i stderr output
    import re
    ffmpeg_exe, _ = get_ffmpeg_paths()
    result = subprocess.run(
        [ffmpeg_exe, "-i", str(video_path)],
        capture_output=True, text=True,
    )
    text = result.stderr

    # Duration: 00:00:41.56
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", text)
    if m:
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    else:
        duration = 120.0

    # 480x268
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    if m:
        width, height = int(m.group(1)), int(m.group(2))
    else:
        width, height = 1920, 1080

    # 23.99 fps  or  23.98 tbr
    m = re.search(r"([\d.]+)\s*fps", text)
    if m:
        fps = float(m.group(1))
    else:
        fps = 24.0

    return width, height, duration, fps


def run_ffmpeg(cmd, label=""):
    """Run an ffmpeg command and raise on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed ({label}):\n{result.stderr[-1000:]}"
        )


# ─────────────────────────────────────────────
# Font helpers
# ─────────────────────────────────────────────

WINDOWS_FONT_CANDIDATES = [
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/YuGothR.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux fallback
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",          # macOS fallback
]


def find_japanese_font():
    for path in WINDOWS_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def load_fonts(font_path, base_size):
    """Return (title_font, header_font, body_font, small_font)."""
    sizes = [base_size + 4, base_size + 2, base_size, base_size - 2]
    if font_path:
        try:
            return tuple(ImageFont.truetype(font_path, s) for s in sizes)
        except Exception:
            pass
    # Fallback: Pillow built-in (no Japanese, but won't crash)
    default = ImageFont.load_default()
    return default, default, default, default


# ─────────────────────────────────────────────
# Overlay image generation
# ─────────────────────────────────────────────

PANEL_BG      = (10,  10,  30, 210)   # dark blue-black, semi-transparent
BORDER_COLOR  = (100, 180, 255, 200)
TITLE_COLOR   = (255, 215,   0, 255)   # gold
HEADER_COLOR  = (100, 200, 255, 255)   # light blue
WORD_COLOR    = (255, 255, 255, 255)   # white
MEANING_COLOR = (180, 255, 180, 255)   # light green
GRAMMAR_COLOR = (255, 210, 100, 255)   # amber
CONN_COLOR    = (200, 200, 200, 255)   # light grey


def draw_text_safe(draw, pos, text, font, fill):
    """Draw text; silently skip if text is empty."""
    if text:
        draw.text(pos, text, font=font, fill=fill)


def create_vocab_overlay(width, height, vocabulary, font_path=None):
    """
    Semi-transparent panel for vocabulary.
    Placed in the top-left quadrant.
    """
    base = max(14, int(height * 0.022))
    title_f, header_f, body_f, small_f = load_fonts(font_path, base)
    line_h = base + 8

    # Estimate panel height
    lines_needed = 2 + len(vocabulary) * 3 + 2
    panel_h = min(int(height * 0.55), lines_needed * line_h + 30)
    panel_w = int(width * 0.42)
    px, py = 18, 18

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    panel = Image.new("RGBA", (panel_w, panel_h), PANEL_BG)
    canvas.paste(panel, (px, py), panel)

    draw = ImageDraw.Draw(canvas)
    draw.rectangle([px, py, px + panel_w - 1, py + panel_h - 1],
                   outline=BORDER_COLOR, width=2)

    x = px + 12
    y = py + 10

    draw_text_safe(draw, (x, y), "今回の単語", title_f, TITLE_COLOR)
    y += base + 10
    draw.line([(x, y), (px + panel_w - 12, y)], fill=BORDER_COLOR, width=1)
    y += 8

    for item in vocabulary:
        word    = item.get("word", "")
        reading = item.get("reading", "")
        meaning = item.get("meaning", "")
        level   = item.get("level", "")

        label = f"▶ {word}"
        if reading:
            label += f"（{reading}）"
        if level:
            label += f" [{level}]"

        draw_text_safe(draw, (x, y), label, body_f, WORD_COLOR)
        y += line_h

        if meaning:
            draw_text_safe(draw, (x + 16, y), f"→ {meaning}", small_f, MEANING_COLOR)
            y += line_h

        y += 4
        if y > py + panel_h - line_h:
            break

    return canvas


def create_grammar_overlay(width, height, grammar, font_path=None):
    """
    Semi-transparent panel for grammar points.
    Placed in the top-right quadrant.
    """
    base = max(14, int(height * 0.022))
    title_f, header_f, body_f, small_f = load_fonts(font_path, base)
    line_h = base + 8

    lines_needed = 2 + len(grammar) * 4 + 2
    panel_h = min(int(height * 0.65), lines_needed * line_h + 30)
    panel_w = int(width * 0.44)
    px = width - panel_w - 18
    py = 18

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    panel = Image.new("RGBA", (panel_w, panel_h), PANEL_BG)
    canvas.paste(panel, (px, py), panel)

    draw = ImageDraw.Draw(canvas)
    draw.rectangle([px, py, px + panel_w - 1, py + panel_h - 1],
                   outline=BORDER_COLOR, width=2)

    x = px + 12
    y = py + 10

    draw_text_safe(draw, (x, y), "今回の文法", title_f, TITLE_COLOR)
    y += base + 10
    draw.line([(x, y), (px + panel_w - 12, y)], fill=BORDER_COLOR, width=1)
    y += 8

    for item in grammar:
        pattern    = item.get("pattern", "")
        connection = item.get("connection", "")
        meaning    = item.get("meaning", "")

        draw_text_safe(draw, (x, y), f"◆ {pattern}", body_f, GRAMMAR_COLOR)
        y += line_h

        if connection:
            draw_text_safe(draw, (x + 16, y), f"接続：{connection}", small_f, CONN_COLOR)
            y += line_h

        if meaning:
            draw_text_safe(draw, (x + 16, y), f"→ {meaning}", small_f, MEANING_COLOR)
            y += line_h

        y += 6
        if y > py + panel_h - line_h:
            break

    return canvas


def create_transition_frame(width, height, font_path=None):
    """
    Full-frame image used as the ~1s transition clip between Part 1 and Part 2.
    Dark background with centered 'Next Part' text.
    """
    img = Image.new("RGB", (width, height), (10, 10, 30))
    draw = ImageDraw.Draw(img)

    # Horizontal divider lines
    mid_y = height // 2
    line_x0, line_x1 = int(width * 0.15), int(width * 0.85)
    draw.line([(line_x0, mid_y - 28), (line_x1, mid_y - 28)], fill=(100, 180, 255), width=1)
    draw.line([(line_x0, mid_y + 36), (line_x1, mid_y + 36)], fill=(100, 180, 255), width=1)

    # Main label
    label_size = max(24, int(height * 0.07))
    sub_size   = max(14, int(height * 0.035))
    if font_path:
        try:
            label_font = ImageFont.truetype(font_path, label_size)
            sub_font   = ImageFont.truetype(font_path, sub_size)
        except Exception:
            label_font = sub_font = ImageFont.load_default()
    else:
        label_font = sub_font = ImageFont.load_default()

    label_text = "Next Part"
    sub_text   = "▶  Part 2  —  解説編"

    # Center label
    bbox = draw.textbbox((0, 0), label_text, font=label_font)
    lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((width - lw) // 2, mid_y - lh - 6), label_text, font=label_font, fill=(255, 215, 0))

    # Center sub-label
    bbox2 = draw.textbbox((0, 0), sub_text, font=sub_font)
    sw = bbox2[2] - bbox2[0]
    draw.text(((width - sw) // 2, mid_y + 8), sub_text, font=sub_font, fill=(180, 220, 255))

    return img


def create_combined_overlay(width, height, vocabulary, grammar, font_path=None):
    """
    Show vocabulary on the left and grammar on the right simultaneously.
    """
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    if vocabulary:
        v_img = create_vocab_overlay(width, height, vocabulary, font_path)
        canvas = Image.alpha_composite(canvas, v_img)

    if grammar:
        g_img = create_grammar_overlay(width, height, grammar, font_path)
        canvas = Image.alpha_composite(canvas, g_img)

    return canvas


# ─────────────────────────────────────────────
# Main processing pipeline
# ─────────────────────────────────────────────

def process_video(
    input_path,
    output_path,
    unsubtitled_path,
    vocabulary,
    grammar,
    duration=60,
    subtitle_cover_pct=0.13,
    overlay_mode="split",   # "split" | "combined"
    ffmpeg_exe=None,
    ffprobe_exe=None,
    verbose=False,
):
    """
    Build the 2-part learning video.

    unsubtitled_path: where to save Part 1 (subtitle-covered clip)
    output_path:      where to save the final product (Part 1 + Part 2)

    overlay_mode:
      "split"    — first half of Part 2 shows vocab, second half shows grammar
      "combined" — whole Part 2 shows vocab (left) + grammar (right) together
    """
    if ffmpeg_exe is None:
        ffmpeg_exe, ffprobe_exe = get_ffmpeg_paths()

    input_path = str(input_path)

    # ── Video metadata ────────────────────────────────────────────────
    print(f"Reading video info: {input_path}")
    width, height, video_dur, fps = get_video_info(ffprobe_exe, input_path)
    clip_dur = min(duration, video_dur)
    print(f"  Resolution: {width}x{height}  |  FPS: {fps:.2f}  |  Duration: {video_dur:.1f}s")
    print(f"  Using first {clip_dur:.0f}s for each part\n")

    font_path = find_japanese_font()
    print(f"  Font: {font_path or 'fallback (no Japanese font found)'}\n")

    with tempfile.TemporaryDirectory() as tmp:
        part1 = str(unsubtitled_path)   # save directly to unsubtitled folder
        part2 = os.path.join(tmp, "part2.mp4")
        concat_txt = os.path.join(tmp, "concat.txt")

        # ── PART 1: Cover subtitle area ───────────────────────────────
        print("▶ Part 1 — covering subtitle area …")
        sub_h = int(height * subtitle_cover_pct)
        sub_y = height - sub_h

        # Blur + semi-transparent overlay: crop subtitle region → gblur → overlay back → dark tint
        flt1 = (
            f"[0:v]split[main][orig];"
            f"[orig]crop={width}:{sub_h}:0:{sub_y},gblur=sigma=18[blurred];"
            f"[main][blurred]overlay=0:{sub_y}[v1];"
            f"[v1]drawbox=x=0:y={sub_y}:w={width}:h={sub_h}:color=black@0.45:t=fill[vout]"
        )
        cmd1 = [
            ffmpeg_exe, "-y",
            "-ss", "0", "-t", str(clip_dur),
            "-i", input_path,
            "-filter_complex", flt1,
            "-map", "[vout]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            part1,
        ]
        run_ffmpeg(cmd1, "part1")
        print("  Done.\n")

        # ── PART 2: Add annotation overlays ───────────────────────────
        print("▶ Part 2 — generating annotation overlay …")

        if overlay_mode == "combined":
            overlay_png = os.path.join(tmp, "overlay_combined.png")
            img = create_combined_overlay(width, height, vocabulary, grammar, font_path)
            img.save(overlay_png)

            cmd2 = [
                ffmpeg_exe, "-y",
                "-ss", "0", "-t", str(clip_dur),
                "-i", input_path,
                "-i", overlay_png,
                "-filter_complex", "[0:v][1:v]overlay=0:0[vout]",
                "-map", "[vout]", "-map", "0:a",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-b:a", "128k",
                part2,
            ]
            run_ffmpeg(cmd2, "part2-combined")

        else:  # split mode
            half = clip_dur / 2
            vocab_png   = os.path.join(tmp, "overlay_vocab.png")
            grammar_png = os.path.join(tmp, "overlay_grammar.png")

            v_img = create_vocab_overlay(width, height, vocabulary, font_path)
            v_img.save(vocab_png)

            g_img = create_grammar_overlay(width, height, grammar, font_path)
            g_img.save(grammar_png)

            # Show vocab overlay for [0, half), grammar overlay for [half, end)
            flt = (
                f"[0:v][1:v]overlay=0:0:enable='between(t,0,{half})'[v1];"
                f"[v1][2:v]overlay=0:0:enable='between(t,{half},{clip_dur})'[vout]"
            )
            cmd2 = [
                ffmpeg_exe, "-y",
                "-ss", "0", "-t", str(clip_dur),
                "-i", input_path,
                "-i", vocab_png,
                "-i", grammar_png,
                "-filter_complex", flt,
                "-map", "[vout]", "-map", "0:a",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-b:a", "128k",
                part2,
            ]
            run_ffmpeg(cmd2, "part2-split")

        print("  Done.\n")

        # ── Transition clip (~1 s) ─────────────────────────────────────
        print("▶ Generating transition clip …")
        transition_png = os.path.join(tmp, "transition.png")
        transition_mp4 = os.path.join(tmp, "transition.mp4")

        tr_img = create_transition_frame(width, height, font_path)
        tr_img.save(transition_png)

        cmd_tr = [
            ffmpeg_exe, "-y",
            "-loop", "1", "-i", transition_png,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", "1.5",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            transition_mp4,
        ]
        run_ffmpeg(cmd_tr, "transition")
        print("  Done.\n")

        # ── Concatenate Part 1 + Transition + Part 2 ──────────────────
        print("▶ Concatenating …")
        with open(concat_txt, "w", encoding="utf-8") as f:
            for seg in (part1, transition_mp4, part2):
                f.write(f"file '{seg.replace(chr(92), '/')}'\n")

        cmd3 = [
            ffmpeg_exe, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_txt,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ]
        run_ffmpeg(cmd3, "concat")
        print("  Done.\n")

    print(f"✅ Unsubtitled saved to : {unsubtitled_path}")
    print(f"✅ Product saved to     : {output_path}")
    return True


# ─────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Japanese Learning Video Editor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example config.json
-------------------
{
  "vocabulary": [
    {"word": "確認",    "reading": "かくにん",    "meaning": "确认 / to confirm",        "level": "N3"},
    {"word": "緊張",    "reading": "きんちょう",   "meaning": "紧张 / nervous",            "level": "N3"},
    {"word": "諦める",  "reading": "あきらめる",   "meaning": "放弃 / to give up",         "level": "N3"},
    {"word": "我慢",    "reading": "がまん",       "meaning": "忍耐 / to endure",          "level": "N3"},
    {"word": "仕方ない","reading": "しかたない",   "meaning": "没办法 / can't be helped",  "level": "N3"}
  ],
  "grammar": [
    {
      "pattern":    "〜てしまう",
      "connection": "V-て形 ＋ しまう",
      "meaning":    "表示完成（常带遗憾）/ done/ended up doing"
    },
    {
      "pattern":    "〜ばよかった",
      "connection": "V-ば形 ＋ よかった",
      "meaning":    "表示后悔 / should have done"
    },
    {
      "pattern":    "〜だけじゃなく",
      "connection": "N / V普通形 ＋ だけじゃなく",
      "meaning":    "不只是… / not only…"
    }
  ]
}
""",
    )

    parser.add_argument("input",  help="Input video file (MP4, MKV, etc.)")
    parser.add_argument("--config",  "-c", required=True,
                        help="JSON file with vocabulary and grammar lists")
    parser.add_argument("--duration", "-d", type=float, default=60,
                        help="Seconds to use from the video for each part (default: 60)")
    parser.add_argument("--subtitle-cover", type=float, default=0.13,
                        help="Fraction of video height to black out for subtitles (default: 0.13)")
    parser.add_argument("--mode", choices=["split", "combined"], default="split",
                        help="split=vocab first half / grammar second half; "
                             "combined=both panels shown together (default: split)")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    # ── Directory layout ──────────────────────────────────────────────
    # project_root/
    #   video/         <- input videos
    #   unsubtitled/   <- Part 1 output (subtitle-covered clip)
    #   product/       <- final learning video
    base_dir = Path(__file__).parent
    unsubtitled_dir = base_dir / "unsubtitled"
    product_dir     = base_dir / "product"
    unsubtitled_dir.mkdir(exist_ok=True)
    product_dir.mkdir(exist_ok=True)

    stem = Path(args.input).stem
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    unsubtitled_path = unsubtitled_dir / f"{stem}_{ts}.mp4"
    output_path      = product_dir     / f"{stem}_learning_{ts}.mp4"

    # Load config
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    vocabulary = cfg.get("vocabulary", [])
    grammar    = cfg.get("grammar",    [])

    print(f"Vocabulary items : {len(vocabulary)}")
    print(f"Grammar items    : {len(grammar)}")
    print(f"Overlay mode     : {args.mode}")
    print(f"Part duration    : {args.duration}s")
    print(f"Subtitle cover   : {args.subtitle_cover * 100:.0f}% of frame height")
    print(f"Unsubtitled  -> : {unsubtitled_path}")
    print(f"Product      -> : {output_path}\n")

    ffmpeg_exe, ffprobe_exe = get_ffmpeg_paths()
    print(f"FFmpeg : {ffmpeg_exe}")
    print(f"FFprobe: {ffprobe_exe}\n")

    process_video(
        input_path=args.input,
        output_path=output_path,
        unsubtitled_path=unsubtitled_path,
        vocabulary=vocabulary,
        grammar=grammar,
        duration=args.duration,
        subtitle_cover_pct=args.subtitle_cover,
        overlay_mode=args.mode,
        ffmpeg_exe=ffmpeg_exe,
        ffprobe_exe=ffprobe_exe,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
