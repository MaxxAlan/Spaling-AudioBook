import { z } from 'zod';
import { provenanceSchema } from './common.js';

const item = z.object({ value: z.string(), provenance: provenanceSchema });
export const canonSchema = z.object({
  timelineRules: z.array(item), hardCanon: z.array(item), worldRules: z.array(item), magicRules: z.array(item),
  characters: z.array(item), factions: z.array(item), locations: z.array(item), visualMotifs: z.array(item),
  forbiddenContradictions: z.array(item),
});
export type CanonRules = z.infer<typeof canonSchema>;
