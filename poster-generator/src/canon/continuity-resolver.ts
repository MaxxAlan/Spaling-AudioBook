import type { CanonRules } from '../schemas/canon.js';
import type { ChapterAnalysis } from '../schemas/chapter.js';
import type { MasterPosition } from '../schemas/master.js';

export interface ContinuityWarning { field: string; higherPrioritySource: string; lowerPrioritySource: string; decision: string; reason: string; evidence: Array<{ sourcePath: string; lineStart: number; lineEnd: number }>; }
export interface ResolvedContext { timeline: string; canonFacts: string[]; chapterFacts: string[]; allowedVisualFacts: string[]; futureSpoilers: string[]; warnings: ContinuityWarning[]; }
export function resolveContinuity(canon: CanonRules, master: MasterPosition, chapter: ChapterAnalysis): ResolvedContext {
  const warnings: ContinuityWarning[] = [];
  if (chapter.timeline && master.timeline && chapter.timeline !== master.timeline && !master.timeline.includes(chapter.timeline)) warnings.push({ field: 'timeline', higherPrioritySource: 'master.md', lowerPrioritySource: 'chapter.txt', decision: master.timeline, reason: 'master.md has higher priority than chapter inference for timeline placement', evidence: [] });
  const canonFacts = [...canon.hardCanon, ...canon.timelineRules, ...canon.worldRules, ...canon.magicRules, ...canon.characters].map((item) => item.value);
  const chapterFacts = [...chapter.events, ...chapter.revealedFacts, ...chapter.magicUsed];
  return { timeline: master.timeline, canonFacts, chapterFacts, allowedVisualFacts: chapterFacts, futureSpoilers: master.futureSpoilers, warnings };
}
