import type { LoadedSource } from './loader.js';

export interface SourceChunk { chunkIndex: number; startLine: number; endLine: number; text: string; previousContext: string; }
export function chunkSource(source: LoadedSource, maxLines = 160, overlap = 20): SourceChunk[] {
  if (maxLines < 2 || overlap >= maxLines || overlap < 0) throw new Error('Chunk settings require 0 <= overlap < maxLines.');
  const chunks: SourceChunk[] = []; let start = 0;
  while (start < source.lines.length) {
    let end = Math.min(start + maxLines, source.lines.length);
    if (end < source.lines.length) {
      const searchFloor = Math.max(start + Math.floor(maxLines * 0.65), start + 1);
      for (let cursor = end; cursor >= searchFloor; cursor -= 1) if ((source.lines[cursor - 1] ?? '').trim() === '') { end = cursor; break; }
    }
    const contextStart = Math.max(0, start - overlap);
    chunks.push({ chunkIndex: chunks.length, startLine: start + 1, endLine: end, text: source.lines.slice(start, end).join('\n'), previousContext: source.lines.slice(contextStart, start).join('\n') });
    if (end === source.lines.length) break;
    start = Math.max(start + 1, end - overlap);
  }
  return chunks;
}
