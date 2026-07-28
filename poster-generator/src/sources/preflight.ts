import type { LoadedSource } from './loader.js';

const CHAPTER_HEADING = /^\s*(?:-{3,}\s*)?(?:#{1,6}\s*)?(?:Chương|Chapter)\s+(\d+)\b/iu;

export function assertSingleChapterSource(source: LoadedSource): void {
  const chapterNumbers = new Set<number>();
  for (const line of source.lines) {
    const match = CHAPTER_HEADING.exec(line);
    if (match?.[1]) chapterNumbers.add(Number(match[1]));
  }
  if (chapterNumbers.size > 1) {
    throw new Error(
      `File chương chứa nhiều chương (${[...chapterNumbers].join(', ')}). ` +
      'Hãy chọn một file chỉ chứa một chương để tránh trộn cảnh và nhân vật.',
    );
  }
  const meaningfulLines = source.lines.filter((line) => line.trim() && !CHAPTER_HEADING.test(line));
  if (meaningfulLines.length < 2) throw new Error('File chương không có đủ nội dung để phân tích.');
}
