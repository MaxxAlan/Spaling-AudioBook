"""Character detection and tracking across a chapter.

Builds a character registry from parsed dialogue lines,
assigning unique identifiers to unknown speakers.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from models.character import Character
from text_processing.dialogue_parser import ParsedLine, LineType
from utils.logging_config import get_logger

logger = get_logger("text_processing.character_detector")


class CharacterDetector:
    """Detects and tracks characters from parsed dialogue lines.

    Maintains a registry of named characters and generates
    'unknown_character_XX' identifiers for unattributed dialogue.
    """

    def __init__(self) -> None:
        """Initialize the character detector."""
        self._characters: Dict[str, Character] = {}
        self._unknown_counter: int = 0
        self._last_dialogue_speaker: Optional[str] = None

        # Always add narrator
        narrator = Character.create_narrator()
        self._characters["narrator"] = narrator

    @property
    def characters(self) -> Dict[str, Character]:
        """Return the current character registry."""
        return dict(self._characters)

    def process_lines(self, parsed_lines: List[ParsedLine]) -> List[ParsedLine]:
        """Process parsed lines to detect and register characters.

        Updates speaker fields on dialogue lines where possible.
        Creates Character objects for newly detected speakers.

        Args:
            parsed_lines: List of classified text lines.

        Returns:
            The same list with speaker fields potentially updated.
        """
        for line in parsed_lines:
            if line.line_type == LineType.DIALOGUE:
                self._process_dialogue_line(line)
            elif line.line_type == LineType.INNER_THOUGHT:
                self._process_thought_line(line)

        # Log summary
        named = sum(1 for c in self._characters.values() if not c.name.startswith("unknown_"))
        unknown = sum(1 for c in self._characters.values() if c.name.startswith("unknown_"))
        logger.info(
            "Detected %d characters: %d named, %d unknown",
            len(self._characters), named, unknown,
        )

        return parsed_lines

    def _process_dialogue_line(self, line: ParsedLine) -> None:
        """Process a dialogue line to detect or assign a speaker.

        Args:
            line: A parsed line classified as DIALOGUE.
        """
        if line.speaker:
            # Speaker was already detected by the dialogue parser
            self._register_character(line.speaker)
            self._last_dialogue_speaker = line.speaker
        else:
            # No speaker detected — assign unknown
            speaker = self._create_unknown_character()
            line.speaker = speaker
            self._last_dialogue_speaker = speaker

    def _process_thought_line(self, line: ParsedLine) -> None:
        """Process an inner thought line.

        Inner thoughts are typically from the last speaking character
        or the protagonist (often the narrator's POV character).

        Args:
            line: A parsed line classified as INNER_THOUGHT.
        """
        if self._last_dialogue_speaker:
            line.speaker = self._last_dialogue_speaker
        else:
            line.speaker = "narrator"

    def _register_character(self, name: str) -> Character:
        """Register a named character or return existing one.

        Args:
            name: Character name.

        Returns:
            The Character object.
        """
        if name not in self._characters:
            # Guess gender from name context (default male for Vietnamese fiction)
            character = Character(
                name=name,
                gender="male",
                voice_id="male_young_01",
                display_name=name,
            )
            self._characters[name] = character
            logger.debug("Registered new character: %s", name)

        # Increment dialogue count
        self._characters[name].dialogue_count += 1
        return self._characters[name]

    def _create_unknown_character(self) -> str:
        """Create a new unknown character entry.

        Returns:
            The unknown character's name identifier.
        """
        self._unknown_counter += 1
        character = Character.create_unknown(self._unknown_counter)
        self._characters[character.name] = character
        logger.debug("Created unknown character: %s", character.name)
        return character.name

    def reassign_speaker(self, old_name: str, new_name: str) -> None:
        """Reassign an unknown speaker to a named character.

        Used when the user manually identifies a character.

        Args:
            old_name: The current speaker name (e.g., 'unknown_character_01').
            new_name: The new speaker name to assign.
        """
        if old_name in self._characters:
            character = self._characters.pop(old_name)
            character.name = new_name
            character.display_name = new_name

            if new_name in self._characters:
                # Merge dialogue counts
                self._characters[new_name].dialogue_count += character.dialogue_count
            else:
                self._characters[new_name] = character

            logger.info("Reassigned speaker: %s → %s", old_name, new_name)

    def get_character(self, name: str) -> Optional[Character]:
        """Get a character by name.

        Args:
            name: Character name to look up.

        Returns:
            Character object or None if not found.
        """
        return self._characters.get(name)
