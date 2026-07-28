import path from 'node:path';
import os from 'node:os';
import { z } from 'zod';
import type { LoadedSource } from '../sources/loader.js';
import type { TextAIProvider } from '../providers/text/types.js';
import type { ChapterAnalysis } from '../schemas/chapter.js';
import {
  analysisSceneSchema,
  conflictSchema,
  coverageReportSchema,
  extractionResultSchema,
  narrativeSpineSchema,
  sceneArchitectureSchema,
  storyEventSchema,
  structuralCandidatesSchema,
  validationReportSchema,
  workerExtractionPlanSchema,
  type AnalysisConflict,
  type AnalysisScene,
  type CoverageReport,
  type ExtractionResult,
  type NarrativeBeat,
  type NarrativeSpine,
  type SceneArchitecture,
  type StoryEvent,
  type StructuralCandidates,
  type ValidationReport,
  type WorkerExtractionPlan,
} from '../schemas/analysis-v3.js';
import { segmentStructure } from './structural-segmenter.js';
import { AnalysisArtifactStore, fullSha256 } from './artifact-store.js';
import {
  GUIDED_WORKER_PROMPT_VERSION,
  GUIDED_WORKER_SYSTEM,
  NARRATIVE_SPINE_PROMPT_VERSION,
  NARRATIVE_SPINE_SYSTEM,
  SCENE_ARCHITECTURE_PROMPT_VERSION,
  SCENE_ARCHITECTURE_SYSTEM,
} from '../prompts/analysis-v3.js';

export type AnalysisProfile = 'fast' | 'balanced' | 'quality' | 'all-7b';

export interface AnalysisV3Options {
  source: LoadedSource;
  chapterNumber: number;
  timeline: string;
  context: string;
  directory: string;
  profile: AnalysisProfile;
  directorModel: string;
  workerModel: string;
  targetSceneCount: number;
  directorContextTokens?: number;
  directorMaxTokens?: number;
  createDirector: () => TextAIProvider;
  createWorker: () => TextAIProvider;
  onProgress?: (message: string) => void;
}

export interface AnalysisV3Result {
  chapterAnalysis: ChapterAnalysis;
  spine: NarrativeSpine;
  events: StoryEvent[];
  scenes: AnalysisScene[];
  conflicts: AnalysisConflict[];
  coverage: CoverageReport;
  validation: ValidationReport;
  manifest: ReturnType<AnalysisArtifactStore['snapshot']>;
}

const IMPLEMENTATION_VERSION = 'analysis-v3.4.0-literary';

function estimateTokens(text: string): number {
  return Math.ceil(text.length / 3);
}

function compactDirectorPrompt(
  source: LoadedSource,
  structural: StructuralCandidates,
  context: string,
  maxChars: number,
): string {
  const excerpts = structural.candidates.map((candidate) => {
    const indexes = [
      candidate.lineStart, candidate.lineStart + 1,
      Math.floor((candidate.lineStart + candidate.lineEnd) / 2),
      candidate.lineEnd - 1, candidate.lineEnd,
    ].filter((line, index, values) =>
      line >= candidate.lineStart && line <= candidate.lineEnd && values.indexOf(line) === index,
    );
    return `${candidate.candidateId} lines ${candidate.lineStart}-${candidate.lineEnd}:\n${
      indexes.map((line) => `${line}: ${(source.lines[line - 1] ?? '').slice(0, 320)}`).join('\n')
    }`;
  }).join('\n\n');
  const prompt = `Canon/context (compact):\n${context.slice(0, 6000)}

Structural candidates (all ranges must be covered):
${JSON.stringify(structural)}

Representative source evidence from every block:
${excerpts}

Build the complete narrative spine across every structural range. Workers will inspect all source lines later.`;
  return prompt.slice(0, maxChars);
}

function groundedSpineSchema(source: LoadedSource, structural: StructuralCandidates) {
  return narrativeSpineSchema.superRefine((spine, context) => {
    const minimumBlocks = Math.max(1, structural.candidates.length - 2);
    if (spine.blocks.length < minimumBlocks || spine.blocks.length > structural.candidates.length + 2) {
      context.addIssue({ code: 'custom', message: `Expected ${minimumBlocks}-${structural.candidates.length + 2} grounded blocks, received ${spine.blocks.length}.` });
    }
    const blockIds = new Set(spine.blocks.map((block) => block.blockId));
    for (const block of spine.blocks) {
      if (block.lineStart < 1 || block.lineEnd > source.lines.length || block.lineStart > block.lineEnd) {
        context.addIssue({ code: 'custom', message: `Block ${block.blockId} has source range outside 1-${source.lines.length}.` });
      }
      for (const evidence of block.evidence) {
        if (evidence.lineStart < block.lineStart || evidence.lineEnd > block.lineEnd || evidence.lineEnd > source.lines.length) {
          context.addIssue({ code: 'custom', message: `Block ${block.blockId} has invalid evidence range.` });
        }
      }
      const blockText = source.lines.slice(block.lineStart - 1, block.lineEnd).join(' ').toLocaleLowerCase('vi');
      for (const character of block.activeCharacters) {
        if (character.trim() && !blockText.includes(character.trim().toLocaleLowerCase('vi'))) {
          context.addIssue({ code: 'custom', message: `Block ${block.blockId} names character "${character}" outside its source span.` });
        }
      }
    }
    for (const beat of spine.beats) {
      const block = spine.blocks.find((item) => item.blockId === beat.blockId);
      if (!block || beat.lineStart < block.lineStart || beat.lineEnd > block.lineEnd) {
        context.addIssue({ code: 'custom', message: `Beat ${beat.beatId} is outside its source block.` });
      }
    }
    for (const plan of spine.workerExtractionPlan) {
      const block = spine.blocks.find((item) => item.blockId === plan.blockId);
      if (!blockIds.has(plan.blockId) || !block || plan.lineStart !== block.lineStart || plan.lineEnd !== block.lineEnd) {
        context.addIssue({ code: 'custom', message: `Worker plan ${plan.blockId} does not match its source block.` });
      }
    }
    for (const candidate of structural.candidates) {
      for (let line=candidate.lineStart;line<=candidate.lineEnd;line+=1) {
        if (source.lines[line-1]?.trim() && !spine.blocks.some((block) => block.lineStart <= line && block.lineEnd >= line)) {
          context.addIssue({ code: 'custom', message: `Structural candidate ${candidate.candidateId} leaves source line ${line} uncovered.` });
          break;
        }
      }
    }
  });
}

function lineEvidence(source: LoadedSource, start: number, end = start) {
  const safeStart = Math.max(1, Math.min(source.lines.length, start));
  const safeEnd = Math.max(safeStart, Math.min(source.lines.length, end));
  return [{
    source: 'chapter' as const,
    sourcePath: source.path,
    lineStart: safeStart,
    lineEnd: safeEnd,
    quote: source.lines.slice(safeStart - 1, safeEnd).filter((line) => line.trim()).join(' ').slice(0, 600),
  }];
}

function beatType(text: string): NarrativeBeat['beatType'] {
  if (/(?:quyết định|lựa chọn|ra lệnh|sẽ\s|decid|order)/iu.test(text)) return 'decision';
  if (/(?:tiết lộ|nhận ra|phát hiện|sự thật|reveal|discover|realiz)/iu.test(text)) return 'revelation';
  if (/(?:nhưng|tuy nhiên|đột nhiên|bất ngờ|however|suddenly)/iu.test(text)) return 'reversal';
  if (/(?:đe dọa|nguy hiểm|chiến tranh|tấn công|threat|war|attack)/iu.test(text)) return 'threat_escalation';
  if (/(?:xung đột|tranh cãi|đối đầu|conflict|argu)/iu.test(text)) return 'conflict';
  return 'setup';
}

function fallbackSpine(source: LoadedSource, structural: StructuralCandidates, workerModel: string): NarrativeSpine {
  const blocks = structural.candidates.map((candidate, index) => ({
    blockId: `block_${String(index + 1).padStart(3, '0')}`,
    lineStart: candidate.lineStart,
    lineEnd: candidate.lineEnd,
    povHolder: null,
    location: null,
    timeContext: null,
    activeCharacters: [],
    structuralReason: candidate.structuralReason,
    confidence: 0.5,
    evidence: candidate.evidence,
  }));
  const beats: NarrativeBeat[] = [];
  for (const block of blocks) {
    const nonEmpty = source.lines
      .slice(block.lineStart - 1, block.lineEnd)
      .map((text, index) => ({ text: text.trim(), line: block.lineStart + index }))
      .filter(({ text }) => text.length >= 20);
    const groups = nonEmpty.length > 5
      ? [nonEmpty.slice(0, Math.ceil(nonEmpty.length / 2)), nonEmpty.slice(Math.ceil(nonEmpty.length / 2))]
      : [nonEmpty];
    for (const group of groups.filter((item) => item.length)) {
      const first = group[0]!;
      const last = group[group.length - 1]!;
      const turning = group[Math.floor(group.length / 2)]!;
      beats.push({
        beatId: `beat_${String(beats.length + 1).padStart(3, '0')}`,
        blockId: block.blockId,
        lineStart: first.line,
        lineEnd: last.line,
        beatType: beatType(group.map(({ text }) => text).join(' ')),
        setup: first.text.slice(0, 300),
        pressure: turning.text.slice(0, 300),
        turningPoint: turning.text.slice(0, 300),
        resultingState: last.text.slice(0, 300),
        dramaticFunction: beatType(group.map(({ text }) => text).join(' ')),
        evidence: lineEvidence(source, first.line, last.line),
      });
    }
  }
  const workerExtractionPlan = blocks.map((block) => {
    const blockBeats = beats.filter((beat) => beat.blockId === block.blockId);
    return {
      blockId: block.blockId,
      lineStart: block.lineStart,
      lineEnd: block.lineEnd,
      expectedPov: block.povHolder,
      expectedLocation: block.location,
      requiredEventTypes: [...new Set(blockBeats.map((beat) => beat.beatType))],
      minimumEvidenceItems: Math.max(1, Math.min(8, Math.ceil((block.lineEnd - block.lineStart + 1) / 12))),
      blockComplexity: blockBeats.length > 2 ? 'high' as const : 'medium' as const,
      recommendedWorker: workerModel,
    };
  });
  return { blocks, beats, unresolvedQuestions: ['POV and location require director confirmation.'], workerExtractionPlan };
}

function fallbackExtraction(source: LoadedSource, plan: WorkerExtractionPlan, spine: NarrativeSpine, model: string): ExtractionResult {
  const candidates = source.lines
    .slice(plan.lineStart - 1, plan.lineEnd)
    .map((text, index) => ({ text: text.trim(), line: plan.lineStart + index }))
    .filter(({ text }) => text.length >= 25 && !/^\s*(?:\*{3,}|-{3,})\s*$/.test(text));
  const step = Math.max(1, Math.ceil(candidates.length / 20));
  const selected = candidates.filter((_item, index) => index % step === 0).slice(0, 20);
  const events = selected.map((item, index): StoryEvent => {
    const beat = spine.beats.find((entry) =>
      entry.blockId === plan.blockId && item.line >= entry.lineStart && item.line <= entry.lineEnd,
    ) ?? spine.beats.find((entry) => entry.blockId === plan.blockId)!;
    return {
      eventId: `${plan.blockId}_event_${String(index + 1).padStart(3, '0')}`,
      beatId: beat.beatId,
      lineStart: item.line,
      lineEnd: item.line,
      eventType: beatType(item.text),
      actor: null,
      action: item.text.slice(0, 500),
      stateBefore: null,
      stateAfter: item.text.slice(0, 300),
      target: null,
      location: plan.expectedLocation,
      evidence: lineEvidence(source, item.line),
      resolutionRequired: true,
    };
  });
  return { blockId: plan.blockId, requestedBackend: model, actualBackend: model, fallbackReason: null, events };
}

function promptFor<T>(provider: TextAIProvider, prompt: string, fallback: T): string {
  return provider.name === 'mock' ? `${prompt}\nMOCK_RESULT_JSON\n${JSON.stringify(fallback)}` : prompt;
}

function normalizeEvents(source: LoadedSource, results: ExtractionResult[], spine: NarrativeSpine): StoryEvent[] {
  const knownBeatIds = new Set(spine.beats.map((beat) => beat.beatId));
  const seen = new Set<string>();
  const normalized: StoryEvent[] = [];
  for (const result of results) {
    for (const event of result.events) {
      const lineStart = Math.max(1, Math.min(source.lines.length, event.lineStart));
      const lineEnd = Math.max(lineStart, Math.min(source.lines.length, event.lineEnd));
      const evidence = event.evidence.filter((item) =>
        item.source === 'chapter' && item.lineStart >= lineStart && item.lineEnd <= lineEnd &&
        item.lineStart >= 1 && item.lineEnd <= source.lines.length,
      );
      if (!knownBeatIds.has(event.beatId) || !evidence.length) continue;
      const sourceText = source.lines.slice(lineStart - 1, lineEnd).join(' ');
      const actor = event.actor && sourceText.toLocaleLowerCase('vi').includes(event.actor.toLocaleLowerCase('vi'))
        ? event.actor
        : null;
      const key = `${lineStart}:${lineEnd}:${event.action.toLocaleLowerCase('vi')}`;
      if (seen.has(key)) continue;
      seen.add(key);
      normalized.push({
        ...event,
        lineStart,
        lineEnd,
        actor,
        evidence,
        resolutionRequired: event.resolutionRequired || (event.actor !== null && actor === null),
      });
    }
  }
  return normalized.sort((a, b) => a.lineStart - b.lineStart || a.lineEnd - b.lineEnd);
}

function detectConflicts(plans: WorkerExtractionPlan[], events: StoryEvent[]): AnalysisConflict[] {
  const conflicts: AnalysisConflict[] = [];
  for (const plan of plans) {
    const blockEvents = events.filter((event) => event.lineStart >= plan.lineStart && event.lineEnd <= plan.lineEnd);
    if (blockEvents.length < plan.minimumEvidenceItems) {
      conflicts.push({
        conflictId: `coverage_${plan.blockId}`,
        blockId: plan.blockId,
        kind: 'coverage_gap',
        lineStart: plan.lineStart,
        lineEnd: plan.lineEnd,
        reason: `Only ${blockEvents.length}/${plan.minimumEvidenceItems} required evidence-backed events were extracted.`,
        resolutionRequired: true,
      });
    }
    for (const event of blockEvents.filter((item) => item.resolutionRequired)) {
      conflicts.push({
        conflictId: `actor_${event.eventId}`,
        blockId: plan.blockId,
        kind: 'unresolved_actor',
        lineStart: event.lineStart,
        lineEnd: event.lineEnd,
        reason: 'Actor remains unresolved because supplied evidence does not name the actor.',
        resolutionRequired: false,
      });
    }
  }
  return conflicts;
}

export function groundedSceneUnits(
  source: LoadedSource,
  spine: NarrativeSpine,
): StoryEvent[] {
  const units: StoryEvent[] = [];
  for (let lineIndex = 0; lineIndex < source.lines.length; lineIndex += 1) {
    const line = source.lines[lineIndex]!.trim();
    const lineNumber = lineIndex + 1;
    if (line.length < 20 || /^\s*(?:#{1,6}\s*)?(?:Chương|Chapter)\s+\d+\b/iu.test(line) ||
        /^\s*(?:\*{3,}|-{3,}|_{3,})\s*$/.test(line)) continue;
    const beat = spine.beats.find((item) => lineNumber >= item.lineStart && lineNumber <= item.lineEnd);
    if (!beat) continue;
    const block = spine.blocks.find((item) => item.blockId === beat.blockId);
    const sentences = line.split(/(?<=[.!?…])\s+/u).map((item) => item.trim()).filter((item) => item.length >= 20);
    for (let sentenceIndex = 0; sentenceIndex < Math.max(1, sentences.length); sentenceIndex += 1) {
      const sourceAction = sentences[sentenceIndex] ?? line;
      const representation = literaryRepresentation(sourceAction);
      if (representation === 'none') continue;
      units.push({
        eventId: `grounded_${lineNumber}_${sentenceIndex + 1}`,
        beatId: beat.beatId,
        lineStart: lineNumber,
        lineEnd: lineNumber,
        eventType: representation,
        actor: block?.activeCharacters.find((name) => sourceAction.toLocaleLowerCase('vi').includes(name.toLocaleLowerCase('vi'))) ?? null,
        action: literaryVisualAnchor(sourceAction),
        stateBefore: null,
        stateAfter: sourceAction.slice(0, 300),
        target: null,
        location: sourceGroundedLocation(source, lineNumber, block),
        evidence: lineEvidence(source, lineNumber),
        resolutionRequired: false,
      });
    }
  }
  return units;
}

const VISIBLE_ACTION = /(?:bước|đi|chạy|nhảy|quay|ngoảnh|nhìn|liếc|trừng|đứng|ngồi|nằm|quỳ|cúi|ngẩng|run rẩy|siết|ôm|chạm|cầm|rút|ném|đánh|đấm|đá|chém|bắn|tấn công|đối đầu|va chạm|nổ|vỡ|nứt|sụp|cháy|bùng|bao phủ|cuộn|rơi|bay|xuất hiện|biến đổi|mở|đóng|mỉm cười|bật cười|khóc|nước mắt|ánh mắt|sắc mặt|walk|run|turn|look|glance|stare|stand|sit|kneel|bow|tremble|clench|embrace|hold|draw|throw|fight|attack|strike|clash|explode|break|crack|collapse|burn|burst|surround|rise|fall|transform|smile|cry|tears|expression)/iu;
const VISUAL_EFFECT = /(?:ma thuật|ma lực|phép|nghi lễ|lửa|sét|gió|băng|khói|sương|mưa|tuyết|máu|bóng tối|vực thẳm|ánh sáng|màu|mùi|âm thanh|tiếng|lạnh|nóng|magic|spell|ritual|fire|lightning|wind|ice|smoke|mist|rain|snow|blood|shadow|abyss|void|light|color|sound|cold|heat)/iu;
const INNER_TURN = /(?:nhận ra|hiểu ra|chợt hiểu|cảm thấy|suy nghĩ|do dự|quyết định|lựa chọn|tin rằng|nghi ngờ|lo sợ|hy vọng|tuyệt vọng|ân hận|day dứt|ý thức|trong lòng|trong tâm trí|realiz|understand|feel|decid|choose|believ|doubt|fear|hope|regret)/iu;
const MEMORY = /(?:nhớ lại|hồi tưởng|ký ức|năm đó|ngày ấy|hồi ấy|trong quá khứ|mơ thấy|remember|recall|memory|years ago|dreamed)/iu;
const RELATIONSHIP = /(?:tha thứ|phản bội|tin tưởng|nghi kỵ|xa cách|thân thiết|bảo vệ|an ủi|trấn an|hứa|thề|từ chối|đồng ý|forgive|betray|trust|comfort|promise|swear|refuse|agree)/iu;
const REVELATION = /(?:tiết lộ|sự thật|phát hiện|hóa ra|thì ra|bí mật|lộ ra|reveal|truth|discover|secret)/iu;
const TRANSITION = /(?:trong khi đó|cùng lúc|nhiều năm trước|sáng hôm sau|đêm đó|một lúc sau|ở phía|tại nơi|meanwhile|years earlier|the next morning|later that)/iu;
const PURE_DIALOGUE = /^\s*[“"'«].*[”"'»]\s*[.!?…]*\s*$/u;

export type LiteraryRepresentation = NonNullable<AnalysisScene['representationMode']> | 'none';

export function literaryRepresentation(text: string): LiteraryRepresentation {
  const value = text.replace(/\s+/g, ' ').trim();
  if (value.length < 20) return 'none';
  if (MEMORY.test(value)) return 'memory';
  if (REVELATION.test(value)) return 'revelation';
  if (RELATIONSHIP.test(value)) return 'relationship';
  if (INNER_TURN.test(value)) return 'inner_turn';
  if (TRANSITION.test(value)) return 'transition';
  if (PURE_DIALOGUE.test(value)) return value.length >= 35 ? 'dialogue_reaction' : 'none';
  if (VISIBLE_ACTION.test(value)) return 'literal_action';
  if (VISUAL_EFFECT.test(value)) return 'atmosphere';
  return 'none';
}

export function isVisualizable(text: string): boolean {
  return literaryRepresentation(text) !== 'none';
}

export function literaryVisualAnchor(text: string): string {
  const value = text.replace(/\s+/g, ' ').trim().slice(0, 500);
  if (/^(?:Show the source-present|Show the source-grounded|Depict the explicitly remembered|Show the revelation|Establish the source-described|Preserve this authored)/i.test(value)) {
    return value;
  }
  switch (literaryRepresentation(value)) {
    case 'dialogue_reaction': return `Show the source-present speaker and listeners at this consequential line, using source-described expression and body language: ${value}`;
    case 'inner_turn': return `Show the source-present character visibly processing this inner turning point through expression, posture and source-described surroundings: ${value}`;
    case 'memory': return `Depict the explicitly remembered source moment, keeping it visually distinct from the present without inventing details: ${value}`;
    case 'relationship': return `Show the source-grounded relationship shift through distance, gesture, gaze and blocking: ${value}`;
    case 'revelation': return `Show the revelation and its immediate source-described reaction or consequence: ${value}`;
    case 'transition': return `Establish the source-described change of time, place or viewpoint: ${value}`;
    case 'atmosphere': return `Preserve this authored sensory atmosphere as a concrete environmental moment: ${value}`;
    default: return value;
  }
}

function sourceGroundedLocation(
  source: LoadedSource,
  lineNumber: number,
  block?: NarrativeSpine['blocks'][number],
): string {
  if (block?.location?.trim() && !/không xác định|unknown|unspecified/iu.test(block.location)) return block.location.trim();
  const start = Math.max(block?.lineStart ?? 1, lineNumber - 2);
  const end = Math.min(block?.lineEnd ?? source.lines.length, lineNumber + 2);
  const nearby = source.lines.slice(start - 1, end)
    .map((line) => line.trim())
    .find((line) => /(?:\btrong\b|\btại\b|\bgiữa\b|\btrên\b|\bdưới\b|\bbên\b|\bvào\b|\bđến\b|\bin\b|\bat\b|\binside\b|\bamid\b|\bunder\b|\bnear\b)/iu.test(line));
  const evidence = (nearby || source.lines[lineNumber - 1] || '').replace(/\s+/g, ' ').trim().slice(0, 240);
  return evidence ? `source-described setting: ${evidence}` : '';
}

function repairSceneContract(
  source: LoadedSource,
  spine: NarrativeSpine,
  scene: AnalysisScene,
): AnalysisScene {
  const block = spine.blocks.find((item) => scene.sourceBlockIds.includes(item.blockId))
    ?? spine.blocks.find((item) => scene.lineStart >= item.lineStart && scene.lineStart <= item.lineEnd);
  const location = scene.location?.trim() && !/không xác định|unknown|unspecified/iu.test(scene.location)
    ? scene.location.trim()
    : sourceGroundedLocation(source, scene.lineStart, block);
  const evidenceFacts = scene.evidence.map((item) => item.quote?.replace(/\s+/g, ' ').trim()).filter((item): item is string => Boolean(item));
  const sourceMeaning = evidenceFacts.find((item) => literaryRepresentation(item) !== 'none') ?? scene.visualAnchor;
  const detectedRepresentation = literaryRepresentation(sourceMeaning);
  const representation = scene.representationMode ?? (
    detectedRepresentation === 'none' ? 'literal_action' : detectedRepresentation
  );
  const visualAnchor = literaryVisualAnchor(
    literaryRepresentation(scene.visualAnchor) !== 'none' ? scene.visualAnchor : sourceMeaning,
  );
  return {
    ...scene,
    location,
    visualAnchor,
    representationMode: representation,
    authorialIntent: scene.authorialIntent || scene.sceneFunction,
    narrativeSubtext: [...new Set([
      ...(scene.narrativeSubtext ?? []),
      scene.emotionalCenter,
      scene.turningPoint,
    ].filter(Boolean))].slice(0, 6),
    sensoryAnchors: [...new Set([
      ...(scene.sensoryAnchors ?? []),
      ...evidenceFacts.filter((item) => VISUAL_EFFECT.test(item)),
    ])].slice(0, 6),
    requiredVisualFacts: [...new Set([visualAnchor, ...scene.requiredVisualFacts, ...evidenceFacts])].slice(0, 6),
    mustPreserve: [...new Set([visualAnchor, ...scene.mustPreserve, scene.turningPoint])].slice(0, 6),
  };
}

export function fallbackScenes(
  source: LoadedSource,
  spine: NarrativeSpine,
  events: StoryEvent[],
  target: number,
): SceneArchitecture {
  const derived = spine.beats.filter((beat) => isVisualizable(beat.turningPoint)).map((beat, index): StoryEvent => ({
    eventId: `derived_event_${index + 1}`,
    beatId: beat.beatId,
    lineStart: beat.lineStart,
    lineEnd: beat.lineEnd,
    eventType: beat.beatType,
    actor: null,
    action: literaryVisualAnchor(beat.turningPoint),
    stateBefore: null,
    stateAfter: beat.resultingState,
    target: null,
    location: sourceGroundedLocation(source, beat.lineStart, spine.blocks.find((block) => block.blockId === beat.blockId)),
    evidence: beat.evidence,
    resolutionRequired: false,
  }));
  const sourceUnits = groundedSceneUnits(source, spine);
  const visualEvents = events.filter((event) => isVisualizable(event.action));
  let available = visualEvents.length ? [...visualEvents] : sourceUnits.length ? [...sourceUnits] : derived;
  if (visualEvents.length && target > visualEvents.length && sourceUnits.length) {
    const needed = target - visualEvents.length;
    const eventLines = new Set(visualEvents.flatMap((event) =>
      Array.from({ length: event.lineEnd - event.lineStart + 1 }, (_item, index) => event.lineStart + index),
    ));
    let candidates = sourceUnits.filter((unit) => !eventLines.has(unit.lineStart));
    if (candidates.length < needed) candidates = sourceUnits;
    const supplements = needed >= candidates.length
      ? candidates
      : Array.from({ length: needed }, (_item, index) =>
        candidates[Math.min(candidates.length - 1, Math.floor((index + 0.5) * candidates.length / needed))]!,
      );
    available = [...visualEvents, ...supplements].sort((a, b) => a.lineStart - b.lineStart || a.lineEnd - b.lineEnd);
  }
  if (!available.length) throw new Error('No source-grounded visual event is available for storyboard rendering.');
  const count = Math.max(1, Math.min(target, available.length));
  const highDensity = target > 24;
  const units = !highDensity || count === available.length
    ? available
    : Array.from({ length: count }, (_item, index) =>
      available[Math.min(available.length - 1, Math.floor((index + 0.5) * available.length / count))]!,
    );
  const scenes: AnalysisScene[] = [];
  for (let index = 0; index < count; index += 1) {
    const group = highDensity
      ? [units[index]!]
      : units.slice(
        Math.floor(index * units.length / count),
        Math.max(Math.floor(index * units.length / count) + 1, Math.floor((index + 1) * units.length / count)),
      );
    const first = group[0]!;
    const last = group[group.length - 1]!;
    const beat = spine.beats.find((item) => item.beatId === first.beatId)!;
    const block = spine.blocks.find((item) => item.blockId === beat.blockId)!;
    const sourceMeaning = group.map((event) => event.stateAfter || event.action).join('; ');
    const detectedRepresentation = literaryRepresentation(sourceMeaning);
    scenes.push({
      sceneId: `scene_${String(index + 1).padStart(3, '0')}`,
      sourceBlockIds: [...new Set(group.map((event) => spine.beats.find((item) => item.beatId === event.beatId)?.blockId).filter((item): item is string => Boolean(item)))],
      sourceBeatIds: [...new Set(group.map((event) => event.beatId))],
      sourceEventIds: group.map((event) => event.eventId),
      lineStart: first.lineStart,
      lineEnd: last.lineEnd,
      povHolder: block.povHolder,
      location: first.location ?? sourceGroundedLocation(source, first.lineStart, block),
      sceneFunction: beat.dramaticFunction,
      visualAnchor: literaryVisualAnchor(group.map((event) => event.action).join('; ')),
      requiredVisualFacts: group.map((event) => event.action).slice(0, 4),
      forbiddenVisuals: ['events, characters, locations, and objects outside the cited source range'],
      emotionalCenter: beat.pressure || beat.dramaticFunction,
      turningPoint: beat.turningPoint,
      continuityRequirements: block.activeCharacters,
      mustPreserve: group.map((event) => event.action).slice(0, 4),
      importance: Math.min(1, 0.5 + group.length / 20),
      representationMode: detectedRepresentation === 'none' ? 'literal_action' : detectedRepresentation,
      authorialIntent: beat.dramaticFunction,
      narrativeSubtext: [...new Set([beat.pressure, beat.turningPoint, beat.resultingState].filter(Boolean))],
      sensoryAnchors: group
        .flatMap((event) => event.evidence.map((item) => item.quote))
        .filter((item): item is string => typeof item === 'string' && VISUAL_EFFECT.test(item))
        .slice(0, 6),
      evidence: group.flatMap((event) => event.evidence),
    });
  }
  return {
    operations: [{ operation: 'APPROVE', lineStart: null, lineEnd: null, backend: null, reason: 'Deterministic evidence-grounded scene architecture.' }],
    scenes: scenes.map((scene) => repairSceneContract(source, spine, scene)),
  };
}

function coverage(
  source: LoadedSource,
  structural: StructuralCandidates,
  spine: NarrativeSpine,
  architecture: SceneArchitecture,
): CoverageReport {
  const covered = new Set<number>();
  for (const block of spine.blocks) {
    for (let line = block.lineStart; line <= block.lineEnd; line += 1) covered.add(line);
  }
  const uncoveredLines = structural.contentLines.filter((line) => !covered.has(line));
  const ideaUnits = groundedSceneUnits(source, spine);
  const uncoveredIdeas = ideaUnits.filter((unit) => {
    const sourceMeaning = (unit.stateAfter ?? unit.action).replace(/\s+/g, ' ').trim().slice(0, 80);
    return !architecture.scenes.some((scene) => {
      if (scene.lineStart > unit.lineEnd || scene.lineEnd < unit.lineStart) return false;
      if (scene.sourceEventIds.includes(unit.eventId)) return true;
      const contract = [
        scene.visualAnchor, ...scene.requiredVisualFacts, ...scene.mustPreserve,
        ...scene.evidence.map((item) => item.quote ?? ''),
      ].join(' ').replace(/\s+/g, ' ');
      return sourceMeaning.length >= 20 && contract.includes(sourceMeaning);
    });
  });
  return {
    lineCount: structural.lineCount,
    contentLineCount: structural.contentLines.length,
    coveredLineCount: structural.contentLines.length - uncoveredLines.length,
    uncoveredLines,
    coverage: structural.contentLines.length ? (structural.contentLines.length - uncoveredLines.length) / structural.contentLines.length : 1,
    ideaUnitCount: ideaUnits.length,
    coveredIdeaUnitCount: ideaUnits.length - uncoveredIdeas.length,
    uncoveredIdeaLines: [...new Set(uncoveredIdeas.map((unit) => unit.lineStart))],
    ideaCoverage: ideaUnits.length ? (ideaUnits.length - uncoveredIdeas.length) / ideaUnits.length : 1,
  };
}

export function repairStructuralSeparators(
  architecture: SceneArchitecture,
  separators: number[],
): SceneArchitecture {
  if (!separators.length) return architecture;
  const scenes = architecture.scenes.map((scene) => {
    const separator = separators.find((line) => line > scene.lineStart && line < scene.lineEnd);
    if (separator === undefined) return scene;
    const lineEnd = separator - 1;
    return {
      ...scene,
      lineEnd,
      evidence: scene.evidence.map((item) => ({
        ...item,
        lineEnd: Math.min(item.lineEnd, lineEnd),
      })),
    };
  });
  return { ...architecture, scenes };
}

function validate(
  source: LoadedSource,
  structural: StructuralCandidates,
  spine: NarrativeSpine,
  events: StoryEvent[],
  architecture: SceneArchitecture,
  report: CoverageReport,
  target: number,
): ValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  const blockIds = new Set(spine.blocks.map((block) => block.blockId));
  const beatIds = new Set(spine.beats.map((beat) => beat.beatId));
  if (report.uncoveredLines.length) errors.push(`Uncovered content lines: ${report.uncoveredLines.join(', ')}`);
  if (report.ideaCoverage < 0.9) {
    warnings.push(`Only ${(report.ideaCoverage * 100).toFixed(1)}% of literary idea units are represented by selected scenes.`);
  }
  for (const block of spine.blocks) {
    if (block.lineStart < 1 || block.lineEnd > source.lines.length || block.lineStart > block.lineEnd) errors.push(`Invalid block range: ${block.blockId}`);
  }
  for (const beat of spine.beats) {
    if (!blockIds.has(beat.blockId) || !beat.evidence.length) errors.push(`Invalid beat source: ${beat.beatId}`);
  }
  for (const event of events) {
    if (!beatIds.has(event.beatId) || !event.evidence.length) errors.push(`Invalid event source: ${event.eventId}`);
  }
  for (const scene of architecture.scenes) {
    if (!scene.sourceBeatIds.length || scene.sourceBeatIds.some((id) => !beatIds.has(id))) errors.push(`Scene lacks valid source beats: ${scene.sceneId}`);
    if (!scene.evidence.length || !scene.visualAnchor || !scene.emotionalCenter || !scene.turningPoint) errors.push(`Scene contract incomplete: ${scene.sceneId}`);
    if (scene.lineStart < 1 || scene.lineEnd > source.lines.length || scene.lineStart > scene.lineEnd) errors.push(`Invalid scene range: ${scene.sceneId}`);
    if (!scene.location.trim() || /không xác định|unknown|unspecified/iu.test(scene.location)) errors.push(`Scene lacks source-grounded location: ${scene.sceneId}`);
    if (!isVisualizable(scene.visualAnchor)) errors.push(`Scene lacks visible action: ${scene.sceneId}`);
    if (structural.separators.some((line) => line > scene.lineStart && line < scene.lineEnd)) {
      errors.push(`Scene crosses a structural separator: ${scene.sceneId}`);
    }
  }
  const minimumScenes = Math.min(8, target);
  if (architecture.scenes.length < minimumScenes) warnings.push(`Scene count ${architecture.scenes.length} is below preferred minimum ${minimumScenes}.`);
  if (architecture.scenes.length > target) errors.push(`Scene count ${architecture.scenes.length} exceeds configured maximum ${target}.`);
  return {
    valid: errors.length === 0,
    errors,
    warnings,
    blockCount: spine.blocks.length,
    beatCount: spine.beats.length,
    eventCount: events.length,
    sceneCount: architecture.scenes.length,
  };
}

function toLegacy(source: LoadedSource, chapterNumber: number, timeline: string, spine: NarrativeSpine, events: StoryEvent[], scenes: AnalysisScene[]): ChapterAnalysis {
  const chapterTitle = (source.lines.slice(0, 8).find((line) => /(?:Chương|Chapter)\s*\d+/iu.test(line)) ?? `Chapter ${chapterNumber}`).replace(/^#+\s*/, '').trim();
  const characters = [...new Set([
    ...spine.blocks.flatMap((block) => block.activeCharacters),
    ...events.flatMap((event) => event.actor ? [event.actor] : []),
  ])];
  return {
    chapterNumber,
    chapterTitle,
    timeline,
    summary: spine.beats.map((beat) => beat.dramaticFunction).join(' → '),
    povCharacters: [...new Set(spine.blocks.flatMap((block) => block.povHolder ? [block.povHolder] : []))],
    charactersPresent: characters,
    locations: [...new Set(spine.blocks.flatMap((block) => block.location ? [block.location] : []))],
    events: events.map((event) => event.action),
    revealedFacts: events.filter((event) => event.eventType === 'revelation').map((event) => event.action),
    emotionalArc: spine.beats.map((beat) => beat.resultingState),
    magicUsed: [],
    objects: [],
    creatures: [],
    visualMotifs: scenes.map((scene) => scene.visualAnchor),
    scenes: scenes.map((scene) => ({
      sceneId: scene.sceneId,
      startLine: scene.lineStart,
      endLine: scene.lineEnd,
      location: scene.location,
      time: spine.blocks.find((block) => block.blockId === scene.sourceBlockIds[0])?.timeContext ?? '',
      characters: spine.blocks.find((block) => block.blockId === scene.sourceBlockIds[0])?.activeCharacters ?? [],
      objective: scene.sceneFunction,
      opposition: scene.emotionalCenter,
      action: scene.visualAnchor,
      turningPoint: scene.turningPoint,
      result: scene.mustPreserve.join('; '),
      emotion: scene.emotionalCenter,
      sensoryDetails: scene.sensoryAnchors,
      visualElements: [scene.visualAnchor, ...scene.requiredVisualFacts, ...scene.mustPreserve],
      thumbnailPotential: [scene.sceneFunction],
      spoilerLevel: 'low' as const,
      evidence: scene.evidence,
      representationMode: scene.representationMode,
      authorialIntent: scene.authorialIntent,
      narrativeSubtext: scene.narrativeSubtext,
    })),
  };
}

async function closeProvider(provider: TextAIProvider | undefined, onProgress?: (message: string) => void): Promise<void> {
  if (!provider) return;
  onProgress?.(`Đang dỡ model ${provider.model}; RAM trống ${Math.round(os.freemem() / 1024 / 1024)} MB, VRAM do Ollama quản lý.`);
  await provider.close?.();
}

export async function runAnalysisV3(options: AnalysisV3Options): Promise<AnalysisV3Result> {
  const workflowStarted = Date.now();
  const store = new AnalysisArtifactStore(options.directory);
  await store.load();
  const sourceHash = fullSha256(options.source.text);
  const contextHash = fullSha256(options.context);
  const baseInputs = { chapter: sourceHash, context: contextHash };
  const progress = options.onProgress;
  progress?.(`[analysis:v3] profile=${options.profile}; director=${options.directorModel}; worker=${options.workerModel}`);

  const structuralRun = await store.run({
    jobId: 'structural_segmentation',
    jobType: 'structural_segmentation',
    output: 'structural_candidates.json',
    inputHashes: { chapter: sourceHash },
    config: { maxBlockLines: 48 },
    backend: 'python-deterministic',
    promptVersion: 'none',
    schemaVersion: 'structural-candidates-v1',
    implementationVersion: IMPLEMENTATION_VERSION,
    schema: structuralCandidatesSchema,
    execute: async () => segmentStructure(options.source),
  });
  progress?.(`[analysis:v3] Structural segmentation: ${structuralRun.resumed ? 'resume' : 'xong'} ${structuralRun.value.candidates.length} candidate blocks.`);

  const fallbackSpineValue = fallbackSpine(options.source, structuralRun.value, options.workerModel);
  const checkedSpineSchema = groundedSpineSchema(options.source, structuralRun.value);
  const useDirector = options.profile !== 'fast';
  const fullNarrativePrompt = `Canon/context:\n${options.context}\n\nStructural candidates:\n${JSON.stringify(structuralRun.value)}\n\nLine-numbered chapter:\n${options.source.lines.map((line, index) => `${index + 1}: ${line}`).join('\n')}`;
  const directorContextTokens = options.directorContextTokens ?? 16_384;
  const directorMaxTokens = options.directorMaxTokens ?? 2_048;
  const reserveTokens = Math.max(1_024, Math.ceil(directorContextTokens * 0.15));
  const inputBudget = directorContextTokens - directorMaxTokens - reserveTokens;
  const fullInputTokens = estimateTokens(NARRATIVE_SPINE_SYSTEM + fullNarrativePrompt);
  const analysisMode = !useDirector ? 'deterministic' : fullInputTokens <= inputBudget ? 'direct' : 'hierarchical';
  const narrativePrompt = analysisMode === 'hierarchical'
    ? compactDirectorPrompt(options.source, structuralRun.value, options.context, Math.max(6000, inputBudget * 3 - NARRATIVE_SPINE_SYSTEM.length))
    : fullNarrativePrompt;
  const estimatedInputTokens = estimateTokens(NARRATIVE_SPINE_SYSTEM + narrativePrompt);
  const useSpineDirector = useDirector;
  let director: TextAIProvider | undefined;
  if (useDirector) director = options.createDirector();
  const spineStarted = Date.now();
  progress?.('[analysis:v3] Narrative Director '+options.directorModel+': bắt đầu ('+options.context.length+' context chars; model 7B hiểu toàn cục, lập narrative spine).');
  const spineRun = await store.run({
    jobId: 'narrative_spine',
    jobType: 'narrative_spine',
    dependencies: ['structural_segmentation'],
    output: 'narrative_spine.json',
    inputHashes: baseInputs,
    config: { profile: options.profile, analysisMode, contextTokens: directorContextTokens, maxTokens: directorMaxTokens, estimatedInputTokens, inputBudget },
    backend: useSpineDirector ? options.directorModel : 'python-deterministic',
    promptVersion: useSpineDirector ? `${NARRATIVE_SPINE_PROMPT_VERSION}-${analysisMode}` : `${analysisMode}-spine-v1`,
    schemaVersion: 'narrative-spine-v1',
    implementationVersion: IMPLEMENTATION_VERSION,
    schema: checkedSpineSchema,
    execute: async () => {
      if (!director) return fallbackSpineValue;
      return director.generateStructured(NARRATIVE_SPINE_SYSTEM, promptFor(director, narrativePrompt, fallbackSpineValue), checkedSpineSchema);
    },
  });
  progress?.(`[analysis:v3] Narrative Director ${options.directorModel}: ${spineRun.resumed ? 'resume checkpoint' : `${spineRun.value.blocks.length} blocks, ${spineRun.value.beats.length} beats`} trong ${((Date.now()-spineStarted)/1000).toFixed(1)}s.`);
  await closeProvider(director, progress);

  const planRun = await store.run({
    jobId: 'worker_extraction_plan',
    jobType: 'worker_extraction_plan',
    dependencies: ['narrative_spine'],
    output: 'worker_extraction_plan.json',
    inputHashes: { narrativeSpine: fullSha256(JSON.stringify(spineRun.value)) },
    config: {},
    backend: 'python-deterministic',
    promptVersion: 'none',
    schemaVersion: 'worker-plan-v1',
    implementationVersion: IMPLEMENTATION_VERSION,
    schema: z.array(workerExtractionPlanSchema),
    execute: async () => spineRun.value.workerExtractionPlan,
  });

  const worker = options.profile === 'all-7b' ? options.createDirector() : options.createWorker();
  const extractionResults: ExtractionResult[] = [];
  for (const plan of planRun.value) {
    const blockText = options.source.lines.slice(plan.lineStart - 1, plan.lineEnd).join('\n');
    const fallback = fallbackExtraction(options.source, plan, spineRun.value, worker.model);
    const blockStarted=Date.now();
    progress?.('[analysis:v3] Guided worker '+worker.model+': bắt đầu '+plan.blockId+' (dòng '+plan.lineStart+'-'+plan.lineEnd+').');
    const result = await store.run({
      jobId: `block_extract_${plan.blockId}`,
      jobType: 'guided_block_extraction',
      dependencies: ['worker_extraction_plan'],
      output: path.join('extractions', `${plan.blockId}.json`),
      inputHashes: {
        blockSource: fullSha256(blockText),
        plan: fullSha256(JSON.stringify(plan)),
      },
      config: { profile: options.profile, contextTokens: 16384, maxTokens: 10000 },
      backend: worker.model,
      promptVersion: GUIDED_WORKER_PROMPT_VERSION,
      schemaVersion: 'guided-extraction-v2',
      implementationVersion: IMPLEMENTATION_VERSION,
      schema: extractionResultSchema,
      execute: async () => {
        const prompt = `Extraction plan:\n${JSON.stringify(plan)}\n\nKnown block/beat metadata:\n${JSON.stringify({
          block: spineRun.value.blocks.find((block) => block.blockId === plan.blockId),
          beats: spineRun.value.beats.filter((beat) => beat.blockId === plan.blockId),
        })}\n\nSupplied source lines:\n${options.source.lines.slice(plan.lineStart - 1, plan.lineEnd).map((line, index) => `${plan.lineStart + index}: ${line}`).join('\n')}`;
        return worker.generateStructured(GUIDED_WORKER_SYSTEM, promptFor(worker, prompt, fallback), extractionResultSchema);
      },
    });
    extractionResults.push(result.value);
    progress?.(`[analysis:v3] Guided worker ${worker.model}: ${plan.blockId} ${result.resumed ? 'resume' : `${result.value.events.length} events`} trong ${((Date.now()-blockStarted)/1000).toFixed(1)}s.`);
  }
  await closeProvider(worker, progress);

  const eventsRun = await store.run({
    jobId: 'normalize_events',
    jobType: 'normalize_events',
    dependencies: planRun.value.map((plan) => `block_extract_${plan.blockId}`),
    output: 'normalized_events.json',
    inputHashes: { extractions: fullSha256(JSON.stringify(extractionResults)), chapter: sourceHash },
    config: {},
    backend: 'python-deterministic',
    promptVersion: 'none',
    schemaVersion: 'story-events-v1',
    implementationVersion: IMPLEMENTATION_VERSION,
    schema: z.array(storyEventSchema),
    execute: async () => normalizeEvents(options.source, extractionResults, spineRun.value),
  });

  const conflictsRun = await store.run({
    jobId: 'conflict_detection',
    jobType: 'conflict_detection',
    dependencies: ['normalize_events'],
    output: 'unresolved_conflicts.json',
    inputHashes: { events: fullSha256(JSON.stringify(eventsRun.value)), plan: fullSha256(JSON.stringify(planRun.value)) },
    config: {},
    backend: 'python-deterministic',
    promptVersion: 'none',
    schemaVersion: 'conflicts-v1',
    implementationVersion: IMPLEMENTATION_VERSION,
    schema: z.array(conflictSchema),
    execute: async () => detectConflicts(planRun.value, eventsRun.value),
  });

  const fallbackArchitecture = fallbackScenes(options.source, spineRun.value, eventsRun.value, options.targetSceneCount);
  const useSceneDirector = useDirector && options.targetSceneCount <= 24;
  let sceneDirector: TextAIProvider | undefined;
  if (useSceneDirector) sceneDirector = options.createDirector();
  const sceneStarted=Date.now();
  progress?.(useSceneDirector
    ? `[analysis:v3] Scene Director ${options.directorModel}: bắt đầu từ ${eventsRun.value.length} events.`
    : `[analysis:v3] High-density router: dựng ${fallbackArchitecture.scenes.length} cảnh trực tiếp từ source evidence.`);
  const sceneRun = await store.run({
    jobId: 'scene_architecture',
    jobType: 'scene_architecture',
    dependencies: ['conflict_detection'],
    output: 'scenes.json',
    inputHashes: {
      spine: fullSha256(JSON.stringify(spineRun.value)),
      events: fullSha256(JSON.stringify(eventsRun.value)),
      conflicts: fullSha256(JSON.stringify(conflictsRun.value)),
    },
    config: { profile: options.profile, contextTokens: directorContextTokens, maxTokens: directorMaxTokens, mode: useSceneDirector ? 'director' : 'high-density-grounded' },
    backend: useSceneDirector ? options.directorModel : 'python-deterministic',
    promptVersion: useSceneDirector ? SCENE_ARCHITECTURE_PROMPT_VERSION : 'high-density-scenes-v1',
    schemaVersion: 'scene-architecture-v1',
    implementationVersion: IMPLEMENTATION_VERSION,
    targetScenePolicy: { min: Math.min(8, options.targetSceneCount), max: options.targetSceneCount },
    schema: sceneArchitectureSchema,
    execute: async () => {
      if (!sceneDirector) return fallbackArchitecture;
      const prompt = `Narrative spine:\n${JSON.stringify(spineRun.value)}\n\nNormalized events:\n${JSON.stringify(eventsRun.value)}\n\nUnresolved conflicts:\n${JSON.stringify(conflictsRun.value)}\n\nTarget scene range: ${Math.min(8, options.targetSceneCount)}-${options.targetSceneCount}.`;
      const generated = await sceneDirector.generateStructured(SCENE_ARCHITECTURE_SYSTEM, promptFor(sceneDirector, prompt, fallbackArchitecture), sceneArchitectureSchema);
      const evidenceBackedMinimum = Math.min(fallbackArchitecture.scenes.length, options.targetSceneCount);
      if (generated.scenes.length < evidenceBackedMinimum) {
        progress?.(`[analysis:v3] Scene Director chỉ trả ${generated.scenes.length}/${evidenceBackedMinimum} cảnh; dùng kiến trúc deterministic có bằng chứng.`);
        return fallbackArchitecture;
      }
      const repaired = repairStructuralSeparators(generated, structuralRun.value.separators);
      if (repaired.scenes.some((scene, index) => scene.lineEnd !== generated.scenes[index]?.lineEnd)) {
        progress?.('[analysis:v3] Scene Director có cảnh bắc qua separator; đã tự kẹp về đúng structural segment.');
      }
      return { ...repaired, scenes: repaired.scenes.map((scene) => repairSceneContract(options.source, spineRun.value, scene)) };
    },
  });
  progress?.(`[analysis:v3] ${useSceneDirector ? `Scene Director ${options.directorModel}` : 'High-density router'}: ${sceneRun.resumed ? 'resume checkpoint' : `${sceneRun.value.scenes.length} grounded scenes`} trong ${((Date.now()-sceneStarted)/1000).toFixed(1)}s.`);
  await closeProvider(sceneDirector, progress);

  const coverageRun = await store.run({
    jobId: 'coverage_report',
    jobType: 'coverage_report',
    dependencies: ['scene_architecture'],
    output: 'coverage_report.json',
    inputHashes: {
      structural: fullSha256(JSON.stringify(structuralRun.value)),
      spine: fullSha256(JSON.stringify(spineRun.value)),
      scenes: fullSha256(JSON.stringify(sceneRun.value)),
    },
    config: {},
    backend: 'python-deterministic',
    promptVersion: 'none',
    schemaVersion: 'coverage-report-v2-literary',
    implementationVersion: IMPLEMENTATION_VERSION,
    schema: coverageReportSchema,
    execute: async () => coverage(options.source, structuralRun.value, spineRun.value, sceneRun.value),
  });

  const validationRun = await store.run({
    jobId: 'analysis_validation',
    jobType: 'analysis_validation',
    dependencies: ['coverage_report'],
    output: 'validation_report.json',
    inputHashes: {
      chapter: sourceHash,
      spine: fullSha256(JSON.stringify(spineRun.value)),
      events: fullSha256(JSON.stringify(eventsRun.value)),
      scenes: fullSha256(JSON.stringify(sceneRun.value)),
    },
    config: { targetSceneCount: options.targetSceneCount },
    backend: 'python-deterministic',
    promptVersion: 'none',
    schemaVersion: 'validation-report-v1',
    implementationVersion: IMPLEMENTATION_VERSION,
    targetScenePolicy: { min: Math.min(8, options.targetSceneCount), max: options.targetSceneCount },
    schema: validationReportSchema,
    execute: async () => validate(options.source, structuralRun.value, spineRun.value, eventsRun.value, sceneRun.value, coverageRun.value, options.targetSceneCount),
  });

  await store.run({
    jobId: 'analysis_commit',
    jobType: 'analysis_commit',
    dependencies: ['analysis_validation'],
    output: 'chapter_map.json',
    inputHashes: {
      validation: fullSha256(JSON.stringify(validationRun.value)),
      scenes: fullSha256(JSON.stringify(sceneRun.value)),
    },
    config: {},
    backend: 'python-deterministic',
    promptVersion: 'none',
    schemaVersion: 'chapter-map-v1',
    implementationVersion: IMPLEMENTATION_VERSION,
    schema: z.object({
      version: z.literal(3),
      chapterNumber: z.number().int().positive(),
      blocks: z.array(spineRun.value.blocks.length ? z.object({ blockId: z.string() }).passthrough() : z.never()),
      beats: z.array(spineRun.value.beats.length ? z.object({ beatId: z.string() }).passthrough() : z.never()),
      events: z.array(storyEventSchema),
      scenes: z.array(analysisSceneSchema),
      validation: validationReportSchema,
    }),
    execute: async () => ({
      version: 3 as const,
      chapterNumber: options.chapterNumber,
      blocks: spineRun.value.blocks,
      beats: spineRun.value.beats,
      events: eventsRun.value,
      scenes: sceneRun.value.scenes,
      validation: validationRun.value,
    }),
  });

  if (!validationRun.value.valid) throw new Error(`Analysis v3 validation failed: ${validationRun.value.errors.join('; ')}`);
  progress?.(`[analysis:v3] Hợp lệ sau ${((Date.now()-workflowStarted)/1000).toFixed(1)}s: coverage ${(coverageRun.value.coverage * 100).toFixed(1)}%, ${eventsRun.value.length} events, ${sceneRun.value.scenes.length} scenes.`);
  return {
    chapterAnalysis: toLegacy(options.source, options.chapterNumber, options.timeline, spineRun.value, eventsRun.value, sceneRun.value.scenes),
    spine: spineRun.value,
    events: eventsRun.value,
    scenes: sceneRun.value.scenes,
    conflicts: conflictsRun.value,
    coverage: coverageRun.value,
    validation: validationRun.value,
    manifest: store.snapshot(),
  };
}
