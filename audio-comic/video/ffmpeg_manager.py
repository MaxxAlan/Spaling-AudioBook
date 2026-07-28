"""FFmpeg manager for detecting, validating, and running FFmpeg commands.

Handles path detection, command building, process execution,
and output parsing. Properly escapes paths with spaces and Vietnamese chars.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from core.exceptions import FFmpegNotFoundError, FFprobeNotFoundError, VideoExportError
from utils.logging_config import get_logger

logger = get_logger("video.ffmpeg_manager")


def _resolve_chocolatey_binary(candidate: str, name: str) -> str:
    """Bypass Chocolatey's forwarding shim, which can deadlock on noisy FFmpeg jobs."""
    if os.name != "nt" or not candidate or "chocolatey\\bin" not in candidate.lower():
        return candidate
    install = Path(os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey"))
    real = install / "lib" / "ffmpeg" / "tools" / "ffmpeg" / "bin" / f"{name}.exe"
    return str(real) if real.is_file() else candidate


class FFmpegManager:
    """Manager for FFmpeg/FFprobe operations.

    Provides detection, command building, execution, and output
    validation for video processing operations.
    """

    def __init__(
        self,
        ffmpeg_path: str = "",
        ffprobe_path: str = "",
    ) -> None:
        """Initialize FFmpeg manager.

        Args:
            ffmpeg_path: Custom FFmpeg path (auto-detect if empty).
            ffprobe_path: Custom FFprobe path (auto-detect if empty).
        """
        self._ffmpeg = _resolve_chocolatey_binary(
            ffmpeg_path or shutil.which("ffmpeg") or "", "ffmpeg"
        )
        self._ffprobe = _resolve_chocolatey_binary(
            ffprobe_path or shutil.which("ffprobe") or "", "ffprobe"
        )
        self.last_encoder_error = ""

    @property
    def ffmpeg_path(self) -> str:
        """FFmpeg binary path."""
        return self._ffmpeg

    @property
    def ffprobe_path(self) -> str:
        """FFprobe binary path."""
        return self._ffprobe

    @property
    def is_available(self) -> bool:
        """Check if FFmpeg is available."""
        return bool(self._ffmpeg) and Path(self._ffmpeg).exists() if self._ffmpeg else bool(shutil.which("ffmpeg"))

    def ensure_ffmpeg(self) -> str:
        """Ensure FFmpeg is available, raising an error if not.

        Returns:
            Path to FFmpeg binary.

        Raises:
            FFmpegNotFoundError: If FFmpeg is not found.
        """
        if self._ffmpeg and (Path(self._ffmpeg).exists() or shutil.which(self._ffmpeg)):
            return self._ffmpeg

        detected = shutil.which("ffmpeg")
        if detected:
            self._ffmpeg = detected
            return detected

        raise FFmpegNotFoundError(
            "FFmpeg không được tìm thấy trên hệ thống",
        )

    def ensure_ffprobe(self) -> str:
        """Ensure FFprobe is available.

        Returns:
            Path to FFprobe binary.

        Raises:
            FFprobeNotFoundError: If FFprobe is not found.
        """
        if self._ffprobe and (Path(self._ffprobe).exists() or shutil.which(self._ffprobe)):
            return self._ffprobe

        detected = shutil.which("ffprobe")
        if detected:
            self._ffprobe = detected
            return detected

        raise FFprobeNotFoundError(
            "FFprobe không được tìm thấy (cần cho validation)",
        )

    def run_ffmpeg(
        self,
        args: List[str],
        timeout: int | None = 3000,
        progress_callback: Callable[[float], None] | None = None,
    ) -> subprocess.CompletedProcess:
        """Run an FFmpeg command.

        Args:
            args: FFmpeg arguments (without the ffmpeg binary itself).
            timeout: Timeout in seconds.

        Returns:
            CompletedProcess result.

        Raises:
            FFmpegNotFoundError: If FFmpeg is not found.
            VideoExportError: If the command fails.
        """
        ffmpeg = self.ensure_ffmpeg()
        cmd = [ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error"]
        if progress_callback:
            cmd += ["-progress", "pipe:1"]
        cmd += args

        logger.info("FFmpeg command: %s", " ".join(f'"{a}"' if " " in a else a for a in cmd))

        try:
            if progress_callback:
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    encoding="utf-8", errors="replace",
                )
                assert process.stdout is not None
                for line in process.stdout:
                    if line.startswith("out_time="):
                        hours, minutes, seconds = line.strip().split("=", 1)[1].split(":")
                        progress_callback(
                            int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                        )
                try:
                    _, stderr = process.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    raise
                result = subprocess.CompletedProcess(cmd, process.returncode, "", stderr)
            else:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout,
                    encoding="utf-8", errors="replace",
                )

            if result.returncode != 0:
                error_msg = result.stderr[-500:] if result.stderr else "No error output"
                lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
                summary = next(
                    (
                        line for line in lines
                        if "driver" in line.lower() or "nvenc" in line.lower()
                        or "error" in line.lower()
                    ),
                    lines[0] if lines else error_msg,
                )
                raise VideoExportError(
                    f"FFmpeg failed (code {result.returncode}): {summary}",
                    details=error_msg,
                )

            return result

        except subprocess.TimeoutExpired:
            raise VideoExportError(
                f"FFmpeg timed out after {timeout}s",
            )
        except FileNotFoundError:
            raise FFmpegNotFoundError(
                f"FFmpeg binary not found: {ffmpeg}",
            )

    def supports_encoder(self, encoder: str) -> bool:
        """Return whether an encoder can actually initialize on this machine."""
        try:
            result = subprocess.run(
                [
                    self.ensure_ffmpeg(), "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=size=128x128:duration=0.1",
                    "-frames:v", "1", "-an", "-c:v", encoder, "-f", "null", "-",
                ],
                capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace",
            )
            self.last_encoder_error = result.stderr.strip()
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            self.last_encoder_error = f"Không thể khởi tạo thử encoder {encoder}."
            return False

    def probe_file(self, filepath: str) -> dict:
        """Get media file information using FFprobe.

        Args:
            filepath: Path to the media file.

        Returns:
            Dict with streams, format, and duration information.

        Raises:
            FFprobeNotFoundError: If FFprobe is not found.
        """
        ffprobe = self.ensure_ffprobe()

        cmd = [
            ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(filepath),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                logger.warning("FFprobe failed for %s: %s", filepath, result.stderr[:200])
                return {}

            return json.loads(result.stdout)

        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning("FFprobe error for %s: %s", filepath, e)
            return {}

    def get_duration(self, filepath: str) -> float:
        """Get the duration of a media file in seconds.

        Args:
            filepath: Path to the media file.

        Returns:
            Duration in seconds, or 0.0 if unknown.
        """
        info = self.probe_file(filepath)
        fmt = info.get("format", {})
        try:
            return float(fmt.get("duration", 0))
        except (ValueError, TypeError):
            return 0.0

    def get_streams(self, filepath: str) -> Tuple[List[dict], List[dict]]:
        """Get video and audio stream info.

        Args:
            filepath: Path to the media file.

        Returns:
            Tuple of (video_streams, audio_streams).
        """
        info = self.probe_file(filepath)
        streams = info.get("streams", [])

        video = [s for s in streams if s.get("codec_type") == "video"]
        audio = [s for s in streams if s.get("codec_type") == "audio"]

        return video, audio
