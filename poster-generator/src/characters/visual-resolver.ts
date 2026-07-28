import type { CanonRules } from '../schemas/canon.js';
import type { ChapterAnalysis } from '../schemas/chapter.js';
import type { CharacterVisual } from '../schemas/character.js';
import type { LoadedSource } from '../sources/loader.js';
import { mapReferences } from './reference-loader.js';
import { slugify } from '../utils/paths.js';

function match(text: string, expressions: RegExp[]): string | null {
  for (const expression of expressions) {
    const found = text.match(expression);
    if (found?.[1]) return found[1].trim();
  }
  return null;
}

function numberMatch(text: string, expressions: RegExp[]): number | null {
  const value = match(text, expressions);
  return value ? Number(value) : null;
}

function relevantCanon(canon: CanonRules, name: string): string {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return [...canon.characters, ...canon.hardCanon, ...canon.visualMotifs, ...canon.magicRules]
    .filter((item) => new RegExp(escaped, 'iu').test(item.value))
    .map((item) => item.value)
    .join('\n');
}

function genderMatch(text: string): string | null {
  if (/\b(?:nữ|cô gái|thiếu nữ|nàng|cô ấy|bà ấy)\b/iu.test(text)) return 'female';
  if (/\b(?:nam|chàng trai|thiếu niên|hắn|anh ấy|ông ấy)\b/iu.test(text)) return 'male';
  return null;
}

export function resolveCharacterVisuals(
  analysis: ChapterAnalysis,
  chapter: LoadedSource,
  canon: CanonRules,
  references: string[],
): CharacterVisual[] {
  return analysis.charactersPresent.map((name) => {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const canonText = relevantCanon(canon, name);
    const chapterLines = chapter.lines
      .map((value, i) => ({ value, i }))
      .filter(({ value }) => new RegExp(escaped, 'iu').test(value));
    const chapterText = chapterLines.map(({ value }) => value).join('\n');
    const all = `${canonText}\n${chapterText}`;

    const realAge = numberMatch(canonText, [
      /tuổi thật\D{0,20}(\d{1,3})\b/iu,
      /(?:tuổi thật|đã)\D{0,15}(\d{1,3})\s*tuổi/iu,
    ]);
    const visibleAge = numberMatch(all, [
      /(?:trông|ngoại hình|dáng vẻ|nhìn)[^\n]{0,35}?(\d{1,3})\s*tuổi/iu,
      /tầm\s*(\d{1,3})\s*tuổi/iu,
    ]) ?? realAge;
    const eyes = match(canonText, [
      /mắt\s+chuyển\s+([^,.;]{2,24})/iu,
      /(?:đôi )?mắt\s+([^,.]{2,24}?)(?=\s+(?:của|quét|nhìn|ánh|đang|vẫn)\b|[,.;])/iu,
    ]);
    const hair = match(canonText, [/mái tóc\s+([^,.]{2,24}?)(?=\s+của\b|[,.;])/iu]);
    const clothing = match(all, [
      /(?:mặc|khoác)\s+([^,.]{3,48})/iu,
      /(?:áo|váy|giáp|trường bào)\s+([^,.]{2,40})/iu,
    ]);
    const line = chapterLines[0];
    const evidence = line ? [{
      source: 'chapter' as const,
      sourcePath: chapter.path,
      lineStart: line.i + 1,
      lineEnd: line.i + 1,
      quote: line.value.trim().slice(0, 240),
    }] : [];
    const appearance = { face: null, hair, eyes, skin: null, body: null, clothing, accessories: [] as string[] };
    const unknown = (['face', 'hair', 'eyes', 'skin', 'body', 'clothing'] as const)
      .filter((attribute) => appearance[attribute] === null);

    return {
      characterId: slugify(name),
      name,
      identity: { realAge, visibleAge, gender: genderMatch(all) },
      canonicalAppearance: appearance,
      chapterState: {
        emotion: analysis.emotionalArc[0] ?? '',
        injuries: /bị thương|chảy máu|trật chân/iu.test(chapterText) ? ['injury described in chapter'] : [],
        temporaryChanges: [],
        magicEffects: analysis.magicUsed.filter((value) => new RegExp(escaped, 'iu').test(value)).slice(0, 4),
      },
      lockedAttributes: [
        eyes ? 'eyes' : '',
        hair ? 'hair' : '',
        clothing ? 'clothing' : '',
        visibleAge ? 'visibleAge' : '',
        genderMatch(all) ? 'gender' : '',
      ].filter(Boolean),
      provisionalAttributes: unknown.map((attribute) => `${attribute}: stable provisional design required`),
      unknownAttributes: unknown,
      referenceImages: mapReferences(name, references),
      evidence,
    };
  });
}
