import type { ThumbnailBrief } from '../schemas/thumbnail.js';

export function filterFutureSpoilers<T extends string>(values: T[], futureSpoilers: readonly string[]): T[] {
  const forbidden = new Set(futureSpoilers.flatMap((item) => item.toLocaleLowerCase('vi').split(/[^\p{L}\p{N}]+/u)).filter((token) => token.length > 5));
  return values.filter((value) => !value.toLocaleLowerCase('vi').split(/[^\p{L}\p{N}]+/u).some((token) => forbidden.has(token)));
}
export function assertBriefSpoilerSafe(brief: ThumbnailBrief, chapterText: string): void {
  const haystack = chapterText.toLocaleLowerCase('vi');
  for (const subject of brief.secondarySubjects) {
    const name = typeof subject === 'string' ? subject : subject.name;
    if (name && !haystack.includes(name.toLocaleLowerCase('vi'))) throw new Error(`Spoiler firewall: secondary subject "${name}" does not appear in the chapter.`);
  }
}
