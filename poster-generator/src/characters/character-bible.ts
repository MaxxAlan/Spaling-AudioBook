/**
 * Character Bible – khóa chặt visual identity xuyên suốt bộ truyện.
 *
 * Mục tiêu P0:
 * - face / hair / eyes / skin / body KHÔNG ĐƯỢC thay đổi sau khi lock.
 * - Chỉ clothing, injuries, temporaryEffects được phép biến đổi theo chapter.
 * - Inject identityPrompt + reference images mạnh vào mọi lần generate ảnh.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { z } from 'zod';
import type { CharacterVisual } from '../schemas/character.js';
import type { CharacterState } from '../schemas/character.js';

// ── Schema ──────────────────────────────────────────────────────────
export const characterBibleSchema = z.object({
  characterId: z.string(),
  name: z.string(),
  version: z.number().int().positive(),
  lockedAt: z.string(),
  sourceChapters: z.array(z.string()),
  identity: z.object({
    realAge: z.number().nullable(),
    visibleAge: z.number().nullable(),
    gender: z.string().nullable(),
  }),
  lockedAppearance: z.object({
    face: z.string(),
    hair: z.string(),
    eyes: z.string(),
    skin: z.string(),
    body: z.string(),
  }),
  mutableAppearance: z.object({
    clothing: z.string(),
    accessories: z.array(z.string()),
    injuries: z.array(z.string()),
    temporaryEffects: z.array(z.string()),
  }),
  referenceImages: z.array(z.string()),
  identityPrompt: z.string(),
  evidence: z.array(z.any()).default([]),
});

export type CharacterBible = z.infer<typeof characterBibleSchema>;

const HARD_LOCKED = ['face', 'hair', 'eyes', 'skin', 'body'] as const;

// ── Paths ────────────────────────────────────────────────────────────
export function bibleDir(projectRoot: string, characterId: string): string {
  return path.join(projectRoot, 'characters', characterId);
}

export function biblePath(projectRoot: string, characterId: string): string {
  return path.join(bibleDir(projectRoot, characterId), 'bible.json');
}

// ── Load / Save ──────────────────────────────────────────────────────
export async function loadCharacterBible(
  projectRoot: string,
  characterId: string,
): Promise<CharacterBible | null> {
  const file = biblePath(projectRoot, characterId);
  try {
    const raw = JSON.parse(await fs.readFile(file, 'utf8'));
    return characterBibleSchema.parse(raw);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') return null;
    throw err;
  }
}

export async function saveCharacterBible(
  projectRoot: string,
  bible: CharacterBible,
): Promise<void> {
  const dir = bibleDir(projectRoot, bible.characterId);
  await fs.mkdir(dir, { recursive: true });
  const file = path.join(dir, 'bible.json');
  await fs.writeFile(file, `${JSON.stringify(bible, null, 2)}\n`, 'utf8');
}

// ── Build identity prompt mạnh ───────────────────────────────────────
export function buildIdentityPrompt(bible: CharacterBible): string {
  const a = bible.lockedAppearance;
  const id = bible.identity;
  const parts = [
    `consistent character identity lock`,
    `name: ${bible.name}`,
    id.gender ? `gender: ${id.gender}` : '',
    id.visibleAge != null ? `apparent age: ${id.visibleAge}` : '',
    `face: ${a.face}`,
    `hair: ${a.hair}`,
    `eyes: ${a.eyes}`,
    `skin: ${a.skin}`,
    `body: ${a.body}`,
    `same face, same hair, same eyes, same skin tone across all frames`,
    `do not change facial structure, hair color, eye color or skin tone`,
  ].filter(Boolean);
  return parts.join(', ');
}

// ── Tạo Bible từ CharacterVisual (chapter 1 / master) ────────────────
export function createBibleFromVisual(
  visual: CharacterVisual,
  sourceChapter: string,
  existingRefs: string[] = [],
): CharacterBible {
  const fallback = {
    face: 'distinct angular face with clear bone structure',
    hair: 'straight dark hair, medium length',
    eyes: 'deep brown eyes',
    skin: 'neutral medium skin tone',
    body: 'lean athletic build',
  };
  const ca = visual.canonicalAppearance;
  const lockedAppearance = {
    face: ca.face ?? fallback.face,
    hair: ca.hair ?? fallback.hair,
    eyes: ca.eyes ?? fallback.eyes,
    skin: ca.skin ?? fallback.skin,
    body: ca.body ?? fallback.body,
  };

  const bible: CharacterBible = {
    characterId: visual.characterId,
    name: visual.name,
    version: 1,
    lockedAt: new Date().toISOString(),
    sourceChapters: [sourceChapter],
    identity: { ...visual.identity },
    lockedAppearance,
    mutableAppearance: {
      clothing: ca.clothing ?? 'plain layered clothing',
      accessories: [...(ca.accessories ?? [])],
      injuries: [...(visual.chapterState?.injuries ?? [])],
      temporaryEffects: [...(visual.chapterState?.temporaryChanges ?? [])],
    },
    referenceImages: [
      ...new Set([...(visual.referenceImages ?? []), ...existingRefs]),
    ],
    identityPrompt: '',
    evidence: visual.evidence ?? [],
  };
  bible.identityPrompt = buildIdentityPrompt(bible);
  return bible;
}

// ── Áp dụng Bible lên CharacterVisual (ưu tiên tuyệt đối) ────────────
export function applyBibleToVisual(
  visual: CharacterVisual,
  bible: CharacterBible,
): CharacterVisual {
  const appearance = { ...visual.canonicalAppearance };

  for (const key of HARD_LOCKED) {
    appearance[key] = bible.lockedAppearance[key];
  }

  if (!appearance.clothing) {
    appearance.clothing = bible.mutableAppearance.clothing;
  }
  if (!appearance.accessories?.length) {
    appearance.accessories = [...bible.mutableAppearance.accessories];
  }

  return {
    ...visual,
    identity: {
      realAge: visual.identity.realAge ?? bible.identity.realAge,
      visibleAge: visual.identity.visibleAge ?? bible.identity.visibleAge,
      gender: visual.identity.gender ?? bible.identity.gender,
    },
    canonicalAppearance: appearance,
    lockedAttributes: [
      ...new Set([...visual.lockedAttributes, ...HARD_LOCKED, 'visibleAge', 'gender']),
    ],
    provisionalAttributes: visual.provisionalAttributes.filter(
      (p) => !HARD_LOCKED.some((h) => p.startsWith(h)),
    ),
    unknownAttributes: visual.unknownAttributes.filter(
      (u) => !(HARD_LOCKED as readonly string[]).includes(u),
    ),
    referenceImages: [
      ...new Set([...bible.referenceImages, ...(visual.referenceImages ?? [])]),
    ],
  };
}

// ── Merge state + Bible (gọi sau resolveCharacterVisuals) ─────────────
export async function enforceBibles(
  projectRoot: string,
  state: CharacterState,
  resolved: CharacterVisual[],
  currentChapter: string,
): Promise<{ state: CharacterState; visuals: CharacterVisual[] }> {
  const nextState = structuredClone(state);
  const nextVisuals: CharacterVisual[] = [];

  for (const visual of resolved) {
    let bible = await loadCharacterBible(projectRoot, visual.characterId);

    if (!bible) {
      bible = createBibleFromVisual(visual, currentChapter);
      await saveCharacterBible(projectRoot, bible);
    } else {
      const mutableChanged =
        (visual.canonicalAppearance.clothing &&
          visual.canonicalAppearance.clothing !== bible.mutableAppearance.clothing) ||
        (visual.chapterState?.injuries?.length ?? 0) > 0;

      if (mutableChanged) {
        bible = {
          ...bible,
          mutableAppearance: {
            clothing:
              visual.canonicalAppearance.clothing ??
              bible.mutableAppearance.clothing,
            accessories:
              visual.canonicalAppearance.accessories?.length
                ? visual.canonicalAppearance.accessories
                : bible.mutableAppearance.accessories,
            injuries: [
              ...new Set([
                ...bible.mutableAppearance.injuries,
                ...(visual.chapterState?.injuries ?? []),
              ]),
            ],
            temporaryEffects: [
              ...new Set([
                ...bible.mutableAppearance.temporaryEffects,
                ...(visual.chapterState?.temporaryChanges ?? []),
              ]),
            ],
          },
          sourceChapters: [
            ...new Set([...bible.sourceChapters, currentChapter]),
          ],
        };
        await saveCharacterBible(projectRoot, bible);
      }
    }

    const enforced = applyBibleToVisual(visual, bible);
    nextVisuals.push(enforced);

    const prev = nextState.characters[visual.characterId];
    nextState.characters[visual.characterId] = {
      ...(prev ?? enforced),
      ...enforced,
      revisions: prev?.revisions ?? [],
      lockedAttributes: [
        ...new Set([
          ...(prev?.lockedAttributes ?? []),
          ...enforced.lockedAttributes,
          ...HARD_LOCKED,
        ]),
      ],
    };
  }

  return { state: nextState, visuals: nextVisuals };
}

// ── Prompt inject helper (dùng khi gọi image generator) ──────────────
export function injectIdentityIntoPrompt(
  basePrompt: string,
  bible: CharacterBible | null,
): string {
  if (!bible) return basePrompt;
  const refs = bible.referenceImages.length
    ? `reference images: ${bible.referenceImages.join(', ')}`
    : '';
  return [
    bible.identityPrompt,
    refs,
    basePrompt,
    'different face, different hair color, different eye color, different skin tone, inconsistent character, face morph',
  ]
    .filter(Boolean)
    .join('. ');
}
