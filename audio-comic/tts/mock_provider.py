"""Mock TTS provider for testing and demo purposes.

Generates silent or simple tone WAV files without any model dependency.
Allows end-to-end pipeline testing without GPU or model installation.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from typing import List

from tts.base import TTSProvider, VoiceInfo
from utils.logging_config import get_logger

logger = get_logger("tts.mock_provider")


class MockTTSProvider(TTSProvider):
    """Mock TTS that generates placeholder WAV files.

    Generates short silent WAV files with duration based on text length.
    Useful for testing the full pipeline without real TTS models.
    """

    def __init__(
        self,
        sample_rate: int = 44100,
        channels: int = 1,
        generate_tone: bool = False,
        max_duration_seconds: float | None = None,
    ) -> None:
        """Initialize MockTTS.

        Args:
            sample_rate: Output sample rate.
            channels: Number of audio channels.
            generate_tone: If True, generate a simple tone instead of silence.
        """
        self._sample_rate = sample_rate
        self._channels = channels
        self._generate_tone = generate_tone
        self._max_duration_seconds = max_duration_seconds
        self._loaded = False

    @property
    def provider_name(self) -> str:
        return "MockTTS"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_model(self) -> None:
        """Mock model loading (instant)."""
        logger.info("MockTTS loaded (no real model)")
        self._loaded = True

    def list_voices(self) -> List[VoiceInfo]:
        """Return a list of mock voices matching the default voice profiles."""
        return [
            VoiceInfo("narrator_male_01", "Mock Narrator Nam", "male", "vi"),
            VoiceInfo("narrator_female_01", "Mock Narrator Nữ", "female", "vi"),
            VoiceInfo("male_young_01", "Mock Nam Trẻ 01", "male", "vi", "young"),
            VoiceInfo("male_young_02", "Mock Nam Trẻ 02", "male", "vi", "young"),
            VoiceInfo("male_middle_01", "Mock Nam Trung Niên", "male", "vi", "middle"),
            VoiceInfo("male_old_01", "Mock Nam Lớn Tuổi", "male", "vi", "old"),
            VoiceInfo("female_young_01", "Mock Nữ Trẻ 01", "female", "vi", "young"),
            VoiceInfo("female_young_02", "Mock Nữ Trẻ 02", "female", "vi", "young"),
            VoiceInfo("female_middle_01", "Mock Nữ Trung Niên", "female", "vi", "middle"),
            VoiceInfo("female_old_01", "Mock Nữ Lớn Tuổi", "female", "vi", "old"),
            VoiceInfo("child_01", "Mock Trẻ Em", "neutral", "vi", "child"),
            VoiceInfo("villain_01", "Mock Phản Diện", "male", "vi"),
            VoiceInfo("mysterious_01", "Mock Bí Ẩn", "neutral", "vi"),
        ]

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 0.0,
        emotion: str = "neutral",
    ) -> str:
        """Generate a placeholder WAV file.

        Duration is estimated from text length:
        ~150 characters per second at normal speed.

        Args:
            text: Text to "synthesize".
            voice_id: Voice ID (ignored in mock).
            output_path: Output WAV file path.
            speed: Speed multiplier.
            pitch: Pitch adjustment (ignored).
            emotion: Emotion hint (ignored).

        Returns:
            Path to the generated WAV file.
        """
        # Estimate duration: ~6-7 chars per second for Vietnamese
        chars_per_second = 7.0 * speed
        duration_seconds = max(0.5, len(text) / chars_per_second)
        if self._max_duration_seconds is not None:
            duration_seconds = min(duration_seconds, self._max_duration_seconds)

        num_samples = int(duration_seconds * self._sample_rate)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(self._channels)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(self._sample_rate)

            if self._generate_tone:
                # Generate a simple sine-wave-like tone (triangle wave for simplicity)
                import math
                freq = 440.0 + (hash(voice_id) % 200)  # Vary by voice
                data = bytearray()
                for i in range(num_samples):
                    t = i / self._sample_rate
                    value = int(4000 * math.sin(2 * math.pi * freq * t))
                    for _ in range(self._channels):
                        data.extend(struct.pack("<h", max(-32768, min(32767, value))))
                wav.writeframes(bytes(data))
            else:
                # Generate silence
                silence = b"\x00\x00" * self._channels * num_samples
                wav.writeframes(silence)

        logger.debug(
            "MockTTS: generated %.1fs WAV for '%s...' → %s",
            duration_seconds, text[:30], output.name,
        )
        return str(output.resolve())

    def unload_model(self) -> None:
        """Mock model unloading."""
        self._loaded = False
        logger.info("MockTTS unloaded")

    def get_sample_rate(self) -> int:
        return self._sample_rate
