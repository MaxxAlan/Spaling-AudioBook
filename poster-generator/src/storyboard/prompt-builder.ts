import type { ThumbnailBrief } from '../schemas/thumbnail.js';
import { NEGATIVE_PROMPT, REQUIRED_NO_TEXT, REQUIRED_SOURCE_FIDELITY } from '../thumbnail/prompt-builder.js';

export type StoryboardTone = 'dark' | 'neutral';

const DARK = /(?:dark|shadow|night|abyss|void|black|violet|blood|death|fear|horror|ruin|storm|combat|battle|attack|fight|ma thuật đen|hắc|đen|tím|bóng tối|vực thẳm|máu|chết|kinh hoàng|chiến|tấn công|đổ nát|bão)/iu;
const COMBAT = /(?:combat|battle|fight|attack|strike|clash|duel|war|chiến|đánh|tấn công|va chạm|đối đầu|chém|đấm|bắn|nổ)/iu;
const MAGIC = /(?:magic|spell|ritual|curse|mana|energy|abyss|void|ma thuật|phép|ma lực|nghi lễ|lời nguyền|vực thẳm|ấn)/iu;

function compact(value: string, limit = 280): string {
  return value.replace(/\s+/g, ' ').trim().slice(0, limit);
}

export function storyboardTone(brief: ThumbnailBrief): StoryboardTone {
  const text = [
    brief.coreVisualIdea, brief.lighting, ...brief.colorPalette,
    ...brief.magicEffects, ...(brief.requiredVisuals ?? []),
  ].join(' ');
  return DARK.test(text) ? 'dark' : 'neutral';
}

function shotGrammar(brief: ThumbnailBrief, platform: 'youtube' | 'tiktok'): string {
  const text = [brief.coreVisualIdea, ...(brief.requiredVisuals ?? []), ...brief.magicEffects].join(' ');
  if (COMBAT.test(text)) {
    return platform === 'youtube'
      ? 'dynamic medium-wide or wide action shot; show attacker, target, direction of motion, point of impact, defensive response, and physical consequence in one coherent frame'
      : 'dynamic vertical medium-wide action shot; keep attacker, target, impact and consequence readable from foreground to background';
  }
  if (MAGIC.test(text)) {
    return platform === 'youtube'
      ? 'cinematic wide or medium-wide shot; show the caster, complete magical effect, its target, scale, and interaction with the environment'
      : 'vertical medium-wide shot; show the caster, full magical effect, target and environmental reaction without cropping the effect';
  }
  if (brief.representationMode === 'dialogue_reaction' || brief.representationMode === 'relationship') {
    return 'environmental medium two-shot or over-the-shoulder composition; make speaker-listener reaction, distance, gaze and relationship blocking readable; never reduce the scene to a solo portrait';
  }
  if (brief.representationMode === 'inner_turn' || brief.representationMode === 'revelation') {
    return 'environmental medium shot; communicate the internal turn through grounded expression, posture, gaze, nearby people and source-confirmed surroundings; avoid an isolated beauty portrait';
  }
  if (brief.representationMode === 'memory') {
    return 'cinematic memory tableau grounded only in the recalled source event; distinguish remembered time from the present through composition and motivated lighting, without inventing symbols';
  }
  if (brief.representationMode === 'atmosphere' || brief.representationMode === 'transition') {
    return 'wide establishing story frame; foreground the source-described place, time, weather and sensory change while keeping any present character spatially grounded';
  }
  return platform === 'youtube'
    ? 'cinematic establishing or medium shot chosen for the visible event; preserve spatial relationships and environmental context'
    : 'vertical establishing or medium shot chosen for the visible event; preserve spatial relationships and environmental context';
}

export function assertStoryboardBrief(brief: ThumbnailBrief): void {
  if (!brief.environment.trim() || /không xác định|unknown|unspecified/iu.test(brief.environment)) {
    throw new Error(`Storyboard scene ${brief.selectedConcept.sceneId} lacks a source-grounded location.`);
  }
  if (!brief.coreVisualIdea.trim() || /^[“"'«].*[”"'»][.!?…]*$/u.test(brief.coreVisualIdea.trim())) {
    throw new Error(`Storyboard scene ${brief.selectedConcept.sceneId} lacks a visible action.`);
  }
}

export function buildStoryboardPrompt(
  brief: ThumbnailBrief,
  platform: 'youtube' | 'tiktok',
): string {
  assertStoryboardBrief(brief);
  const tone = storyboardTone(brief);
  const orientation = platform === 'youtube'
    ? 'horizontal 16:9 cinematic story keyframe'
    : 'vertical 9:16 cinematic story keyframe';
  const color = tone === 'dark'
    ? 'full-color image, low-key exposure, deep blacks, restrained saturation, colored emissive magic, localized rim light, volumetric smoke and shadow; readable faces and action; never monochrome or grayscale'
    : 'full-color image with source-grounded time-of-day, weather and motivated cinematic lighting; natural restrained saturation; never monochrome or grayscale';
  const secondary = brief.secondarySubjects
    .map((item) => typeof item === 'string' ? item : `${item.name} (${item.description})`)
    .join(', ');
  const required = (brief.requiredVisuals ?? [brief.coreVisualIdea]).map((item) => compact(item)).filter(Boolean).slice(0, 6);
  const meaning = brief.narrativeMeaning.map((item) => compact(item)).filter(Boolean).slice(0, 6);

  return `A ${orientation}, not a thumbnail, poster, advertisement, portrait sheet, collage, or product image.

${color}. ${REQUIRED_SOURCE_FIDELITY}.
Depict this exact visible event: ${compact(brief.coreVisualIdea)}.
Primary subject: ${compact(brief.mainSubject.visualDescription)}; ${compact(brief.mainSubject.action)}; ${compact(brief.mainSubject.expression, 120)}.
Character continuity lock: ${brief.continuityRequirements.map((item) => compact(item, 100)).join('; ')}.
${secondary ? `Other source-confirmed subjects: ${compact(secondary)}.` : ''}
Source-grounded location: ${compact(brief.environment)}.
Required visible facts: ${required.join('; ')}.
${meaning.length ? `Narrative meaning that the frame must communicate: ${meaning.join('; ')}. Express it only through source-grounded action, reaction, blocking, atmosphere and objects; do not invent symbolic props.` : ''}
${brief.magicEffects.length ? `Magic and physical effects: ${brief.magicEffects.map((item) => compact(item, 100)).join('; ')}. Effects must visibly interact with characters and environment.` : ''}
${brief.objects.length ? `Source-confirmed objects: ${brief.objects.join(', ')}.` : ''}
${brief.creatures.length ? `Source-confirmed creatures: ${brief.creatures.join(', ')}.` : ''}
${shotGrammar(brief, platform)}.
Lighting and palette: ${compact(brief.lighting)}; ${brief.colorPalette.join(', ')}.
Keep stable character identity and current chapter state. Do not add culture-specific clothing, hats, architecture, symbols or ethnicity without source evidence.
Painterly cinematic realism, physically coherent action, atmospheric depth, ${REQUIRED_NO_TEXT}.`;
}

export function buildStoryboardNegativePrompt(brief: ThumbnailBrief): string {
  const storySpecific = storyboardTone(brief) === 'dark'
    ? ', cheerful pastel palette, clean sunny pastoral mood, glossy fashion portrait, bright commercial lighting, empty peaceful landscape, static character posing'
    : '';
  return `${NEGATIVE_PROMPT}, thumbnail layout, portrait sheet, character lineup, static pose, empty scene, missing action, missing target, missing magic effect, cultural costume not supported by source${storySpecific}`;
}
