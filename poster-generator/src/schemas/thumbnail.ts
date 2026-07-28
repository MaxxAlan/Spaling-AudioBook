import { z } from 'zod';
import { evidenceSchema } from './common.js';
import { scoresSchema } from './scene.js';

export const conceptTypeSchema = z.enum(['character', 'climax', 'mystery', 'symbolic']);
export const thumbnailConceptSchema = z.object({ type: conceptTypeSchema, sceneId: z.string(), title: z.string(), visualHook: z.string(), reason: z.string(), spoilerLevel: z.enum(['low','medium','high']), scores: scoresSchema, weightedScore: z.number() });
const composition = z.object({ subjectPosition: z.string(), cameraShot: z.string(), cameraAngle: z.string(), depth: z.string(), cropSafety: z.string(), visualFlow: z.string() });
export const thumbnailBriefSchema = z.object({
  chapter: z.object({ number: z.number(), title: z.string(), timeline: z.string() }),
  selectedConcept: z.object({ type: conceptTypeSchema, sceneId: z.string(), reason: z.string(), spoilerLevel: z.enum(['low','medium','high']) }),
  coreVisualIdea: z.string(), mainSubject: z.object({ characterId: z.string(), visualDescription: z.string(), pose: z.string(), expression: z.string(), action: z.string(), chapterState: z.string() }),
  secondarySubjects: z.array(z.union([z.string(), z.object({ name: z.string(), description: z.string() })])),
  foreground: z.string(), midground: z.string(), background: z.string(), environment: z.string(),
  requiredVisuals: z.array(z.string()).min(1).optional(),
  narrativeMeaning: z.array(z.string()).default([]),
  representationMode: z.enum([
    'literal_action', 'dialogue_reaction', 'inner_turn', 'memory',
    'atmosphere', 'relationship', 'revelation', 'transition',
  ]).default('literal_action'),
  magicEffects: z.array(z.string()), objects: z.array(z.string()), creatures: z.array(z.string()), visualSymbols: z.array(z.string()), lighting: z.string(), colorPalette: z.array(z.string()),
  dialogue: z.string().optional(),
  importantObjects: z.string().optional(),
  youtubeComposition: composition, tiktokComposition: composition,
  style: z.object({ genre: z.string(), rendering: z.string(), texture: z.string(), detail: z.string() }),
  continuityRequirements: z.array(z.string()), forbiddenElements: z.array(z.string()), evidence: z.array(evidenceSchema).optional(),
});
export type ConceptType = z.infer<typeof conceptTypeSchema>;
export type ThumbnailConcept = z.infer<typeof thumbnailConceptSchema>;
export type ThumbnailBrief = z.infer<typeof thumbnailBriefSchema>;
