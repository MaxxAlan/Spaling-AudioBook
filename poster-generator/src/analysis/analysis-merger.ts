import type { ChunkAnalysis, ChapterAnalysis, Scene, Dialogue, ImportantObject, ImportantEvent } from '../schemas/chapter.js';

function unique(values: string[]): string[] { return [...new Set(values.filter(Boolean))]; }
function mergeDialogues(chunks: ChunkAnalysis[]): Dialogue[] {
  const all: Dialogue[] = [];
  const seen = new Set<string>();
  for (const chunk of chunks) {
    for (const d of chunk.dialogues ?? []) {
      const key = `${d.speaker}:${d.text.slice(0, 50)}`;
      if (!seen.has(key)) { seen.add(key); all.push(d); }
    }
  }
  return all;
}
function mergeObjects(chunks: ChunkAnalysis[]): ImportantObject[] {
  const all: ImportantObject[] = [];
  const seen = new Set<string>();
  for (const chunk of chunks) {
    for (const o of chunk.importantObjects ?? []) {
      if (!seen.has(o.name)) { seen.add(o.name); all.push(o); }
    }
  }
  return all;
}
function mergeEvents(chunks: ChunkAnalysis[]): ImportantEvent[] {
  const all: ImportantEvent[] = [];
  const seen = new Set<string>();
  for (const chunk of chunks) {
    for (const e of chunk.importantEvents ?? []) {
      const key = e.event.slice(0, 60);
      if (!seen.has(key)) { seen.add(key); all.push(e); }
    }
  }
  return all;
}
export function mergeChunkAnalyses(chunks: ChunkAnalysis[], chapterNumber: number, title: string, timeline: string): ChapterAnalysis {
  if (!chunks.length) throw new Error('Cannot merge zero chapter chunks.');
  const ordered = [...chunks].sort((a, b) => a.chunkIndex - b.chunkIndex); const seen = new Set<string>(); const scenes: Scene[] = [];
  for (const scene of ordered.flatMap((chunk) => chunk.scenes)) { const key = `${scene.startLine}:${scene.action}`; if (!seen.has(key)) { seen.add(key); scenes.push({ ...scene, sceneId: `scene-${String(scenes.length + 1).padStart(2, '0')}` }); } }
  const dialogues = mergeDialogues(ordered);
  const importantObjects = mergeObjects(ordered);
  const importantEvents = mergeEvents(ordered);
  return { chapterNumber, chapterTitle: title, timeline, summary: ordered.map((item) => item.summary).join(' ').slice(0, 4000), povCharacters: unique(ordered.flatMap((item) => item.povCharacters)), charactersPresent: unique(ordered.flatMap((item) => item.charactersPresent)), locations: unique(ordered.flatMap((item) => item.locations)), events: unique(ordered.flatMap((item) => item.events)), revealedFacts: unique(ordered.flatMap((item) => item.revealedFacts)), emotionalArc: unique(ordered.flatMap((item) => item.emotionalArc)), magicUsed: unique(ordered.flatMap((item) => item.magicUsed)), objects: unique(ordered.flatMap((item) => item.objects)), creatures: unique(ordered.flatMap((item) => item.creatures)), visualMotifs: unique(ordered.flatMap((item) => item.visualMotifs)), scenes, dialogues, importantObjects, importantEvents };
}
