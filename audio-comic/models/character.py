"""Character data model for voice casting management."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Character:
    """A character detected in the chapter script.

    Attributes:
        name: Character name (e.g., 'Minh', 'narrator', 'unknown_character_01').
        gender: Voice gender assignment ('male', 'female', 'neutral').
        voice_id: Assigned voice profile ID from voice_profiles.
        speed: Speech speed multiplier.
        pitch: Pitch adjustment.
        volume: Volume multiplier.
        default_emotion: Default emotion for this character.
        pause_after_ms: Default pause after this character's lines.
        dialogue_count: How many dialogue segments this character has.
        is_narrator: Whether this character is the narrator.
        display_name: Optional display name override for UI.
    """

    name: str
    gender: str = "male"
    voice_id: str = "narrator_male_01"
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    default_emotion: str = "neutral"
    pause_after_ms: int = 500
    dialogue_count: int = 0
    is_narrator: bool = False
    display_name: Optional[str] = None

    @property
    def label(self) -> str:
        """Display label for the character in UI."""
        return self.display_name or self.name

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON export."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Character:
        """Deserialize from dictionary."""
        return cls(**data)

    @classmethod
    def create_narrator(cls, gender: str = "male") -> Character:
        """Factory method for creating a narrator character."""
        voice_id = f"narrator_{gender}_01"
        return cls(
            name="narrator",
            gender=gender,
            voice_id=voice_id,
            speed=0.95,
            pause_after_ms=500,
            is_narrator=True,
            display_name="Người dẫn truyện",
        )

    @classmethod
    def create_unknown(cls, index: int, gender: str = "male") -> Character:
        """Factory method for unknown characters."""
        return cls(
            name=f"unknown_character_{index:02d}",
            gender=gender,
            voice_id=f"{gender}_young_01",
            display_name=f"Nhân vật chưa xác định {index:02d}",
        )
