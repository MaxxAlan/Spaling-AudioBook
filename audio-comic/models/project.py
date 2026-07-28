"""Project data model representing a single chapter processing job."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from models.segment import Segment
from models.character import Character
from models.voice_profile import VoiceProfile
from models.export_settings import ExportSettings


@dataclass
class Project:
    """Represents a single chapter processing project.

    A project holds all configuration, segments, characters, and paths
    needed to process one chapter from text to final output.

    Attributes:
        story_name: Name of the story/novel.
        chapter_number: Chapter number.
        chapter_title: Title of the chapter.
        language: Content language code (default: 'vi').
        source_text: Raw chapter text content.
        segments: Analyzed script segments.
        characters: Detected characters with voice assignments.
        voice_profile: Voice profile for this project.
        export_settings: Export configuration.
        project_dir: Root directory for this project's files.
        output_dir: Final output directory.
    """

    story_name: str = ""
    chapter_number: int = 1
    chapter_title: str = ""
    language: str = "vi"
    source_text: str = ""
    segments: List[Segment] = field(default_factory=list)
    characters: Dict[str, Character] = field(default_factory=dict)
    voice_profile: VoiceProfile = field(default_factory=VoiceProfile)
    export_settings: ExportSettings = field(default_factory=lambda: ExportSettings())
    project_dir: Optional[str] = None
    output_dir: Optional[str] = None

    @property
    def project_id(self) -> str:
        """Unique project identifier from story slug and chapter number."""
        slug = self.story_slug
        return f"{slug}_chapter_{self.chapter_number:03d}"

    @property
    def story_slug(self) -> str:
        """URL-safe slug from story name."""
        slug = self.story_name.lower().strip()
        # Replace Vietnamese special chars and spaces with hyphens
        replacements = {
            " ": "-", "đ": "d", "Đ": "d",
            "á": "a", "à": "a", "ả": "a", "ã": "a", "ạ": "a",
            "ă": "a", "ắ": "a", "ằ": "a", "ẳ": "a", "ẵ": "a", "ặ": "a",
            "â": "a", "ấ": "a", "ầ": "a", "ẩ": "a", "ẫ": "a", "ậ": "a",
            "é": "e", "è": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
            "ê": "e", "ế": "e", "ề": "e", "ể": "e", "ễ": "e", "ệ": "e",
            "í": "i", "ì": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
            "ó": "o", "ò": "o", "ỏ": "o", "õ": "o", "ọ": "o",
            "ô": "o", "ố": "o", "ồ": "o", "ổ": "o", "ỗ": "o", "ộ": "o",
            "ơ": "o", "ớ": "o", "ờ": "o", "ở": "o", "ỡ": "o", "ợ": "o",
            "ú": "u", "ù": "u", "ủ": "u", "ũ": "u", "ụ": "u",
            "ư": "u", "ứ": "u", "ừ": "u", "ử": "u", "ữ": "u", "ự": "u",
            "ý": "y", "ỳ": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
        }
        for src, dst in replacements.items():
            slug = slug.replace(src, dst)
        # Remove non-alphanumeric except hyphens
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        # Collapse multiple hyphens
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug.strip("-")

    def get_output_filename(self, suffix: str, extension: str) -> str:
        """Generate standardized output filename.

        Args:
            suffix: File purpose suffix (e.g., 'audiocomic', 'poster', 'youtube').
            extension: File extension without dot (e.g., 'wav', 'png', 'mp4').

        Returns:
            Formatted filename string.
        """
        return f"{self.story_slug}_chapter_{self.chapter_number:03d}_{suffix}.{extension}"

    def to_dict(self) -> dict:
        """Serialize project to dictionary for JSON storage."""
        return {
            "story_name": self.story_name,
            "chapter_number": self.chapter_number,
            "chapter_title": self.chapter_title,
            "language": self.language,
            "source_text": self.source_text,
            "segments": [s.to_dict() for s in self.segments],
            "characters": {
                name: char.to_dict()
                for name, char in self.characters.items()
            },
            "voice_profile": self.voice_profile.to_dict(),
            "export_settings": self.export_settings.to_dict(),
            "project_dir": self.project_dir,
            "output_dir": self.output_dir,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Project:
        """Deserialize project from dictionary."""
        segments = [Segment.from_dict(s) for s in data.get("segments", [])]
        characters = {
            name: Character.from_dict(char_data)
            for name, char_data in data.get("characters", {}).items()
        }
        voice_profile = VoiceProfile.from_dict(data.get("voice_profile", {}))
        export_settings = ExportSettings.from_dict(data.get("export_settings", {}))

        return cls(
            story_name=data.get("story_name", ""),
            chapter_number=data.get("chapter_number", 1),
            chapter_title=data.get("chapter_title", ""),
            language=data.get("language", "vi"),
            source_text=data.get("source_text", ""),
            segments=segments,
            characters=characters,
            voice_profile=voice_profile,
            export_settings=export_settings,
            project_dir=data.get("project_dir"),
            output_dir=data.get("output_dir"),
        )

    def save(self, filepath: Path) -> None:
        """Save project to a JSON file.

        Args:
            filepath: Destination file path.
        """
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filepath: Path) -> Project:
        """Load project from a JSON file.

        Args:
            filepath: Source file path.

        Returns:
            The loaded Project instance.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
