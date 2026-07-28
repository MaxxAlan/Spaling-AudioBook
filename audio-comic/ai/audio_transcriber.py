"""Rebuild SRT subtitles from an existing audio file with faster-whisper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from video.subtitles import write_srt_cues


class AudioTranscriptionError(ValueError):
    """Raised when an audio file cannot be transcribed into subtitles."""


@dataclass(frozen=True)
class TranscriptionResult:
    srt_path: str
    audio_path: str
    model: str
    device: str
    language: str
    language_probability: float
    duration_seconds: float
    segment_count: int


def _runtime_options(device: str, compute_type: str) -> tuple[str, str]:
    normalized_device = device.lower().strip()
    device_name = {"gpu": "cuda", "cuda": "cuda", "cpu": "cpu", "auto": "auto"}.get(
        normalized_device
    )
    if device_name is None:
        raise AudioTranscriptionError("--device phải là auto, cpu hoặc gpu")

    normalized_compute = compute_type.lower().strip()
    if normalized_compute == "auto":
        normalized_compute = {
            "cuda": "float16",
            "cpu": "int8",
            "auto": "default",
        }[device_name]
    if normalized_compute not in {"default", "int8", "float16", "float32"}:
        raise AudioTranscriptionError(
            "--compute-type phải là auto, default, int8, float16 hoặc float32"
        )
    return device_name, normalized_compute


def _default_output(audio: Path, language: str) -> Path:
    suffix = language if language and language != "auto" else "vi"
    return audio.with_name(f"{audio.stem}.{suffix}.srt")


def _word_cues(words: object, max_chars: int = 84) -> list[tuple[float, float, str]]:
    """Group Whisper word timestamps into readable subtitle cards."""
    cues: list[tuple[float, float, str]] = []
    text = ""
    start = 0.0
    end = 0.0
    for word in words or []:
        part = str(getattr(word, "word", "")).strip()
        word_start = float(getattr(word, "start", 0.0) or 0.0) * 1000.0
        word_end = float(getattr(word, "end", 0.0) or 0.0) * 1000.0
        if not part or word_end <= word_start:
            continue
        candidate = f"{text} {part}".strip()
        too_long = bool(text) and len(candidate) > max_chars
        too_slow = bool(text) and word_end - start > 6_000.0
        if too_long or too_slow:
            cues.append((start, end, text))
            text = part
            start = word_start
        else:
            if not text:
                start = word_start
            text = candidate
        end = word_end
    if text:
        cues.append((start, end, text))

    # Avoid a flash cue containing only the final word after an 84-char split.
    if len(cues) >= 2 and cues[-1][1] - cues[-1][0] < 1_000.0:
        previous, final = cues[-2], cues[-1]
        merged = f"{previous[2]} {final[2]}"
        if len(merged) <= max_chars + 20:
            cues[-2:] = [(previous[0], final[1], merged)]
    return cues


def transcribe_audio_to_srt(
    audio_path: str,
    output_path: str | None = None,
    *,
    model_name: str = "small",
    language: str = "vi",
    device: str = "auto",
    compute_type: str = "auto",
    beam_size: int = 5,
    vad_filter: bool = True,
    initial_prompt: str = "",
    progress_callback: Callable[[float, str], None] | None = None,
) -> TranscriptionResult:
    """Transcribe WAV/MP3/etc. and write a UTF-8 SRT file.

    ``faster-whisper`` is imported lazily so the normal audiobook workflow does
    not need to install the ASR runtime.
    """
    audio = Path(audio_path).expanduser().resolve()
    if not audio.is_file():
        raise AudioTranscriptionError(f"Không tìm thấy file audio: {audio}")
    if beam_size < 1:
        raise AudioTranscriptionError("--beam-size phải từ 1 trở lên")
    if not model_name.strip():
        raise AudioTranscriptionError("--model không được để trống")
    explicit_output = Path(output_path).expanduser().resolve() if output_path else None
    if explicit_output is not None and explicit_output.suffix.lower() != ".srt":
        raise AudioTranscriptionError("--output phải là một file có đuôi .srt")

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        requirements = Path(__file__).resolve().parents[2] / "requirements-asr.txt"
        raise AudioTranscriptionError(
            "Thiếu faster-whisper để chuyển audio thành SRT. Cài bằng lệnh: "
            f'python -m pip install -r "{requirements}"'
        ) from exc

    runtime_device, runtime_compute = _runtime_options(device, compute_type)
    requested_language = None if language.lower().strip() == "auto" else language.lower().strip()
    if progress_callback:
        progress_callback(0.0, f"Nạp model {model_name} ({runtime_device}/{runtime_compute})")

    try:
        model = WhisperModel(
            model_name.strip(), device=runtime_device, compute_type=runtime_compute
        )
        options: dict[str, object] = {
            "beam_size": beam_size,
            "language": requested_language,
            "task": "transcribe",
            "vad_filter": vad_filter,
            "word_timestamps": True,
            "condition_on_previous_text": True,
        }
        if initial_prompt.strip():
            options["initial_prompt"] = initial_prompt.strip()
        segments, info = model.transcribe(str(audio), **options)

        duration = float(getattr(info, "duration", 0.0) or 0.0)
        timed_cues: list[tuple[float, float, str]] = []
        for segment in segments:
            text = str(getattr(segment, "text", "")).strip()
            start = float(getattr(segment, "start", 0.0) or 0.0)
            end = float(getattr(segment, "end", start) or start)
            segment_cues = _word_cues(getattr(segment, "words", None))
            if segment_cues:
                timed_cues.extend(segment_cues)
            elif text and end > start:
                timed_cues.append((start * 1000.0, end * 1000.0, text))
            if progress_callback and duration > 0:
                progress_callback(min(99.0, end / duration * 100.0), text[:80])
    except AudioTranscriptionError:
        raise
    except Exception as exc:
        raise AudioTranscriptionError(
            f"Không thể nhận dạng audio bằng model {model_name}: {exc}"
        ) from exc

    if not timed_cues:
        raise AudioTranscriptionError("AI không nhận dạng được lời nói nào trong file audio")

    detected_language = str(getattr(info, "language", requested_language or "unknown"))
    probability = float(getattr(info, "language_probability", 0.0) or 0.0)
    output = explicit_output or _default_output(audio, detected_language)
    written = write_srt_cues(timed_cues, str(output))
    if progress_callback:
        progress_callback(100.0, f"Đã ghi {len(timed_cues)} đoạn phụ đề")
    return TranscriptionResult(
        srt_path=written,
        audio_path=str(audio),
        model=model_name.strip(),
        device=runtime_device,
        language=detected_language,
        language_probability=probability,
        duration_seconds=duration,
        segment_count=len(timed_cues),
    )
