"""Hashing utilities for cache key generation."""

from __future__ import annotations

import hashlib


def generate_cache_key(
    text: str,
    voice_id: str,
    speed: float = 1.0,
    pitch: float = 0.0,
    tts_model_version: str = "default",
) -> str:
    """Generate a SHA256 cache key from segment parameters.

    The cache key uniquely identifies a TTS output. If any parameter
    changes, a new audio segment must be generated.

    Args:
        text: Normalized text content.
        voice_id: Voice profile identifier.
        speed: Playback speed multiplier.
        pitch: Pitch adjustment value.
        tts_model_version: TTS model version string.

    Returns:
        Hex digest of the SHA256 hash.
    """
    components = [
        text.strip(),
        voice_id,
        f"speed:{speed:.4f}",
        f"pitch:{pitch:.4f}",
        f"model:{tts_model_version}",
    ]
    combined = "|".join(components)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def file_hash(filepath: str, algorithm: str = "sha256") -> str:
    """Compute hash of a file's contents.

    Args:
        filepath: Path to the file.
        algorithm: Hash algorithm name (sha256, md5, etc.).

    Returns:
        Hex digest of the file hash.
    """
    h = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
