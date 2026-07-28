"""Path utilities for Audio-Comic Offline System.

Uses pathlib exclusively. Handles Unicode paths, slugification,
and project directory structure creation.
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Optional


def normalize_user_path(value: str | Path) -> str:
    """Clean pasted paths while preserving inner spaces and ``&`` characters."""
    text = str(value).strip()
    while len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        text = text[1:-1].strip()
    if not text:
        raise ValueError("Đường dẫn không được để trống")
    return os.path.expanduser(os.path.expandvars(text))


def get_app_root() -> Path:
    """Get the application root directory (where app.py lives).

    Returns:
        Absolute path to the application root.
    """
    return Path(__file__).resolve().parent.parent


def get_config_dir() -> Path:
    """Get the config directory path."""
    return get_app_root() / "config"


def get_default_projects_dir() -> Path:
    """Get the default projects directory."""
    return get_app_root() / "projects"


def get_default_cache_dir() -> Path:
    """Get the default cache directory."""
    return get_app_root() / "cache"


def ensure_dir(path: Path) -> Path:
    """Create directory if it doesn't exist, including parents.

    Args:
        path: Directory path to ensure exists.

    Returns:
        The same path (for chaining).
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(text: str, max_length: int = 80) -> str:
    """Convert text to a URL/filename-safe slug.

    Handles Vietnamese diacritics by transliterating them to ASCII.

    Args:
        text: Input text to slugify.
        max_length: Maximum slug length.

    Returns:
        Lowercase ASCII slug with hyphens as separators.
    """
    # Vietnamese character mapping
    vietnamese_map = {
        "đ": "d", "Đ": "D",
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

    text = text.lower().strip()
    for src, dst in vietnamese_map.items():
        text = text.replace(src, dst.lower())

    # Use NFKD normalization for remaining Unicode
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Replace non-alphanumeric with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")

    # Collapse multiple hyphens
    text = re.sub(r"-{2,}", "-", text)

    return text[:max_length]


def get_project_dir(
    projects_root: Path,
    story_slug: str,
    chapter_number: int,
) -> Path:
    """Get the project directory for a specific chapter.

    Args:
        projects_root: Root projects directory.
        story_slug: Slugified story name.
        chapter_number: Chapter number.

    Returns:
        Path to the project directory.
    """
    dir_name = f"{story_slug}_chapter_{chapter_number:03d}"
    return projects_root / dir_name


def create_project_structure(project_dir: Path) -> dict[str, Path]:
    """Create the full project subdirectory structure.

    Args:
        project_dir: Root directory for this project.

    Returns:
        Dictionary mapping subdirectory names to their paths.
    """
    subdirs = {
        "source": project_dir / "source",
        "script": project_dir / "script",
        "voices": project_dir / "voices",
        "cache": project_dir / "cache",
        "cache_tts": project_dir / "cache" / "tts",
        "poster": project_dir / "poster",
        "audio": project_dir / "audio",
        "audio_segments": project_dir / "audio" / "segments",
        "video": project_dir / "video",
        "logs": project_dir / "logs",
    }

    for subdir in subdirs.values():
        ensure_dir(subdir)

    return subdirs


def safe_filename(name: str, max_length: int = 200) -> str:
    """Make a string safe for use as a filename on Windows and Linux.

    Preserves Vietnamese characters (they are valid in filenames)
    but removes characters that are invalid on Windows.

    Args:
        name: The desired filename.
        max_length: Maximum filename length.

    Returns:
        Sanitized filename string.
    """
    # Remove characters invalid on Windows
    invalid_chars = r'<>:"/\|?*'
    for char in invalid_chars:
        name = name.replace(char, "")

    # Remove control characters
    name = "".join(c for c in name if ord(c) >= 32)

    # Strip dots and spaces from ends (Windows limitation)
    name = name.strip(". ")

    return name[:max_length] if name else "untitled"


def find_versioned_path(filepath: Path) -> Path:
    """Find a non-conflicting versioned path if file already exists.

    If 'output.mp4' exists, returns 'output_v2.mp4', etc.

    Args:
        filepath: Desired file path.

    Returns:
        A path that doesn't conflict with existing files.
    """
    if not filepath.exists():
        return filepath

    stem = filepath.stem
    suffix = filepath.suffix
    parent = filepath.parent
    version = 2

    while True:
        versioned = parent / f"{stem}_v{version}{suffix}"
        if not versioned.exists():
            return versioned
        version += 1
