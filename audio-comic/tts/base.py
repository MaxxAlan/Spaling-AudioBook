"""Abstract base class for TTS providers.

Defines the TTSProvider interface that all TTS engines must implement.
This adapter pattern allows swapping engines without affecting the pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class VoiceInfo:
    """Information about an available TTS voice.

    Attributes:
        voice_id: Unique voice identifier.
        name: Human-readable voice name.
        gender: Voice gender ('male', 'female', 'neutral').
        language: Language code (e.g., 'vi', 'en').
        age_group: Age group ('child', 'young', 'adult', 'middle', 'old').
        description: Optional description.
    """
    voice_id: str
    name: str
    gender: str = "male"
    language: str = "vi"
    age_group: str = "adult"
    description: str = ""


class TTSProvider(ABC):
    """Abstract base class for Text-to-Speech providers.

    All TTS engines (VieNeu, SAPI5, Mock, LocalWave) must implement
    this interface. The pipeline interacts only through this interface,
    enabling hot-swapping of TTS engines.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the human-readable provider name."""
        ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if the TTS model is currently loaded."""
        ...

    @abstractmethod
    def load_model(self) -> None:
        """Load the TTS model into memory.

        Raises:
            TTSModelNotFoundError: If model files are missing.
            TTSProviderError: If initialization fails.
        """
        ...

    @abstractmethod
    def list_voices(self) -> List[VoiceInfo]:
        """List all available voices for this provider.

        Returns:
            List of VoiceInfo objects describing available voices.
        """
        ...

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 0.0,
        emotion: str = "neutral",
    ) -> str:
        """Synthesize speech from text and save to file.

        Args:
            text: Text to synthesize.
            voice_id: Voice identifier to use.
            output_path: File path for the output WAV file.
            speed: Playback speed multiplier (1.0 = normal).
            pitch: Pitch adjustment (-1.0 to 1.0).
            emotion: Emotional tone hint.

        Returns:
            Absolute path to the generated WAV file.

        Raises:
            TTSGenerationError: If synthesis fails.
        """
        ...

    @abstractmethod
    def unload_model(self) -> None:
        """Unload the TTS model to free memory."""
        ...

    def get_voice(self, voice_id: str) -> Optional[VoiceInfo]:
        """Get a specific voice by ID.

        Args:
            voice_id: Voice identifier.

        Returns:
            VoiceInfo or None if not found.
        """
        for voice in self.list_voices():
            if voice.voice_id == voice_id:
                return voice
        return None

    def supports_emotion(self) -> bool:
        """Check if this provider supports emotion control.

        Returns:
            True if emotions can be specified. Default False.
        """
        return False

    def supports_voice_cloning(self) -> bool:
        """Check if this provider supports voice cloning.

        Returns:
            True if voice cloning is available. Default False.
        """
        return False

    def get_sample_rate(self) -> int:
        """Get the output sample rate of this provider.

        Returns:
            Sample rate in Hz. Default 44100.
        """
        return 44100
