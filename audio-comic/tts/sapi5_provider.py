"""Windows SAPI5 TTS provider (fallback).

Uses Windows Speech API through pyttsx3 or direct COM automation.
Serves as a fallback when VieNeu-TTS is not available.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import List, Optional

from core.exceptions import TTSProviderError, TTSGenerationError
from tts.base import TTSProvider, VoiceInfo
from utils.logging_config import get_logger

logger = get_logger("tts.sapi5_provider")


class WindowsSAPI5Provider(TTSProvider):
    """Windows SAPI5 TTS provider using pyttsx3.

    Auto-detects installed SAPI5 voices on Windows.
    Falls back gracefully if no Vietnamese voices are available.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        """Initialize SAPI5 provider.

        Args:
            sample_rate: Desired output sample rate.
        """
        self._engine = None
        self._voices: List[VoiceInfo] = []
        self._loaded = False
        self._sample_rate = sample_rate

    @property
    def provider_name(self) -> str:
        return "Windows SAPI5"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_model(self) -> None:
        """Initialize the SAPI5 engine and discover available voices.

        Raises:
            TTSProviderError: If not on Windows or pyttsx3 unavailable.
        """
        if platform.system() != "Windows":
            raise TTSProviderError(
                "SAPI5 chỉ hoạt động trên Windows",
                details="Hệ điều hành hiện tại không phải Windows",
            )

        try:
            import pyttsx3
            self._engine = pyttsx3.init("sapi5")
        except ImportError:
            raise TTSProviderError(
                "pyttsx3 chưa được cài đặt",
                details="pip install pyttsx3",
            )
        except Exception as e:
            raise TTSProviderError(
                "Không thể khởi tạo SAPI5 engine",
                details=str(e),
            )

        # Discover voices
        self._voices = []
        try:
            voices = self._engine.getProperty("voices")
            has_vietnamese = False

            for i, voice in enumerate(voices):
                lang = getattr(voice, "languages", [""])[0] if hasattr(voice, "languages") else ""
                gender = "female" if "female" in voice.name.lower() else "male"

                voice_info = VoiceInfo(
                    voice_id=f"sapi5_{i:02d}",
                    name=voice.name,
                    gender=gender,
                    language="vi" if "vietnamese" in voice.name.lower() else "en",
                    description=f"SAPI5: {voice.name}",
                )
                self._voices.append(voice_info)

                if "vietnamese" in voice.name.lower() or "viet" in voice.name.lower():
                    has_vietnamese = True

            if not has_vietnamese:
                logger.warning(
                    "Không tìm thấy voice tiếng Việt trong SAPI5. "
                    "Có %d voice khác có sẵn.", len(self._voices)
                )

        except Exception as e:
            logger.error("Lỗi khi liệt kê SAPI5 voices: %s", e)

        self._loaded = True
        logger.info("SAPI5 loaded with %d voices", len(self._voices))

    def list_voices(self) -> List[VoiceInfo]:
        """List discovered SAPI5 voices."""
        return list(self._voices)

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 0.0,
        emotion: str = "neutral",
    ) -> str:
        """Synthesize speech using SAPI5 and save to WAV.

        Args:
            text: Text to synthesize.
            voice_id: SAPI5 voice ID (e.g., 'sapi5_00').
            output_path: Output WAV file path.
            speed: Speed multiplier.
            pitch: Pitch adjustment (limited support in SAPI5).
            emotion: Ignored by SAPI5.

        Returns:
            Path to the generated WAV file.

        Raises:
            TTSGenerationError: If synthesis fails.
        """
        if not self._loaded or self._engine is None:
            raise TTSGenerationError(
                "SAPI5 engine chưa được khởi tạo",
                details="Gọi load_model() trước khi synthesize",
            )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Set voice
            voices = self._engine.getProperty("voices")
            voice_idx = self._get_voice_index(voice_id)
            if voice_idx is not None and voice_idx < len(voices):
                self._engine.setProperty("voice", voices[voice_idx].id)

            # Set speed (pyttsx3 rate: words per minute, default ~200)
            base_rate = 200
            self._engine.setProperty("rate", int(base_rate * speed))

            # Save to file
            self._engine.save_to_file(text, str(output))
            self._engine.runAndWait()

            if not output.exists() or output.stat().st_size == 0:
                raise TTSGenerationError(
                    f"SAPI5 không tạo được file audio",
                    details=f"Output path: {output}",
                )

            logger.debug("SAPI5: synthesized '%s...' → %s", text[:30], output.name)
            return str(output.resolve())

        except TTSGenerationError:
            raise
        except Exception as e:
            raise TTSGenerationError(
                f"Lỗi SAPI5 synthesis: {e}",
                details=str(e),
            )

    def _get_voice_index(self, voice_id: str) -> Optional[int]:
        """Extract voice index from voice_id like 'sapi5_02'."""
        try:
            if voice_id.startswith("sapi5_"):
                return int(voice_id.split("_")[1])
        except (ValueError, IndexError):
            pass
        return None

    def unload_model(self) -> None:
        """Stop and cleanup the SAPI5 engine."""
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass
            self._engine = None
        self._loaded = False
        logger.info("SAPI5 unloaded")

    def get_sample_rate(self) -> int:
        # SAPI5 typically outputs at 22050 Hz
        return 22050
