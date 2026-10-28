"""Text normalization for Vietnamese content.

Handles number-to-word conversion, date formatting, abbreviation expansion,
symbol cleanup, and whitespace normalization before TTS synthesis.

Lớp ``VietnameseTextNormalizer`` là adapter: mặc định dùng regex nội bộ
(``backend="builtin"``), có thể thử ``vietnormalizer`` hoặc ``vinorm`` nếu
người dùng đã cài (không bắt buộc).
"""

from __future__ import annotations

import importlib
import re
from typing import Dict, List, Optional, Tuple

from utils.logging_config import get_logger

logger = get_logger("text_processing.normalizer")
NORMALIZATION_VERSION = "tts-text-v3"


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
    "TP.HCM": "Thành phố Hồ Chí Minh",
    "TP.": "thành phố",
    "VN": "Việt Nam",
    "VD": "ví dụ",
    "VD:": "ví dụ:",
    "GS.": "giáo sư",
    "PGS.": "phó giáo sư",
    "TS.": "tiến sĩ",
    "ThS.": "thạc sĩ",
    "CN.": "cử nhân",
    "BS.": "bác sĩ",
    "KTS.": "kiến trúc sư",
    "Tr.": "trang",
    "Q.": "quận",
    "P.": "phường",
    "TT.": "thị trấn",
    "km": "ki-lô-mét",
    "kg": "ki-lô-gam",
    "cm": "xen-ti-mét",
    "mm": "mi-li-mét",
    "m2": "mét vuông",
    "m3": "mét khối",
}

# Compound abbreviations must be protected before dotted proper names, so that
# "TP.HCM" is still expanded while "Roslet.James.P" is left untouched.
_COMPOUND_ABBREVIATIONS: Dict[str, str] = {
    "TP.HCM": "Thành phố Hồ Chí Minh",
}

# Dotted proper-name chains such as "Roslet.James.P".
_DOTTED_NAME = re.compile(
    r"(?<!\w)[A-Za-zÀ-Ỹ][\wÀ-ỹ]*(?:\.[A-Za-zÀ-Ỹ][\wÀ-ỹ]*)+\.?(?!\w)"
)
# Single-letter initials such as "P." or "J.".
_SINGLE_INITIAL = re.compile(r"(?<!\w)[A-Za-zÀ-Ỹ]\.(?!\w)")
# Single-letter abbreviations that must still be expanded (Q. → quận).
_EXPANDED_INITIALS = {"Q."}
# Placeholder dùng ký tự private-use (không phải chữ số) để các bước
# chuẩn hóa số không vô tình đọc chỉ số placeholder thành chữ.
_MASK = "\x00{}\x01"
_MASK_BASE = 0xE000
_MASK_RESTORE = re.compile(r"\x00([\uE000-\uF8FF])\x01")

_UNIT_WORDS = r"(?:nghìn\s+tỷ|triệu\s+tỷ|nghìn|ngàn|tỷ|triệu)"
_CURRENCY_WORDS = r"(?:đô\s*la|đô|USD|VND|đồng|\$)"
_CURRENCY_PATTERN = re.compile(
    rf"(?<!\w)(\d[\d.,]*)\s*(?:({_UNIT_WORDS})\s*)?({_CURRENCY_WORDS})(?!\w)",
    re.IGNORECASE,
)
_DOLLAR_PREFIX = re.compile(r"\$\s*(\d[\d.,]*)")


def number_to_vietnamese(n: int) -> str:
    """Chuyển một số nguyên thành chữ tiếng Việt.

    Args:
        n: Số nguyên cần chuyển (hỗ trợ tới hàng nghìn tỷ).

    Returns:
        Chuỗi chữ tiếng Việt tương ứng.
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


def _number_token_to_words(token: str) -> Optional[str]:
    """Convert a numeric token (with , or . separators) to Vietnamese words."""
    cleaned = token.strip()
    if not cleaned or not re.fullmatch(r"\d[\d.,]*", cleaned):
        return None

    # Comma thousands separator: 1,000,000
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", cleaned):
        cleaned = cleaned.replace(",", "")
    # Dot thousands separator (at least two groups): 1.000.000
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3}){2,}", cleaned):
        cleaned = cleaned.replace(".", "")
    # Currency amounts like 30.000 are far more likely thousands than decimals.
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cleaned):
        cleaned = cleaned.replace(".", "")

    if re.fullmatch(r"\d+", cleaned):
        if len(cleaned) > 12:
            return None
        return number_to_vietnamese(int(cleaned))
    if re.fullmatch(r"\d+\.\d+", cleaned):
        return _convert_number_str(cleaned)
    return None


def _normalize_currency(text: str) -> str:
    """Convert amounts followed by a currency word into spoken Vietnamese."""

    def _replace(match: re.Match) -> str:
        words = _number_token_to_words(match.group(1))
        if words is None:
            return match.group(0)
        unit = " ".join((match.group(2) or "").split())
        currency = match.group(3).casefold()
        spoken = "đồng" if currency == "đồng" else "đô la"
        return " ".join(part for part in (words, unit, spoken) if part)

    text = _CURRENCY_PATTERN.sub(_replace, text)

    def _replace_dollar(match: re.Match) -> str:
        words = _number_token_to_words(match.group(1))
        if words is None:
            return match.group(0)
        return f"{words} đô la"

    return _DOLLAR_PREFIX.sub(_replace_dollar, text)


def _convert_number_str(s: str) -> str:
    """Convert a number string (possibly decimal) to Vietnamese."""
    if "." in s:
        parts = s.split(".", 1)
        return number_to_vietnamese(int(parts[0])) + " phẩy " + number_to_vietnamese(int(parts[1]))
    return number_to_vietnamese(int(s))


def normalize_numbers(text: str) -> str:
    """Chuyển các con số độc lập trong văn bản thành chữ tiếng Việt.

    Xử lý số nguyên (kể cả dấu phân cách hàng nghìn), số thập phân và
    phần trăm. Không đổi số nằm trong mã định danh.

    Args:
        text: Văn bản đầu vào.

    Returns:
        Văn bản đã chuyển số thành chữ.
    """
    # Percentages: 50% → năm mươi phần trăm
    text = re.sub(
        r"(?<![\w.,])(\d[\d.,]*)\s*%",
        lambda m: (
            (_number_token_to_words(m.group(1)) or m.group(1)) + " phần trăm"
        ),
        text,
    )

    # Thousand separators (comma style: 1,000,000)
    text = re.sub(
        r"(?<!\w)\d{1,3}(?:,\d{3})+(?!\w)",
        lambda m: number_to_vietnamese(int(m.group(0).replace(",", ""))),
        text,
    )

    # Thousand separators (dot style: 1.000.000) before decimal handling
    text = re.sub(
        r"(?<!\w)\d{1,3}(?:\.\d{3}){2,}(?!\w)",
        lambda m: number_to_vietnamese(int(m.group(0).replace(".", ""))),
        text,
    )

    # Vietnamese convention: dot + exactly 3 digits is a thousands separator,
    # while dot + 1-2 digits is a decimal (3.14 → ba phẩy mười bốn).
    text = re.sub(
        r"(?<!\w)\d{1,3}(?:\.\d{3})+(?!\w)",
        lambda m: number_to_vietnamese(int(m.group(0).replace(".", ""))),
        text,
    )

    # Decimals: 3.14 → ba phẩy mười bốn
    def _convert_decimal(m: re.Match) -> str:
        integer_part = m.group(1)
        decimal_part = m.group(2)
        result = number_to_vietnamese(int(integer_part)) + " phẩy "
        if len(decimal_part) <= 2:
            result += number_to_vietnamese(int(decimal_part))
        else:
            result += " ".join(
                _ONES[int(d)] if int(d) > 0 else "không" for d in decimal_part
            )
        return result

    text = re.sub(r"\b(\d+)\.(\d+)\b(?!%)", _convert_decimal, text)

    # Large standalone integers (not part of a word/code)
    def _convert_integer(m: re.Match) -> str:
        num_str = m.group(0)
        if len(num_str) > 12:
            return num_str
        try:
            return number_to_vietnamese(int(num_str))
        except (ValueError, OverflowError):
            return num_str

    text = re.sub(r"(?<!\w)\d{1,12}(?!\w)", _convert_integer, text)

    return text


def normalize_dates(text: str) -> str:
    """Chuyển các mẫu ngày tháng thành dạng đọc tiếng Việt.

    Hỗ trợ:
    - DD/MM/YYYY → ngày DD tháng MM năm YYYY
    - DD-MM-YYYY → ngày DD tháng MM năm YYYY

    Args:
        text: Văn bản đầu vào.

    Returns:
        Văn bản đã chuyển ngày tháng sang dạng đọc.
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

    text = re.sub(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b", _convert_date, text)
    return text


def expand_abbreviations(text: str) -> str:
    """Mở rộng các viết tắt tiếng Việt thường gặp.

    Khóa dài được thay trước và word-boundary ngăn thay một phần
    (ví dụ ``TP.`` bên trong ``TP.HCM``).

    Args:
        text: Văn bản đầu vào.

    Returns:
        Văn bản đã mở rộng viết tắt.
    """
    for abbr in sorted(ABBREVIATIONS, key=len, reverse=True):
        expansion = ABBREVIATIONS[abbr]
        pattern = rf"(?<!\w){re.escape(abbr)}(?!\w)"
        text = re.sub(pattern, lambda _m, value=expansion: value, text)
    return text


def _protect_tokens(text: str) -> Tuple[str, List[str]]:
    """Mask dotted names/initials so normalization cannot destroy them."""
    values: List[str] = []

    def _mask(value: str) -> str:
        values.append(value)
        return _MASK.format(chr(_MASK_BASE + len(values) - 1))

    for abbr, expansion in sorted(
        _COMPOUND_ABBREVIATIONS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        text = re.sub(
            rf"(?<!\w){re.escape(abbr)}(?!\w)",
            lambda _m, value=expansion: _mask(value),
            text,
            flags=re.IGNORECASE,
        )

    text = _DOTTED_NAME.sub(lambda m: _mask(m.group(0)), text)

    def _mask_initial(match: re.Match) -> str:
        token = match.group(0)
        if token.upper() in _EXPANDED_INITIALS:
            return token
        return _mask(token)

    text = _SINGLE_INITIAL.sub(_mask_initial, text)
    return text, values


def _restore_tokens(text: str, values: List[str]) -> str:
    """Restore masked tokens (or their expansions) into the text."""
    return _MASK_RESTORE.sub(
        lambda m: values[ord(m.group(1)) - _MASK_BASE], text
    )


def _normalize_symbols(text: str) -> str:
    """Replace prose symbols with TTS-friendly punctuation."""
    text = text.replace("***", " . . . ")
    text = re.sub(r"\*{3,}", " . . . ", text)
    text = text.replace("—", ", ").replace("–", ", ")
    text = re.sub(r"…+", ". ", text)
    return text


def _tidy_spacing(text: str) -> str:
    """Remove spacing artifacts introduced by replacements only."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Không gộp khoảng trắng trước dấu chấm: " . . . " là ba khoảng lặng TTS.
    text = re.sub(r"\s+([,;:!?…])", r"\1", text)
    text = re.sub(r"([,;:])\s*,\s*", r"\1 ", text)
    text = re.sub(r"([,;:])(?=\S)", r"\1 ", text)
    return text


class VietnameseTextNormalizer:
    """Chuẩn hóa văn bản tiếng Việt trước khi tổng hợp giọng nói.

    Adapter pattern: mặc định dùng regex nội bộ, không cần thư viện ngoài.
    Nếu chọn backend ngoài mà chưa cài, tự động fallback về ``builtin``.
    """

    SUPPORTED_BACKENDS = ("builtin", "vietnormalizer", "vinorm")

    def __init__(self, backend: str = "builtin") -> None:
        self.requested_backend = backend
        self.backend = "builtin"
        self._external = None
        if backend not in self.SUPPORTED_BACKENDS:
            logger.warning(
                "Backend chuẩn hóa không hỗ trợ: %s. Dùng builtin.", backend
            )
            return

        if backend != "builtin":
            self._external = self._load_external(backend)
            if self._external is not None:
                self.backend = backend
            else:
                logger.warning(
                    "Không import được backend '%s'. Fallback về builtin.", backend
                )

    @staticmethod
    def _load_external(backend: str):
        """Try to load an optional normalizer backend (returns callable or None)."""
        try:
            module = importlib.import_module(backend)
        except ImportError:
            return None

        for name in ("normalize", "normalize_text"):
            func = getattr(module, name, None)
            if callable(func):
                return func
        logger.warning("Module '%s' không có hàm normalize().", backend)
        return None

    def normalize(self, text: str) -> str:
        """Chuẩn hóa văn bản thô thành dạng TTS đọc được.

        Thứ tự: bảo vệ tên riêng/viết tắt có dấu chấm → mở rộng viết tắt →
        ngày → tiền tệ → phần trăm/số → ký hiệu → khôi phục token → khoảng trắng.

        Args:
            text: Văn bản gốc.

        Returns:
            Văn bản đã chuẩn hóa, giữ nguyên dấu câu và cấu trúc câu.
        """
        if not text:
            return text or ""

        if self._external is not None:
            try:
                text = self._external(text)
            except Exception as exc:  # pragma: no cover - optional backend
                logger.warning(
                    "Backend '%s' lỗi (%s). Chuyển sang builtin.",
                    self.backend,
                    exc,
                )
                self._external = None
                self.backend = "builtin"

        text, values = _protect_tokens(text)
        text = expand_abbreviations(text)
        text = normalize_dates(text)
        text = _normalize_currency(text)
        text = normalize_numbers(text)
        text = _normalize_symbols(text)
        text = _restore_tokens(text, values)
        return _tidy_spacing(text)


_PUNCT_TRANSLATION = str.maketrans({
    "，": ",", "。": ".", "？": "?", "！": "!", "；": ";", "：": ":",
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "…": "…", "–": "—",
})


def compile_spoken_text(text: str, *, conservative: bool = False) -> str:
    """Chuẩn hóa dấu câu an toàn cho VieNeu.

    Dấu câu chỉ còn vai trò điều khiển ngữ điệu, không bị đọc thành nội dung.
    ``conservative`` bỏ dấu câu phụ trợ sau lần render đầu thất bại.
    Lưu ý: không bao giờ xóa critical words (tên riêng / số) – chúng được
    bảo vệ ở tầng extract trước khi gọi hàm này.
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
        # Chỉ bỏ dấu câu phụ trợ, giữ nguyên nội dung từ vựng
        text = text.replace('"', "").replace("'", "")
        text = re.sub(r"[;:—–()\[\]{}]", " ", text)  # space thay vì comma để tránh gộp từ
        text = re.sub(r"\s+", " ", text)
        text = text.replace("…", ".")
    text = re.sub(r"\s+([,.;:!?…])", r"\1", text)
    text = re.sub(r"""([,.;:!?…])(?=[^\s"'])""", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;:")
    return text


def alignment_text(text: str) -> str:
    """Trả về văn bản không dấu câu để so khớp nguồn với ASR cục bộ."""
    value = compile_spoken_text(text, conservative=True).casefold()
    value = re.sub(r"[^\w\sđĐ]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


_normalizer_singleton: Optional[VietnameseTextNormalizer] = None
_pronunciation_singleton = None


def prepare_for_tts(raw_text: str) -> str:
    """Chuẩn bị văn bản thô cho TTS: normalize trước, áp từ điển phát âm sau.

    Thứ tự này bắt buộc: normalizer có thể phá vỡ tên riêng (dấu chấm, số)
    nếu từ điển phát âm chạy trước.

    Args:
        raw_text: Nội dung segment gốc.

    Returns:
        Văn bản đã chuẩn hóa và thay tên riêng bằng cách đọc tiếng Việt.
    """
    global _normalizer_singleton, _pronunciation_singleton

    if _normalizer_singleton is None:
        _normalizer_singleton = VietnameseTextNormalizer()
    text = _normalizer_singleton.normalize(raw_text)

    if _pronunciation_singleton is None:
        from text_processing.pronunciation import PronunciationDict

        _pronunciation_singleton = PronunciationDict()
    return _pronunciation_singleton.apply(text)


def normalize_text(
    text: str,
    *,
    conservative: bool = False,
    critical_words: list[str] | None = None,
) -> str:
    """Apply all text normalizations for TTS processing.

    Pipeline: Vietnamese normalize → pronunciation dictionary → punctuation.
    critical_words được giữ nguyên (không bị expand / cắt).

    Args:
        text: Raw text from a segment.
        conservative: Chế độ rút gọn dấu câu (chỉ dùng khi retry cuối).
        critical_words: Danh sách từ cần bảo vệ (tùy chọn).

    Returns:
        Normalized text ready for TTS synthesis.
    """
    logger.debug("Normalizing text: %s...", text[:50] if text else "")

    text = prepare_for_tts(text)
    return compile_spoken_text(text, conservative=conservative)
