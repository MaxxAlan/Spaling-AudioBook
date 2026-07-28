"""Audio export to WAV and MP3 formats."""

from __future__ import annotations

import subprocess
import shutil
import os
from pathlib import Path
from typing import Optional

from core.exceptions import AudioExportError
from utils.logging_config import get_logger

logger = get_logger("audio.exporter")


def export_wav(
    input_path: str,
    output_path: str,
) -> str:
    """Export/copy a WAV file to the output directory.

    Args:
        input_path: Source WAV file path.
        output_path: Destination WAV file path.

    Returns:
        Path to the exported WAV file.

    Raises:
        AudioExportError: If export fails.
    """
    src = Path(input_path)
    dst = Path(output_path)

    if not src.exists():
        raise AudioExportError(
            f"Source WAV file not found: {src}",
        )

    dst.parent.mkdir(parents=True, exist_ok=True)

    if src.resolve() != dst.resolve():
        shutil.copy2(str(src), str(dst))

    logger.info("Exported WAV: %s (%.1f MB)", dst.name, dst.stat().st_size / (1024 * 1024))
    return str(dst.resolve())


def export_mp3(
    input_wav_path: str,
    output_mp3_path: str,
    bitrate: str = "192k",
    ffmpeg_path: str = "",
) -> str:
    """Convert WAV to MP3 using FFmpeg.

    Args:
        input_wav_path: Source WAV file path.
        output_mp3_path: Destination MP3 file path.
        bitrate: MP3 bitrate (e.g., '192k', '320k').
        ffmpeg_path: Custom FFmpeg path (auto-detect if empty).

    Returns:
        Path to the exported MP3 file.

    Raises:
        AudioExportError: If conversion fails or FFmpeg is missing.
    """
    src = Path(input_wav_path)
    dst = Path(output_mp3_path)

    if not src.exists():
        raise AudioExportError(f"Source WAV not found: {src}")

    ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg:
        raise AudioExportError(
            "FFmpeg không được tìm thấy. Cần FFmpeg để xuất MP3.",
        )

    dst.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",  # Overwrite
        "-i", str(src),
        "-codec:a", "libmp3lame",
        "-b:a", bitrate,
        "-q:a", "0",
        str(dst),
    ]

    logger.info("Exporting MP3: %s (bitrate: %s)", dst.name, bitrate)
    logger.debug("FFmpeg command: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=None if os.environ.get("AUDIOBOOK_OVERNIGHT") == "1" else 9000,
        )

        if result.returncode != 0:
            raise AudioExportError(
                f"FFmpeg MP3 export failed (code {result.returncode})",
                details=result.stderr[:500] if result.stderr else "",
            )

        if not dst.exists() or dst.stat().st_size == 0:
            raise AudioExportError(
                "FFmpeg tạo file MP3 rỗng",
            )

        logger.info(
            "Exported MP3: %s (%.1f MB)",
            dst.name, dst.stat().st_size / (1024 * 1024),
        )
        return str(dst.resolve())

    except subprocess.TimeoutExpired:
        raise AudioExportError("FFmpeg MP3 export timed out (>150 minutes)")
    except FileNotFoundError:
        raise AudioExportError(f"FFmpeg not found at: {ffmpeg}")
