"""Create an audiobook video from a timed sequence of story images."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Iterable, Optional

from core.exceptions import VideoExportError
from video.ffmpeg_manager import FFmpegManager


def _concat_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "'\\''")


def _subtitle_filter(path: Path) -> str:
    escaped = path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
    style = "FontName=Arial,FontSize=22,MarginV=36,Alignment=2,Outline=2,Shadow=1"
    return f"subtitles=filename='{escaped}':force_style='{style}'"


def create_storyboard_video(
    image_paths: Iterable[str],
    audio_path: str,
    output_path: str,
    durations: Optional[Iterable[float]] = None,
    subtitle_path: Optional[str] = None,
    subtitle_mode: str = "soft",
    ffmpeg_manager: Optional[FFmpegManager] = None,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    crf: int = 20,
    preset: str = "medium",
    video_encoder: str = "libx264",
    unlimited: bool = False,
    progress_callback: Callable[[float, float], None] | None = None,
) -> str:
    """Combine images/audio and optionally embed or burn Vietnamese subtitles."""
    images = [Path(value).resolve() for value in image_paths]
    audio = Path(audio_path).resolve()
    subtitles = Path(subtitle_path).resolve() if subtitle_path else None
    output = Path(output_path).resolve()
    if not images:
        raise VideoExportError("Storyboard cần ít nhất 1 ảnh")
    missing = [str(value) for value in images if not value.is_file()]
    if missing:
        raise VideoExportError(f"Không tìm thấy ảnh storyboard: {missing[0]}")
    if not audio.is_file():
        raise VideoExportError(f"Không tìm thấy audio: {audio}")
    if subtitles is not None and not subtitles.is_file():
        raise VideoExportError(f"Không tìm thấy phụ đề: {subtitles}")
    if subtitle_mode not in ("none", "soft", "burn"):
        raise VideoExportError(f"Chế độ phụ đề không hợp lệ: {subtitle_mode}")
    manager = ffmpeg_manager or FFmpegManager()
    audio_duration = manager.get_duration(str(audio))
    if audio_duration <= 0:
        raise VideoExportError("Không đọc được thời lượng audio")
    values = list(durations or [audio_duration / len(images)] * len(images))
    if len(values) != len(images) or any(value <= 0 for value in values):
        raise VideoExportError("Số mốc thời gian storyboard không hợp lệ")
    scale = audio_duration / sum(values)
    values = [value * scale for value in values]
    output.parent.mkdir(parents=True, exist_ok=True)
    list_path: Path | None = None
    soft_subtitles = subtitles is not None and subtitle_mode == "soft"
    burn_subtitles = subtitles is not None and subtitle_mode == "burn"
    render_output = (
        output.with_name(f"{output.stem}.video-only.tmp.mp4")
        if soft_subtitles else output
    )
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".ffconcat",
            prefix="audiobook-", dir=output.parent, delete=False,
        ) as handle:
            handle.write("ffconcat version 1.0\n")
            for image, duration in zip(images, values):
                handle.write(f"file '{_concat_path(image)}'\n")
                handle.write(f"duration {duration:.6f}\n")
            handle.write(f"file '{_concat_path(images[-1])}'\n")
            list_path = Path(handle.name)
        video_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},format=yuv420p"
        )
        if burn_subtitles:
            video_filter += f",{_subtitle_filter(subtitles)}"
        video_codec = ["-c:v", video_encoder]
        video_quality = (
            ["-preset", "p4", "-cq", str(crf), "-b:v", "0"]
            if video_encoder == "h264_nvenc"
            else ["-preset", preset, "-crf", str(crf)]
        )
        ffmpeg_args = [
            "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
            "-vf", video_filter,
            *video_codec, *video_quality,
            "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
            "-t", f"{audio_duration:.6f}", "-shortest",
            "-movflags", "+faststart", str(render_output),
        ]
        ffmpeg_kwargs = {"timeout": None if unlimited else 18000}
        if progress_callback:
            ffmpeg_kwargs["progress_callback"] = (
                lambda position: progress_callback(position, audio_duration)
            )
        manager.run_ffmpeg(ffmpeg_args, **ffmpeg_kwargs)
        if soft_subtitles:
            manager.run_ffmpeg([
                "-y", "-i", str(render_output), "-i", str(subtitles),
                "-map", "0:v:0", "-map", "0:a:0", "-map", "1:s:0",
                "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
                "-metadata:s:s:0", "language=vie",
                "-metadata:s:s:0", "title=Tiếng Việt",
                "-disposition:s:0", "default",
                "-movflags", "+faststart", str(output),
            ], timeout=None if unlimited else 3000)
            render_output.unlink(missing_ok=True)
    except VideoExportError:
        render_output.unlink(missing_ok=True)
        if render_output != output:
            output.unlink(missing_ok=True)
        raise
    finally:
        if list_path is not None:
            list_path.unlink(missing_ok=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise VideoExportError("FFmpeg không tạo được video storyboard")
    return str(output)
