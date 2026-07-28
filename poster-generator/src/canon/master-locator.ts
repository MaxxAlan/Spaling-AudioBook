import path from 'node:path';
import type { LoadedSource } from '../sources/loader.js';
import type { MasterIndex, MasterPosition } from '../schemas/master.js';
import { AppError } from '../utils/errors.js';

export function detectChapterNumber(chapter: LoadedSource, explicit?: number): number {
  if (explicit !== undefined) { if (!Number.isInteger(explicit) || explicit < 1) throw new AppError('INVALID_CHAPTER_NUMBER', 'Số chương phải là số nguyên dương.'); return explicit; }
  const candidates = [chapter.lines.slice(0, 12).join('\n'), path.basename(chapter.path)];
  for (const value of candidates) { const match = value.match(/(?:Chương|Chapter|chapter[-_ ]?)(?:\s*[:#-]?\s*)(\d+)/i); if (match?.[1]) return Number(match[1]); }
  throw new AppError('CHAPTER_NUMBER_NOT_FOUND', `Không xác định được số chương từ tiêu đề hoặc tên file: ${chapter.path}`);
}
export function locateMaster(index: MasterIndex, chapterNumber: number): MasterPosition {
  const ranges = index.chapterRanges.filter((range) => chapterNumber >= range.start && chapterNumber <= range.end).sort((a, b) => (a.end - a.start) - (b.end - b.start));
  const selected = ranges[0];
  if (!selected) throw new AppError('MASTER_CHAPTER_NOT_FOUND', `Không tìm thấy chương ${chapterNumber} trong master index.`);
  const nextRangeLine = Math.min(...index.chapterRanges.filter((item) => item.provenance.lineStart > selected.provenance.lineStart).map((item) => item.provenance.lineStart), Number.POSITIVE_INFINITY);
  const localTransitions = index.timelineTransitions.filter((item) => item.provenance.lineStart >= selected.provenance.lineStart && item.provenance.lineStart < nextRangeLine);
  const priorTransitions = index.timelineTransitions.filter((item) => item.provenance.lineStart < selected.provenance.lineStart);
  const temporalEvidence = /năm\s+\d+|year\s+\d+|niên đại|mốc thời gian|hồi tưởng|quay về|timeline\s*:/i;
  const transition = [...localTransitions].reverse().find((item) => temporalEvidence.test(item.value))
    ?? [...priorTransitions].reverse().find((item) => temporalEvidence.test(item.value))
    ?? localTransitions.at(-1)
    ?? priorTransitions.at(-1);
  const timeline = selected.timeline || transition?.value || 'timeline from master range';
  const futureSpoilers = index.lockedMilestones.filter((item) => item.provenance.lineStart > selected.provenance.lineEnd).map((item) => item.value);
  return { chapterNumber, grandArc: selected.grandArc, volume: selected.volume, miniArc: selected.miniArc, timeline, arcPurpose: selected.arcPurpose, centralConflict: selected.centralConflict, lockedMilestones: index.lockedMilestones.filter((item) => item.provenance.lineStart <= selected.provenance.lineEnd).map((item) => item.value), futureSpoilers };
}
