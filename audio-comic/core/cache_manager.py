"""Cache manager for TTS segment caching and resume.

Uses SHA256 keys to avoid regenerating unchanged segments.
Tracks cache size and supports clearing per-project or globally.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from utils.hashing import generate_cache_key
from utils.logging_config import get_logger

logger = get_logger("core.cache_manager")


class CacheManager:
    """Manages TTS segment cache with SHA256-based keys.

    Cache structure:
        cache_dir/
            tts/
                <sha256_hex>.wav
            index.json   (maps keys to metadata)
    """

    def __init__(self, cache_dir: Path) -> None:
        """Initialize cache manager.

        Args:
            cache_dir: Root directory for cache storage.
        """
        self._cache_dir = cache_dir
        self._tts_dir = cache_dir / "tts"
        self._index_path = cache_dir / "index.json"
        self._index: dict = {}

        self._tts_dir.mkdir(parents=True, exist_ok=True)
        self._load_index()

    def _load_index(self) -> None:
        """Load the cache index from disk."""
        if self._index_path.exists():
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Cache index corrupted, resetting: %s", e)
                self._index = {}
        else:
            self._index = {}

    def _save_index(self) -> None:
        """Save the cache index to disk."""
        try:
            with open(self._index_path, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error("Failed to save cache index: %s", e)

    def get_cache_key(
        self,
        text: str,
        voice_id: str,
        speed: float = 1.0,
        pitch: float = 0.0,
        model_version: str = "default",
    ) -> str:
        """Generate a cache key for a segment.

        Args:
            text: Normalized text content.
            voice_id: Voice profile ID.
            speed: Speed multiplier.
            pitch: Pitch adjustment.
            model_version: TTS model version.

        Returns:
            SHA256 hex digest cache key.
        """
        return generate_cache_key(text, voice_id, speed, pitch, model_version)

    def has_cached(self, cache_key: str) -> bool:
        """Check if a cached audio file exists for the given key.

        Args:
            cache_key: SHA256 cache key.

        Returns:
            True if cached file exists and is valid.
        """
        if cache_key not in self._index:
            return False

        cached_path = self._tts_dir / f"{cache_key}.wav"
        if cached_path.exists() and cached_path.stat().st_size > 0:
            return True

        # Remove stale index entry
        del self._index[cache_key]
        self._save_index()
        return False

    def get_cached_path(self, cache_key: str) -> Optional[str]:
        """Get the file path for a cached segment.

        Args:
            cache_key: SHA256 cache key.

        Returns:
            Absolute path to cached WAV file, or None if not cached.
        """
        if self.has_cached(cache_key):
            return str((self._tts_dir / f"{cache_key}.wav").resolve())
        return None

    def store(
        self,
        cache_key: str,
        source_wav_path: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Store a generated WAV file in the cache.

        Args:
            cache_key: SHA256 cache key.
            source_wav_path: Path to the WAV file to cache.
            metadata: Optional metadata to store with the cache entry.

        Returns:
            Path to the cached file.
        """
        source = Path(source_wav_path)
        if not source.exists():
            logger.warning("Cannot cache non-existent file: %s", source)
            return source_wav_path

        dest = self._tts_dir / f"{cache_key}.wav"
        if source.resolve() != dest.resolve():
            shutil.copy2(str(source), str(dest))

        self._index[cache_key] = {
            "size": dest.stat().st_size,
            **(metadata or {}),
        }
        self._save_index()

        logger.debug("Cached segment: %s (%.1f KB)", cache_key[:12], dest.stat().st_size / 1024)
        return str(dest.resolve())

    def invalidate(self, cache_key: str) -> None:
        """Remove a specific cached entry.

        Args:
            cache_key: SHA256 cache key to invalidate.
        """
        cached_path = self._tts_dir / f"{cache_key}.wav"
        if cached_path.exists():
            cached_path.unlink()
        if cache_key in self._index:
            del self._index[cache_key]
            self._save_index()
        logger.debug("Invalidated cache: %s", cache_key[:12])

    def clear_project_cache(self, project_id: str) -> int:
        """Clear cache entries for a specific project.

        Args:
            project_id: Project identifier.

        Returns:
            Number of entries cleared.
        """
        keys_to_remove = [
            k for k, v in self._index.items()
            if v.get("project_id") == project_id
        ]
        for key in keys_to_remove:
            self.invalidate(key)
        logger.info("Cleared %d cache entries for project: %s", len(keys_to_remove), project_id)
        return len(keys_to_remove)

    def clear_all(self) -> int:
        """Clear the entire cache.

        Returns:
            Number of entries cleared.
        """
        count = len(self._index)
        if self._tts_dir.exists():
            shutil.rmtree(self._tts_dir)
            self._tts_dir.mkdir(parents=True, exist_ok=True)
        self._index = {}
        self._save_index()
        logger.info("Cleared entire cache: %d entries", count)
        return count

    def get_cache_size(self) -> int:
        """Get total cache size in bytes.

        Returns:
            Total cache size in bytes.
        """
        total = 0
        if self._tts_dir.exists():
            for f in self._tts_dir.glob("*.wav"):
                total += f.stat().st_size
        return total

    def get_cache_size_display(self) -> str:
        """Get human-readable cache size string.

        Returns:
            Formatted size string (e.g., '45.2 MB').
        """
        size = self.get_cache_size()
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"

    @property
    def entry_count(self) -> int:
        """Number of cached entries."""
        return len(self._index)
