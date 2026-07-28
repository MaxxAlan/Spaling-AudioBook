import { z } from 'zod';
import { evidenceSchema } from './common.js';

const nullableText = z.string().nullable();
export const characterVisualSchema = z.object({
  characterId: z.string(), name: z.string(), identity: z.object({ realAge: z.number().nullable(), visibleAge: z.number().nullable(), gender: nullableText }),
  canonicalAppearance: z.object({ face: nullableText, hair: nullableText, eyes: nullableText, skin: nullableText, body: nullableText, clothing: nullableText, accessories: z.array(z.string()) }),
  chapterState: z.object({ emotion: z.string(), injuries: z.array(z.string()), temporaryChanges: z.array(z.string()), magicEffects: z.array(z.string()) }),
  lockedAttributes: z.array(z.string()), provisionalAttributes: z.array(z.string()), unknownAttributes: z.array(z.string()),
  referenceImages: z.array(z.string()), evidence: z.array(evidenceSchema),
});
export const revisionSchema = z.object({ attribute: z.string(), oldValue: z.string(), newValue: z.string(), reason: z.string(), source: z.string(), createdAt: z.string() });
export const characterStateEntrySchema = characterVisualSchema.extend({ revisions: z.array(revisionSchema).default([]) });
export const characterStateSchema = z.object({ version: z.literal(1), characters: z.record(z.string(), characterStateEntrySchema) });
export type CharacterVisual = z.infer<typeof characterVisualSchema>;
export type CharacterState = z.infer<typeof characterStateSchema>;
