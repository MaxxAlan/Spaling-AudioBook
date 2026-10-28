"""Điểm vào tương thích cho phân tích văn bản và chuẩn bị TTS.

Repo hiện tách logic thành hai module:
- ``script_analyzer``: tách hội thoại / tạo segment.
- ``normalizer``: chuẩn hóa văn bản + áp từ điển phát âm trước khi TTS.

Module này chỉ re-export, không chứa logic trùng lặp.
"""

from __future__ import annotations

from text_processing.normalizer import (
    NORMALIZATION_VERSION,
    VietnameseTextNormalizer,
    normalize_text,
    prepare_for_tts,
)
from text_processing.script_analyzer import analyze_script

__all__ = [
    "NORMALIZATION_VERSION",
    "VietnameseTextNormalizer",
    "analyze_script",
    "normalize_text",
    "prepare_for_tts",
]
