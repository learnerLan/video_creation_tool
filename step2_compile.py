#!/usr/bin/env python3
"""
Step 2 — Compile
================
读取 config_example.json，将词汇/文法注释叠加到原视频上生成 Part 2，
再与 Part 1 拼接，输出最终学习视频到 product/ 文件夹。

【时间戳模式】config 中每条目有 "at" 字段时，注释卡片只在对应时间点弹出，
显示 display_dur 秒（默认 3 秒）后消失。

Usage:
    python step2_compile.py --config config_example.json
    python step2_compile.py --meta text/xxx_meta.json --config config_example.json
    python step2_compile.py --config config_example.json --display-dur 2.5
    python step2_compile.py --config config_example.json --mode combined   （无时间戳时的经典模式）
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from jp_video_editor import (
    get_ffmpeg_paths,
    run_ffmpeg,
    find_japanese_font,
    load_fonts,
    draw_text_safe,
    wrap_text,
    create_vocab_overlay,
    create_grammar_overlay,
    create_combined_overlay,
    create_transition_frame,
    PANEL_BG, BORDER_COLOR, WORD_COLOR, MEANING_COLOR,
    GRAMMAR_COLOR, CONN_COLOR, TITLE_COLOR,
)


# ─────────────────────────────────────────────
# 单条目卡片渲染
# ─────────────────────────────────────────────

CARD_W_RATIO = 0.44   # 卡片总宽度占视频宽度的比例
COL1_RATIO   = 0.18   # 第一列（level）占卡片宽度的比例

def create_item_card(width, height, item, item_type, font_path=None):
    """
    渲染单条注释卡片，两列布局：
      第一列（窄）：level 标签，垂直居中显示
      第二列（宽）：各字段各占一行，从上到下排列
    词汇卡片 → 左上角；文法卡片 → 右上角
    """
    base   = max(14, int(height * 0.028))
    _, _, body_f, small_f = load_fonts(font_path, base)
    line_h = base + 10

    panel_w = int(width * CARD_W_RATIO)
    col1_w  = int(panel_w * COL1_RATIO)   # level 列宽

    if item_type == "vocab":
        level   = item.get("level", "")
        word    = item.get("word",    "")
        reading = item.get("reading", "")
        meaning = item.get("meaning", "")

        col1_text  = level
        col1_color = TITLE_COLOR          # 金色

        # 第二列：每个字段单独一行
        col2_lines = []
        if word:
            col2_lines.append((f"▶ {word}", WORD_COLOR, body_f))
        if reading:
            col2_lines.append((f"（{reading}）", CONN_COLOR, small_f))
        if meaning:
            col2_lines.append((f"→ {meaning}", MEANING_COLOR, small_f))

        px, py = 18, 18   # 左上角

    else:  # grammar
        level      = item.get("level",   "")
        pattern    = item.get("pattern", item.get("word", ""))
        connection = item.get("connection", "")
        meaning    = item.get("meaning",  "")

        col1_text  = level if level else "文法"
        col1_color = GRAMMAR_COLOR        # 琥珀色

        col2_lines = []
        if pattern:
            col2_lines.append((f"◆ {pattern}", GRAMMAR_COLOR, body_f))
        if connection:
            col2_lines.append((f"接続：{connection}", CONN_COLOR, small_f))
        if meaning:
            col2_lines.append((f"→ {meaning}", MEANING_COLOR, small_f))

        px = width - panel_w - 18         # 右上角
        py = 18

    # ── 自动换行展开 col2_lines ──────────────────────────────────────────────
    avail_w = panel_w - col1_w - 16   # col1 + 8px left + 8px right margin
    tmp_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    expanded = []
    for text, color, font in col2_lines:
        for line in wrap_text(tmp_draw, text, font, avail_w):
            expanded.append((line, color, font))

    panel_h = max(len(expanded) * line_h + 22, line_h + 22)

    # ── 绘制卡片 ─────────────────────────────────────────────────────────────
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    panel  = Image.new("RGBA", (panel_w, panel_h), PANEL_BG)
    canvas.paste(panel, (px, py), panel)

    draw = ImageDraw.Draw(canvas)

    # 外边框
    draw.rectangle(
        [px, py, px + panel_w - 1, py + panel_h - 1],
        outline=BORDER_COLOR, width=2,
    )

    # 两列之间的分隔线
    div_x = px + col1_w
    draw.line([(div_x, py + 6), (div_x, py + panel_h - 6)],
              fill=BORDER_COLOR, width=1)

    # 第一列：level 文字垂直居中
    if col1_text:
        bbox = draw.textbbox((0, 0), col1_text, font=small_f)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        cx = px + (col1_w - tw) // 2
        cy = py + (panel_h - th) // 2
        draw_text_safe(draw, (cx, cy), col1_text, small_f, col1_color)

    # 第二列：各字段逐行排列（已自动换行）
    x2 = div_x + 8
    y2 = py + 10
    for text, color, font in expanded:
        draw_text_safe(draw, (x2, y2), text, font, color)
        y2 += line_h

    return canvas


# ─────────────────────────────────────────────
# 时间戳模式：Part 2 生成
# ─────────────────────────────────────────────

def build_timed_part2(ffmpeg_exe, source_video, timed_items, clip_dur, output_path,
                      display_dur=3.0, fade_dur=0.4):
    """
    timed_items: list of (png_path, start_sec)
    每张覆盖图在指定时间点渐入、显示 display_dur 秒后渐出。

    原理：
      - 每张 PNG 以 -loop 1 循环为整段时长的流
      - format=rgba 确保保留 alpha 通道
      - fade=t=in  → 在 start 前 alpha=0，在 start~start+fade_dur 内从 0→1
      - fade=t=out → 在 fade_out_st~fade_out_st+fade_dur 内从 1→0，之后 alpha=0
    """
    # 主视频
    cmd = [ffmpeg_exe, "-y", "-ss", "0", "-t", str(clip_dur), "-i", str(source_video)]

    # 每张覆盖图：循环至整段时长
    for png_path, _ in timed_items:
        cmd += ["-loop", "1", "-t", str(clip_dur), "-i", str(png_path)]

    n = len(timed_items)
    filter_parts = []

    # 对每路图像流应用渐入渐出
    for i, (_, start) in enumerate(timed_items):
        end          = min(start + display_dur, clip_dur)
        fade_out_st  = max(start + fade_dur + 0.01, end - fade_dur)
        filter_parts.append(
            f"[{i + 1}:v]format=rgba,"
            f"fade=t=in:st={start}:d={fade_dur}:alpha=1,"
            f"fade=t=out:st={fade_out_st}:d={fade_dur}:alpha=1"
            f"[ov{i}]"
        )

    # 依次叠加到基础视频上
    for i in range(n):
        in_v  = "[0:v]" if i == 0 else f"[v{i}]"
        out_v = "[vout]" if i == n - 1 else f"[v{i + 1}]"
        filter_parts.append(f"{in_v}[ov{i}]overlay=0:0{out_v}")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]
    run_ffmpeg(cmd, "part2-timed")


# ─────────────────────────────────────────────
# Meta 文件定位
# ─────────────────────────────────────────────

def find_latest_meta(text_dir: Path):
    metas = sorted(
        text_dir.glob("*_meta.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return metas[0] if metas else None


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Step 2: 生成注释叠加视频并与 Part 1 合并",
    )
    parser.add_argument("--meta",        "-m", default=None,
                        help="Step 1 生成的 meta JSON（省略则自动检测 text/ 中最新的）")
    parser.add_argument("--config",      "-c", required=True,
                        help="词汇/文法配置文件（config_example.json）")
    parser.add_argument("--display-dur", "-t", type=float, default=3.0,
                        help="每条注释显示时长（秒，默认 3.0）")
    parser.add_argument("--mode", choices=["split", "combined"], default="split",
                        help="无时间戳时的经典模式（默认 split）")
    args = parser.parse_args()

    base_dir    = Path(__file__).parent
    text_dir    = base_dir / "text"
    product_dir = base_dir / "product"
    product_dir.mkdir(exist_ok=True)

    # ── 加载 meta ───────────────────────────────────────────────────────────────
    if args.meta:
        meta_path = Path(args.meta)
        if not meta_path.exists():
            sys.exit(f"找不到 meta 文件：{meta_path}")
    else:
        meta_path = find_latest_meta(text_dir)
        if not meta_path:
            sys.exit("text/ 中没有 meta 文件，请先运行 step1_prepare.py")
        print(f"自动检测到 meta 文件：{meta_path.name}")

    meta         = json.loads(meta_path.read_text(encoding="utf-8"))
    source_video = meta["source_video"]
    part1_path   = meta["part1_video"]
    width        = meta["width"]
    height       = meta["height"]
    clip_dur     = meta["clip_dur"]
    fps          = meta.get("fps", 24.0)
    ts           = meta["timestamp"]

    for label, path in [("原始视频", source_video), ("Part 1 视频", part1_path)]:
        if not Path(path).exists():
            sys.exit(f"{label}不存在：{path}\n请重新运行 step1_prepare.py")

    # ── 加载 config ─────────────────────────────────────────────────────────────
    if not Path(args.config).exists():
        sys.exit(f"找不到 config：{args.config}")
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    vocabulary = cfg.get("vocabulary", [])
    grammar    = cfg.get("grammar",    [])

    # 判断是否启用时间戳模式
    has_timestamps = any("at" in item for item in vocabulary + grammar)

    stem        = Path(source_video).stem
    output_path = product_dir / f"{stem}_learning_{ts}.mp4"

    ffmpeg_exe, _ = get_ffmpeg_paths()
    font_path     = find_japanese_font()

    print(f"FFmpeg      : {ffmpeg_exe}")
    print(f"原始视频    : {source_video}")
    print(f"Part 1 视频 : {part1_path}")
    print(f"词汇数量    : {len(vocabulary)}")
    print(f"文法数量    : {len(grammar)}")
    print(f"显示模式    : {'时间戳模式' if has_timestamps else f'经典模式（{args.mode}）'}")
    if has_timestamps:
        print(f"显示时长    : {args.display_dur}s / 条")
    print(f"输出路径    : {output_path}")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path       = Path(tmp)
        part2_path     = tmp_path / "part2.mp4"
        concat_txt     = tmp_path / "concat.txt"
        transition_png = tmp_path / "transition.png"
        transition_mp4 = tmp_path / "transition.mp4"

        # ── Part 2 ──────────────────────────────────────────────────────────────
        print("▶ Part 2 — 生成注释叠加视频 …")

        if has_timestamps:
            # ── 时间戳模式：每条注释按时间点单独弹出 ──────────────────────────
            timed_items = []

            for i, item in enumerate(vocabulary):
                start = float(item.get("at", 0))
                png   = tmp_path / f"card_vocab_{i}.png"
                create_item_card(width, height, item, "vocab", font_path).save(str(png))
                timed_items.append((str(png), start))
                print(f"  词汇 [{item.get('word','')}]  at {start:.0f}s")

            for i, item in enumerate(grammar):
                start = float(item.get("at", 0))
                png   = tmp_path / f"card_grammar_{i}.png"
                create_item_card(width, height, item, "grammar", font_path).save(str(png))
                timed_items.append((str(png), start))
                print(f"  文法 [{item.get('pattern', item.get('word',''))}]  at {start:.0f}s")

            # 按出现时间排序，确保 FFmpeg 滤镜链顺序合理
            timed_items.sort(key=lambda x: x[1])

            build_timed_part2(
                ffmpeg_exe, source_video, timed_items,
                clip_dur, str(part2_path),
                display_dur=args.display_dur,
                fade_dur=0.4,
            )

        else:
            # ── 经典模式（向下兼容）────────────────────────────────────────────
            if args.mode == "combined":
                overlay_png = str(tmp_path / "overlay_combined.png")
                create_combined_overlay(width, height, vocabulary, grammar, font_path).save(overlay_png)
                cmd2 = [
                    ffmpeg_exe, "-y",
                    "-ss", "0", "-t", str(clip_dur),
                    "-i", source_video,
                    "-i", overlay_png,
                    "-filter_complex", "[0:v][1:v]overlay=0:0[vout]",
                    "-map", "[vout]", "-map", "0:a",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-c:a", "aac", "-b:a", "128k",
                    str(part2_path),
                ]
                run_ffmpeg(cmd2, "part2-combined")
            else:
                half        = clip_dur / 2
                vocab_png   = str(tmp_path / "overlay_vocab.png")
                grammar_png = str(tmp_path / "overlay_grammar.png")
                create_vocab_overlay(width, height, vocabulary, font_path).save(vocab_png)
                create_grammar_overlay(width, height, grammar, font_path).save(grammar_png)
                flt = (
                    f"[0:v][1:v]overlay=0:0:enable='between(t,0,{half})'[v1];"
                    f"[v1][2:v]overlay=0:0:enable='between(t,{half},{clip_dur})'[vout]"
                )
                cmd2 = [
                    ffmpeg_exe, "-y",
                    "-ss", "0", "-t", str(clip_dur),
                    "-i", source_video,
                    "-i", vocab_png, "-i", grammar_png,
                    "-filter_complex", flt,
                    "-map", "[vout]", "-map", "0:a",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-c:a", "aac", "-b:a", "128k",
                    str(part2_path),
                ]
                run_ffmpeg(cmd2, "part2-split")

        print("  Done.\n")

        # ── 过渡画面（1.5 秒）───────────────────────────────────────────────────
        print("▶ 生成过渡画面 …")
        create_transition_frame(width, height, font_path).save(str(transition_png))
        fps_int = max(1, int(round(fps)))
        cmd_tr = [
            ffmpeg_exe, "-y",
            # 图像输入：-t 限制循环时长，-r 对齐源视频帧率
            "-loop", "1", "-t", "1.5", "-r", str(fps_int), "-i", str(transition_png),
            # 静音音频输入
            "-f", "lavfi", "-t", "1.5", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            # 强制 yuv420p 与 Part1/Part2 像素格式一致
            "-vf", "format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            str(transition_mp4),
        ]
        run_ffmpeg(cmd_tr, "transition")
        print("  Done.\n")

        # ── 拼接 ────────────────────────────────────────────────────────────────
        print("▶ 拼接 Part 1 + 过渡画面 + Part 2 …")
        with open(str(concat_txt), "w", encoding="utf-8") as f:
            for seg in (part1_path, str(transition_mp4), str(part2_path)):
                f.write(f"file '{str(seg).replace(chr(92), '/')}'\n")

        cmd3 = [
            ffmpeg_exe, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ]
        run_ffmpeg(cmd3, "concat")
        print("  Done.\n")

    print("=" * 60)
    print(f"✅ 最终学习视频 : {output_path}")


if __name__ == "__main__":
    main()
