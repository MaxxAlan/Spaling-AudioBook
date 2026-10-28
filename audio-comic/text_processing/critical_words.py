"""Phát hiện và bảo vệ từ quan trọng trước khi TTS (chống miss chữ).

Critical words = tên riêng, số, thuật ngữ khoa học/pháp y/viễn tưởng, viết tắt quan trọng.
Được inject vào Segment.critical_words và dùng trong semantic QA + retry.
"""

from __future__ import annotations

import re
from typing import List, Set

# Pattern bắt tên riêng tiếng Việt / Latin (viết hoa đầu từ)
_PROPER_NAME = re.compile(
    r"\b([A-ZĐÂĂÊÔƠƯ][\wđĐâăêôơưÂĂÊÔƠƯàáạảãèéẹẻẽìíịỉĩòóọỏõùúụủũỳýỵỷỹ]+"
    r"(?:\s+[A-ZĐÂĂÊÔƠƯ][\wđĐâăêôơưÂĂÊÔƠƯàáạảãèéẹẻẽìíịỉĩòóọỏõùúụủũỳýỵỷỹ]+){0,4})\b"
)

# Số (kể cả số La Mã, phần trăm, đơn vị)
_NUMBER = re.compile(
    r"\b(\d+(?:[.,]\d+)?%?|\d+/\d+|[IVXLCDM]{1,6})\b",
    re.IGNORECASE,
)

# Thuật ngữ thường gặp trong truyện pháp y / khoa học / viễn tưởng (có thể mở rộng)
_DOMAIN_TERMS: Set[str] = {
    "adn", "dna", "arn", "rna", "pcr", "xét nghiệm", "pháp y", "hiện trường",
    "mẫu máu", "dấu vân tay", "vân tay", "huyết thanh", "tế bào", "virus",
    "bacterium", "kháng thể", "vaccine", "gen", "genome", "crispr",
    "nanobot", "cyber", "hologram", "quantum", "plasma", "reactor",
    "hyperspace", "wormhole", "android", "cyborg", "neuralink",
    "chứng cứ", "hiện vật", "khám nghiệm", "tử thi", "xác chết",
}

# Viết tắt quan trọng không nên bị expand hoặc miss
_PROTECTED_ABBR = re.compile(
    r"\b(TP\.HCM|TP\.|VN|DNA|ADN|RNA|ARN|PCR|HIV|AIDS|COVID|AI|GPU|CPU|API)\b",
    re.IGNORECASE,
)


def extract_critical_words(text: str, extra: List[str] | None = None) -> List[str]:
    """Trích xuất danh sách từ quan trọng cần bảo vệ khi TTS + QA.

    Args:
        text: Văn bản gốc của segment.
        extra: Danh sách bổ sung (từ Character Bible / master.md).

    Returns:
        List từ unique, giữ thứ tự xuất hiện, đã lower-case để so khớp.
    """
    if not text or not text.strip():
        return []

    found: List[str] = []
    seen: Set[str] = set()

    def _add(word: str) -> None:
        w = word.strip()
        if not w:
            return
        key = w.casefold()
        if key not in seen and len(key) >= 2:
            seen.add(key)
            found.append(w)

    # 1. Tên riêng
    for m in _PROPER_NAME.finditer(text):
        _add(m.group(1))

    # 2. Số
    for m in _NUMBER.finditer(text):
        _add(m.group(1))

    # 3. Viết tắt được bảo vệ
    for m in _PROTECTED_ABBR.finditer(text):
        _add(m.group(1))

    # 4. Thuật ngữ domain (match cả cụm)
    lower = text.casefold()
    for term in sorted(_DOMAIN_TERMS, key=len, reverse=True):
        if term in lower:
            # Lấy đúng casing gần nhất từ text gốc
            idx = lower.find(term)
            _add(text[idx : idx + len(term)])

    # 5. Extra từ Character Bible / user
    if extra:
        for w in extra:
            _add(w)

    return found


def missing_critical_words(
    source: str,
    transcript: str,
    critical: List[str],
) -> List[str]:
    """Trả về danh sách critical words bị thiếu trong transcript ASR.

    So khớp case-insensitive, cho phép biến thể nhẹ (bỏ dấu câu).
    Bỏ qua critical word không còn xuất hiện trong ``source`` vì normalizer
    hoặc từ điển phát âm đã thay nó bằng dạng đọc (số → chữ, tên riêng →
    phiên âm). Những từ đó được kiểm tra gián tiếp qua WER/CER.
    """
    if not critical:
        return []

    actual = re.sub(r"[^\w\sđĐ]", " ", transcript.casefold())
    actual = re.sub(r"\s+", " ", actual).strip()
    source_compact = re.sub(r"[^\wđĐ]", "", source.casefold())
    missing: List[str] = []

    for word in critical:
        key = re.sub(r"[^\wđĐ]", "", word.casefold())
        if len(key) < 2:
            continue
        if key not in source_compact:
            continue
        # Cho phép match gần đúng (số / tên)
        if key not in actual.replace(" ", "") and key not in actual:
            missing.append(word)

    return missing


def protect_in_text(text: str, critical: List[str]) -> str:
    """Giữ nguyên critical words khi normalize (placeholder tạm thời).

    Hiện tại chỉ dùng để đánh dấu; normalizer sẽ không đụng đến chúng
    vì chúng đã là token sạch. Hàm này để mở rộng sau (nếu cần mask).
    """
    return text
