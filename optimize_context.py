#!/usr/bin/env python3
"""
Smart context optimizer for audiobook generation.
Uses chapter_summary to find relevant characters, timeline, glossary entries.
"""
import os
import re
import json
from pathlib import Path


def extract_chapter_summary(content: str, chapter: int) -> dict:
    """Extract YAML summary for specific chapter."""
    pattern = rf'## CHƯƠNG {chapter}\s*\n```yaml\n(.*?)\n```'
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if not match:
        return {}

    yaml_text = match.group(1)
    result = {
        'raw': yaml_text,
        'pov': [],
        'characters': [],
        'location': '',
        'objective': '',
        'hook': '',
    }

    # Extract POV
    pov_match = re.search(r'pov:\s*\[(.*?)\]', yaml_text)
    if pov_match:
        result['pov'] = [p.strip().strip('"\'') for p in pov_match.group(1).split(',') if p.strip()]

    # Extract character names from relationship_changes
    rel_match = re.search(r'relationship_changes:\s*\n(.*?)(?=\n  \w+:|$)', yaml_text, re.DOTALL)
    if rel_match:
        for line in rel_match.group(1).split('\n'):
            key_match = re.match(r'\s+(.+?)_and_(.+?):', line, re.IGNORECASE)
            if key_match:
                char1 = key_match.group(1).replace('_', ' ').strip().strip('"\'')
                char2 = key_match.group(2).replace('_', ' ').strip().strip('"\'')
                if len(char1) > 1 and len(char2) > 1:
                    result['characters'].extend([char1, char2])

    # Extract location
    loc_match = re.search(r'location:\s*"(.*?)"', yaml_text)
    if loc_match:
        result['location'] = loc_match.group(1)

    # Extract objective
    obj_match = re.search(r'objective:\s*"(.*?)"', yaml_text)
    if obj_match:
        result['objective'] = obj_match.group(1)

    # Extract hook
    hook_match = re.search(r'hook:\s*"(.*?)"', yaml_text)
    if hook_match:
        result['hook'] = hook_match.group(1)

    # Deduplicate characters
    result['characters'] = list(set(result['characters']))

    return result


def search_character(content: str, char_name: str) -> str:
    """Search for specific character block in characters.md."""
    lines = content.split('\n')

    # First pass: find exact heading match
    for i, line in enumerate(lines):
        if line.startswith('###'):
            heading = line[4:].strip()
            if heading.lower() == char_name.lower():
                block = [line]
                for j in range(i+1, len(lines)):
                    if lines[j].startswith('###') or lines[j].startswith('##'):
                        break
                    block.append(lines[j])
                return '\n'.join(block)

    # Second pass: find heading containing the name
    for i, line in enumerate(lines):
        if line.startswith('###'):
            heading = line[4:].strip()
            if char_name.lower() in heading.lower():
                block = [line]
                for j in range(i+1, len(lines)):
                    if lines[j].startswith('###') or lines[j].startswith('##'):
                        break
                    block.append(lines[j])
                return '\n'.join(block)

    # Third pass: search for any word in the name (for compound names)
    parts = char_name.split()
    for part in parts:
        if len(part) > 3:
            for i, line in enumerate(lines):
                if line.startswith('###'):
                    heading = line[4:].strip()
                    if part.lower() in heading.lower():
                        block = [line]
                        for j in range(i+1, len(lines)):
                            if lines[j].startswith('###') or lines[j].startswith('##'):
                                break
                            block.append(lines[j])
                        return '\n'.join(block)

    return ''


def search_characters_for_chapter(content: str, chapter_summary: dict, chapter_text: str = '') -> str:
    """Search for characters mentioned in chapter summary."""
    chars_to_find = chapter_summary.get('characters', [])
    pov_chars = chapter_summary.get('pov', [])
    all_chars = list(set(chars_to_find + pov_chars))

    chapter_folded = chapter_text.casefold()
    for line in content.splitlines():
        if not line.startswith('###'):
            continue
        heading = line[3:].strip()
        canonical = re.split(r'\s+[—–-]\s+|\s*\(', heading, maxsplit=1)[0].strip()
        if canonical and canonical.casefold() in chapter_folded:
            all_chars.append(canonical)

    if not all_chars:
        return content[:2000]

    found = []
    seen_headings = set()

    for char_name in all_chars:
        # Search for exact character
        result = search_character(content, char_name)
        if result:
            heading = result.split('\n')[0].strip()
            if heading not in seen_headings:
                found.append(result)
                seen_headings.add(heading)

    return '\n\n'.join(found)[:6000] if found else content[:2000]


def search_timeline_for_chapter(content: str, chapter: int) -> str:
    """Search for timeline entries matching chapter number."""
    lines = content.split('\n')
    relevant = []

    for line in lines:
        # Match "Ch.X" or "Ch. X" pattern in timeline table
        if re.search(rf'Ch\.?\s*{chapter}\b', line, re.IGNORECASE):
            relevant.append(line)

    if relevant:
        return '\n'.join(relevant)[:1500]

    # Fallback: find closest chapter entries
    closest = []
    for line in lines:
        match = re.search(r'Ch\.?\s*(\d+)', line, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            if abs(num - chapter) <= 2:
                closest.append(line)

    return '\n'.join(closest)[:1500] if closest else content[:1000]


def search_master_for_chapter(content: str, chapter: int) -> str:
    """Keep the narrowest ranged section and its heading ancestors."""
    lines = content.splitlines()

    def chapter_range(line: str) -> tuple[int, int] | None:
        normalized = re.sub(r'(?<=\d)[.,](?=\d{3}\b)', '', line)
        match = re.search(
            r'(?:Chương|Chapters?|Ch\.)\s*(\d+)\s*[–—-]\s*(\d+)',
            normalized,
            re.IGNORECASE,
        )
        return (int(match.group(1)), int(match.group(2))) if match else None

    candidates = []
    for index, line in enumerate(lines):
        bounds = chapter_range(line)
        heading = re.match(r'^(#{1,6})\s+', line)
        if heading and bounds and bounds[0] <= chapter <= bounds[1]:
            candidates.append((bounds[1] - bounds[0], -len(heading.group(1)), index))
    if not candidates:
        return content

    section_start = min(candidates)[2]
    selected_level = len(re.match(r'^(#{1,6})\s+', lines[section_start]).group(1))
    section_end = next(
        (
            index for index in range(section_start + 1, len(lines))
            if (match := re.match(r'^(#{1,6})\s+', lines[index]))
            and len(match.group(1)) <= selected_level
        ),
        len(lines),
    )
    ancestors: dict[int, str] = {}
    for line in lines[:section_start]:
        match = re.match(r'^(#{1,6})\s+', line)
        if not match:
            continue
        level = len(match.group(1))
        ancestors[level] = line
        for deeper in [key for key in ancestors if key > level]:
            del ancestors[deeper]
    selected = [ancestors[level] for level in sorted(ancestors) if level < selected_level]
    selected.extend(
        line for line in lines[:section_start]
        if (bounds := chapter_range(line))
        and bounds[0] <= chapter <= bounds[1]
        and re.search(r'cold open|hồi tưởng|quay về|timeline|niên đại|mốc thời gian|năm\s+\d+|year\s+\d+', line, re.IGNORECASE)
    )
    selected.extend(lines[section_start:section_end])
    return '\n'.join(selected).strip() + '\n'

def search_glossary_for_chapter(content: str, chapter_summary: dict, chapter_text: str = '') -> str:
    """Search for glossary terms mentioned in chapter summary."""
    # Extract key terms from summary
    raw = chapter_summary.get('raw', '')
    terms_to_find = set()

    # Find capitalized terms that might be glossary entries
    for word in raw.split():
        clean = word.strip('",.:;()[]')
        if len(clean) > 3 and clean[0].isupper() and not clean.isupper():
            terms_to_find.add(clean)

    chapter_folded = chapter_text.casefold()
    for line in content.splitlines():
        if line.startswith('#'):
            term = line.lstrip('#').strip().split('—', 1)[0].strip()
            if len(term) > 2 and term.casefold() in chapter_folded:
                terms_to_find.add(term)

    lines = content.split('\n')
    found = []

    for line in lines:
        # Check if line contains any term
        for term in terms_to_find:
            if term.lower() in line.lower():
                found.append(line)
                break

    # Also keep section headers
    for line in lines:
        if line.startswith('## '):
            found.append(line)

    return '\n'.join(dict.fromkeys(found))[:3000] if found else content[:1000]


def extract_summaries_for_chapter(content: str, chapter: int) -> str:
    """Extract summaries for chapters before current (context)."""
    lines = content.split('\n')
    relevant = []
    in_chapter = False

    for line in lines:
        match = re.search(r'(?:Chương|Chapter)\s*(\d+)', line, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            if num < chapter:
                in_chapter = True
                relevant.append(line)
            elif num == chapter:
                in_chapter = True
                relevant.append(line)
            else:
                in_chapter = False
        elif in_chapter:
            relevant.append(line)

    return '\n'.join(relevant)[-3000:] if relevant else content[:2000]


def optimize_context(context_dir: str, chapter: int, chapter_text: str = '') -> dict:
    """Smart optimize all context files for a specific chapter."""
    context_path = Path(context_dir)
    result = {}

    # Load chapter_summaries first to get chapter context
    summaries_file = context_path / 'chapter_summaries.md'
    chapter_summary = {}
    if summaries_file.exists():
        content = summaries_file.read_text(encoding='utf-8')
        chapter_summary = extract_chapter_summary(content, chapter)
        result['chapter_summary'] = chapter_summary.get('raw', '')[:2000]
        result['chapter_summaries'] = extract_summaries_for_chapter(content, chapter)

    # Load master.md - keep the hierarchy and ranges needed by storyboard-gen
    master_file = context_path / 'master.md'
    if master_file.exists():
        content = master_file.read_text(encoding='utf-8')
        result['master'] = search_master_for_chapter(content, chapter)

    # Load request.md - keep full (usually short)
    request_file = context_path / 'request.md'
    if request_file.exists():
        result['request'] = request_file.read_text(encoding='utf-8')[:6000]

    # Load characters.md - search for relevant characters
    chars_file = context_path / 'characters.md'
    if chars_file.exists():
        content = chars_file.read_text(encoding='utf-8')
        result['characters'] = search_characters_for_chapter(content, chapter_summary, chapter_text)

    # Load glossary.md - search for relevant terms
    glossary_file = context_path / 'glossary.md'
    if glossary_file.exists():
        content = glossary_file.read_text(encoding='utf-8')
        result['glossary'] = search_glossary_for_chapter(content, chapter_summary, chapter_text)

    # Load timeline.md - search for chapter entries
    timeline_file = context_path / 'timeline.md'
    if timeline_file.exists():
        content = timeline_file.read_text(encoding='utf-8')
        result['timeline'] = search_timeline_for_chapter(content, chapter)

    return result


def print_stats(context: dict):
    """Print token estimation stats."""
    total_chars = sum(len(v) for v in context.values())
    est_tokens = total_chars // 4

    print(f"\n{'='*60}")
    print(f"Context Optimization Stats:")
    print(f"{'='*60}")
    for key, value in context.items():
        print(f"  {key:20s}: {len(value):6d} chars (~{len(value)//4:5d} tokens)")
    print(f"{'='*60}")
    print(f"  {'TOTAL':20s}: {total_chars:6d} chars (~{est_tokens:5d} tokens)")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("Usage: python optimize_context.py <context_dir> <chapter_number>")
        print("Example: python optimize_context.py 'C:\\path\\to\\.md' 3")
        sys.exit(1)

    context_dir = sys.argv[1]
    chapter = int(sys.argv[2])

    context = optimize_context(context_dir, chapter)
    print_stats(context)

    # Save optimized context
    output_file = os.path.join(context_dir, f'optimized_ch{chapter}.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

    print(f"Saved optimized context to: {output_file}")
