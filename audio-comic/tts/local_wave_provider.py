"""Local WAV file provider for testing and placeholder audio.

Uses pre-recorded WAV files as TTS output. Useful for testing
pipeline with known audio content or when no TTS engine is available.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List

from core.exceptions import TTSGenerationError
from tts.base import TTSProvider, VoiceInfo
from utils.logging_config import get_logger

logger = get_logger("tts.local_wave_provider")


class LocalWaveProvider(TTSProvider):
    """TTS provider that uses pre-recorded WAV files.

    Maps voice_ids to directories containing numbered WAV files.
    When synthesize() is called, it copies the next available WAV file
    to the output path.
    """

    def __init__(self, audio_dir: str = "") -> None:
        """Initialize LocalWave provider.

        Args:
            audio_dir: Root directory containing voice subdirectories
                       with pre-recorded WAV files.
        """
        self._audio_dir = Path(audio_dir) if audio_dir else Path(".")
        self._loaded = False
        self._voice_files: Dict[str, List[Path]] = {}
        self._voice_counters: Dict[str, int] = {}

    @property
    def provider_name(self) -> str:
        return "LocalWave"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_model(self) -> None:
        """Scan audio directory for available WAV files.

        Expected structure:
            audio_dir/
                voice_id_1/
                    001.wav
                    002.wav
                voice_id_2/
                    001.wav
        """
        if not self._audio_dir.exists():
            logger.warning(
                "LocalWave audio directory not found: %s", self._audio_dir
            )
            self._loaded = True
            return

        for voice_dir in sorted(self._audio_dir.iterdir()):
            if voice_dir.is_dir():
                wav_files = sorted(voice_dir.glob("*.wav"))
                if wav_files:
                    voice_id = voice_dir.name
                    self._voice_files[voice_id] = wav_files
                    self._voice_counters[voice_id] = 0
                    logger.debug(
                        "LocalWave: found %d files for voice '%s'",
                        len(wav_files), voice_id,
                    )

        self._loaded = True
        logger.info(
            "LocalWave loaded: %d voices, %d total files",
            len(self._voice_files),
            sum(len(f) for f in self._voice_files.values()),
        )

    def list_voices(self) -> List[VoiceInfo]:
        """List available local voices based on directory names."""
        return [
            VoiceInfo(
                voice_id=vid,
                name=f"Local: {vid}",
                description=f"{len(files)} pre-recorded files",
            )
            for vid, files in self._voice_files.items()
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
        """Copy the next available WAV file to the output path.

        Args:
            text: Ignored (pre-recorded audio).
            voice_id: Voice directory name.
            output_path: Destination file path.
            speed: Ignored.
            pitch: Ignored.
            emotion: Ignored.

        Returns:
            Path to the copied WAV file.

        Raises:
            TTSGenerationError: If no files available for the voice.
        """
        if voice_id not in self._voice_files:
            raise TTSGenerationError(
                f"Không tìm thấy voice '{voice_id}' trong LocalWave",
                details=f"Available: {list(self._voice_files.keys())}",
            )

        files = self._voice_files[voice_id]
        idx = self._voice_counters[voice_id] % len(files)
        source = files[idx]
        self._voice_counters[voice_id] = idx + 1

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(str(source), str(output))

        logger.debug("LocalWave: copied %s → %s", source.name, output.name)
        return str(output.resolve())

    def unload_model(self) -> None:
        """Clear file references."""
        self._voice_files.clear()
        self._voice_counters.clear()
        self._loaded = False
        logger.info("LocalWave unloaded")
