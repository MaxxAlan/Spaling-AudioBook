import fs from 'node:fs/promises';
import path from 'node:path';

export interface ContextData {
  characters: string;
  glossary: string;
  timeline: string;
  chapterSummaries: string;
  loadedFiles: string[];
}

const CONTEXT_FILES: Record<string, string> = {
  characters: 'characters.md',
  glossary: 'glossary.md',
  timeline: 'timeline.md',
  chapterSummaries: 'chapter_summaries.md',
};

export async function loadContextFiles(
  contextDir: string,
  maxCharsPerFile = 12000,
): Promise<ContextData> {
  const ctx: ContextData = {
    characters: '',
    glossary: '',
    timeline: '',
    chapterSummaries: '',
    loadedFiles: [],
  };

  try {
    await fs.access(contextDir);
  } catch {
    return ctx;
  }

  for (const [key, filename] of Object.entries(CONTEXT_FILES)) {
    const filepath = path.join(contextDir, filename);
    try {
      let content = await fs.readFile(filepath, 'utf-8');
      if (key !== 'chapterSummaries' && content.length > maxCharsPerFile) {
        content = content.slice(0, maxCharsPerFile) + '\n\n[...truncated...]';
      }
      (ctx as any)[key] = content;
      ctx.loadedFiles.push(filename);
    } catch {
      // File not found - skip silently
    }
  }

  return ctx;
}

export function buildImageContextPrompt(ctx: ContextData): string {
  const sections: string[] = [];

  if (ctx.characters) {
    sections.push(`--- CHARACTERS ---\n${ctx.characters.slice(0, 2000)}`);
  }
  if (ctx.glossary) {
    sections.push(`--- GLOSSARY ---\n${ctx.glossary.slice(0, 1500)}`);
  }
  if (ctx.timeline) {
    sections.push(`--- TIMELINE ---\n${ctx.timeline.slice(0, 1500)}`);
  }
  if (ctx.chapterSummaries) {
    sections.push(`--- CHAPTER SUMMARY ---\n${ctx.chapterSummaries.slice(0, 1000)}`);
  }

  return sections.join('\n\n');
}

export function extractChapterSummary(summaries: string, chapterNumber: number): string {
  const lines = summaries.split('\n');
  let inChapter = false;
  const chapterLines: string[] = [];
  const heading = new RegExp(`(?:chapter|chương)\\s*${chapterNumber}\\b`, 'iu');

  for (const line of lines) {
    if (heading.test(line)) {
      inChapter = true;
      chapterLines.length = 0;
      chapterLines.push(line);
      continue;
    }
    if (inChapter) {
      if (line.trim().startsWith('#') && !heading.test(line)) {
        break;
      }
      chapterLines.push(line);
    }
  }

  return chapterLines.join('\n');
}
