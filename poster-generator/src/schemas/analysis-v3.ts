import { z } from 'zod';
import { evidenceSchema } from './common.js';

const nullableText = z.string().nullable();

export const structuralCandidateSchema = z.object({
  candidateId: z.string(),
  lineStart: z.number().int().positive(),
  lineEnd: z.number().int().positive(),
  structuralReason: z.string(),
  evidence: z.array(evidenceSchema).min(1),
});

export const structuralCandidatesSchema = z.object({
  lineCount: z.number().int().positive(),
  contentLines: z.array(z.number().int().positive()),
  separators: z.array(z.number().int().positive()),
  candidates: z.array(structuralCandidateSchema).min(1),
});

export const narrativeBlockSchema = z.object({
  blockId: z.string(),
  lineStart: z.number().int().positive(),
  lineEnd: z.number().int().positive(),
  povHolder: nullableText,
  location: nullableText,
  timeContext: nullableText,
  activeCharacters: z.array(z.string()),
  structuralReason: z.string(),
  confidence: z.number().min(0).max(1),
  evidence: z.array(evidenceSchema).min(1),
});

export const beatTypeSchema = z.enum([
  'setup', 'revelation', 'decision', 'reversal', 'conflict', 'belief_change',
  'relationship_change', 'goal_change', 'threat_escalation', 'transition',
  'resolution', 'foreshadowing',
]);

export const narrativeBeatSchema = z.object({
  beatId: z.string(),
  blockId: z.string(),
  lineStart: z.number().int().positive(),
  lineEnd: z.number().int().positive(),
  beatType: beatTypeSchema,
  setup: z.string(),
  pressure: z.string(),
  turningPoint: z.string(),
  resultingState: z.string(),
  dramaticFunction: z.string(),
  evidence: z.array(evidenceSchema).min(1),
});

export const workerExtractionPlanSchema = z.object({
  blockId: z.string(),
  lineStart: z.number().int().positive(),
  lineEnd: z.number().int().positive(),
  expectedPov: nullableText,
  expectedLocation: nullableText,
  requiredEventTypes: z.array(z.string()).min(1),
  minimumEvidenceItems: z.number().int().min(1),
  blockComplexity: z.enum(['low', 'medium', 'high']).default('medium'),
  recommendedWorker: z.string().default('qwen2.5:1.5b'),
});

export const narrativeSpineSchema = z.object({
  blocks: z.array(narrativeBlockSchema).min(1),
  beats: z.array(narrativeBeatSchema).min(1),
  unresolvedQuestions: z.array(z.string()),
  workerExtractionPlan: z.array(workerExtractionPlanSchema).min(1),
});

export const storyEventSchema = z.object({
  eventId: z.string(),
  beatId: z.string(),
  lineStart: z.number().int().positive(),
  lineEnd: z.number().int().positive(),
  eventType: z.string(),
  actor: nullableText,
  action: z.string().min(1),
  stateBefore: nullableText,
  stateAfter: nullableText,
  target: nullableText,
  location: nullableText,
  evidence: z.array(evidenceSchema).min(1),
  resolutionRequired: z.boolean().default(false),
});

export const extractionResultSchema = z.object({
  blockId: z.string(),
  requestedBackend: z.string(),
  actualBackend: z.string(),
  fallbackReason: nullableText,
  events: z.array(storyEventSchema).max(32),
});

export const conflictSchema = z.object({
  conflictId: z.string(),
  blockId: z.string(),
  kind: z.enum(['coverage_gap', 'evidence_gap', 'spine_worker_conflict', 'unresolved_actor']),
  lineStart: z.number().int().positive(),
  lineEnd: z.number().int().positive(),
  reason: z.string(),
  resolutionRequired: z.boolean(),
});

export const analysisSceneSchema = z.object({
  sceneId: z.string(),
  sourceBlockIds: z.array(z.string()).min(1),
  sourceBeatIds: z.array(z.string()).min(1),
  sourceEventIds: z.array(z.string()),
  lineStart: z.number().int().positive(),
  lineEnd: z.number().int().positive(),
  povHolder: nullableText,
  location: z.string(),
  sceneFunction: z.string().min(1),
  visualAnchor: z.string().min(1),
  requiredVisualFacts: z.array(z.string()).min(1).default(['source-grounded visible action']),
  forbiddenVisuals: z.array(z.string()).default([]),
  emotionalCenter: z.string().min(1),
  turningPoint: z.string().min(1),
  continuityRequirements: z.array(z.string()),
  mustPreserve: z.array(z.string()),
  importance: z.number().min(0).max(1),
  representationMode: z.enum([
    'literal_action', 'dialogue_reaction', 'inner_turn', 'memory',
    'atmosphere', 'relationship', 'revelation', 'transition',
  ]).default('literal_action'),
  authorialIntent: z.string().default('preserve the source event and its consequence'),
  narrativeSubtext: z.array(z.string()).default([]),
  sensoryAnchors: z.array(z.string()).default([]),
  evidence: z.array(evidenceSchema).min(1),
});

export const sceneArchitectureSchema = z.object({
  operations: z.array(z.object({
    operation: z.enum([
      'APPROVE', 'MERGE_BEATS', 'SPLIT_BEAT', 'REASSIGN_POV',
      'REQUEST_REEXTRACTION', 'REQUEST_EVIDENCE', 'REVISE_RANGE',
      'CREATE_SCENE', 'MERGE_SCENES', 'SPLIT_SCENE',
    ]),
    lineStart: z.number().int().positive().nullable(),
    lineEnd: z.number().int().positive().nullable(),
    backend: nullableText,
    reason: z.string(),
  })),
  scenes: z.array(analysisSceneSchema).min(1),
});

export const coverageReportSchema = z.object({
  lineCount: z.number().int().positive(),
  contentLineCount: z.number().int().nonnegative(),
  coveredLineCount: z.number().int().nonnegative(),
  uncoveredLines: z.array(z.number().int().positive()),
  coverage: z.number().min(0).max(1),
  ideaUnitCount: z.number().int().nonnegative().default(0),
  coveredIdeaUnitCount: z.number().int().nonnegative().default(0),
  uncoveredIdeaLines: z.array(z.number().int().positive()).default([]),
  ideaCoverage: z.number().min(0).max(1).default(1),
});

export const validationReportSchema = z.object({
  valid: z.boolean(),
  errors: z.array(z.string()),
  warnings: z.array(z.string()),
  blockCount: z.number().int().nonnegative(),
  beatCount: z.number().int().nonnegative(),
  eventCount: z.number().int().nonnegative(),
  sceneCount: z.number().int().nonnegative(),
});

export type StructuralCandidates = z.infer<typeof structuralCandidatesSchema>;
export type NarrativeBlock = z.infer<typeof narrativeBlockSchema>;
export type NarrativeBeat = z.infer<typeof narrativeBeatSchema>;
export type WorkerExtractionPlan = z.infer<typeof workerExtractionPlanSchema>;
export type NarrativeSpine = z.infer<typeof narrativeSpineSchema>;
export type StoryEvent = z.infer<typeof storyEventSchema>;
export type ExtractionResult = z.infer<typeof extractionResultSchema>;
export type AnalysisConflict = z.infer<typeof conflictSchema>;
export type AnalysisScene = z.infer<typeof analysisSceneSchema>;
export type SceneArchitecture = z.infer<typeof sceneArchitectureSchema>;
export type CoverageReport = z.infer<typeof coverageReportSchema>;
export type ValidationReport = z.infer<typeof validationReportSchema>;
