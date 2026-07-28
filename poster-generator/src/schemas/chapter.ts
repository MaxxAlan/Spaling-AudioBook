import { z } from 'zod';
import { evidenceSchema } from './common.js';

export const dialogueSchema = z.object({
  speaker: z.string(),
  text: z.string(),
  emotion: z.string(),
  context: z.string(),
  visualMoment: z.string().optional(),
});

export const importantObjectSchema = z.object({
  name: z.string(),
  description: z.string(),
  significance: z.string(),
  visualDetails: z.string(),
});

export const importantEventSchema = z.object({
  event: z.string(),
  impact: z.string(),
  visualMoment: z.string(),
});

export const sceneSchema = z.object({
  sceneId: z.string(), startLine: z.number().int().positive(), endLine: z.number().int().positive(), location: z.string(),
  time: z.string(), characters: z.array(z.string()), objective: z.string(), opposition: z.string(), action: z.string(),
  turningPoint: z.string(), result: z.string(), emotion: z.string(), sensoryDetails: z.array(z.string()),
  visualElements: z.array(z.string()), thumbnailPotential: z.array(z.string()), spoilerLevel: z.enum(['low', 'medium', 'high']),
  evidence: z.array(evidenceSchema),
  representationMode: z.enum([
    'literal_action', 'dialogue_reaction', 'inner_turn', 'memory',
    'atmosphere', 'relationship', 'revelation', 'transition',
  ]).optional(),
  authorialIntent: z.string().optional(),
  narrativeSubtext: z.array(z.string()).optional(),
  mood: z.string().optional(),
  lighting: z.string().optional(),
  dominantColors: z.array(z.string()).optional(),
  dialogues: z.array(dialogueSchema).optional(),
});

export const chapterAnalysisSchema = z.object({
  chapterNumber: z.number().int().positive(), chapterTitle: z.string(), timeline: z.string(), summary: z.string(),
  povCharacters: z.array(z.string()), charactersPresent: z.array(z.string()), locations: z.array(z.string()),
  events: z.array(z.string()), revealedFacts: z.array(z.string()), emotionalArc: z.array(z.string()), magicUsed: z.array(z.string()),
  objects: z.array(z.string()), creatures: z.array(z.string()), visualMotifs: z.array(z.string()), scenes: z.array(sceneSchema),
  dialogues: z.array(dialogueSchema).optional(),
  importantObjects: z.array(importantObjectSchema).optional(),
  importantEvents: z.array(importantEventSchema).optional(),
});
export const chunkAnalysisSchema = chapterAnalysisSchema.omit({ chapterNumber: true, chapterTitle: true, timeline: true }).extend({
  chunkIndex: z.number().int().nonnegative(), startLine: z.number().int().positive(), endLine: z.number().int().positive(),
});
export type Dialogue = z.infer<typeof dialogueSchema>;
export type ImportantObject = z.infer<typeof importantObjectSchema>;
export type ImportantEvent = z.infer<typeof importantEventSchema>;
export type Scene = z.infer<typeof sceneSchema>;
export type ChapterAnalysis = z.infer<typeof chapterAnalysisSchema>;
export type ChunkAnalysis = z.infer<typeof chunkAnalysisSchema>;
