import type { Scene } from '../schemas/chapter.js';
import type { SceneCandidate, SceneScores } from '../schemas/scene.js';

export const SCORE_WEIGHTS: Record<keyof SceneScores, number> = { chapterRelevance: .18, visualImpact: .18, smallScreenReadability: .16, mainSubjectClarity: .14, emotionalImpact: .10, curiosity: .10, platformAdaptability: .06, continuityAccuracy: .04, spoilerSafety: .04 };
export type SceneWeights = Partial<Record<keyof SceneScores, number>>;
export function normalizedWeights(overrides: SceneWeights = {}): Record<keyof SceneScores, number> {
  const merged={...SCORE_WEIGHTS,...overrides};
  const total=Object.values(merged).reduce((sum,value)=>sum+Math.max(0,Number(value)||0),0);
  if(total<=0) return {...SCORE_WEIGHTS};
  return Object.fromEntries(
    Object.entries(merged).map(([key,value])=>[key,Math.max(0,Number(value)||0)/total]),
  ) as Record<keyof SceneScores,number>;
}
export function weightedScore(scores: SceneScores, overrides: SceneWeights = {}): number {
  const weights=normalizedWeights(overrides);
  return Number((Object.entries(weights) as Array<[keyof SceneScores, number]>).reduce((sum, [key, weight]) => sum + scores[key] * weight, 0).toFixed(3));
}
export function scoreScene(scene: Scene, sceneCount: number, weights: SceneWeights = {}): SceneCandidate {
  const text = `${scene.action} ${scene.turningPoint} ${scene.result} ${scene.visualElements.join(' ')}`; const subjectCount = scene.characters.length;
  const combat=/chiến|đánh|tấn công|đối đầu|va chạm|chém|bắn|nổ|combat|battle|fight|attack|strike|clash/iu.test(text);
  const magic=/ma thuật|ma lực|phép|nghi lễ|vực thẳm|lửa|sét|băng|magic|spell|ritual|abyss|fire|lightning|ice/iu.test(text);
  const visible=/bước|chạy|quay|nhìn|cầm|rút|ném|vỡ|nứt|sụp|cháy|bùng|bao phủ|walk|run|turn|look|hold|draw|throw|break|crack|collapse|burn|burst|surround/iu.test(text);
  const literary=/nhận ra|hiểu ra|quyết định|lựa chọn|ký ức|nhớ lại|tiết lộ|sự thật|tha thứ|phản bội|lời hứa|im lặng|do dự|realiz|decid|choos|memory|remember|reveal|truth|forgiv|betray|promise|silence|hesitat/iu.test(text);
  const atmosphere=/mưa|tuyết|sương|khói|bóng tối|ánh sáng|gió|lạnh|nóng|âm thanh|tiếng|rain|snow|mist|smoke|shadow|light|wind|cold|heat|sound/iu.test(text);
  const visual = combat||magic ? 10 : visible||atmosphere ? 8 : literary||scene.representationMode !== undefined ? 7 : 3;
  const clarity = subjectCount === 1 ? 9 : subjectCount === 0 ? 6 : Math.max(3, 9 - subjectCount);
  const small = Math.max(3, clarity - (scene.visualElements.length > 6 ? 2 : 0));
  const consequence=/chết|bị thương|thay đổi|phá hủy|sụp|vỡ|bỏ chạy|quyết định|tiết lộ|phản bội|lời hứa|death|wound|change|destroy|collapse|flee|decid|reveal|betray|promise/iu.test(text);
  const scores: SceneScores = { chapterRelevance: consequence ? 10 : combat||magic ? 9 : literary ? 8 : Math.min(8, 6 + (sceneCount <= 8 ? 1 : 0)), visualImpact: visual, smallScreenReadability: small, mainSubjectClarity: clarity, emotionalImpact: /đau|căm|sợ|chết|kinh hoàng|do dự|ân hận|hy vọng|tuyệt vọng|pain|rage|fear|death|horror|hesitat|regret|hope|despair/iu.test(`${text} ${scene.emotion}`) ? 9 : literary ? 8 : 6, curiosity: /bí|nghi lễ|luồng|từ xa|vực thẳm|ký ức|tiết lộ|sự thật|mystery|ritual|abyss|unknown|memory|reveal|truth/iu.test(text) ? 9 : 6, platformAdaptability: combat ? 9 : subjectCount <= 3 ? 8 : 5, continuityAccuracy: scene.evidence.length&&scene.location&&!/không xác định|unknown/iu.test(scene.location) ? 10 : 3, spoilerSafety: scene.spoilerLevel === 'low' ? 10 : scene.spoilerLevel === 'medium' ? 6 : 2 };
  return { scene, scores, weightedScore: weightedScore(scores,weights), rationale: `Grounded authored moment; subjects=${subjectCount}; combat=${combat}; magic=${magic}; literary=${literary}; consequence=${consequence}.` };
}
export function rankScenes(scenes: Scene[], weights: SceneWeights = {}): SceneCandidate[] {
  if (!scenes.length) throw new Error('Không có scene hợp lệ để tạo thumbnail.'); return scenes.map((scene) => scoreScene(scene, scenes.length,weights)).sort((a, b) => b.weightedScore - a.weightedScore);
}
