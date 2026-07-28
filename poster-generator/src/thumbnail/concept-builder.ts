import type { SceneCandidate } from '../schemas/scene.js';
import type { ConceptType, ThumbnailConcept } from '../schemas/thumbnail.js';
import { weightedScore } from '../analysis/scene-ranker.js';

const types: ConceptType[] = ['character','climax','mystery','symbolic'];
export function buildConcepts(candidates: SceneCandidate[]): ThumbnailConcept[] {
  const fitness = (candidate: SceneCandidate, type: ConceptType): number => {
    const text = `${candidate.scene.action} ${candidate.scene.turningPoint}`;
    if (type === 'character') return (candidate.scores.mainSubjectClarity + candidate.scores.emotionalImpact) / 2 + (candidate.scene.characters.length === 1 ? 1 : 0);
    if (type === 'climax') return (candidate.scores.visualImpact + candidate.scores.chapterRelevance + candidate.scores.emotionalImpact) / 3 + (/nghi lễ|bao phủ|đối đầu|lao|nứt/i.test(text) ? 1 : 0);
    if (type === 'mystery') return (candidate.scores.curiosity + candidate.scores.spoilerSafety) / 2 + (/từ xa|bí ẩn|không rõ|bóng/i.test(text) ? 1 : 0);
    return (candidate.scores.visualImpact + candidate.scores.curiosity) / 2 + (/giọt|pha lê|vòng tròn|phù ấn/i.test(text) ? 1 : 0);
  };
  return types.map((type) => {
    const candidate = [...candidates].sort((a,b) => fitness(b,type) - fitness(a,type) || b.weightedScore - a.weightedScore)[0]!;
    const bonus = Math.max(0,fitness(candidate,type)-8) * .12;
    return { type, sceneId: candidate.scene.sceneId, title: `${type} focus`, visualHook: candidate.scene.turningPoint || candidate.scene.action, reason: `${type} interpretation selected by ${type}-specific scene fitness and global thumbnail scoring`, spoilerLevel: candidate.scene.spoilerLevel, scores: candidate.scores, weightedScore: Number((weightedScore(candidate.scores) + bonus).toFixed(3)) };
  }).sort((a, b) => b.weightedScore - a.weightedScore);
}
export function selectConcept(concepts: ThumbnailConcept[], requested: ConceptType | 'auto'): ThumbnailConcept {
  const selected = requested === 'auto' ? concepts[0] : concepts.find((item) => item.type === requested); if (!selected) throw new Error(`Không có concept hợp lệ: ${requested}`); return selected;
}
