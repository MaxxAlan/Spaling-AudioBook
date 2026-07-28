import { z } from 'zod';

export const provenanceSchema = z.object({
  sourcePath: z.string(), lineStart: z.number().int().nonnegative(), lineEnd: z.number().int().nonnegative(),
});
export const evidenceSchema = z.object({
  source: z.enum(['chapter', 'master', 'rules', 'state', 'inference']),
  sourcePath: z.string(), lineStart: z.number().int().nonnegative(), lineEnd: z.number().int().nonnegative(),
  quote: z.string().optional(),
});
export type Provenance = z.infer<typeof provenanceSchema>;
export type Evidence = z.infer<typeof evidenceSchema>;
