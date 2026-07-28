import { z } from 'zod';
import { sceneSchema } from './chapter.js';

export const scoresSchema = z.object({
  chapterRelevance: z.number().min(0).max(10), visualImpact: z.number().min(0).max(10),
  smallScreenReadability: z.number().min(0).max(10), mainSubjectClarity: z.number().min(0).max(10),
  emotionalImpact: z.number().min(0).max(10), curiosity: z.number().min(0).max(10),
  platformAdaptability: z.number().min(0).max(10), continuityAccuracy: z.number().min(0).max(10), spoilerSafety: z.number().min(0).max(10),
});
export const sceneCandidateSchema = z.object({ scene: sceneSchema, scores: scoresSchema, weightedScore: z.number(), rationale: z.string() });
export type SceneScores = z.infer<typeof scoresSchema>;
export type SceneCandidate = z.infer<typeof sceneCandidateSchema>;
