"""Offline semantic verification for generated TTS segments.

Nâng cấp P0:
- Ngưỡng WER/CER chặt hơn với câu ≥ 6 từ.
- Kiểm tra missing critical_words (tên riêng, số, thuật ngữ).
- Text integrity score hỗ trợ quyết định approve.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from text_processing.normalizer import alignment_text
from text_processing.critical_words import missing_critical_words


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


def text_integrity_score(expected_words: list[str], actual_words: list[str]) -> float:
    """Điểm toàn vẹn nội dung (0–1). Càng cao càng tốt."""
    if not expected_words:
        return 1.0
    # Jaccard đơn giản trên tập từ + penalty thiếu số lượng
    set_e, set_a = set(expected_words), set(actual_words)
    inter = len(set_e & set_a)
    union = len(set_e | set_a) or 1
    jaccard = inter / union
    length_ratio = min(1.0, len(actual_words) / max(1, len(expected_words)))
    return round(0.65 * jaccard + 0.35 * length_ratio, 4)


@dataclass(frozen=True)
class SemanticReview:
    approved: bool
    transcript: str
    word_error_rate: float
    char_error_rate: float
    reasons: list[str]
    integrity_score: float = 1.0
    missing_critical: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def review_transcript(
    source: str,
    transcript: str,
    critical_words: Optional[List[str]] = None,
) -> SemanticReview:
    """Đánh giá transcript ASR so với source text.

    Ngưỡng P0 (câu ≥ 6 từ):
      - WER ≤ 0.25 và CER ≤ 0.18 mới được xem là tốt.
      - Missing bất kỳ critical_word nào → reject.
    """
    expected = alignment_text(source)
    actual = alignment_text(transcript)
    expected_words, actual_words = expected.split(), actual.split()
    n_words = len(expected_words)

    wer = _distance(expected_words, actual_words) / max(1, n_words)
    cer = _distance(
        list(expected.replace(" ", "")),
        list(actual.replace(" ", "")),
    ) / max(1, len(expected.replace(" ", "")))

    integrity = text_integrity_score(expected_words, actual_words)
    reasons: list[str] = []
    missing: list[str] = []

    # 1. Spoken punctuation
    punctuation_words = (
        "dấu phẩy", "dấu chấm", "dấu hỏi", "chấm hỏi", "chấm than",
    )
    if any(phrase in actual and phrase not in expected for phrase in punctuation_words):
        reasons.append("spoken_punctuation")
    elif any(word in actual_words and word not in expected_words for word in ("phẩy", "chấm")):
        reasons.append("spoken_punctuation")

    # 2. Repeated phrase
    if _repeated_phrase(actual_words) and not _repeated_phrase(expected_words):
        reasons.append("repeated_phrase")

    # 3. Content mismatch – ngưỡng chặt hơn theo độ dài
    if n_words >= 6:
        if wer > 0.25 or cer > 0.18:
            reasons.append("content_mismatch")
    elif n_words >= 4:
        if wer > 0.40 and cer > 0.30:
            reasons.append("content_mismatch")

    # 4. Word omission (thiếu nhiều từ)
    if expected_words and len(actual_words) < max(1, int(n_words * 0.75)):
        reasons.append("word_omission")

    # 5. Missing critical words (ưu tiên cao)
    if critical_words:
        missing = missing_critical_words(source, transcript, critical_words)
        if missing:
            reasons.append("missing_critical_words")

    # 6. Integrity score thấp
    if integrity < 0.72 and n_words >= 4:
        if "content_mismatch" not in reasons:
            reasons.append("low_integrity")

    return SemanticReview(
        approved=not reasons,
        transcript=transcript,
        word_error_rate=round(wer, 4),
        char_error_rate=round(cer, 4),
        reasons=reasons,
        integrity_score=integrity,
        missing_critical=missing,
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

    def verify(
        self,
        audio_path: str,
        source: str,
        critical_words: Optional[List[str]] = None,
    ) -> SemanticReview:
        if not Path(audio_path).is_file():
            return SemanticReview(
                False, "", 1.0, 1.0, ["file_missing_or_empty"], 0.0, []
            )
        segments, _info = self._load().transcribe(
            audio_path,
            language="vi",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        transcript = " ".join(str(item.text).strip() for item in segments).strip()
        return review_transcript(source, transcript, critical_words=critical_words)
