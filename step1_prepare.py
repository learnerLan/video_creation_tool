#!/usr/bin/env python3
"""
Step 1 — Prepare
================
做两件事：
  1. 遮挡字幕区域 → 保存到 unsubtitled/  （Part 1）
  2. 音声转写（日语）→ 带时间戳的 txt → 保存到 text/
  3. 写出 meta JSON 供 Step 2 使用

Usage:
    python step1_prepare.py video/input.mp4
    python step1_prepare.py video/input.mp4 --duration 60 --subtitle-cover 0.13
    python step1_prepare.py video/input.mp4 --whisper-model medium

Whisper model sizes (首次运行自动下载):
    tiny   ~75 MB  速度最快，精度略低
    base   ~145 MB
    small  ~488 MB  推荐，日语效果好  ← 默认
    medium ~1.5 GB  精度高，速度慢

依赖安装:
    pip install faster-whisper
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 复用 jp_video_editor 中的 FFmpeg 工具函数 ──────────────────────────────────
from jp_video_editor import get_ffmpeg_paths, get_video_info, run_ffmpeg


# ─────────────────────────────────────────────
# 音声转写
# ─────────────────────────────────────────────

MODEL_SIZE_MB = {"tiny": 75, "base": 145, "small": 488, "medium": 1500, "large": 2900}


def transcribe_audio(video_path, out_txt_path, whisper_model="small"):
    """
    用 faster-whisper 将视频音轨转写为带时间戳的日语文本。
    输出格式：
        [00:02] セリフ内容
        [00:08] 次のセリフ
        ...
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError(
            "需要安装 faster-whisper：\n"
            "    pip install faster-whisper"
        )

    size_mb = MODEL_SIZE_MB.get(whisper_model, "?")
    print(f"  加载 Whisper 模型 '{whisper_model}'（首次运行约下载 {size_mb} MB）…")
    model = WhisperModel(whisper_model, device="cpu", compute_type="int8")

    print("  转写音频中（日语）…")
    segments, info = model.transcribe(
        str(video_path),
        language="ja",
        beam_size=5,
        vad_filter=True,          # 过滤静音片段
        vad_parameters={"min_silence_duration_ms": 500},
    )

    lines = []
    for seg in segments:
        minutes = int(seg.start) // 60
        seconds = int(seg.start) % 60
        ts = f"[{minutes:02d}:{seconds:02d}]"
        text = seg.text.strip()
        if text:
            lines.append(f"{ts} {text}")

    out_path = Path(out_txt_path)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  共转写 {len(lines)} 段 → {out_path.name}")
    return lines


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Step 1: 遮挡字幕 + 音声转写",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
完成后请：
  1. 打开 text/ 文件夹中的 .txt 文件，阅读转写内容
  2. 整理 N3 以上文法和词汇，填写 config_example.json
  3. 运行 step2_compile.py 生成最终学习视频
""",
    )
    parser.add_argument("input",
                        help="输入视频文件（MP4、MKV 等）")
    parser.add_argument("--duration", "-d", type=float, default=60,
                        help="截取视频前 N 秒（默认 60）")
    parser.add_argument("--subtitle-cover", type=float, default=0.13,
                        help="字幕区域占画面高度的比例（默认 0.13）")
    parser.add_argument("--whisper-model", "-m", default="small",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper 模型大小（默认 small）")
    parser.add_argument("--no-transcribe", action="store_true",
                        help="跳过音声转写（仅生成字幕遮挡视频）")
    args = parser.parse_args()

    # ── 目录准备 ───────────────────────────────────────────────────────────────
    base_dir        = Path(__file__).parent
    unsubtitled_dir = base_dir / "unsubtitled"
    text_dir        = base_dir / "text"
    unsubtitled_dir.mkdir(exist_ok=True)
    text_dir.mkdir(exist_ok=True)

    stem = Path(args.input).stem
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")

    part1_path = unsubtitled_dir / f"{stem}_{ts}.mp4"
    txt_path   = text_dir / f"{stem}_{ts}.txt"
    meta_path  = text_dir / f"{stem}_{ts}_meta.json"

    ffmpeg_exe, ffprobe_exe = get_ffmpeg_paths()
    print(f"FFmpeg : {ffmpeg_exe}\n")

    # ── 视频信息 ────────────────────────────────────────────────────────────────
    print(f"读取视频信息：{args.input}")
    width, height, video_dur, fps = get_video_info(ffprobe_exe, args.input)
    clip_dur = min(args.duration, video_dur)
    print(f"  分辨率: {width}x{height}  |  FPS: {fps:.2f}  |  时长: {video_dur:.1f}s")
    print(f"  处理前 {clip_dur:.0f}s\n")

    # ── Part 1：遮挡字幕区域 ────────────────────────────────────────────────────
    print("▶ Part 1 — 遮挡字幕区域 …")
    sub_h = int(height * args.subtitle_cover)
    sub_y = height - sub_h

    flt = (
        f"[0:v]split[main][orig];"
        f"[orig]crop={width}:{sub_h}:0:{sub_y},gblur=sigma=18[blurred];"
        f"[main][blurred]overlay=0:{sub_y}[v1];"
        f"[v1]drawbox=x=0:y={sub_y}:w={width}:h={sub_h}:color=black@0.45:t=fill[vout]"
    )
    cmd1 = [
        ffmpeg_exe, "-y",
        "-ss", "0", "-t", str(clip_dur),
        "-i", str(args.input),
        "-filter_complex", flt,
        "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        str(part1_path),
    ]
    run_ffmpeg(cmd1, "part1")
    print(f"  Done → {part1_path}\n")

    # ── 音声转写 ────────────────────────────────────────────────────────────────
    if not args.no_transcribe:
        print("▶ 音声转写（日语）…")
        transcribe_audio(args.input, txt_path, args.whisper_model)
        print(f"  Done → {txt_path}\n")
    else:
        print("▶ 跳过音声转写（--no-transcribe）\n")
        txt_path = None

    # ── 写出 meta 文件（供 Step 2 读取）────────────────────────────────────────
    meta = {
        "source_video":       str(Path(args.input).resolve()),
        "part1_video":        str(part1_path.resolve()),
        "transcript":         str(txt_path.resolve()) if txt_path else None,
        "width":              width,
        "height":             height,
        "video_duration":     video_dur,
        "fps":                fps,
        "clip_dur":           clip_dur,
        "subtitle_cover_pct": args.subtitle_cover,
        "timestamp":          ts,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 完成提示 ────────────────────────────────────────────────────────────────
    print("=" * 60)
    print(f"✅ Part 1（字幕遮挡）  : {part1_path}")
    if txt_path:
        print(f"✅ 转写文本            : {txt_path}")
    print(f"✅ Meta 文件           : {meta_path}")
    print()
    print("接下来：")
    if txt_path:
        print(f"  1. 阅读转写文本：{txt_path}")
        print(f"  2. 整理文法/词汇，编辑 config_example.json")
    else:
        print(f"  1. 整理文法/词汇，编辑 config_example.json")
    print(f"  3. 运行 Step 2：")
    print(f"       python step2_compile.py --config config_example.json")
    print(f"     （或指定 meta）")
    print(f"       python step2_compile.py --meta \"{meta_path}\" --config config_example.json")


if __name__ == "__main__":
    main()
