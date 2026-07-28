"""Script analyzer orchestrator.

Coordinates the full text analysis pipeline:
text → normalize → parse lines → detect characters → generate segments.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Tuple

from models.segment import Segment, SegmentType
from models.character import Character
from text_processing.normalizer import normalize_text
from text_processing.sentence_splitter import split_into_sentences
from text_processing.dialogue_parser import (
    LineType,
    ParsedLine,
    parse_text_block,
)
from text_processing.character_detector import CharacterDetector
from utils.logging_config import get_logger

logger = get_logger("text_processing.script_analyzer")

# Mapping from LineType to SegmentType
_LINE_TO_SEGMENT: Dict[LineType, SegmentType] = {
    LineType.NARRATION: SegmentType.NARRATION,
    LineType.DIALOGUE: SegmentType.DIALOGUE,
    LineType.INNER_THOUGHT: SegmentType.INNER_THOUGHT,
    LineType.CHAPTER_TITLE: SegmentType.CHAPTER_TITLE,
    LineType.SCENE_BREAK: SegmentType.SCENE_BREAK,
}

# Pause durations by segment type (ms)
_DEFAULT_PAUSES: Dict[SegmentType, int] = {
    SegmentType.NARRATION: 500,
    SegmentType.DIALOGUE: 400,
    SegmentType.INNER_THOUGHT: 600,
    SegmentType.CHAPTER_TITLE: 2000,
    SegmentType.SCENE_BREAK: 1500,
    SegmentType.SOUND_EFFECT_PLACEHOLDER: 300,
}


def analyze_script(
    text: str,
    max_segment_length: int = 500,
) -> Tuple[List[Segment], Dict[str, Character]]:
    """Analyze a chapter text and produce a list of audio segments.

    Pipeline:
    1. Parse text into classified lines (dialogue, narration, etc.)
    2. Detect and register characters
    3. Split long narration into sub-sentences
    4. Generate Segment objects with appropriate metadata

    Args:
        text: Raw chapter text content.
        max_segment_length: Maximum text length per segment for TTS.

    Returns:
        Tuple of (segments list, characters dict).
    """
    logger.info("Starting script analysis (%d chars)", len(text))

    if not text or not text.strip():
        logger.warning("Empty text provided for analysis")
        return [], {"narrator": Character.create_narrator()}

    # Step 1: Parse lines
    parsed_lines = parse_text_block(text)
    logger.info("Parsed %d lines", len(parsed_lines))

    # Step 2: Detect characters
    detector = CharacterDetector()
    parsed_lines = detector.process_lines(parsed_lines)
    characters = detector.characters

    # Step 3: Generate segments
    segments = _generate_segments(parsed_lines, max_segment_length)

    logger.info(
        "Analysis complete: %d segments, %d characters",
        len(segments), len(characters),
    )

    return segments, characters


def _generate_segments(
    parsed_lines: List[ParsedLine],
    max_segment_length: int,
) -> List[Segment]:
    """Convert parsed lines into Segment objects.

    Handles:
    - Merging consecutive same-type narration paragraphs
    - Splitting long narration into sentences
    - Assigning appropriate pauses
    - Filtering empty/silent segments

    Args:
        parsed_lines: Classified lines from the parser.
        max_segment_length: Max text length per segment.

    Returns:
        List of Segment objects ready for TTS.
    """
    segments: List[Segment] = []
    segment_id = 0

    # Buffer for consecutive narration lines
    narration_buffer: List[str] = []

    def flush_narration() -> None:
        """Flush accumulated narration into segments."""
        nonlocal segment_id
        if not narration_buffer:
            return

        full_text = " ".join(narration_buffer)
        narration_buffer.clear()

        # Split into sentences for TTS
        sentences = split_into_sentences(full_text, max_length=max_segment_length)

        for sentence in sentences:
            segment_id += 1
            segments.append(Segment(
                segment_id=segment_id,
                type=SegmentType.NARRATION,
                speaker="narrator",
                text=sentence,
                emotion="neutral",
                voice_id="narrator_male_01",
                speed=1.0,
                pause_after_ms=_DEFAULT_PAUSES[SegmentType.NARRATION],
            ))

    for line in parsed_lines:
        if line.line_type == LineType.EMPTY:
            # Empty lines might separate paragraphs
            continue

        if line.line_type == LineType.NARRATION:
            narration_buffer.append(line.text)
            continue

        # Flush any buffered narration before non-narration segments
        flush_narration()

        if line.line_type == LineType.SCENE_BREAK:
            segment_id += 1
            segments.append(Segment(
                segment_id=segment_id,
                type=SegmentType.SCENE_BREAK,
                speaker="",
                text="",
                pause_after_ms=_DEFAULT_PAUSES[SegmentType.SCENE_BREAK],
            ))
            continue

        if line.line_type == LineType.CHAPTER_TITLE:
            segment_id += 1
            segments.append(Segment(
                segment_id=segment_id,
                type=SegmentType.CHAPTER_TITLE,
                speaker="narrator",
                text=line.text,
                voice_id="narrator_male_01",
                speed=0.9,
                pause_after_ms=_DEFAULT_PAUSES[SegmentType.CHAPTER_TITLE],
            ))
            continue

        if line.line_type == LineType.DIALOGUE:
            # Split dialogue if too long
            dialogue_parts = split_into_sentences(
                line.text, max_length=max_segment_length,
            )
            if line.attribution and dialogue_parts:
                dialogue_parts[-1] = f"{dialogue_parts[-1]} {line.attribution}".strip()
            speaker = line.speaker or "narrator"

            for part in dialogue_parts:
                segment_id += 1
                segments.append(Segment(
                    segment_id=segment_id,
                    type=SegmentType.DIALOGUE,
                    speaker=speaker,
                    text=part,
                    emotion=_detect_emotion(part),
                    voice_id="",  # Will be assigned during voice casting
                    pause_after_ms=_DEFAULT_PAUSES[SegmentType.DIALOGUE],
                ))
            continue

        if line.line_type == LineType.INNER_THOUGHT:
            segment_id += 1
            segments.append(Segment(
                segment_id=segment_id,
                type=SegmentType.INNER_THOUGHT,
                speaker=line.speaker or "narrator",
                text=line.text,
                emotion="contemplative",
                voice_id="",
                speed=0.95,
                pause_after_ms=_DEFAULT_PAUSES[SegmentType.INNER_THOUGHT],
            ))
            continue

    # Flush remaining narration
    flush_narration()

    # Attribution and inner-thought lines can bypass the narration buffer.
    # Enforce the TTS limit globally so a novel-length input never sends an
    # oversized request to the model.
    bounded: List[Segment] = []
    for segment in segments:
        parts = (
            split_into_sentences(segment.text, max_length=max_segment_length)
            if not segment.is_silent and len(segment.text) > max_segment_length
            else [segment.text]
        )
        for part_index, part in enumerate(parts):
            bounded.append(replace(
                segment,
                segment_id=len(bounded) + 1,
                text=part,
                pause_after_ms=segment.pause_after_ms if part_index == len(parts) - 1 else 200,
            ))

    return bounded


def _detect_emotion(text: str) -> str:
    """Simple emotion detection from text cues.

    Args:
        text: Dialogue or narration text.

    Returns:
        Emotion label string.
    """
    text_lower = text.lower()

    if text.endswith("!") or text.endswith("?!"):
        if any(w in text_lower for w in ["không", "đừng", "thôi", "dừng"]):
            return "urgent"
        return "excited"

    if text.endswith("?"):
        return "questioning"

    if text.endswith("..."):
        return "hesitant"

    if any(w in text_lower for w in ["buồn", "khóc", "nước mắt", "đau"]):
        return "sad"

    if any(w in text_lower for w in ["tức", "giận", "căm", "hận", "quát"]):
        return "angry"

    if any(w in text_lower for w in ["sợ", "run", "kinh", "hoảng"]):
        return "fearful"

    if any(w in text_lower for w in ["cười", "vui", "hạnh phúc", "thích"]):
        return "happy"

    if any(w in text_lower for w in ["thì thầm", "nhỏ giọng", "khẽ"]):
        return "whisper"

    return "neutral"
