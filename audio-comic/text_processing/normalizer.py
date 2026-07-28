"""Text normalization for Vietnamese content.

Handles number-to-word conversion, date formatting, abbreviation expansion,
and whitespace normalization before TTS synthesis.
"""

from __future__ import annotations

import re
from typing import Dict, List

from utils.logging_config import get_logger

logger = get_logger("text_processing.normalizer")
NORMALIZATION_VERSION = "tts-text-v2"


# Vietnamese number words
_ONES = [
    "", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín",
]
_TEENS_SPECIAL = {
    10: "mười", 11: "mười một", 14: "mười bốn", 15: "mười lăm",
}
_TENS = [
    "", "mười", "hai mươi", "ba mươi", "bốn mươi", "năm mươi",
    "sáu mươi", "bảy mươi", "tám mươi", "chín mươi",
]

# Common Vietnamese abbreviations
ABBREVIATIONS: Dict[str, str] = {
    "TP.": "Thành phố",
    "TP.HCM": "Thành phố Hồ Chí Minh",
    "VN": "Việt Nam",
    "VD": "ví dụ",
    "VD:": "ví dụ:",
    "GS.": "Giáo sư",
    "PGS.": "Phó Giáo sư",
    "TS.": "Tiến sĩ",
    "ThS.": "Thạc sĩ",
    "CN.": "Cử nhân",
    "BS.": "Bác sĩ",
    "KTS.": "Kiến trúc sư",
    "Tr.": "Trang",
    "Q.": "Quận",
    "P.": "Phường",
    "TT.": "Thị trấn",
    "km": "ki-lô-mét",
    "kg": "ki-lô-gam",
    "cm": "xen-ti-mét",
    "mm": "mi-li-mét",
    "m2": "mét vuông",
    "m3": "mét khối",
}


def number_to_vietnamese(n: int) -> str:
    """Convert an integer to Vietnamese words.

    Args:
        n: Integer to convert (supports up to billions).

    Returns:
        Vietnamese word representation.
    """
    if n == 0:
        return "không"
    if n < 0:
        return "âm " + number_to_vietnamese(-n)

    parts: List[str] = []

    if n >= 1_000_000_000:
        billions = n // 1_000_000_000
        parts.append(number_to_vietnamese(billions) + " tỷ")
        n %= 1_000_000_000

    if n >= 1_000_000:
        millions = n // 1_000_000
        parts.append(number_to_vietnamese(millions) + " triệu")
        n %= 1_000_000

    if n >= 1_000:
        thousands = n // 1_000
        parts.append(number_to_vietnamese(thousands) + " nghìn")
        n %= 1_000
        if 0 < n < 100:
            parts.append("không trăm")

    if n >= 100:
        hundreds = n // 100
        parts.append(_ONES[hundreds] + " trăm")
        n %= 100
        if 0 < n < 10:
            parts.append("lẻ")

    if n >= 20:
        tens = n // 10
        ones = n % 10
        parts.append(_TENS[tens])
        if ones == 1:
            parts.append("mốt")
        elif ones == 4:
            parts.append("tư")
        elif ones == 5:
            parts.append("lăm")
        elif ones > 0:
            parts.append(_ONES[ones])
    elif n >= 10:
        if n in _TEENS_SPECIAL:
            parts.append(_TEENS_SPECIAL[n])
        else:
            parts.append("mười " + _ONES[n - 10])
    elif n > 0:
        parts.append(_ONES[n])

    return " ".join(parts)


def normalize_numbers(text: str) -> str:
    """Convert standalone numbers in text to Vietnamese words.

    Handles integers, decimals, and percentages.
    Does not convert numbers that are part of identifiers or codes.

    Args:
        text: Input text.

    Returns:
        Text with numbers converted to words.
    """
    # Percentages: 50% → năm mươi phần trăm
    text = re.sub(
        r"\b(\d+(?:\.\d+)?)\s*%",
        lambda m: _convert_number_str(m.group(1)) + " phần trăm",
        text,
    )

    # Decimals: 3.14 → ba phẩy mười bốn
    def _convert_decimal(m: re.Match) -> str:
        integer_part = m.group(1)
        decimal_part = m.group(2)
        result = number_to_vietnamese(int(integer_part)) + " phẩy "
        # Read decimal digits individually or as number
        if len(decimal_part) <= 2:
            result += number_to_vietnamese(int(decimal_part))
        else:
            result += " ".join(_ONES[int(d)] if int(d) > 0 else "không" for d in decimal_part)
        return result

    text = re.sub(r"\b(\d+)\.(\d+)\b(?!%)", _convert_decimal, text)

    # Large standalone integers (not part of a word/code)
    def _convert_integer(m: re.Match) -> str:
        num_str = m.group(0)
        # Skip if too long (likely a code/ID) or if preceded by specific patterns
        if len(num_str) > 12:
            return num_str
        try:
            return number_to_vietnamese(int(num_str))
        except (ValueError, OverflowError):
            return num_str

    text = re.sub(r"(?<!\w)\d{1,12}(?!\w)", _convert_integer, text)

    return text


def _convert_number_str(s: str) -> str:
    """Convert a number string (possibly decimal) to Vietnamese."""
    if "." in s:
        parts = s.split(".", 1)
        return number_to_vietnamese(int(parts[0])) + " phẩy " + number_to_vietnamese(int(parts[1]))
    return number_to_vietnamese(int(s))


def normalize_dates(text: str) -> str:
    """Convert date patterns to spoken Vietnamese.

    Handles:
    - DD/MM/YYYY → ngày DD tháng MM năm YYYY
    - DD-MM-YYYY → ngày DD tháng MM năm YYYY

    Args:
        text: Input text.

    Returns:
        Text with dates converted to spoken form.
    """
    def _convert_date(m: re.Match) -> str:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3))
        return (
            f"ngày {number_to_vietnamese(day)} "
            f"tháng {number_to_vietnamese(month)} "
            f"năm {number_to_vietnamese(year)}"
        )

    # DD/MM/YYYY or DD-MM-YYYY
    text = re.sub(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b", _convert_date, text)
    return text


def expand_abbreviations(text: str) -> str:
    """Expand common Vietnamese abbreviations.

    Args:
        text: Input text.

    Returns:
        Text with abbreviations expanded.
    """
    for abbr, expansion in ABBREVIATIONS.items():
        # Use word boundaries to avoid partial matches
        text = text.replace(abbr, expansion)
    return text


_PUNCT_TRANSLATION = str.maketrans({
    "，": ",", "。": ".", "？": "?", "！": "!", "；": ";", "：": ":",
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "…": "…", "–": "—",
})


def compile_spoken_text(text: str, *, conservative: bool = False) -> str:
    """Compile display text into punctuation-safe text for VieNeu.

    Punctuation remains prosody control, never literal narration content.
    ``conservative`` removes optional punctuation after a failed first render.
    """
    text = text.translate(_PUNCT_TRANSLATION)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", text)
    text = re.sub(r"([!?])(?:\s*[!?])+", r"\1", text)
    text = re.sub(r"\.{4,}", "…", text)
    text = re.sub(r"…+", "…", text)
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r";{2,}", ";", text)
    text = re.sub(r"^\s*[-–—•*#]+\s*", "", text)
    text = re.sub(r"(?m)^\s*[,.;:!?…]+\s*$", "", text)
    if conservative:
        text = text.replace('"', "").replace("'", "")
        text = re.sub(r"[;:—–()\[\]{}]", ",", text)
        text = re.sub(r"\s*,\s*", " ", text)
        text = text.replace("…", ".")
    text = re.sub(r"\s+([,.;:!?…])", r"\1", text)
    text = re.sub(r"""([,.;:!?…])(?=[^\s"'])""", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;:")
    return text


def alignment_text(text: str) -> str:
    """Return punctuation-free text used to compare source with local ASR."""
    value = compile_spoken_text(text, conservative=True).casefold()
    value = re.sub(r"[^\w\sđĐ]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(text: str, *, conservative: bool = False) -> str:
    """Apply all text normalizations for TTS processing.

    Pipeline: abbreviations → dates → numbers → whitespace.

    Args:
        text: Raw text from a segment.

    Returns:
        Normalized text ready for TTS synthesis.
    """
    logger.debug("Normalizing text: %s...", text[:50])

    text = expand_abbreviations(text)
    text = normalize_dates(text)
    text = normalize_numbers(text)

    return compile_spoken_text(text, conservative=conservative)
