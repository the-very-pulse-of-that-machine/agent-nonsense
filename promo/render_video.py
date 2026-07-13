from __future__ import annotations

import argparse
import math
import subprocess
import wave
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont


WIDTH = 1920
HEIGHT = 1080
FPS = 24
DURATION_SECONDS = 30
ROOT = Path(__file__).resolve().parents[1]
MEDIA_DIR = ROOT / "media"
VIDEO_PATH = MEDIA_DIR / "agent-nonsense-promo.mp4"
POSTER_PATH = MEDIA_DIR / "agent-nonsense-promo-poster.png"
CONTACT_SHEET_PATH = MEDIA_DIR / "agent-nonsense-promo-contact-sheet.png"

INK = "#f4f1ea"
MUTED = "#9b9b94"
PANEL = "#17181b"
PANEL_LIGHT = "#202227"
BACKGROUND = "#0d0e10"
CORAL = "#ff5a47"
MINT = "#69d7ae"
YELLOW = "#f2c14e"
BLUE = "#64a8ff"


def load_font(size: int, mono: bool = False, bold: bool = False) -> ImageFont.FreeTypeFont:
    if mono:
        candidates = ["C:/Windows/Fonts/CascadiaMono.ttf", "C:/Windows/Fonts/consola.ttf"]
    elif bold:
        candidates = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/seguisb.ttf"]
    else:
        candidates = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf"]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


FONT_24 = load_font(24)
FONT_28 = load_font(28)
FONT_30_MONO = load_font(30, mono=True)
FONT_32 = load_font(32)
FONT_34_BOLD = load_font(34, bold=True)
FONT_38_MONO = load_font(38, mono=True)
FONT_42 = load_font(42)
FONT_48_BOLD = load_font(48, bold=True)
FONT_58_BOLD = load_font(58, bold=True)
FONT_76_BOLD = load_font(76, bold=True)
FONT_112_BOLD = load_font(112, bold=True)


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def smoothstep(value: float) -> float:
    progress = clamp(value)
    return progress * progress * (3 - 2 * progress)


def ease_out(value: float) -> float:
    progress = clamp(value)
    return 1 - (1 - progress) ** 3


def scene_opacity(time_seconds: float, start: float, end: float, fade: float = 0.55) -> float:
    fade_in = smoothstep((time_seconds - start) / fade)
    fade_out = smoothstep((end - time_seconds) / fade)
    return min(fade_in, fade_out)


def composite_scene(frame: Image.Image, layer: Image.Image, opacity: float) -> None:
    if opacity <= 0:
        return
    if opacity < 1:
        layer = layer.copy()
        alpha_channel = layer.getchannel("A").point(lambda value: int(value * opacity))
        layer.putalpha(alpha_channel)
    frame.alpha_composite(layer)


def draw_background(frame: Image.Image, time_seconds: float) -> None:
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=BACKGROUND)
    draw.rectangle((0, 0, 18, HEIGHT), fill=CORAL)
    for column in range(0, WIDTH, 96):
        draw.line((column, 0, column, HEIGHT), fill="#141519", width=1)
    for row in range(0, HEIGHT, 96):
        draw.line((0, row, WIDTH, row), fill="#141519", width=1)
    moving_row = int((time_seconds * 42) % HEIGHT)
    draw.line((0, moving_row, WIDTH, moving_row), fill="#202126", width=1)


def draw_brand_mark(draw: ImageDraw.ImageDraw, left: int, top: int, size: int = 74) -> None:
    draw.rounded_rectangle((left, top, left + size, top + size), radius=8, fill=CORAL)
    label_font = load_font(max(24, int(size * 0.35)), bold=True)
    draw.text((left + size / 2, top + size / 2), "AN", font=label_font, fill=BACKGROUND, anchor="mm")


def draw_chrome(draw: ImageDraw.ImageDraw, title: str, left: int, top: int, right: int, bottom: int) -> None:
    draw.rounded_rectangle((left, top, right, bottom), radius=8, fill=PANEL, outline="#34363d", width=2)
    draw.rectangle((left + 1, top + 58, right - 1, top + 60), fill="#2a2c31")
    for index, color in enumerate((CORAL, YELLOW, MINT)):
        center_left = left + 30 + index * 30
        draw.ellipse((center_left, top + 23, center_left + 14, top + 37), fill=color)
    draw.text((left + 130, top + 29), title, font=FONT_24, fill=MUTED, anchor="lm")


def draw_header(draw: ImageDraw.ImageDraw, section: str) -> None:
    draw_brand_mark(draw, 70, 48, 56)
    draw.text((146, 76), "agent-nonsense", font=FONT_34_BOLD, fill=INK, anchor="lm")
    draw.text((1840, 76), section.upper(), font=FONT_24, fill=MUTED, anchor="rm")


def draw_title_scene(time_seconds: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    progress = ease_out((time_seconds - 0.2) / 1.2)
    offset = int((1 - progress) * 70)
    draw_brand_mark(draw, 170, 160 + offset, 96)
    draw.text((170, 330 + offset), "agent-nonsense", font=FONT_112_BOLD, fill=INK)
    draw.text((176, 485 + offset), "不花钱，也能体验 token 流动的荒诞效果", font=FONT_48_BOLD, fill="#d8d5ce")
    draw.rectangle((176, 585 + offset, 1020, 590 + offset), fill=CORAL)
    badges = (("ZERO TOKEN", MINT), ("OPENAI + CLAUDE", BLUE), ("API ONLY", YELLOW))
    badge_left = 176
    for label, color in badges:
        label_width = int(draw.textlength(label, font=FONT_24)) + 54
        draw.rounded_rectangle((badge_left, 650 + offset, badge_left + label_width, 704 + offset), radius=8, fill=PANEL_LIGHT)
        draw.ellipse((badge_left + 18, 671 + offset, badge_left + 30, 683 + offset), fill=color)
        draw.text((badge_left + 40, 677 + offset), label, font=FONT_24, fill=INK, anchor="lm")
        badge_left += label_width + 18
    pulse = 0.5 + 0.5 * math.sin(time_seconds * math.pi * 2)
    pulse_color = (255, 90, 71, int(45 + pulse * 55))
    draw.ellipse((1390, 220, 1750, 580), outline=pulse_color, width=4)
    draw.ellipse((1460, 290, 1680, 510), fill=CORAL)
    draw.text((1570, 400), "0", font=FONT_112_BOLD, fill=BACKGROUND, anchor="mm")
    draw.text((1570, 530), "tokens", font=FONT_32, fill=INK, anchor="mm")
    draw.text((176, 935), "LOCAL SIMULATION SERVICE  /  MIT LICENSE", font=FONT_24, fill=MUTED)
    return layer


def draw_setup_scene(time_seconds: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw_header(draw, "01 / launch")
    draw_chrome(draw, "PowerShell — local service", 145, 155, 1775, 900)
    command = "agent-nonsense --port 8788 --continuous-stream --simulate-tools"
    type_progress = clamp((time_seconds - 4.5) / 2.0)
    visible_command = command[: int(len(command) * type_progress)]
    draw.text((215, 270), "PS C:\\workspace>", font=FONT_30_MONO, fill=MINT)
    draw.text((510, 270), visible_command, font=FONT_30_MONO, fill=INK)
    cursor_left = 510 + int(draw.textlength(visible_command, font=FONT_30_MONO)) + 4
    if int(time_seconds * 3) % 2 == 0:
        draw.rectangle((cursor_left, 246, cursor_left + 14, 282), fill=CORAL)
    response_progress = smoothstep((time_seconds - 6.1) / 0.7)
    if response_progress > 0:
        lines = (
            ("agent-nonsense listening on http://127.0.0.1:8788", BLUE),
            ('{"service":"agent-nonsense","upstream_calls":0,"token_usage":0}', MUTED),
            ("stream cadence  2.0s + jitter", YELLOW),
            ("sandbox tools   enabled", MINT),
        )
        for index, (line, color) in enumerate(lines):
            line_progress = smoothstep((time_seconds - (6.2 + index * 0.32)) / 0.35)
            if line_progress > 0:
                draw.text((215, 380 + index * 72), line, font=FONT_30_MONO, fill=color)
    draw.rounded_rectangle((1245, 690, 1665, 825), radius=8, fill="#101113", outline="#34363d", width=2)
    draw.text((1280, 730), "UPSTREAM CALLS", font=FONT_24, fill=MUTED)
    draw.text((1280, 790), "0", font=FONT_58_BOLD, fill=MINT, anchor="lm")
    return layer


def draw_conversation_scene(time_seconds: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw_header(draw, "02 / streaming")
    draw_chrome(draw, "OpenAI Responses — stream=true", 105, 138, 1815, 955)
    draw.rounded_rectangle((155, 225, 1625, 318), radius=8, fill="#24262b")
    draw.text((195, 271), "USER", font=FONT_24, fill=BLUE, anchor="lm")
    draw.text((315, 271), "检查 Python 文件读写模块，定位潜在 bug 并验证修复结果。", font=FONT_32, fill=INK, anchor="lm")
    events = (
        (10.2, "ANALYSIS", "我先确认目录结构和调用链，避免直接修改错误的入口。", CORAL),
        (12.2, "tool.call", 'list_files  {"path":"."}', YELLOW),
        (14.2, "tool.result", "发现 18 个文件，锁定 agent_nonsense/server.py", MINT),
        (16.2, "CHECKING", "边界条件集中在路径逃逸和空文件处理，我先做最小验证。", CORAL),
        (18.2, "tool.call", 'read_file  {"path":"agent_nonsense/server.py"}', YELLOW),
        (20.2, "NEXT STEP", "工具结果已回到上下文，继续核对测试覆盖与回归风险。", CORAL),
    )
    for index, (event_time, label, message, color) in enumerate(events):
        reveal = smoothstep((time_seconds - event_time) / 0.42)
        if reveal <= 0:
            continue
        row_top = 375 + index * 84
        draw.line((195, row_top - 28, 195, row_top + 38), fill="#33353a", width=2)
        marker_radius = 7 if label in {"ANALYSIS", "CHECKING", "NEXT STEP"} else 5
        draw.ellipse((188 - marker_radius, row_top - marker_radius, 188 + marker_radius, row_top + marker_radius), fill=color)
        draw.text((225, row_top), label, font=FONT_24, fill=color, anchor="lm")
        message_left = 410
        visible_length = max(1, int(len(message) * reveal))
        draw.text((message_left, row_top), message[:visible_length], font=FONT_28, fill=INK, anchor="lm")
    draw.rounded_rectangle((1665, 225, 1765, 318), radius=8, fill="#101113", outline="#34363d", width=2)
    draw.text((1715, 252), "2.0s", font=FONT_28, fill=MINT, anchor="mm")
    draw.text((1715, 293), "节奏", font=FONT_24, fill=MUTED, anchor="mm")
    return layer


def draw_feature_icon(draw: ImageDraw.ImageDraw, center_left: int, center_top: int, color: str, kind: str) -> None:
    draw.rounded_rectangle((center_left - 40, center_top - 40, center_left + 40, center_top + 40), radius=8, fill=color)
    if kind == "api":
        draw.line((center_left - 20, center_top, center_left + 20, center_top), fill=BACKGROUND, width=8)
        draw.line((center_left - 10, center_top - 16, center_left - 25, center_top, center_left - 10, center_top + 16), fill=BACKGROUND, width=6)
        draw.line((center_left + 10, center_top - 16, center_left + 25, center_top, center_left + 10, center_top + 16), fill=BACKGROUND, width=6)
    elif kind == "zero":
        draw.ellipse((center_left - 22, center_top - 28, center_left + 22, center_top + 28), outline=BACKGROUND, width=8)
    elif kind == "tool":
        draw.rectangle((center_left - 24, center_top - 17, center_left + 24, center_top + 21), outline=BACKGROUND, width=7)
        draw.line((center_left - 10, center_top - 28, center_left + 10, center_top - 28), fill=BACKGROUND, width=7)
    else:
        for offset in (-16, 0, 16):
            draw.line((center_left - 25, center_top + offset, center_left + 25, center_top + offset), fill=BACKGROUND, width=6)


def draw_features_scene(time_seconds: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw_header(draw, "03 / capabilities")
    draw.text((150, 205), "没有 token，但有 token 流动的感觉", font=FONT_76_BOLD, fill=INK)
    draw.text((155, 310), "零成本接入桌面 Agent，看一场永不结束的“努力工作”。", font=FONT_42, fill=MUTED)
    features = (
        ("0 元体验", "没有模型账单", MINT, "zero"),
        ("流动感拉满", "每 2 秒推进一次", BLUE, "stream"),
        ("Agent 原味", "SSE + 工具调用", YELLOW, "tool"),
        ("荒诞但诚实", "不请求上游模型", CORAL, "api"),
    )
    card_width = 390
    start_left = 150
    for index, (title, detail, color, kind) in enumerate(features):
        reveal = ease_out((time_seconds - (22.0 + index * 0.22)) / 0.65)
        if reveal <= 0:
            continue
        card_left = start_left + index * 420
        card_top = int(460 + (1 - reveal) * 45)
        draw.rounded_rectangle((card_left, card_top, card_left + card_width, card_top + 300), radius=8, fill=PANEL, outline="#34363d", width=2)
        draw_feature_icon(draw, card_left + 75, card_top + 78, color, kind)
        draw.text((card_left + 35, card_top + 168), title, font=FONT_34_BOLD, fill=INK)
        draw.text((card_left + 35, card_top + 225), detail, font=FONT_28, fill=MUTED)
        draw.rectangle((card_left + 35, card_top + 270, card_left + 355, card_top + 274), fill=color)
    draw.text((150, 910), "API only  ·  Local first  ·  MIT licensed", font=FONT_28, fill=MUTED)
    return layer


def draw_end_scene(time_seconds: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    progress = ease_out((time_seconds - 26.2) / 0.9)
    offset = int((1 - progress) * 55)
    draw_brand_mark(draw, 150, 150 + offset, 86)
    draw.text((150, 300 + offset), "agent-nonsense", font=FONT_112_BOLD, fill=INK)
    draw.text((155, 450 + offset), "让不存在的 token，一直流动。", font=FONT_58_BOLD, fill="#d8d5ce")
    draw.rounded_rectangle((155, 590 + offset, 1550, 690 + offset), radius=8, fill=PANEL, outline="#3a3c42", width=2)
    draw.text((205, 640 + offset), "pip install agent-nonsense", font=FONT_38_MONO, fill=MINT, anchor="lm")
    draw.text((155, 780 + offset), "http://127.0.0.1:8788/v1", font=FONT_38_MONO, fill=BLUE)
    draw.text((155, 865 + offset), "FREE TO RUN  /  ABSURD TO WATCH  /  CONTINUOUS STREAM", font=FONT_24, fill=MUTED)
    draw.text((1750, 855), "0", font=FONT_112_BOLD, fill=CORAL, anchor="mm")
    draw.text((1750, 930), "tokens", font=FONT_28, fill=INK, anchor="mm")
    return layer


def render_frame(time_seconds: float) -> Image.Image:
    frame = Image.new("RGBA", (WIDTH, HEIGHT), BACKGROUND)
    draw_background(frame, time_seconds)
    scenes = (
        (draw_title_scene(time_seconds), scene_opacity(time_seconds, 0.0, 4.5)),
        (draw_setup_scene(time_seconds), scene_opacity(time_seconds, 4.0, 9.5)),
        (draw_conversation_scene(time_seconds), scene_opacity(time_seconds, 9.0, 21.8)),
        (draw_features_scene(time_seconds), scene_opacity(time_seconds, 21.3, 26.7)),
        (draw_end_scene(time_seconds), scene_opacity(time_seconds, 26.2, 30.1)),
    )
    for layer, opacity in scenes:
        composite_scene(frame, layer, opacity)
    return frame.convert("RGB")


def render_preview_assets() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    poster = render_frame(28.0)
    poster.save(POSTER_PATH, quality=95)
    preview_times = (1.8, 6.8, 13.8, 19.0, 23.8, 28.0)
    sheet = Image.new("RGB", (1920, 1620), BACKGROUND)
    for index, preview_time in enumerate(preview_times):
        thumbnail = render_frame(preview_time).resize((960, 540), Image.Resampling.LANCZOS)
        left = (index % 2) * 960
        top = (index // 2) * 540
        sheet.paste(thumbnail, (left, top))
    sheet.save(CONTACT_SHEET_PATH, quality=92)


def render_audio(output_path: Path) -> None:
    sample_rate = 44100
    sample_count = int(DURATION_SECONDS * sample_rate)
    timeline = np.arange(sample_count, dtype=np.float64) / sample_rate
    fade_in = np.minimum(1.0, timeline / 1.5)
    fade_out = np.minimum(1.0, (DURATION_SECONDS - timeline) / 1.8)
    envelope = np.maximum(0.0, fade_in * fade_out)
    ambient = (
        0.030 * np.sin(2 * np.pi * 110.0 * timeline)
        + 0.018 * np.sin(2 * np.pi * 164.81 * timeline)
        + 0.012 * np.sin(2 * np.pi * 220.0 * timeline)
    ) * envelope
    audio = ambient
    cue_times = (4.2, 6.2, 9.2, 10.2, 12.2, 14.2, 16.2, 18.2, 20.2, 21.5, 26.2)
    for cue_index, cue_time in enumerate(cue_times):
        cue_start = int(cue_time * sample_rate)
        cue_length = int(0.18 * sample_rate)
        cue_timeline = np.arange(cue_length, dtype=np.float64) / sample_rate
        frequency = 440.0 if cue_index % 2 == 0 else 554.37
        cue = 0.09 * np.sin(2 * np.pi * frequency * cue_timeline) * np.exp(-cue_timeline * 22)
        cue_end = min(sample_count, cue_start + cue_length)
        audio[cue_start:cue_end] += cue[: cue_end - cue_start]
    stereo = np.column_stack((audio, audio * 0.94))
    pcm = np.int16(np.clip(stereo, -1.0, 1.0) * 32767)
    with wave.open(str(output_path), "wb") as audio_file:
        audio_file.setnchannels(2)
        audio_file.setsampwidth(2)
        audio_file.setframerate(sample_rate)
        audio_file.writeframes(pcm.tobytes())


def render_video() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    silent_path = MEDIA_DIR / ".agent-nonsense-promo-silent.mp4"
    audio_path = MEDIA_DIR / ".agent-nonsense-promo.wav"
    writer = imageio.get_writer(
        silent_path,
        fps=FPS,
        codec="libx264",
        quality=8,
        macro_block_size=None,
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    )
    try:
        for frame_index in range(DURATION_SECONDS * FPS):
            writer.append_data(np.asarray(render_frame(frame_index / FPS)))
    finally:
        writer.close()
    render_audio(audio_path)
    ffmpeg_executable = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg_executable,
        "-y",
        "-i",
        str(silent_path),
        "-i",
        str(audio_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(VIDEO_PATH),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    silent_path.unlink(missing_ok=True)
    audio_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the Agent Nonsense promotional video")
    parser.add_argument("--preview-only", action="store_true", help="Render poster and contact sheet without encoding video")
    arguments = parser.parse_args()
    render_preview_assets()
    if not arguments.preview_only:
        render_video()
    print(f"poster={POSTER_PATH}")
    print(f"contact_sheet={CONTACT_SHEET_PATH}")
    if not arguments.preview_only:
        print(f"video={VIDEO_PATH}")


if __name__ == "__main__":
    main()
