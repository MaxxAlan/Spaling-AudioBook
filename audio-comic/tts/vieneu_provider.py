"""Adapter for the installed VieNeu-TTS 3.x runtime."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
from typing import Any, List, Optional

from core.exceptions import TTSGenerationError, TTSModelNotFoundError, TTSProviderError
from tts.base import TTSProvider, VoiceInfo
from tts.voice_registry import (
    load_custom_voices,
    registry_fingerprint,
    resolve_custom_voice,
)
from utils.logging_config import get_logger

logger = get_logger("tts.vieneu_provider")


class VieNeuTTSProvider(TTSProvider):
    """Offline Vietnamese TTS using VieNeu v3 Turbo (ONNX CPU/PyTorch GPU)."""

    def __init__(
        self,
        model_path: str = "",
        checkpoint_path: str = "",
        device: str = "auto",
        dtype: str = "auto",
        seed: int = 42,
        cache_dir: str = "",
        default_voice: str = "Thanh Bình",
        style: str = "doc_truyen",
        temperature: float = 0.6,
        top_k: int = 20,
        top_p: float = 0.88,
        repetition_penalty: float = 1.15,
        max_chars: int = 256,
        pitch_ratio: float = 0.936,
        tempo_ratio: float = 1.019,
        voice_registry_path: str = "",
    ) -> None:
        self._model_path = model_path
        self._checkpoint_path = checkpoint_path
        self._device = device
        self._dtype = dtype
        self._seed = seed
        self._cache_dir = cache_dir
        self._default_voice = default_voice
        self._style = style
        self._temperature = temperature
        self._top_k = top_k
        self._top_p = top_p
        self._repetition_penalty = repetition_penalty
        self._max_chars = max_chars
        self._pitch_ratio = pitch_ratio
        self._tempo_ratio = tempo_ratio
        self._voice_registry_path = voice_registry_path or None
        self._custom_voices = load_custom_voices(self._voice_registry_path)
        self._loaded_custom_ids: set[str] = set()
        self._tts: Any = None
        self._loaded = False
        self._sample_rate = 48000
        self._voice_ids: List[str] = []
        self._segment_options: dict[str, float] = {}

    def set_segment_options(self, options: dict[str, float] | None) -> None:
        """Apply bounded AI sampling overrides for the next synthesis call."""
        self._segment_options = dict(options or {})

    @property
    def provider_name(self) -> str:
        # Settings are part of the cache identity. Changing prosody must not
        # silently reuse audio produced with the previous voice/style.
        return (
            f"VieNeu-TTS-v3-Turbo:{self._default_voice}:{self._style}:"
            f"{self._temperature}:{self._top_k}:{self._top_p}:"
            f"{self._repetition_penalty}:pitch={self._pitch_ratio}:"
            f"tempo={self._tempo_ratio}:voices="
            f"{registry_fingerprint(self._voice_registry_path)}"
        )

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_model(self) -> None:
        try:
            from vieneu import Vieneu
        except ImportError as exc:
            raise TTSModelNotFoundError(
                "VieNeu-TTS chưa được cài đặt", details="Chạy: pip install vieneu"
            ) from exc

        kwargs: dict[str, Any] = {
            "device": self._device or "auto",
            "dtype": self._dtype or "auto",
        }
        model_source = self._checkpoint_path or self._model_path
        if model_source:
            kwargs["backbone_repo"] = model_source

        try:
            logger.info("Loading VieNeu v3 Turbo on %s", kwargs["device"])
            self._tts = Vieneu(mode="v3turbo", **kwargs)
            self._install_custom_voices()
            self._sample_rate = int(getattr(self._tts, "sample_rate", 48000))
            self._voice_ids = [
                voice_id for _description, voice_id in self._tts.list_preset_voices()
            ]
            resolved_default = resolve_custom_voice(
                self._default_voice, self._custom_voices
            )
            if resolved_default and resolved_default.voice_id not in self._voice_ids:
                raise TTSProviderError(
                    f"Không thể nạp giọng tùy chỉnh '{resolved_default.name}'"
                )
            self._loaded = True
            logger.info(
                "VieNeu ready: backend=%s, sample_rate=%d, voices=%d",
                getattr(self._tts, "backend", "unknown"),
                self._sample_rate,
                len(self._voice_ids),
            )
        except Exception as exc:
            self._tts = None
            raise TTSProviderError(
                f"Không thể tải VieNeu-TTS: {exc}", details=str(exc)
            ) from exc

    def list_voices(self) -> List[VoiceInfo]:
        if self._loaded and self._tts is not None:
            built_in = [
                VoiceInfo(voice_id, description, "neutral", "vi")
                for description, voice_id in self._tts.list_preset_voices()
                if voice_id not in self._loaded_custom_ids
            ]
            return built_in + [
                VoiceInfo(
                    voice.voice_id,
                    voice.name,
                    voice.gender,
                    voice.language,
                    description=voice.description,
                )
                for voice in self._custom_voices
                if voice.voice_id in self._loaded_custom_ids
            ]
        return [
            VoiceInfo(
                voice.voice_id,
                voice.name,
                voice.gender,
                voice.language,
                description=voice.description,
            )
            for voice in self._custom_voices
        ] or [VoiceInfo("default", "VieNeu mặc định", "neutral", "vi")]

    def _install_custom_voices(self) -> None:
        """Inject serialized embeddings/codes into the loaded VieNeu core."""
        import json
        import numpy as np

        self._loaded_custom_ids.clear()
        for voice in self._custom_voices:
            try:
                if voice.compiled_voice.is_file():
                    payload = json.loads(
                        voice.compiled_voice.read_text(encoding="utf-8")
                    )
                    preset = payload.get("voices", {}).get(voice.voice_id)
                    if not preset:
                        preset = payload.get("presets", {}).get(voice.voice_id)
                    if not preset or preset.get("speaker_emb") is None:
                        raise ValueError("bundle thiếu speaker_emb")
                    self._tts._preset_voices[voice.voice_id] = {
                        "description": voice.description,
                        "gender": voice.gender,
                        "style": preset.get("style", self._style),
                        "speaker_emb": np.asarray(
                            preset["speaker_emb"], dtype=np.float32
                        ),
                        "codes": (
                            np.asarray(preset["codes"], dtype=np.int64)
                            if preset.get("codes") is not None
                            else None
                        ),
                    }
                elif voice.reference_audio.is_file():
                    self._tts.add_voice(
                        voice.voice_id,
                        voice.reference_audio,
                        denoise=True,
                        use_ref_codes=True,
                        description=voice.description,
                        gender=voice.gender,
                        style=self._style,
                    )
                else:
                    raise FileNotFoundError(voice.reference_audio)
                self._loaded_custom_ids.add(voice.voice_id)
                logger.info("Loaded custom voice: %s (%s)", voice.name, voice.voice_id)
            except Exception as exc:
                logger.warning("Skipping custom voice %s: %s", voice.voice_id, exc)

    def _resolve_voice_id(self, value: str) -> str:
        custom = resolve_custom_voice(value, self._custom_voices)
        return custom.voice_id if custom else value

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 0.0,
        emotion: str = "neutral",
        reference_audio: Optional[str] = None,
    ) -> str:
        if not self._loaded or self._tts is None:
            raise TTSGenerationError("VieNeu-TTS chưa được tải")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        options = self._segment_options
        kwargs: dict[str, Any] = {
            "text": text,
            "style": self._style,
            "temperature": options.get("temperature", self._temperature),
            "top_k": int(options.get("top_k", self._top_k)),
            "top_p": options.get("top_p", self._top_p),
            "repetition_penalty": options.get("repetition_penalty", self._repetition_penalty),
            "max_chars": int(options.get("max_chars", self._max_chars)),
            "crossfade_p": 0.03,
            "apply_watermark": True,
        }
        requested_voice = self._resolve_voice_id(voice_id)
        default_voice = self._resolve_voice_id(self._default_voice)
        if reference_audio and Path(reference_audio).is_file():
            kwargs["ref_audio"] = reference_audio
        elif requested_voice in self._voice_ids:
            kwargs["voice"] = requested_voice
        elif default_voice in self._voice_ids:
            kwargs["voice"] = default_voice

        try:
            # VieNeu sampling is stochastic. Resetting the generators makes
            # timbre and energy more consistent between independently cached
            # segments and makes reruns reproducible.
            import random
            import numpy as np

            random.seed(self._seed)
            np.random.seed(self._seed)
            try:
                import torch

                torch.manual_seed(self._seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(self._seed)
            except ImportError:
                pass
            audio = self._tts.infer(**kwargs)
            self._tts.save(audio, output)
            self._apply_audio_tuning(output, speed=speed, pitch=pitch)
            if not output.is_file() or output.stat().st_size <= 44:
                raise TTSGenerationError("VieNeu-TTS tạo file audio rỗng")
            return str(output.resolve())
        except TTSGenerationError:
            raise
        except Exception as exc:
            raise TTSGenerationError(
                f"Lỗi VieNeu-TTS synthesis: {exc}", details=str(exc)
            ) from exc

    def _apply_audio_tuning(
        self, output: Path, speed: float = 1.0, pitch: float = 0.0
    ) -> None:
        """Adjust pitch and tempo independently after synthesis."""
        effective_pitch = max(0.75, min(1.25, self._pitch_ratio * (1.0 + pitch)))
        effective_tempo = max(0.75, min(1.25, self._tempo_ratio * speed))
        if (
            abs(effective_pitch - 1.0) < 0.001
            and abs(effective_tempo - 1.0) < 0.001
        ):
            return
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.warning("FFmpeg unavailable; skipping pitch adjustment")
            return
        shifted = output.with_name(f"{output.stem}.pitch{output.suffix}")
        command = [
            ffmpeg, "-y", "-i", str(output),
            "-af", (
                f"rubberband=pitch={effective_pitch}:"
                f"tempo={effective_tempo}"
            ),
            "-c:a", "pcm_s16le", str(shifted),
        ]
        timeout = None if os.environ.get("AUDIOBOOK_OVERNIGHT") == "1" else 3600
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            # Many stock FFmpeg builds omit librubberband. This fallback
            # changes sample rate and restores tempo with atempo, so every OS
            # still gets independent pitch/tempo control with plain FFmpeg.
            sample_rate = self._sample_rate
            fallback_filter = (
                f"asetrate={sample_rate}*{effective_pitch},"
                f"aresample={sample_rate},"
                f"atempo={effective_tempo / effective_pitch}"
            )
            command = [
                ffmpeg, "-y", "-i", str(output),
                "-af", fallback_filter,
                "-c:a", "pcm_s16le", str(shifted),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0 or not shifted.is_file():
            shifted.unlink(missing_ok=True)
            raise TTSGenerationError(
                "Không thể điều chỉnh tông/tốc độ bằng FFmpeg rubberband",
                details=result.stderr[-500:],
            )
        shifted.replace(output)

    def unload_model(self) -> None:
        self._tts = None
        self._loaded = False
        self._voice_ids = []
        self._loaded_custom_ids.clear()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def supports_voice_cloning(self) -> bool:
        return True

    def get_sample_rate(self) -> int:
        return self._sample_rate
