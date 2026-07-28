"""Encoding helpers for Vietnamese text input."""

from __future__ import annotations

import re
from pathlib import Path

from utils.logging_config import get_logger

logger = get_logger("utils.encoding")


def detect_encoding(filepath: Path) -> str:
    """Detect a useful text encoding without silently losing characters."""
    raw = filepath.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    try:
        import chardet

        result = chardet.detect(raw)
        if result.get("encoding"):
            return str(result["encoding"])
    except ImportError:
        logger.warning("chardet is unavailable; trying Vietnamese legacy encodings")

    for encoding in ("cp1258", "cp1252", "latin-1"):
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def read_text_file(filepath: Path) -> str:
    """Read and clean a TXT file, including UTF-8 BOM and legacy files."""
    filepath = Path(filepath)
    if not filepath.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp TXT: {filepath}")
    encoding = detect_encoding(filepath)
    logger.info("Reading file %s with encoding %s", filepath.name, encoding)
    return clean_text(filepath.read_text(encoding=encoding, errors="replace"))


def clean_text(text: str) -> str:
    """Clean control characters, line endings, quotes, and blank lines."""
    text = "".join(
        char for char in text
        if char in ("\n", "\r", "\t") or ord(char) >= 32
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = normalize_quotes(fix_vietnamese_encoding(text))

    cleaned_lines: list[str] = []
    blank_count = 0
    for line in (line.rstrip() for line in text.split("\n")):
        if line.strip():
            blank_count = 0
            cleaned_lines.append(line)
        else:
            blank_count += 1
            if blank_count <= 2:
                cleaned_lines.append("")
    return "\n".join(cleaned_lines).strip()


def normalize_quotes(text: str) -> str:
    """Normalize curly and CJK quotation marks."""
    replacements = {
        "\u201c": '"', "\u201d": '"', "\u00ab": '"', "\u00bb": '"',
        "\u300c": '"', "\u300d": '"', "\u2018": "'", "\u2019": "'",
    }
    for source, destination in replacements.items():
        text = text.replace(source, destination)
    return text


def fix_vietnamese_encoding(text: str) -> str:
    """Repair the common UTF-8-as-Windows-1252 mojibake failure."""
    markers = ("Ã", "Â", "Ä", "Æ", "áº", "á»")
    if not any(marker in text for marker in markers):
        return text

    for legacy_encoding in ("cp1252", "latin-1"):
        try:
            repaired = text.encode(legacy_encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        before = sum(text.count(marker) for marker in markers)
        after = sum(repaired.count(marker) for marker in markers)
        if after < before:
            return repaired
    return text


def normalize_whitespace(text: str) -> str:
    """Collapse horizontal whitespace while preserving newlines."""
    return re.sub(r"[^\S\n]+", " ", text).strip()
