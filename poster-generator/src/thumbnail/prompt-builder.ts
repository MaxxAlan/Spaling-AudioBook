import type { ThumbnailBrief } from '../schemas/thumbnail.js';
import { YOUTUBE_ARTWORK_PREFIX } from '../prompts/youtube-image-prompt.js';
import { TIKTOK_ARTWORK_PREFIX } from '../prompts/tiktok-image-prompt.js';

export const REQUIRED_NO_TEXT = 'no text, no title, no caption, no typography, no letters, no words, no logo, no watermark, no signature';
export const REQUIRED_FULL_COLOR = 'full-color image, source-grounded color palette, restrained cinematic color grading, clearly readable lighting and materials, never monochrome or grayscale';
export const REQUIRED_SOURCE_FIDELITY = 'faithful adaptation of the supplied chapter evidence; narration language is not cultural evidence; do not invent or substitute culture, ethnicity, clothing, architecture, characters, objects, locations, actions, or magic';
export const NEGATIVE_PROMPT = `text, title, caption, typography, letters, words, random letters,
black and white, monochrome, grayscale, greyscale, desaturated, colorless,
fake writing, malformed text, logo, watermark, signature, credits,
advertisement, commercial product layout, product photography,
sales banner, promotional poster, catalog design,
collage, split screen, multiple unrelated scenes,
tiny main character, distant unreadable face,
duplicate character, cloned face, extra person,
deformed face, asymmetrical eyes, malformed hands,
extra fingers, missing fingers, extra limbs,
distorted anatomy, incorrect visible age,
inconsistent eye color, inconsistent hair color,
incorrect costume, future transformation,
future artifact, future faction symbol,
flat lighting, muddy composition, cluttered background,
low contrast focal subject, blurry face, low quality`;

function formatSecondarySubjects(subjects: ThumbnailBrief['secondarySubjects']): string {
  if (!subjects.length) return '';
  return subjects.map(s => typeof s === 'string' ? s : `${s.name} (${s.description})`).join(', ');
}

export function buildYoutubePrompt(brief: ThumbnailBrief): string {
  const c = brief.youtubeComposition;
  const secondary = formatSecondarySubjects(brief.secondarySubjects);
  const dialogueHint = brief.dialogue ? `\nFacial expression and body language should reflect: ${brief.dialogue}` : '';
  const objectsHint = brief.importantObjects ? `\nInclude these key objects in the scene: ${brief.importantObjects}` : '';
  const creaturesHint = brief.creatures.length ? `\nCreatures present: ${brief.creatures.join(', ')}.` : '';
  const effectsHint = brief.magicEffects.length ? ` Magic effects: ${brief.magicEffects.join('; ')}.` : '';
  const meaningHint = brief.narrativeMeaning.length
    ? `\nNarrative meaning to communicate through source-grounded expression, action, blocking and atmosphere: ${brief.narrativeMeaning.join('; ')}.`
    : '';

  return `${YOUTUBE_ARTWORK_PREFIX}

${REQUIRED_FULL_COLOR}. ${REQUIRED_SOURCE_FIDELITY}. One clear dominant focal subject, large and immediately readable at small size: ${brief.mainSubject.visualDescription}. The character is ${brief.mainSubject.pose}, ${brief.mainSubject.action}, showing ${brief.mainSubject.expression}.${dialogueHint}

Required visible details: ${(brief.requiredVisuals ?? [brief.coreVisualIdea]).join('; ')}.
${meaningHint}
${secondary ? `Secondary subjects: ${secondary}.` : ''}
The scene takes place in ${brief.environment}, with ${brief.coreVisualIdea}.${effectsHint}${objectsHint}${creaturesHint}
${brief.lighting}. Palette: ${brief.colorPalette.join(', ')}.

${c.cameraShot}, ${c.cameraAngle}; ${c.subjectPosition}; ${c.depth}; ${c.cropSafety}; ${c.visualFlow}. Dynamic horizontal visual flow, no tiny important details, no collage, no advertising layout, no product presentation.

Dark fantasy cinematic keyframe, painterly realism, atmospheric storytelling, detailed but visually controlled, ${REQUIRED_NO_TEXT}.`;
}

export function buildTiktokPrompt(brief: ThumbnailBrief): string {
  const c = brief.tiktokComposition;
  const secondary = formatSecondarySubjects(brief.secondarySubjects);
  const dialogueHint = brief.dialogue ? `\nFacial expression and body language should reflect: ${brief.dialogue}` : '';
  const objectsHint = brief.importantObjects ? `\nInclude these key objects in the scene: ${brief.importantObjects}` : '';
  const creaturesHint = brief.creatures.length ? `\nCreatures present: ${brief.creatures.join(', ')}.` : '';
  const meaningHint = brief.narrativeMeaning.length
    ? `\nNarrative meaning to communicate through source-grounded expression, action, blocking and atmosphere: ${brief.narrativeMeaning.join('; ')}.`
    : '';

  return `${TIKTOK_ARTWORK_PREFIX}

${REQUIRED_FULL_COLOR}. ${REQUIRED_SOURCE_FIDELITY}. One clear dominant focal subject, centered and highly readable on a mobile screen: ${brief.mainSubject.visualDescription}. The character is ${brief.mainSubject.pose}, ${brief.mainSubject.action}, showing ${brief.mainSubject.expression}.${dialogueHint}

Required visible details: ${(brief.requiredVisuals ?? [brief.coreVisualIdea]).join('; ')}.
${meaningHint}
${secondary ? `Secondary subjects: ${secondary}.` : ''}
The scene rises vertically through ${brief.foreground || 'the immediate foreground'}, the subject, ${brief.environment}, and the background, with ${brief.coreVisualIdea} framing the character without covering the face.${objectsHint}${creaturesHint}
${brief.lighting}. Palette: ${brief.colorPalette.join(', ')}.

${c.cameraShot}, ${c.cameraAngle}; ${c.subjectPosition}; ${c.depth}; ${c.cropSafety}; ${c.visualFlow}. Strong silhouette, dramatic vertical depth, no wide cinematic crop, no tiny background characters, no advertising layout.

Dark fantasy cinematic keyframe, painterly realism, atmospheric storytelling, ${REQUIRED_NO_TEXT}.`;
}
