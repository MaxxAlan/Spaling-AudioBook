import type { LoadedSource } from '../sources/loader.js';
import type { Evidence } from '../schemas/common.js';
import type { StructuralCandidates } from '../schemas/analysis-v3.js';

const separatorPattern = /^\s*(?:\*{3,}|-{3,}|_{3,})\s*$/;
const transitionPattern = /^\s*(?:Trong khi (?:đó|ấy)|Cùng (?:lúc|thời điểm)(?: đó)?|Ở phía\s+\S|Về phần\s+\S|Tại\s+\S|Ở\s+\S|Sau khi\s+\S|Trước khi\s+\S|Nhiều năm trước\b|Trong ký ức\b|Hồi ấy\b|Đêm đó\b|Sáng hôm sau\b|Một lúc sau\b|Mặt khác\b|Meanwhile\b|At\s+\S|After\s+\S|Years earlier\b|In (?:the )?memory\b|The next morning\b|Later that\b)/iu;
const chapterTitlePattern = /^\s*(?:#+\s*)?(?:Chương|Chapter)\s+\d+/iu;

function evidence(source: LoadedSource, start: number, end: number): Evidence[] {
  const quote = source.lines.slice(start - 1, end).find((line) => line.trim())?.trim() ?? '';
  return [{ source: 'chapter', sourcePath: source.path, lineStart: start, lineEnd: end, quote }];
}

export function segmentStructure(source: LoadedSource, maxBlockLines = 48): StructuralCandidates {
  const contentLines = source.lines.flatMap((line, index) =>
    line.trim() && !separatorPattern.test(line) && !chapterTitlePattern.test(line) ? [index + 1] : [],
  );
  const separators = source.lines.flatMap((line, index) => separatorPattern.test(line) ? [index + 1] : []);
  const ranges: Array<{ start: number; end: number; reason: string }> = [];
  let start = 1;

  const commit = (end: number, reason: string): void => {
    while (start <= end && (!source.lines[start - 1]?.trim() || separatorPattern.test(source.lines[start - 1]!))) start += 1;
    while (end >= start && (!source.lines[end - 1]?.trim() || separatorPattern.test(source.lines[end - 1]!))) end -= 1;
    if (start <= end) ranges.push({ start, end, reason });
    start = end + 1;
  };

  for (let line = 1; line <= source.lines.length; line += 1) {
    const value = source.lines[line - 1] ?? '';
    if (separatorPattern.test(value)) {
      commit(line - 1, 'explicit_separator');
      start = line + 1;
      continue;
    }
    const span = line - start;
    if (span >= 6 && transitionPattern.test(value)) {
      commit(line - 1, 'explicit_transition');
      start = line;
    } else if (span >= maxBlockLines) {
      let boundary = line;
      for (let cursor = line; cursor > Math.max(start + 24, line - 12); cursor -= 1) {
        if (!(source.lines[cursor - 1] ?? '').trim()) { boundary = cursor - 1; break; }
      }
      commit(boundary, 'maximum_block_size');
      start = boundary + 1;
    }
  }
  commit(source.lines.length, 'chapter_end');

  if (!ranges.length) throw new Error('Chapter does not contain analysable content.');
  return {
    lineCount: source.lines.length,
    contentLines,
    separators,
    candidates: ranges.map((range, index) => ({
      candidateId: `candidate_${String(index + 1).padStart(3, '0')}`,
      lineStart: range.start,
      lineEnd: range.end,
      structuralReason: range.reason,
      evidence: evidence(source, range.start, range.end),
    })),
  };
}
