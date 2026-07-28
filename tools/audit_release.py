#!/usr/bin/env python3
"""Fail a release when private/runtime material enters the package."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
BLOCKED_DIRS = {
    ".git", ".venv", ".audiobook-web", ".audiobook-work", ".pytest_cache",
    ".ruff_cache", ".story-thumbnail", "__pycache__", "node_modules", "tests",
    "testing", "examples", "comfyui", "output", "artifacts", "projects",
    "cache", "logs", "temp", "tmp",
}
BLOCKED_SUFFIXES = {
    ".wav", ".mp3", ".mp4", ".safetensors", ".ckpt", ".pt", ".pth",
    ".gguf", ".bin", ".log", ".part", ".pyc", ".map",
}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|client[_-]?secret)\s*[:=]\s*['\"][^'\"]{12,}"),
]


def main() -> int:
    errors: list[str] = []
    for file in ROOT.rglob("*"):
        relative = file.relative_to(ROOT)
        folded = {part.casefold() for part in relative.parts}
        if folded & BLOCKED_DIRS:
            errors.append(f"blocked directory: {relative}")
            continue
        if not file.is_file():
            continue
        if file.stem.casefold() == "openai":
            errors.append(f"online provider is forbidden: {relative}")
            continue
        if file.name.casefold() == ".env" or file.suffix.casefold() in BLOCKED_SUFFIXES:
            errors.append(f"blocked file: {relative}")
            continue
        if file.suffix.casefold() == ".txt" and not file.name.casefold().startswith("requirements"):
            errors.append(f"unexpected text data: {relative}")
            continue
        if file.suffix.casefold() == ".md" and file.name.casefold() != "readme.md":
            errors.append(f"private markdown: {relative}")
            continue
        if file.stat().st_size > 2_000_000:
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"(?i)C:\\Users\\[^\\\r\n]+", text):
            errors.append(f"absolute user path: {relative}")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            errors.append(f"possible secret: {relative}")
    if errors:
        print("Release audit failed:")
        print("\n".join(f"- {item}" for item in sorted(set(errors))))
        return 1
    print(f"Release audit passed: {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
