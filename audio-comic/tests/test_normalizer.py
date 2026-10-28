"""Unit tests cho chuẩn hóa văn bản và từ điển phát âm tiếng Việt."""

from __future__ import annotations

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import pytest

from text_processing.normalizer import VietnameseTextNormalizer, normalize_numbers
from text_processing.pronunciation import PronunciationDict

DICT_PATH = APP_ROOT / "config" / "pronunciation_dict.json"
NORMALIZER = VietnameseTextNormalizer()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30 nghìn tỷ đô", "ba mươi nghìn tỷ đô la"),
        ("1000 đô", "một nghìn đô la"),
        ("$1000", "một nghìn đô la"),
        ("30 nghìn tỷ đô la", "ba mươi nghìn tỷ đô la"),
        ("1,000,000", "một triệu"),
        ("1.000.000", "một triệu"),
        ("1.000", "một nghìn"),
        ("3.14", "ba phẩy mười bốn"),
        ("50%", "năm mươi phần trăm"),
        ("50 %", "năm mươi phần trăm"),
        ("50.000%", "năm mươi nghìn phần trăm"),
    ],
)
def test_numbers_and_currency(raw: str, expected: str) -> None:
    assert NORMALIZER.normalize(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("GS. Nguyễn", "giáo sư Nguyễn"),
        ("TS. Trần", "tiến sĩ Trần"),
        ("TP. Hà Nội", "thành phố Hà Nội"),
        ("Q. Ba Đình", "quận Ba Đình"),
    ],
)
def test_abbreviations(raw: str, expected: str) -> None:
    assert NORMALIZER.normalize(raw) == expected


def test_single_initial_preserved() -> None:
    assert NORMALIZER.normalize("P.") == "P."


def test_dotted_name_preserved() -> None:
    assert NORMALIZER.normalize("Roslet.James.P") == "Roslet.James.P"


def test_compound_abbreviation_still_expands() -> None:
    assert NORMALIZER.normalize("TP.HCM") == "Thành phố Hồ Chí Minh"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Anh ấy nói—rồi im.", "Anh ấy nói, rồi im."),
        ("Chờ…", "Chờ."),
        ("***", ". . ."),
    ],
)
def test_symbols(raw: str, expected: str) -> None:
    assert NORMALIZER.normalize(raw).strip() == expected


def test_chapter2_sentence() -> None:
    raw = (
        "cái đầu của bất kỳ hậu duệ nào còn sống sót "
        "với cái giá 30 nghìn tỷ đô."
    )
    expected = (
        "cái đầu của bất kỳ hậu duệ nào còn sống sót "
        "với cái giá ba mươi nghìn tỷ đô la."
    )
    assert NORMALIZER.normalize(raw) == expected


def test_backend_fallback_to_builtin() -> None:
    normalizer = VietnameseTextNormalizer(backend="backend_khong_ton_tai")
    assert normalizer.backend == "builtin"
    assert normalizer.normalize("50%") == "năm mươi phần trăm"


def test_normalize_numbers_keeps_identifiers() -> None:
    assert normalize_numbers("Mã A12 và 7") == "Mã A12 và bảy"


def test_pronunciation_names() -> None:
    pron = PronunciationDict(str(DICT_PATH))
    assert pron.apply("Rosselt và Teident") == "Rốt-sen và Tay-đen"


def test_pronunciation_word_boundary() -> None:
    pron = PronunciationDict(str(DICT_PATH))
    assert pron.apply("Rosseltian") == "Rosseltian"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AMOS", "A-mốt"),
        ("amos", "A-mốt"),
        ("Amos", "A-mốt"),
    ],
)
def test_pronunciation_case_insensitive(raw: str, expected: str) -> None:
    pron = PronunciationDict(str(DICT_PATH))
    assert pron.apply(raw) == expected


def test_pronunciation_multiword_and_dotted() -> None:
    pron = PronunciationDict(str(DICT_PATH))
    assert pron.apply("Vực Thẳm Ấn") == "Vực Thẳm Ấn"
    assert pron.apply("Roslet.James.P") == "Rốt-lét Giêm-sờ Pê"


def test_normalize_before_pronunciation() -> None:
    pron = PronunciationDict(str(DICT_PATH))
    text = pron.apply(NORMALIZER.normalize("Rosselt có 30 nghìn tỷ đô."))
    assert text == "Rốt-sen có ba mươi nghìn tỷ đô la."


def test_missing_dictionary_is_non_fatal(tmp_path: Path) -> None:
    pron = PronunciationDict(str(tmp_path / "missing.json"))
    assert pron.is_loaded is False
    assert pron.apply("Rosselt") == "Rosselt"


def test_critical_words_skip_pronounced_replacements() -> None:
    from text_processing.critical_words import missing_critical_words

    assert missing_critical_words(
        "Rốt-sen nói", "rốt sen nói", ["Rosselt"]
    ) == []
    assert missing_critical_words("Amos nói", "nói", ["Amos"]) == ["Amos"]
