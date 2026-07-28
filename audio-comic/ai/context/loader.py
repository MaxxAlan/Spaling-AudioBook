"""Load and build context from .md reference files for AI prompts.

Supports: master.md, request.md, characters.md, glossary.md, timeline.md, chapter_summaries.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from utils.logging_config import get_logger

logger = get_logger("ai.context.loader")

_CONTEXT_FILES = {
    "master": "master.md",
    "request": "request.md",
    "characters": "characters.md",
    "glossary": "glossary.md",
    "timeline": "timeline.md",
    "chapter_summaries": "chapter_summaries.md",
}

_SECTION_HEADERS = {
    "master": "# MASTER / TỔNG QUAN TRUYỆN",
    "request": "# REQUEST / YÊU CẦU",
    "characters": "# CHARACTERS / NHÂN VẬT",
    "glossary": "# GLOSSARY / THƯ VIỆN THUẬT NGỮ",
    "timeline": "# TIMELINE / DONG THỜI GIAN",
    "chapter_summaries": "# CHAPTER SUMMARIES / TÓM TẮT CHƯƠNG",
}


@dataclass
class ContextData:
    """Structured context loaded from .md files."""
    master: str = ""
    request: str = ""
    characters: str = ""
    glossary: str = ""
    timeline: str = ""
    chapter_summaries: str = ""
    loaded_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def load_context_files(
    md_dir: str | Path,
    chapter_number: Optional[int] = None,
    max_chars_per_file: int = 4000,
) -> ContextData:
    """Load context from .md directory.

    Args:
        md_dir: Directory containing .md files.
        chapter_number: If provided, extract relevant chapter summary.
        max_chars_per_file: Max characters per file to avoid token overflow.
    """
    md_path = Path(md_dir)
    ctx = ContextData()

    if not md_path.is_dir():
        logger.warning("Context .md directory not found: %s", md_path)
        ctx.errors.append(f"Directory not found: {md_path}")
        return ctx

    for key, filename in _CONTEXT_FILES.items():
        filepath = md_path / filename
        if not filepath.is_file():
            logger.debug("Context file not found (optional): %s", filepath)
            continue
        try:
            content = filepath.read_text(encoding="utf-8")
            if len(content) > max_chars_per_file:
                content = content[:max_chars_per_file] + f"\n\n[...truncated at {max_chars_per_file} chars...]"
            setattr(ctx, key, content)
            ctx.loaded_files.append(filename)
            logger.info("Loaded context: %s (%d chars)", filename, len(content))
        except Exception as exc:
            ctx.errors.append(f"Failed to load {filename}: {exc}")
            logger.warning("Failed to load %s: %s", filepath, exc)

    if chapter_number and ctx.chapter_summaries:
        ctx.chapter_summaries = _extract_chapter_summary(ctx.chapter_summaries, chapter_number)

    return ctx


def build_context_prompt(ctx: ContextData, for_image: bool = False) -> str:
    """Build a context string for AI prompts.

    Args:
        ctx: Loaded context data.
        for_image: If True, focus on visual descriptions for image generation.
    """
    sections = []

    if ctx.characters:
        sections.append(f"--- NHÂN VẬT / CHARACTERS ---\n{ctx.characters[:2000]}")
    if ctx.glossary:
        sections.append(f"--- THUẬT NGỮ / GLOSSARY ---\n{ctx.glossary[:1500]}")
    if ctx.timeline:
        sections.append(f"--- DONG THỜI GIAN / TIMELINE ---\n{ctx.timeline[:1500]}")
    if ctx.chapter_summaries:
        sections.append(f"--- TÓM TẮT CHƯƠNG / CHAPTER SUMMARY ---\n{ctx.chapter_summaries[:1000]}")

    if for_image:
        if ctx.characters:
            sections.append("--- GỢI Ý HÌNH ẢNH / VISUAL HINTS ---\nSử dụng mô tả nhân vật từ characters.md làm chuẩn. Không tự ý thêm đặc điểm không có trong dữ liệu.")
    else:
        if ctx.master:
            sections.append(f"--- TỔNG QUAN / MASTER ---\n{ctx.master[:1000]}")
        if ctx.request:
            sections.append(f"--- YÊU CẦU / REQUEST ---\n{ctx.request[:1000]}")

    if not sections:
        return ""

    return "\n\n".join(sections)


def build_narration_context(ctx: ContextData, chapter_number: Optional[int] = None) -> str:
    """Build compact context for narration guidance (1.5b model)."""
    parts = []
    if ctx.characters:
        parts.append(f"Nhân vật: {ctx.characters[:800]}")
    if ctx.chapter_summaries:
        parts.append(f"Tóm tắt: {ctx.chapter_summaries[:500]}")
    return "\n".join(parts) if parts else ""


def _extract_chapter_summary(summaries: str, chapter_number: int) -> str:
    """Extract summary for a specific chapter from chapter_summaries.md."""
    lines = summaries.split("\n")
    in_chapter = False
    chapter_lines = []
    chapter_marker = f"chapter {chapter_number}"
    alt_marker = f"chương {chapter_number}"

    for line in lines:
        lower = line.lower().strip()
        if chapter_marker in lower or alt_marker in lower:
            in_chapter = True
            chapter_lines = [line]
            continue
        if in_chapter:
            if line.strip().startswith("#") and chapter_marker not in lower and alt_marker not in lower:
                break
            chapter_lines.append(line)

    return "\n".join(chapter_lines) if chapter_lines else ""
