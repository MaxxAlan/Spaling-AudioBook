"""Custom VieNeu voice registry shared by CLI and Web UI."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable


def default_registry_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "custom_voices.json"


def _resolve_asset(registry_path: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = registry_path.parent / path
    return path.resolve()


@dataclass(frozen=True)
class CustomVoice:
    voice_id: str
    name: str
    gender: str
    language: str
    description: str
    aliases: tuple[str, ...]
    reference_audio: Path
    compiled_voice: Path
    consent_confirmed: bool

    def matches(self, value: str) -> bool:
        candidate = value.strip().casefold()
        return candidate in {
            self.voice_id.casefold(),
            self.name.casefold(),
            *(alias.casefold() for alias in self.aliases),
        }


def load_custom_voices(path: str | Path | None = None) -> list[CustomVoice]:
    registry_path = Path(path).resolve() if path else default_registry_path()
    if not registry_path.is_file():
        return []
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    voices: list[CustomVoice] = []
    for raw in payload.get("voices", []):
        if not raw.get("consent_confirmed"):
            continue
        voices.append(
            CustomVoice(
                voice_id=str(raw["id"]),
                name=str(raw["name"]),
                gender=str(raw.get("gender", "neutral")),
                language=str(raw.get("language", "vi")),
                description=str(raw.get("description", "")),
                aliases=tuple(str(item) for item in raw.get("aliases", [])),
                reference_audio=_resolve_asset(
                    registry_path, str(raw.get("reference_audio", ""))
                ),
                compiled_voice=_resolve_asset(
                    registry_path, str(raw.get("compiled_voice", ""))
                ),
                consent_confirmed=True,
            )
        )
    return voices


def resolve_custom_voice(
    value: str, voices: Iterable[CustomVoice]
) -> CustomVoice | None:
    return next((voice for voice in voices if voice.matches(value)), None)


def registry_fingerprint(path: str | Path | None = None) -> str:
    """Return a short cache identity that changes with registry voice assets."""
    registry_path = Path(path).resolve() if path else default_registry_path()
    digest = hashlib.sha256()
    if registry_path.is_file():
        digest.update(registry_path.read_bytes())
    for voice in load_custom_voices(registry_path):
        asset = (
            voice.compiled_voice
            if voice.compiled_voice.is_file()
            else voice.reference_audio
        )
        if asset.is_file():
            digest.update(asset.read_bytes())
    return digest.hexdigest()[:12]
