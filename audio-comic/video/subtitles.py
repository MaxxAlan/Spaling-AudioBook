"""Vietnamese SRT generation from timed narration segments."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


def split_caption_text(text: str, max_chars: int = 84) -> list[str]:
    """Split narration into readable one/two-line subtitle cards."""
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    sentences = re.split(r"(?<=[.!?…])\s+", clean)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        words = sentence.split()
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = word
            else:
                current = candidate
        if current and len(current) >= max_chars * 0.55:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def _timestamp(milliseconds: float) -> str:
    value = max(0, int(round(milliseconds)))
    hours, value = divmod(value, 3_600_000)
    minutes, value = divmod(value, 60_000)
    seconds, millis = divmod(value, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def expand_timed_segment(text: str, start_ms: float, end_ms: float) -> list[tuple[float, float, str]]:
    """Distribute caption cards proportionally across one spoken segment."""
    chunks = split_caption_text(text)
    if not chunks or end_ms <= start_ms:
        return []
    weights = [max(1, len(chunk)) for chunk in chunks]
    total = sum(weights)
    cursor = start_ms
    cues: list[tuple[float, float, str]] = []
    for index, (chunk, weight) in enumerate(zip(chunks, weights)):
        finish = end_ms if index == len(chunks) - 1 else cursor + (end_ms - start_ms) * weight / total
        cues.append((cursor, finish, chunk))
        cursor = finish
    return cues


def write_srt(timed_segments: Iterable[tuple[str, float, float]], output_path: str) -> str:
    """Write UTF-8 Vietnamese subtitles and return the absolute path."""
    cues: list[tuple[float, float, str]] = []
    for text, start_ms, end_ms in timed_segments:
        cues.extend(expand_timed_segment(text, start_ms, end_ms))
    return write_srt_cues(cues, output_path)


def write_srt_cues(
    cues: Iterable[tuple[float, float, str]], output_path: str
) -> str:
    """Write already-sized ``(start_ms, end_ms, text)`` cues without re-splitting."""
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, (start_ms, end_ms, text) in enumerate(cues, 1):
        lines.extend([str(index), f"{_timestamp(start_ms)} --> {_timestamp(end_ms)}", text, ""])
    output.write_text("\n".join(lines), encoding="utf-8")
    return str(output)
