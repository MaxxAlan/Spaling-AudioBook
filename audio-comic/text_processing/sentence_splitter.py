"""Sentence splitting for Vietnamese text.

Splits text into sentences suitable for TTS processing, respecting
Vietnamese punctuation rules, proper names, and TTS segment length limits.
"""

from __future__ import annotations

import re
from typing import List

from utils.logging_config import get_logger

logger = get_logger("text_processing.sentence_splitter")

# Common Vietnamese abbreviations that end with a period but aren't sentence endings
_NON_SENTENCE_ENDINGS = {
    "TP.", "GS.", "PGS.", "TS.", "ThS.", "CN.", "BS.", "KTS.",
    "Tr.", "Q.", "P.", "TT.", "Tp.", "Mr.", "Mrs.", "Ms.", "Dr.",
    "Prof.", "Jr.", "Sr.", "vs.", "etc.", "St.",
}

# Maximum segment length for TTS (characters)
DEFAULT_MAX_SEGMENT_LENGTH = 500
DEFAULT_MIN_SEGMENT_LENGTH = 10


def split_into_sentences(
    text: str,
    max_length: int = DEFAULT_MAX_SEGMENT_LENGTH,
    min_length: int = DEFAULT_MIN_SEGMENT_LENGTH,
) -> List[str]:
    """Split text into sentences for TTS processing.

    Rules:
    - Split on sentence-ending punctuation (. ! ? ;)
    - Don't split on abbreviation periods
    - Don't split on ellipsis (...)
    - Merge very short sentences with neighbors
    - Split very long sentences at clause boundaries

    Args:
        text: Input text block.
        max_length: Maximum characters per sentence.
        min_length: Minimum characters per sentence.

    Returns:
        List of sentence strings.
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # Split on sentence boundaries
    raw_sentences = _split_on_punctuation(text)

    # Merge very short fragments
    merged = _merge_short_fragments(raw_sentences, min_length)

    # Split overly long sentences
    final: List[str] = []
    for sentence in merged:
        if len(sentence) > max_length:
            final.extend(_split_long_sentence(sentence, max_length))
        else:
            final.append(sentence)

    # Final cleanup
    result = [s.strip() for s in final if s.strip()]
    logger.debug("Split text into %d sentences", len(result))
    return result


def _split_on_punctuation(text: str) -> List[str]:
    """Split text on sentence-ending punctuation.

    Handles:
    - Period, exclamation, question mark
    - Ellipsis (treated as sentence ender)
    - Semicolons
    - Preserves the punctuation with the sentence

    Args:
        text: Input text.

    Returns:
        List of raw sentence fragments.
    """
    sentences: List[str] = []
    current = ""

    i = 0
    while i < len(text):
        char = text[i]
        current += char

        # Check for ellipsis
        if char == "." and text[i:i+3] == "...":
            current += ".."
            i += 3
            # This ends a sentence if followed by space/newline or end
            if i >= len(text) or text[i] in (" ", "\n", "\t"):
                sentences.append(current.strip())
                current = ""
            continue

        # Check for sentence-ending punctuation
        if char in ".!?":
            # Check if this period is part of an abbreviation
            if char == ".":
                word_before = _get_word_before_period(current)
                if word_before and word_before + "." in _NON_SENTENCE_ENDINGS:
                    i += 1
                    continue

            # Look ahead: end sentence if followed by space+uppercase, newline, or end
            next_i = i + 1
            while next_i < len(text) and text[next_i] == " ":
                next_i += 1

            if next_i >= len(text) or text[next_i] == "\n":
                sentences.append(current.strip())
                current = ""
            elif text[next_i].isupper() or text[next_i] in ('"', "'", "—", "–", "-"):
                sentences.append(current.strip())
                current = ""

        elif char == ";":
            sentences.append(current.strip())
            current = ""

        elif char == "\n":
            if current.strip():
                sentences.append(current.strip())
                current = ""

        i += 1

    if current.strip():
        sentences.append(current.strip())

    return sentences


def _get_word_before_period(text: str) -> str:
    """Extract the word immediately before the last period in text."""
    text = text.rstrip(".")
    words = text.split()
    if words:
        return words[-1]
    return ""


def _merge_short_fragments(
    sentences: List[str],
    min_length: int,
) -> List[str]:
    """Merge very short sentence fragments with neighbors.

    Args:
        sentences: List of sentence fragments.
        min_length: Minimum acceptable length.

    Returns:
        List with short fragments merged.
    """
    if not sentences:
        return []

    merged: List[str] = []
    buffer = ""

    for sentence in sentences:
        if not sentence.strip():
            continue

        if buffer:
            combined = buffer + " " + sentence
            if len(sentence) >= min_length:
                # Sentence is long enough, flush buffer first
                merged.append(buffer)
                buffer = sentence if len(sentence) < min_length else ""
                if not buffer:
                    merged.append(sentence)
            else:
                # Both are short, combine
                buffer = combined
        else:
            if len(sentence) < min_length:
                buffer = sentence
            else:
                merged.append(sentence)

    if buffer:
        if merged:
            merged[-1] = merged[-1] + " " + buffer
        else:
            merged.append(buffer)

    return merged


def _split_long_sentence(
    sentence: str,
    max_length: int,
) -> List[str]:
    """Split an overly long sentence at clause boundaries.

    Split priority:
    1. Comma followed by space
    2. Conjunction words (và, nhưng, mà, vì, nên, hay, hoặc)
    3. Force split at max_length boundary on word boundary

    Args:
        sentence: Long sentence to split.
        max_length: Maximum length per part.

    Returns:
        List of sentence parts.
    """
    if len(sentence) <= max_length:
        return [sentence]

    parts: List[str] = []

    # Try splitting on commas first
    comma_parts = re.split(r",\s+", sentence)
    if len(comma_parts) > 1:
        current = ""
        for part in comma_parts:
            test = (current + ", " + part).strip(", ") if current else part
            if len(test) <= max_length:
                current = test
            else:
                if current:
                    parts.append(current)
                current = part
        if current:
            parts.append(current)

        # Recursively split any still-too-long parts
        final: List[str] = []
        for part in parts:
            if len(part) > max_length:
                final.extend(_force_split(part, max_length))
            else:
                final.append(part)
        return final

    # Force split on word boundaries
    return _force_split(sentence, max_length)


def _force_split(text: str, max_length: int) -> List[str]:
    """Force split text on word boundaries.

    Args:
        text: Text to split.
        max_length: Maximum length per part.

    Returns:
        List of text parts.
    """
    words = text.split()
    parts: List[str] = []
    current = ""

    for word in words:
        test = (current + " " + word).strip() if current else word
        if len(test) <= max_length:
            current = test
        else:
            if current:
                parts.append(current)
            current = word

    if current:
        parts.append(current)

    return parts
