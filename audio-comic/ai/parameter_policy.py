"""Bounded, auditable per-segment TTS parameter policy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterPolicy:
    base: dict[str, float]
    ranges: dict[str, tuple[float, float]]

    @classmethod
    def from_tts_settings(cls, settings: dict) -> "ParameterPolicy":
        tts = settings.get("tts", {})
        base = {key: float(tts.get(key, default)) for key, default in {
            "temperature": 0.6, "top_k": 20, "top_p": 0.88,
            "repetition_penalty": 1.15,
        }.items()}
        ranges = {
            "temperature": (max(0.1, base["temperature"] - 0.25), min(2.0, base["temperature"] + 0.25)),
            "top_k": (max(1, base["top_k"] - 10), min(200, base["top_k"] + 10)),
            "top_p": (max(0.05, base["top_p"] - 0.10), min(1.0, base["top_p"] + 0.10)),
            "repetition_penalty": (max(0.5, base["repetition_penalty"] - 0.10), min(2.0, base["repetition_penalty"] + 0.10)),
        }
        return cls(base, ranges)

    def clamp(self, name: str, value: float) -> float:
        low, high = self.ranges[name]
        return max(low, min(high, float(value)))

    def options(self, candidate: dict) -> dict[str, float]:
        return {name: self.clamp(name, candidate.get(name, self.base[name])) for name in self.base}
