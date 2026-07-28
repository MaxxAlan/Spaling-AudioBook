"""Audio loudness normalization and noise trimming."""

from __future__ import annotations

import struct
import math
from typing import Tuple

from utils.logging_config import get_logger

logger = get_logger("audio.normalizer")


def calculate_rms(data: bytes, sample_width: int = 2) -> float:
    """Calculate RMS (Root Mean Square) loudness of PCM audio.

    Args:
        data: Raw PCM data.
        sample_width: Sample width in bytes.

    Returns:
        RMS value (0.0 to 1.0 range, normalized to max amplitude).
    """
    if not data:
        return 0.0

    n_samples = len(data) // sample_width
    if n_samples == 0:
        return 0.0

    sum_sq = 0.0
    max_val = 32768.0 if sample_width == 2 else 128.0

    for i in range(n_samples):
        offset = i * sample_width
        if sample_width == 2:
            value = struct.unpack_from("<h", data, offset)[0]
        else:
            value = struct.unpack_from("<b", data, offset)[0]
        sum_sq += (value / max_val) ** 2

    return math.sqrt(sum_sq / n_samples)


def calculate_peak(data: bytes, sample_width: int = 2) -> float:
    """Calculate peak amplitude of PCM audio.

    Args:
        data: Raw PCM data.
        sample_width: Sample width in bytes.

    Returns:
        Peak value (0.0 to 1.0 range).
    """
    if not data:
        return 0.0

    n_samples = len(data) // sample_width
    max_val = 32768.0 if sample_width == 2 else 128.0
    peak = 0.0

    for i in range(n_samples):
        offset = i * sample_width
        if sample_width == 2:
            value = abs(struct.unpack_from("<h", data, offset)[0])
        else:
            value = abs(struct.unpack_from("<b", data, offset)[0])
        peak = max(peak, value / max_val)

    return peak


def normalize_loudness(
    data: bytes,
    target_rms: float = 0.1,
    sample_width: int = 2,
    max_gain_db: float = 20.0,
) -> bytes:
    """Normalize audio loudness to a target RMS level.

    Args:
        data: Raw PCM data.
        target_rms: Target RMS level (0.0 to 1.0).
        sample_width: Sample width in bytes.
        max_gain_db: Maximum gain to apply in dB.

    Returns:
        Loudness-normalized PCM data.
    """
    if not data:
        return data

    current_rms = calculate_rms(data, sample_width)
    if current_rms < 1e-6:
        logger.debug("Audio is silent, skipping normalization")
        return data

    # Calculate gain
    gain = target_rms / current_rms
    max_gain = 10 ** (max_gain_db / 20)
    gain = min(gain, max_gain)

    # Check for clipping
    peak = calculate_peak(data, sample_width)
    if peak * gain > 0.95:
        gain = 0.95 / peak

    logger.debug(
        "Normalizing: RMS %.4f → %.4f (gain: %.2fx)",
        current_rms, current_rms * gain, gain,
    )

    # Apply gain
    n_samples = len(data) // sample_width
    output = bytearray()
    max_val = 32767 if sample_width == 2 else 127

    for i in range(n_samples):
        offset = i * sample_width
        if sample_width == 2:
            value = struct.unpack_from("<h", data, offset)[0]
            new_value = int(value * gain)
            new_value = max(-max_val, min(max_val, new_value))
            output.extend(struct.pack("<h", new_value))
        else:
            value = struct.unpack_from("<b", data, offset)[0]
            new_value = int(value * gain)
            new_value = max(-max_val, min(max_val, new_value))
            output.extend(struct.pack("<b", new_value))

    return bytes(output)


def trim_silence(
    data: bytes,
    threshold_db: float = -40.0,
    sample_width: int = 2,
    channels: int = 1,
    framerate: int = 44100,
    min_silence_ms: int = 50,
) -> bytes:
    """Trim leading and trailing silence from audio.

    Args:
        data: Raw PCM data.
        threshold_db: Silence threshold in dB.
        sample_width: Sample width in bytes.
        channels: Number of channels.
        framerate: Sample rate.
        min_silence_ms: Minimum silence duration to consider (ms).

    Returns:
        Audio with silence trimmed from start and end.
    """
    if not data:
        return data

    frame_size = sample_width * channels
    n_frames = len(data) // frame_size
    threshold = 10 ** (threshold_db / 20) * (32768 if sample_width == 2 else 128)

    # Window size for silence detection
    window_frames = max(1, int(framerate * min_silence_ms / 1000))

    # Find first non-silent frame
    start_frame = 0
    for i in range(0, n_frames, window_frames):
        window_end = min(i + window_frames, n_frames)
        max_amp = 0
        for j in range(i, window_end):
            offset = j * frame_size
            for ch in range(channels):
                ch_offset = offset + ch * sample_width
                if sample_width == 2:
                    value = abs(struct.unpack_from("<h", data, ch_offset)[0])
                else:
                    value = abs(struct.unpack_from("<b", data, ch_offset)[0])
                max_amp = max(max_amp, value)

        if max_amp > threshold:
            start_frame = max(0, i - window_frames)  # Keep a small buffer
            break
    else:
        # All silence
        return data

    # Find last non-silent frame
    end_frame = n_frames
    for i in range(n_frames - 1, -1, -window_frames):
        window_start = max(0, i - window_frames)
        max_amp = 0
        for j in range(window_start, i + 1):
            offset = j * frame_size
            for ch in range(channels):
                ch_offset = offset + ch * sample_width
                if sample_width == 2:
                    value = abs(struct.unpack_from("<h", data, ch_offset)[0])
                else:
                    value = abs(struct.unpack_from("<b", data, ch_offset)[0])
                max_amp = max(max_amp, value)

        if max_amp > threshold:
            end_frame = min(n_frames, i + window_frames + 1)
            break

    trimmed = data[start_frame * frame_size:end_frame * frame_size]
    logger.debug(
        "Trimmed silence: %d → %d frames",
        n_frames, (end_frame - start_frame),
    )
    return trimmed
