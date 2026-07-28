"""Dialogue parser for Vietnamese fiction text.

Identifies dialogue lines using various Vietnamese conventions:
- Em dash (—, –) at line start
- Hyphen (-) at line start
- Quoted speech ("..." or "...")
- Speaker:dialogue pattern (Tên: "lời thoại")
- Inner thoughts (commonly marked with italics or *)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from utils.logging_config import get_logger

logger = get_logger("text_processing.dialogue_parser")


class LineType(Enum):
    """Classification of a text line."""
    NARRATION = "narration"
    DIALOGUE = "dialogue"
    INNER_THOUGHT = "inner_thought"
    SCENE_BREAK = "scene_break"
    CHAPTER_TITLE = "chapter_title"
    EMPTY = "empty"


@dataclass
class ParsedLine:
    """A parsed line of text with classification metadata.

    Attributes:
        text: The cleaned text content.
        line_type: Classification of this line.
        speaker: Detected speaker name, if any.
        attribution: Narration surrounding the dialogue (e.g., "Minh hỏi").
        original: The original raw text before processing.
    """
    text: str
    line_type: LineType
    speaker: Optional[str] = None
    attribution: Optional[str] = None
    original: str = ""


# Patterns for dialogue detection
# Em dash dialogue: — Lời thoại
_EMDASH_PATTERN = re.compile(
    r"^[\s]*[—–\-]\s*(.+)$"
)

# Quoted dialogue: "Lời thoại" or "Lời thoại"
_QUOTED_PATTERN = re.compile(
    r'^[\s]*["\u201c](.+?)["\u201d][\s]*(.*)$'
)

# Speaker:dialogue — Minh: "Xin chào"
_SPEAKER_QUOTED_PATTERN = re.compile(
    r'^[\s]*([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+)*)\s*:\s*["\u201c](.+?)["\u201d][\s]*(.*)$'
)

# Speaker:dialogue without quotes — Minh: Xin chào
_SPEAKER_UNQUOTED_PATTERN = re.compile(
    r'^[\s]*([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+)*)\s*:\s*(.+)$'
)

# Em dash dialogue with speaker attribution: — Lời thoại — Minh nói.
_EMDASH_ATTRIBUTED_PATTERN = re.compile(
    r'^[\s]*[—–\-]\s*(.+?)\s*[—–\-]\s*([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[a-zà-ỹ]+)*\s*(?:nói|hỏi|trả lời|thì thầm|gào|la|hét|cười|kêu|gọi|đáp|thốt|than|kể|bảo|quát|rên|rít|thở dài|gật đầu)\.?)[\s]*$'
)

# Inner thought markers: *suy nghĩ* or (suy nghĩ)
_THOUGHT_PATTERN = re.compile(
    r'^[\s]*\*(.+?)\*[\s]*$'
)
_THOUGHT_PAREN_PATTERN = re.compile(
    r'^[\s]*\((.+?)\)[\s]*$'
)

# Scene break patterns: ***, ----, ===, ~~~
_SCENE_BREAK_PATTERN = re.compile(
    r'^[\s]*(?:[*]{3,}|[-]{3,}|[=]{3,}|[~]{3,}|[#]{3,})[\s]*$'
)

# Chapter title patterns
_CHAPTER_TITLE_PATTERN = re.compile(
    r'^[\s]*(?:Chương|CHƯƠNG|chương)\s+(\d+)\s*[:.]\s*(.+)$'
)
_CHAPTER_TITLE_SIMPLE = re.compile(
    r'^[\s]*(?:Chương|CHƯƠNG|chương)\s+(\d+)[\s]*$'
)


def parse_line(line: str) -> ParsedLine:
    """Parse a single line of text and classify it.

    Detection priority:
    1. Empty / whitespace-only → EMPTY
    2. Scene break markers → SCENE_BREAK
    3. Chapter title → CHAPTER_TITLE
    4. Speaker: "dialogue" → DIALOGUE with speaker
    5. Speaker: dialogue → DIALOGUE with speaker
    6. Em dash with attribution → DIALOGUE with speaker from attribution
    7. Em dash dialogue → DIALOGUE
    8. Quoted dialogue → DIALOGUE
    9. Inner thought (*text*) → INNER_THOUGHT
    10. Everything else → NARRATION

    Args:
        line: A single line of raw text.

    Returns:
        ParsedLine with classification and extracted metadata.
    """
    stripped = line.strip()

    # Empty line
    if not stripped:
        return ParsedLine(text="", line_type=LineType.EMPTY, original=line)

    # Scene break
    if _SCENE_BREAK_PATTERN.match(stripped):
        return ParsedLine(
            text="", line_type=LineType.SCENE_BREAK, original=line,
        )

    # Chapter title with subtitle
    m = _CHAPTER_TITLE_PATTERN.match(stripped)
    if m:
        title_text = f"Chương {m.group(1)}: {m.group(2).strip()}"
        return ParsedLine(
            text=title_text, line_type=LineType.CHAPTER_TITLE, original=line,
        )

    # Chapter title simple
    m = _CHAPTER_TITLE_SIMPLE.match(stripped)
    if m:
        return ParsedLine(
            text=f"Chương {m.group(1)}", line_type=LineType.CHAPTER_TITLE, original=line,
        )

    # Speaker: "dialogue" pattern
    m = _SPEAKER_QUOTED_PATTERN.match(stripped)
    if m:
        speaker = m.group(1).strip()
        dialogue = m.group(2).strip()
        attribution = m.group(3).strip() if m.group(3) else None
        return ParsedLine(
            text=dialogue,
            line_type=LineType.DIALOGUE,
            speaker=speaker,
            attribution=attribution,
            original=line,
        )

    # Speaker: unquoted dialogue
    m = _SPEAKER_UNQUOTED_PATTERN.match(stripped)
    if m:
        speaker = m.group(1).strip()
        dialogue = m.group(2).strip()
        return ParsedLine(
            text=dialogue,
            line_type=LineType.DIALOGUE,
            speaker=speaker,
            original=line,
        )

    # Em dash with attribution: — Lời thoại — Minh nói.
    m = _EMDASH_ATTRIBUTED_PATTERN.match(stripped)
    if m:
        dialogue = m.group(1).strip()
        attr_text = m.group(2).strip()
        speaker = _extract_speaker_from_attribution(attr_text)
        return ParsedLine(
            text=dialogue,
            line_type=LineType.DIALOGUE,
            speaker=speaker,
            attribution=attr_text,
            original=line,
        )

    # Em dash dialogue
    m = _EMDASH_PATTERN.match(stripped)
    if m:
        dialogue = m.group(1).strip()
        # Check if there's an inline attribution
        speaker, clean_text, attribution = _extract_inline_attribution(dialogue)
        return ParsedLine(
            text=clean_text,
            line_type=LineType.DIALOGUE,
            speaker=speaker,
            attribution=attribution,
            original=line,
        )

    # Quoted dialogue "..."
    m = _QUOTED_PATTERN.match(stripped)
    if m:
        dialogue = m.group(1).strip()
        after_quote = m.group(2).strip() if m.group(2) else ""
        speaker = None
        attribution = None
        if after_quote:
            speaker = _extract_speaker_from_attribution(after_quote)
            attribution = after_quote
        return ParsedLine(
            text=dialogue,
            line_type=LineType.DIALOGUE,
            speaker=speaker,
            attribution=attribution,
            original=line,
        )

    # Inner thought *text*
    m = _THOUGHT_PATTERN.match(stripped)
    if m:
        return ParsedLine(
            text=m.group(1).strip(),
            line_type=LineType.INNER_THOUGHT,
            original=line,
        )

    m = _THOUGHT_PAREN_PATTERN.match(stripped)
    if m:
        thought = m.group(1).strip()
        # Only treat as thought if it's not too short (avoid matching "(1)" etc.)
        if len(thought) > 5:
            return ParsedLine(
                text=thought,
                line_type=LineType.INNER_THOUGHT,
                original=line,
            )

    # Default: narration
    return ParsedLine(
        text=stripped, line_type=LineType.NARRATION, original=line,
    )


def _extract_speaker_from_attribution(attribution: str) -> Optional[str]:
    """Extract speaker name from attribution text like 'Minh nói' or 'hắn hỏi'.

    Args:
        attribution: Attribution text after dialogue.

    Returns:
        Extracted speaker name or None.
    """
    if not attribution:
        return None

    # Pattern: Name + verb
    m = re.match(
        r'([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+)*)',
        attribution,
    )
    if m:
        return m.group(1).strip()

    return None


def _extract_inline_attribution(
    text: str,
) -> Tuple[Optional[str], str, Optional[str]]:
    """Extract inline attribution from dialogue text.

    Handles patterns like:
    - "Lời thoại, — Minh nói."
    - "Lời thoại — Minh hỏi — rồi bỏ đi."

    Args:
        text: Dialogue text potentially containing attribution.

    Returns:
        Tuple of (speaker, clean_dialogue, attribution).
    """
    # Look for attribution pattern at end: ... — Name verb.
    m = re.search(
        r'(.*?)\s*[—–\-]\s*([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[a-zà-ỹ]+)*'
        r'\s*(?:nói|hỏi|trả lời|thì thầm|gào|la|hét|cười|kêu|gọi|đáp|thốt|than|kể|bảo|quát|rên|rít|thở dài)\.?)$',
        text,
    )
    if m:
        dialogue = m.group(1).strip()
        attribution = m.group(2).strip()
        speaker = _extract_speaker_from_attribution(attribution)
        return speaker, dialogue, attribution

    return None, text, None


def parse_text_block(text: str) -> List[ParsedLine]:
    """Parse a multi-line text block into classified lines.

    Args:
        text: Multi-line text content.

    Returns:
        List of ParsedLine objects.
    """
    lines = text.split("\n")
    parsed = [parse_line(line) for line in lines]

    # Filter out empty lines at start and end, keep internal ones for context
    while parsed and parsed[0].line_type == LineType.EMPTY:
        parsed.pop(0)
    while parsed and parsed[-1].line_type == LineType.EMPTY:
        parsed.pop()

    logger.info("Parsed %d lines from text block", len(parsed))
    return parsed
