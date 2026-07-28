"""Audio concatenation for merging segments into a final chapter file."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from audio.processor import read_wav_raw, write_wav, standardize_wav
from audio.silence import generate_silence, generate_crossfade
from audio.normalizer import normalize_loudness, trim_silence
from utils.logging_config import get_logger

logger = get_logger("audio.concatenator")


def concatenate_segments(
    segment_files: List[Tuple[str, int]],
    output_path: str,
    target_sample_rate: int = 44100,
    target_channels: int = 2,
    target_sample_width: int = 2,
    crossfade_ms: int = 30,
    normalize: bool = True,
    target_rms: float = 0.1,
    trim: bool = True,
    trim_threshold_db: float = -40.0,
    timing_callback: Optional[Callable[[int, float, float], None]] = None,
) -> str:
    """Concatenate audio segment files with silences into one WAV.

    Each segment is paired with a pause duration (ms) to insert after it.
    Applies standardization, normalization, trimming, and crossfade.

    Args:
        segment_files: List of (wav_path, pause_after_ms) tuples.
        output_path: Path for the final concatenated WAV.
        target_sample_rate: Target sample rate for all segments.
        target_channels: Target channel count.
        target_sample_width: Target sample width in bytes.
        crossfade_ms: Crossfade duration between segments.
        normalize: Whether to normalize loudness.
        target_rms: Target RMS for normalization.
        trim: Whether to trim silence from individual segments.
        trim_threshold_db: Silence trimming threshold.

    Returns:
        Path to the output WAV file.
    """
    if not segment_files:
        logger.warning("No segments to concatenate")
        # Create a short silent file
        silence = generate_silence(
            1000, target_sample_rate, target_channels, target_sample_width,
        )
        write_wav(output_path, silence, target_channels, target_sample_width, target_sample_rate)
        return output_path

    logger.info("Concatenating %d segments...", len(segment_files))

    combined_data = bytearray()
    processed_count = 0

    for i, (wav_path, pause_ms) in enumerate(segment_files):
        if not Path(wav_path).exists():
            logger.warning("Segment file missing, skipping: %s", wav_path)
            continue

        try:
            # Standardize the segment to target format
            std_path = wav_path + ".std.wav"
            standardize_wav(
                wav_path, std_path,
                target_sample_rate, target_channels, target_sample_width,
            )

            # Read standardized data
            raw_data, _, _, _ = read_wav_raw(std_path)

            # Trim silence from individual segments
            if trim and raw_data:
                raw_data = trim_silence(
                    raw_data,
                    threshold_db=trim_threshold_db,
                    sample_width=target_sample_width,
                    channels=target_channels,
                    framerate=target_sample_rate,
                )

            # Normalize loudness per segment
            if normalize and raw_data:
                raw_data = normalize_loudness(
                    raw_data, target_rms, target_sample_width,
                )

            # Add segment data with crossfade. Capture the exact spoken range
            # after standardization/trimming so subtitles follow final audio.
            frame_size = target_sample_width * target_channels
            start_byte = len(combined_data)
            if combined_data and raw_data:
                start_byte = max(0, start_byte - crossfade_ms * target_sample_rate * frame_size // 1000)
            if combined_data and raw_data:
                combined_data = bytearray(generate_crossfade(
                    bytes(combined_data), raw_data,
                    crossfade_ms, target_sample_rate,
                    target_channels, target_sample_width,
                ))
            elif raw_data:
                combined_data.extend(raw_data)

            if timing_callback and raw_data:
                timing_callback(
                    i,
                    start_byte / frame_size / target_sample_rate * 1000,
                    len(combined_data) / frame_size / target_sample_rate * 1000,
                )

            # Add pause
            if pause_ms > 0:
                silence = generate_silence(
                    pause_ms, target_sample_rate,
                    target_channels, target_sample_width,
                )
                combined_data.extend(silence)

            processed_count += 1

            # Clean up temp file
            Path(std_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(
                "Error processing segment %d (%s): %s",
                i, wav_path, e,
            )
            continue

    logger.info(
        "Concatenated %d/%d segments, total size: %.1f MB",
        processed_count, len(segment_files),
        len(combined_data) / (1024 * 1024),
    )

    # Write final output
    write_wav(
        output_path, bytes(combined_data),
        target_channels, target_sample_width, target_sample_rate,
    )

    # Calculate duration
    frame_size = target_sample_width * target_channels
    duration = len(combined_data) / frame_size / target_sample_rate
    logger.info(
        "Final audio: %.1f seconds, written to %s",
        duration, output_path,
    )

    return output_path
