"""Lightweight gate for malformed or silent TTS segment WAVs."""

from __future__ import annotations

import struct
import wave
from pathlib import Path


def verify_tts_wav(path: str, text: str) -> tuple[bool, list[str]]:
    """Reject empty, silent, clipped, or implausibly short TTS output."""
    target = Path(path)
    if not target.is_file() or target.stat().st_size < 1024:
        return False, ["file_missing_or_empty"]
    try:
        with wave.open(str(target), "rb") as stream:
            width, channels, rate, frames = stream.getsampwidth(), stream.getnchannels(), stream.getframerate(), stream.getnframes()
            raw = stream.readframes(frames)
    except (OSError, wave.Error):
        return False, ["invalid_wav"]
    if width != 2 or channels < 1 or rate < 8000 or frames <= 0:
        return False, ["unsupported_audio_format"]
    samples = [value[0] for value in struct.iter_unpack("<h", raw[:len(raw) - len(raw) % 2])]
    if not samples:
        return False, ["no_samples"]
    rms = (sum(value * value for value in samples) / len(samples)) ** 0.5 / 32768.0
    duration = frames / rate
    reasons: list[str] = []
    if duration < max(0.12, min(2.0, len(text.strip()) / 90.0)):
        reasons.append("duration_too_short")
    if rms < 0.002:
        reasons.append("near_silence")
    clipped = sum(1 for value in samples if abs(value) >= 32700) / len(samples)
    if clipped > 0.02:
        reasons.append("clipping")
    return not reasons, reasons
