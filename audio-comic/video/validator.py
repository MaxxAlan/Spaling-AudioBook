"""Validation for narration audio output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from video.ffmpeg_manager import FFmpegManager


@dataclass
class ValidationResult:
    """Result of one output check."""

    check_name: str
    passed: bool
    message: str = ""
    value: str = ""
    expected: str = ""


@dataclass
class FileValidationReport:
    """Complete validation report for one file."""

    filepath: str
    file_type: str
    results: List[ValidationResult]

    @property
    def all_passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def failed_checks(self) -> List[ValidationResult]:
        return [result for result in self.results if not result.passed]


def validate_audio(
    filepath: str,
    ffmpeg_manager: Optional[FFmpegManager] = None,
    expected_sample_rate: int = 44100,
    min_duration: float = 1.0,
) -> FileValidationReport:
    """Check that audio exists and has a valid stream, rate and duration."""
    path = Path(filepath)
    results = [
        ValidationResult(
            "File tồn tại",
            path.exists(),
            "Có" if path.exists() else "Không tìm thấy",
            str(path.exists()),
            "True",
        )
    ]
    if not path.exists():
        return FileValidationReport(filepath, "audio", results)

    size = path.stat().st_size
    results.append(
        ValidationResult(
            "Dung lượng > 0", size > 0, f"{size / 1024:.1f} KB", str(size), "> 0"
        )
    )

    manager = ffmpeg_manager or FFmpegManager()
    try:
        _video_streams, audio_streams = manager.get_streams(filepath)
        results.append(
            ValidationResult(
                "Có audio stream",
                bool(audio_streams),
                f"{len(audio_streams)} stream(s)",
                str(len(audio_streams)),
                ">= 1",
            )
        )
        if audio_streams:
            sample_rate = int(audio_streams[0].get("sample_rate", 0))
            results.append(
                ValidationResult(
                    "Sample rate",
                    sample_rate == expected_sample_rate,
                    f"{sample_rate} Hz",
                    str(sample_rate),
                    str(expected_sample_rate),
                )
            )
        duration = manager.get_duration(filepath)
        results.append(
            ValidationResult(
                "Duration hợp lệ",
                duration >= min_duration,
                f"{duration:.1f}s",
                f"{duration:.1f}",
                f">= {min_duration}",
            )
        )
    except Exception as exc:
        results.append(ValidationResult("FFprobe check", False, f"Lỗi: {exc}"))

    return FileValidationReport(filepath, "audio", results)
