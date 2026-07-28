"""Audiobook image-density presets shared by both CLI workflows."""

from __future__ import annotations

import re


AUDIOBOOK_PROFILE_RANGES: dict[str, tuple[int, int | float]] = {
    "auto": (2, float("inf")),
    "low": (6, 60),
    "medium": (60, 200),
    "high": (100, 400),
    "max": (2, float("inf")),
}

_DENSITY_PER_MINUTE = {"low": 0.5, "medium": 0.8, "high": 1.5, "max": 4.0}


def estimate_scene_hints(text: str) -> int:
    """Estimate structural visual beats without replacing the AI scene analyzer."""
    sentences = [item for item in re.split(r"(?<=[.!?…])\s+|\n+", text) if item.strip()]
    paragraphs = [item for item in re.split(r"\n+", text) if item.strip()]
    return max(len(paragraphs), round(len(sentences) / 3))


def choose_image_count(
    profile: str, audio_duration_seconds: float, *, scene_hints: int = 0
) -> int:
    """Choose number of images based on profile.

    - low/medium/high: duration-based with min/max bounds
    - max: AI decides based on scene_hints (no limit)
    """
    if profile not in AUDIOBOOK_PROFILE_RANGES:
        raise ValueError(f"Audiobook preset không hợp lệ: {profile}")

    if profile in {"auto", "max"}:
        # Source analysis supplies scene_hints; duration prevents sparse long-form videos.
        duration_floor = round(max(0.0, audio_duration_seconds) / 60)
        return max(2, max(scene_hints, duration_floor))

    minimum, maximum = AUDIOBOOK_PROFILE_RANGES[profile]
    duration_target = round(max(0.0, audio_duration_seconds) / 60 * _DENSITY_PER_MINUTE[profile])
    return max(minimum, min(maximum, duration_target))
