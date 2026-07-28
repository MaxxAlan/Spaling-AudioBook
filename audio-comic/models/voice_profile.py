"""Voice profile data model for managing voice assignments across stories."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Optional


@dataclass
class VoiceAssignment:
    """A single voice assignment for a character.

    Attributes:
        voice_id: Voice profile ID.
        speed: Speech speed multiplier.
        pitch: Pitch adjustment.
        volume: Volume multiplier.
        emotion: Default emotion.
        reference_audio: Path to reference audio for voice cloning (VieNeu).
    """

    voice_id: str = "narrator_male_01"
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    emotion: str = "neutral"
    reference_audio: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> VoiceAssignment:
        """Deserialize from dictionary."""
        return cls(**data)


@dataclass
class VoiceProfile:
    """Voice profile for an entire story, mapping characters to voice assignments.

    Attributes:
        story_name: Name of the story.
        characters: Mapping of character name to voice assignment.
        description: Optional description of this voice profile.
    """

    story_name: str = ""
    characters: Dict[str, VoiceAssignment] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON export."""
        return {
            "story_name": self.story_name,
            "description": self.description,
            "characters": {
                name: assignment.to_dict()
                for name, assignment in self.characters.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> VoiceProfile:
        """Deserialize from dictionary."""
        characters = {}
        for name, assignment_data in data.get("characters", {}).items():
            characters[name] = VoiceAssignment.from_dict(assignment_data)
        return cls(
            story_name=data.get("story_name", ""),
            characters=characters,
            description=data.get("description", ""),
        )

    def get_voice(self, character_name: str) -> Optional[VoiceAssignment]:
        """Get voice assignment for a character."""
        return self.characters.get(character_name)

    def set_voice(self, character_name: str, assignment: VoiceAssignment) -> None:
        """Set or update voice assignment for a character."""
        self.characters[character_name] = assignment


class VoiceProfileStore:
    """Manages saving and loading voice profiles from disk.

    Allows reuse of voice configurations across chapters of the same story.
    """

    def __init__(self, profiles_dir: Path) -> None:
        """Initialize the profile store.

        Args:
            profiles_dir: Directory where voice profile JSON files are stored.
        """
        self._profiles_dir = profiles_dir
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

    def save(self, profile: VoiceProfile, filename: Optional[str] = None) -> Path:
        """Save a voice profile to disk.

        Args:
            profile: The voice profile to save.
            filename: Optional filename override. Defaults to slugified story name.

        Returns:
            Path to the saved JSON file.
        """
        if filename is None:
            slug = profile.story_name.lower().replace(" ", "_")
            slug = "".join(c for c in slug if c.isalnum() or c == "_")
            filename = f"{slug}_voices.json"

        filepath = self._profiles_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
        return filepath

    def load(self, filepath: Path) -> VoiceProfile:
        """Load a voice profile from a JSON file.

        Args:
            filepath: Path to the JSON file.

        Returns:
            The loaded VoiceProfile.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return VoiceProfile.from_dict(data)

    def list_profiles(self) -> list[Path]:
        """List all voice profile files in the store directory."""
        return sorted(self._profiles_dir.glob("*_voices.json"))

    def export_profile(self, profile: VoiceProfile, export_path: Path) -> Path:
        """Export a voice profile to a specified path (for sharing).

        Args:
            profile: The voice profile to export.
            export_path: Destination file path.

        Returns:
            Path to the exported file.
        """
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
        return export_path

    def import_profile(self, import_path: Path) -> VoiceProfile:
        """Import a voice profile from an external file.

        Args:
            import_path: Source file path.

        Returns:
            The imported VoiceProfile.
        """
        return self.load(import_path)
