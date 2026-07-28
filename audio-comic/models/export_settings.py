"""Export settings data model."""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class ExportSettings:
    """Configuration for narration audio export.

    Attributes:
        audio_format: Primary audio format ('wav' or 'mp3').
        audio_sample_rate: Sample rate in Hz.
        audio_channels: Number of audio channels (1=mono, 2=stereo).
        audio_bit_depth: Bit depth for WAV (16 or 24).
        mp3_bitrate: MP3 bitrate string (e.g., '192k', '320k').
        export_mp3: Whether to also export MP3 alongside WAV.
        output_dir: Output directory path.
        overwrite_mode: How to handle existing files ('ask', 'overwrite', 'version', 'skip').
    """

    audio_format: str = "wav"
    audio_sample_rate: int = 44100
    audio_channels: int = 2
    audio_bit_depth: int = 16
    mp3_bitrate: str = "192k"
    export_mp3: bool = False
    export_subtitles: bool = False
    output_dir: str = "./output"
    overwrite_mode: str = "ask"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ExportSettings:
        """Deserialize from dictionary."""
        # Filter to only known fields
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)
