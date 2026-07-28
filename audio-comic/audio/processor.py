"""Audio processor for sample rate, channel, and bit depth standardization."""

from __future__ import annotations

import wave
import struct
from pathlib import Path
from typing import Optional, Tuple

from utils.logging_config import get_logger

logger = get_logger("audio.processor")


def get_wav_info(filepath: str) -> dict:
    """Get WAV file information.

    Args:
        filepath: Path to WAV file.

    Returns:
        Dict with channels, sample_width, framerate, n_frames, duration.
    """
    with wave.open(filepath, "rb") as wav:
        info = {
            "channels": wav.getnchannels(),
            "sample_width": wav.getsampwidth(),
            "framerate": wav.getframerate(),
            "n_frames": wav.getnframes(),
            "duration": wav.getnframes() / wav.getframerate(),
        }
    return info


def read_wav_raw(filepath: str) -> Tuple[bytes, int, int, int]:
    """Read raw PCM data from a WAV file.

    Args:
        filepath: Path to WAV file.

    Returns:
        Tuple of (raw_data, channels, sample_width, framerate).
    """
    with wave.open(filepath, "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        framerate = wav.getframerate()
        raw_data = wav.readframes(wav.getnframes())
    return raw_data, channels, sample_width, framerate


def write_wav(
    filepath: str,
    data: bytes,
    channels: int = 2,
    sample_width: int = 2,
    framerate: int = 44100,
) -> None:
    """Write raw PCM data to a WAV file.

    Args:
        filepath: Output file path.
        data: Raw PCM data bytes.
        channels: Number of channels.
        sample_width: Sample width in bytes (2 = 16-bit).
        framerate: Sample rate in Hz.
    """
    output = Path(filepath)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(framerate)
        wav.writeframes(data)


def convert_sample_rate(
    data: bytes,
    src_rate: int,
    dst_rate: int,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Simple sample rate conversion using linear interpolation.

    Args:
        data: Input PCM data.
        src_rate: Source sample rate.
        dst_rate: Destination sample rate.
        channels: Number of channels.
        sample_width: Sample width in bytes.

    Returns:
        Resampled PCM data.
    """
    if src_rate == dst_rate:
        return data

    # Parse samples
    fmt = "<h" if sample_width == 2 else "<b"
    sample_size = sample_width * channels
    n_frames = len(data) // sample_size

    if n_frames == 0:
        return data

    # Decode all samples per channel
    samples_per_channel = []
    for ch in range(channels):
        ch_samples = []
        for i in range(n_frames):
            offset = i * sample_size + ch * sample_width
            if sample_width == 2:
                value = struct.unpack_from("<h", data, offset)[0]
            else:
                value = struct.unpack_from("<b", data, offset)[0]
            ch_samples.append(value)
        samples_per_channel.append(ch_samples)

    # Resample using linear interpolation
    ratio = src_rate / dst_rate
    new_n_frames = int(n_frames / ratio)
    resampled_channels = []

    for ch_samples in samples_per_channel:
        new_samples = []
        for i in range(new_n_frames):
            src_pos = i * ratio
            idx = int(src_pos)
            frac = src_pos - idx
            if idx + 1 < len(ch_samples):
                value = ch_samples[idx] * (1 - frac) + ch_samples[idx + 1] * frac
            else:
                value = ch_samples[min(idx, len(ch_samples) - 1)]
            new_samples.append(int(value))
        resampled_channels.append(new_samples)

    # Encode back
    output = bytearray()
    for i in range(new_n_frames):
        for ch in range(channels):
            value = max(-32768, min(32767, resampled_channels[ch][i]))
            output.extend(struct.pack("<h", value))

    return bytes(output)


def mono_to_stereo(data: bytes, sample_width: int = 2) -> bytes:
    """Convert mono audio to stereo by duplicating channels.

    Args:
        data: Mono PCM data.
        sample_width: Sample width in bytes.

    Returns:
        Stereo PCM data.
    """
    output = bytearray()
    for i in range(0, len(data), sample_width):
        sample = data[i:i + sample_width]
        output.extend(sample)  # Left
        output.extend(sample)  # Right
    return bytes(output)


def standardize_wav(
    input_path: str,
    output_path: str,
    target_rate: int = 44100,
    target_channels: int = 2,
    target_width: int = 2,
) -> str:
    """Standardize a WAV file to target specifications.

    Converts sample rate, channels, and bit depth as needed.

    Args:
        input_path: Input WAV path.
        output_path: Output WAV path.
        target_rate: Target sample rate.
        target_channels: Target channel count.
        target_width: Target sample width in bytes.

    Returns:
        Path to the standardized WAV file.
    """
    raw_data, channels, sample_width, framerate = read_wav_raw(input_path)

    # Convert sample rate
    if framerate != target_rate:
        logger.debug("Converting sample rate: %d → %d", framerate, target_rate)
        raw_data = convert_sample_rate(
            raw_data, framerate, target_rate, channels, sample_width,
        )
        framerate = target_rate

    # Convert channels
    if channels == 1 and target_channels == 2:
        logger.debug("Converting mono → stereo")
        raw_data = mono_to_stereo(raw_data, sample_width)
        channels = 2
    elif channels == 2 and target_channels == 1:
        # Stereo to mono: average channels
        logger.debug("Converting stereo → mono")
        output = bytearray()
        for i in range(0, len(raw_data), sample_width * 2):
            left = struct.unpack_from("<h", raw_data, i)[0]
            right = struct.unpack_from("<h", raw_data, i + sample_width)[0]
            avg = (left + right) // 2
            output.extend(struct.pack("<h", avg))
        raw_data = bytes(output)
        channels = 1

    write_wav(output_path, raw_data, channels, target_width, framerate)
    logger.debug("Standardized WAV: %s", output_path)
    return output_path
