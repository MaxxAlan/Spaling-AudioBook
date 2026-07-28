"""Silence generation for pauses between segments."""

from __future__ import annotations

import struct
from utils.logging_config import get_logger

logger = get_logger("audio.silence")


def generate_silence(
    duration_ms: int,
    sample_rate: int = 44100,
    channels: int = 2,
    sample_width: int = 2,
) -> bytes:
    """Generate silence as raw PCM data.

    Args:
        duration_ms: Duration of silence in milliseconds.
        sample_rate: Sample rate in Hz.
        channels: Number of audio channels.
        sample_width: Sample width in bytes.

    Returns:
        Raw PCM data of silence.
    """
    n_frames = int(sample_rate * duration_ms / 1000)
    frame_size = sample_width * channels
    return b"\x00" * (n_frames * frame_size)


def generate_crossfade(
    data_a: bytes,
    data_b: bytes,
    crossfade_ms: int = 10,
    sample_rate: int = 44100,
    channels: int = 2,
    sample_width: int = 2,
) -> bytes:
    """Create a crossfade between two audio segments to avoid clicks.

    Applies a linear fade-out to the end of data_a and fade-in to
    the start of data_b, then mixes them.

    Args:
        data_a: First audio segment (raw PCM).
        data_b: Second audio segment (raw PCM).
        crossfade_ms: Crossfade duration in milliseconds.
        sample_rate: Sample rate.
        channels: Channel count.
        sample_width: Sample width in bytes.

    Returns:
        Combined audio with crossfade applied.
    """
    frame_size = sample_width * channels
    crossfade_frames = int(sample_rate * crossfade_ms / 1000)

    # If either segment is too short for crossfade, just concatenate
    min_frames_a = len(data_a) // frame_size
    min_frames_b = len(data_b) // frame_size

    if crossfade_frames < 1 or min_frames_a < crossfade_frames or min_frames_b < crossfade_frames:
        return data_a + data_b

    # Split data_a into main + fade-out portion
    crossfade_bytes = crossfade_frames * frame_size
    a_main = data_a[:-crossfade_bytes]
    a_fade = data_a[-crossfade_bytes:]

    # Split data_b into fade-in portion + main
    b_fade = data_b[:crossfade_bytes]
    b_main = data_b[crossfade_bytes:]

    # Mix the crossfade region
    mixed = bytearray()
    for i in range(crossfade_frames):
        fade_out = 1.0 - (i / crossfade_frames)  # 1.0 → 0.0
        fade_in = i / crossfade_frames             # 0.0 → 1.0

        for ch in range(channels):
            offset = (i * channels + ch) * sample_width
            if sample_width == 2:
                val_a = struct.unpack_from("<h", a_fade, offset)[0]
                val_b = struct.unpack_from("<h", b_fade, offset)[0]
                mixed_val = int(val_a * fade_out + val_b * fade_in)
                mixed_val = max(-32768, min(32767, mixed_val))
                mixed.extend(struct.pack("<h", mixed_val))
            else:
                val_a = struct.unpack_from("<b", a_fade, offset)[0]
                val_b = struct.unpack_from("<b", b_fade, offset)[0]
                mixed_val = int(val_a * fade_out + val_b * fade_in)
                mixed_val = max(-128, min(127, mixed_val))
                mixed.extend(struct.pack("<b", mixed_val))

    return a_main + bytes(mixed) + b_main


def apply_fade_in(
    data: bytes,
    fade_ms: int = 50,
    sample_rate: int = 44100,
    channels: int = 2,
    sample_width: int = 2,
) -> bytes:
    """Apply a fade-in effect to the start of audio data.

    Args:
        data: Raw PCM data.
        fade_ms: Fade duration in milliseconds.
        sample_rate: Sample rate.
        channels: Channel count.
        sample_width: Sample width in bytes.

    Returns:
        Audio with fade-in applied.
    """
    frame_size = sample_width * channels
    fade_frames = int(sample_rate * fade_ms / 1000)
    n_frames = len(data) // frame_size

    if fade_frames >= n_frames:
        fade_frames = n_frames

    output = bytearray(data)
    for i in range(fade_frames):
        factor = i / fade_frames
        for ch in range(channels):
            offset = (i * channels + ch) * sample_width
            if sample_width == 2:
                value = struct.unpack_from("<h", output, offset)[0]
                new_val = int(value * factor)
                struct.pack_into("<h", output, offset, max(-32768, min(32767, new_val)))

    return bytes(output)


def apply_fade_out(
    data: bytes,
    fade_ms: int = 50,
    sample_rate: int = 44100,
    channels: int = 2,
    sample_width: int = 2,
) -> bytes:
    """Apply a fade-out effect to the end of audio data.

    Args:
        data: Raw PCM data.
        fade_ms: Fade duration in milliseconds.
        sample_rate: Sample rate.
        channels: Channel count.
        sample_width: Sample width in bytes.

    Returns:
        Audio with fade-out applied.
    """
    frame_size = sample_width * channels
    fade_frames = int(sample_rate * fade_ms / 1000)
    n_frames = len(data) // frame_size

    if fade_frames >= n_frames:
        fade_frames = n_frames

    output = bytearray(data)
    for i in range(fade_frames):
        frame_idx = n_frames - fade_frames + i
        factor = 1.0 - (i / fade_frames)
        for ch in range(channels):
            offset = (frame_idx * channels + ch) * sample_width
            if sample_width == 2:
                value = struct.unpack_from("<h", output, offset)[0]
                new_val = int(value * factor)
                struct.pack_into("<h", output, offset, max(-32768, min(32767, new_val)))

    return bytes(output)
