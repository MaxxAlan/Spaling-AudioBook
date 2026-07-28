import { z } from 'zod';
import { provenanceSchema } from './common.js';

const item = z.object({ value: z.string(), provenance: provenanceSchema });
export const chapterRangeSchema = z.object({
  start: z.number().int().positive(), end: z.number().int().positive(), grandArc: z.string(), volume: z.string(),
  miniArc: z.string(), timeline: z.string(), arcPurpose: z.string(), centralConflict: z.string(),
  provenance: provenanceSchema,
});
export const masterSchema = z.object({
  grandArcs: z.array(item), volumes: z.array(item), miniArcs: z.array(item), chapterRanges: z.array(chapterRangeSchema),
  lockedMilestones: z.array(item), timelineTransitions: z.array(item),
});
export const masterPositionSchema = z.object({
  chapterNumber: z.number().int().positive(), grandArc: z.string(), volume: z.string(), miniArc: z.string(),
  timeline: z.string(), arcPurpose: z.string(), centralConflict: z.string(), lockedMilestones: z.array(z.string()),
  futureSpoilers: z.array(z.string()),
});
export type MasterIndex = z.infer<typeof masterSchema>;
export type MasterPosition = z.infer<typeof masterPositionSchema>;
