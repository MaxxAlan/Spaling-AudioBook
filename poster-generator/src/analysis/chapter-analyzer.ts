import type { LoadedSource } from '../sources/loader.js';
import { chunkSource } from '../sources/chunker.js';
import { analyzeChunkHeuristically } from './chunk-analyzer.js';
import { mergeChunkAnalyses } from './analysis-merger.js';
import type { ChapterAnalysis } from '../schemas/chapter.js';
import type { TextAIProvider } from '../providers/text/types.js';
import { chunkAnalysisSchema } from '../schemas/chapter.js';
import { CHAPTER_ANALYZER_SYSTEM } from '../prompts/chapter-chunk.js';

export async function analyzeFullChapter(source: LoadedSource, chapterNumber: number, timeline: string, maxLines = 160, overlap = 20, provider?: TextAIProvider, context = ''): Promise<ChapterAnalysis> {
  const chunks = chunkSource(source, maxLines, overlap);
  const analyses = await Promise.all(chunks.map(async (chunk) => {
    const fallback = analyzeChunkHeuristically(chunk); if (!provider) return fallback;
    const prompt = provider.name === 'mock'
      ? `Analyze this complete chunk after respecting canon and spoiler context.\nMOCK_RESULT_JSON\n${JSON.stringify(fallback)}`
      : `Canon/master context (future facts are continuity-only and must not become visible):\n${context}\n\nChunk metadata: ${JSON.stringify({ chunkIndex: chunk.chunkIndex, startLine: chunk.startLine, endLine: chunk.endLine, previousContext: chunk.previousContext })}\n\nChapter chunk:\n${chunk.text}\n\nReturn every field required by this JSON Schema:\n${JSON.stringify((await import('zod')).z.toJSONSchema(chunkAnalysisSchema))}`;
    return provider.generateStructured(CHAPTER_ANALYZER_SYSTEM, prompt, chunkAnalysisSchema);
  }));
  const title = (source.lines.slice(0, 8).find((line) => /(?:Chương|Chapter)\s*\d+/i.test(line)) ?? `Chapter ${chapterNumber}`).replace(/^#+\s*/, '').trim();
  return mergeChunkAnalyses(analyses, chapterNumber, title, timeline);
}
