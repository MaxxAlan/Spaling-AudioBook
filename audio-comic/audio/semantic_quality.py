"""Offline semantic verification for generated TTS segments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from text_processing.normalizer import alignment_text


def _distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for row, a in enumerate(left, 1):
        current = [row]
        for column, b in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (a != b),
            ))
        previous = current
    return previous[-1]


def _repeated_phrase(tokens: list[str]) -> bool:
    triples = [tuple(tokens[index:index + 3]) for index in range(max(0, len(tokens) - 2))]
    return any(triples[index] == triples[index + 1] for index in range(max(0, len(triples) - 1)))


@dataclass(frozen=True)
class SemanticReview:
    approved: bool
    transcript: str
    word_error_rate: float
    char_error_rate: float
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def review_transcript(source: str, transcript: str) -> SemanticReview:
    expected = alignment_text(source)
    actual = alignment_text(transcript)
    expected_words, actual_words = expected.split(), actual.split()
    wer = _distance(expected_words, actual_words) / max(1, len(expected_words))
    cer = _distance(list(expected.replace(" ", "")), list(actual.replace(" ", ""))) / max(
        1, len(expected.replace(" ", ""))
    )
    reasons: list[str] = []
    punctuation_words = (
        "dấu phẩy", "dấu chấm", "dấu hỏi", "chấm hỏi", "chấm than",
    )
    if any(phrase in actual and phrase not in expected for phrase in punctuation_words):
        reasons.append("spoken_punctuation")
    elif any(word in actual_words and word not in expected_words for word in ("phẩy", "chấm")):
        reasons.append("spoken_punctuation")
    if _repeated_phrase(actual_words) and not _repeated_phrase(expected_words):
        reasons.append("repeated_phrase")
    # WER is unstable on one-to-three-word attributions: one name variant
    # becomes a 50% error even when the utterance is clear.
    if len(expected_words) >= 4 and wer > 0.45 and cer > 0.35:
        reasons.append("content_mismatch")
    if expected_words and len(actual_words) < max(1, len(expected_words) * 0.65):
        reasons.append("word_omission")
    return SemanticReview(
        approved=not reasons,
        transcript=transcript,
        word_error_rate=round(wer, 4),
        char_error_rate=round(cer, 4),
        reasons=reasons,
    )


class LocalSpeechVerifier:
    """Reuse one faster-whisper model for all segments in a job."""

    def __init__(
        self,
        model_name: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "TTS semantic QA requires faster-whisper; rerun install.bat."
                ) from exc
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def verify(self, audio_path: str, source: str) -> SemanticReview:
        if not Path(audio_path).is_file():
            return SemanticReview(False, "", 1.0, 1.0, ["file_missing_or_empty"])
        segments, _info = self._load().transcribe(
            audio_path,
            language="vi",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        transcript = " ".join(str(item.text).strip() for item in segments).strip()
        return review_transcript(source, transcript)
