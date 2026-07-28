"""Segment data model for script analysis output."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Optional


class SegmentType(enum.Enum):
    """Types of text segments in a chapter script."""

    NARRATION = "narration"
    DIALOGUE = "dialogue"
    INNER_THOUGHT = "inner_thought"
    CHAPTER_TITLE = "chapter_title"
    SCENE_BREAK = "scene_break"
    SOUND_EFFECT_PLACEHOLDER = "sound_effect_placeholder"


@dataclass
class Segment:
    """A single segment of the analyzed chapter script.

    Each segment represents one atomic unit of the audio-comic:
    a narration block, a line of dialogue, a scene break, etc.

    Attributes:
        segment_id: Sequential ID (1-based).
        type: The segment type (narration, dialogue, etc.).
        speaker: Speaker identifier (e.g., 'narrator', character name).
        text: The actual text content.
        emotion: Emotional tone for TTS rendering.
        voice_id: Assigned voice profile ID.
        speed: Playback speed multiplier (1.0 = normal).
        pitch: Pitch adjustment (-1.0 to 1.0).
        pause_after_ms: Silence duration after this segment in ms.
        volume: Volume multiplier (0.0 to 2.0).
        cached: Whether a cached audio file exists for this segment.
        cache_key: SHA256 hash used as cache key.
        audio_path: Path to the generated audio file, if any.
        error: Error message if TTS failed for this segment.
        reading_instruction: Human/AI generated direction used to derive TTS controls.
    """

    segment_id: int
    type: SegmentType
    speaker: str = "narrator"
    text: str = ""
    emotion: str = "neutral"
    voice_id: str = "narrator_male_01"
    speed: float = 1.0
    pitch: float = 0.0
    pause_after_ms: int = 500
    volume: float = 1.0
    cached: bool = False
    cache_key: str = ""
    audio_path: Optional[str] = None
    error: Optional[str] = None
    reading_instruction: str = ""
    inference_options: dict = field(default_factory=dict)
    attempt_history: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON export."""
        data = asdict(self)
        data["type"] = self.type.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Segment:
        """Deserialize from dictionary."""
        data = dict(data)  # shallow copy
        data["type"] = SegmentType(data["type"])
        return cls(**data)

    @property
    def is_silent(self) -> bool:
        """Check if this segment type produces no speech audio."""
        return self.type in (SegmentType.SCENE_BREAK, SegmentType.SOUND_EFFECT_PLACEHOLDER)

    @property
    def display_type(self) -> str:
        """Human-readable type name in Vietnamese."""
        type_names = {
            SegmentType.NARRATION: "Dẫn truyện",
            SegmentType.DIALOGUE: "Hội thoại",
            SegmentType.INNER_THOUGHT: "Suy nghĩ",
            SegmentType.CHAPTER_TITLE: "Tiêu đề",
            SegmentType.SCENE_BREAK: "Chuyển cảnh",
            SegmentType.SOUND_EFFECT_PLACEHOLDER: "Hiệu ứng âm",
        }
        return type_names.get(self.type, self.type.value)
