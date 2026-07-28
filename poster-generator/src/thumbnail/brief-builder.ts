import type { ChapterAnalysis } from '../schemas/chapter.js';
import type { CharacterVisual } from '../schemas/character.js';
import type { SceneCandidate } from '../schemas/scene.js';
import type { ThumbnailBrief, ThumbnailConcept } from '../schemas/thumbnail.js';
import { youtubeComposition, tiktokComposition } from './platform-composer.js';

function englishAction(value:string):string { return value || 'a concrete moment from the chapter'; }

function englishEnvironment(value:string):string { return value || 'the source-described environment'; }

function englishAppearance(value:string|null):string|null { return value; }

function visualEffects(action:string,visualElements:string[]):string[]{
  const text=[action,...visualElements].join(' ');
  const values:string[]=[];
  // Generic effect detection — not hardcoded to one story
  if(/lửa|flame|fire|burn/i.test(text)) values.push('magical fire effects');
  if(/gió|wind/i.test(text)) values.push('wind effects');
  if(/sét|lightning|thunder/i.test(text)) values.push('lightning effects');
  if(/nước|water|rain/i.test(text)) values.push('water effects');
  if(/bóng|shadow|dark/i.test(text)) values.push('dark shadow effects');
  if(/sáng|glow|light|shine/i.test(text)) values.push('glowing light effects');
  if(/nứt|crack|shatter/i.test(text)) values.push('cracking earth effects');
  if(/ma lực|magic|phép/i.test(text)) values.push('magical energy effects');
  return values.slice(0,4);
}

function findDialogueForScene(scene: ChapterAnalysis['scenes'][number]) {
  return scene.dialogues?.find((item) => item.visualMoment?.trim()) ?? null;
}

function conciseExpression(value:string):string {
  if(/căm|giận|angry|rage|hatred/iu.test(value)) return 'controlled anger and hatred';
  if(/sợ|kinh hoàng|fear|terror/iu.test(value)) return 'visible fear and tension';
  if(/đau|pain|wound/iu.test(value)) return 'pain held under control';
  if(/buồn|sad|grief/iu.test(value)) return 'restrained grief';
  if(/vui|happy|joy/iu.test(value)) return 'source-appropriate relief';
  return 'focused expression appropriate to the visible event';
}

function groundedEnvironment(scene:ChapterAnalysis['scenes'][number],analysis:ChapterAnalysis):string {
  const location=scene.location?.trim();
  if(location&&!/không xác định|unknown|unspecified/iu.test(location)) return location;
  const quote=scene.evidence.find((item)=>item.quote?.trim())?.quote?.replace(/\s+/g,' ').trim();
  if(quote) return `the source-described surroundings visible in this evidence: ${quote.slice(0,220)}`;
  return analysis.locations.find((item)=>item.trim()&&!/không xác định|unknown/iu.test(item))
    ?? 'the source-described environment';
}

function findObjectsForScene(analysis: ChapterAnalysis, scene: { visualElements: string[]; action: string }) {
  if (!analysis.importantObjects?.length) return [];
  const sceneText = [...scene.visualElements, scene.action].join(' ').toLowerCase();
  return analysis.importantObjects.filter(o => {
    return sceneText.includes(o.name.toLowerCase()) || sceneText.includes(o.visualDetails.toLowerCase());
  }).slice(0, 3);
}

export function buildBrief(analysis: ChapterAnalysis, concept: ThumbnailConcept, candidates: SceneCandidate[], characters: CharacterVisual[]): ThumbnailBrief {
  const scene = candidates.find((item) => item.scene.sceneId === concept.sceneId)?.scene ?? candidates[0]!.scene;
  const sceneText=[scene.action,...scene.visualElements].join(' ').toLocaleLowerCase('vi');
  const sceneNames=new Set(scene.characters.map((item)=>item.toLocaleLowerCase('vi')));
  const mentionedCharacters=characters.filter((item)=>sceneNames.has(item.name.toLocaleLowerCase('vi'))||item.name.split(/\s+/).some((token)=>token.length>2&&sceneText.includes(token.toLocaleLowerCase('vi'))));
  const character=mentionedCharacters[0];
  const mainName=character?.name??scene.characters[0]??'source-grounded central subject';

  const visibleAge = character?.identity.visibleAge ? `appears about ${character.identity.visibleAge} years old` : 'age not visually specified';
  const appearance = character ? [
    character.identity.gender ? `gender ${character.identity.gender}` : null,
    englishAppearance(character.canonicalAppearance.face),
    englishAppearance(character.canonicalAppearance.hair),
    englishAppearance(character.canonicalAppearance.eyes),
    englishAppearance(character.canonicalAppearance.skin),
    englishAppearance(character.canonicalAppearance.body),
    englishAppearance(character.canonicalAppearance.clothing),
    ...character.canonicalAppearance.accessories,
  ].filter(Boolean).join(', ') : '';
  const action=englishAction(scene.action);
  const environment=englishEnvironment(groundedEnvironment(scene,analysis));
  const effects=visualEffects(scene.action,scene.visualElements);

  // Find dialogue for this scene
  const dialogue = findDialogueForScene(scene);
  const dialogueDesc = dialogue
    ? `Saying: "${dialogue.text.slice(0, 100)}..." with ${dialogue.emotion} expression`
    : '';

  // Find objects for this scene
  const sceneObjects = findObjectsForScene(analysis, scene);
  const objectsDesc = sceneObjects.length
    ? `Key objects: ${sceneObjects.map(o => `${o.name} (${o.visualDetails})`).join(', ')}`
    : '';

  // Use scene mood/lighting if available
  const mood = scene.mood || scene.emotion || '';
  const lighting = scene.lighting || (/hoàng hôn/i.test(scene.time + scene.action) ? 'dramatic blood-red sunset with high local contrast' : 'dramatic motivated cinematic lighting');
  const colors = scene.dominantColors?.length ? scene.dominantColors : ['deep shadow', 'cold blue', 'controlled crimson'];

  return {
    chapter: { number: analysis.chapterNumber, title: analysis.chapterTitle, timeline: analysis.timeline },
    selectedConcept: { type: concept.type, sceneId: concept.sceneId, reason: concept.reason, spoilerLevel: concept.spoilerLevel },
    coreVisualIdea: action,
    mainSubject: {
      characterId: character?.characterId ?? '',
      visualDescription: `${mainName}, ${visibleAge}${appearance ? `, ${appearance}` : ''}`,
      pose: 'active, readable silhouette',
      expression: dialogueDesc || conciseExpression(mood),
      action,
      chapterState: character?.chapterState?.emotion || 'chapter-current state',
    },
    secondarySubjects: mentionedCharacters.slice(1).map((item) => ({
      name: item.name,
      description: [
        item.identity.gender ? `gender ${item.identity.gender}` : '',
        item.canonicalAppearance.face,
        item.canonicalAppearance.hair,
        item.canonicalAppearance.eyes,
        item.canonicalAppearance.clothing,
      ].filter(Boolean).join(', ') || item.name,
    })),
    foreground: effects.includes('cracked earth effects') ? 'cracked earth radiating magical veins' : 'controlled atmospheric foreground',
    midground: mainName,
    background: environment,
    environment,
    requiredVisuals: [...new Set([scene.action, ...scene.visualElements])]
      .map((item)=>item.replace(/\s+/g,' ').trim().slice(0,280)).filter(Boolean).slice(0, 6),
    narrativeMeaning: [...new Set([
      scene.authorialIntent,
      scene.objective,
      scene.opposition,
      scene.turningPoint,
      scene.result,
      ...(scene.narrativeSubtext ?? []),
    ].filter((item): item is string => Boolean(item?.trim())))].slice(0, 6),
    representationMode: scene.representationMode ?? 'literal_action',
    magicEffects: effects,
    objects: sceneObjects.map(o => o.name),
    creatures: (analysis.creatures??[]).filter((creature)=>[scene.action,...scene.visualElements].join(' ').toLowerCase().includes(creature.toLowerCase())),
    visualSymbols: effects,
    lighting,
    colorPalette: colors,
    youtubeComposition,
    tiktokComposition,
    style: {
      genre: 'dark fantasy',
      rendering: 'painterly realism cinematic keyframe',
      texture: 'atmospheric and tactile',
      detail: 'detailed but visually controlled',
    },
    dialogue: dialogueDesc,
    importantObjects: objectsDesc,
    continuityRequirements: character ? [
      `visible age: ${character.identity.visibleAge ?? 'unknown'}`,
      `gender: ${character.identity.gender ?? 'unknown'}`,
      ...Object.entries(character.canonicalAppearance)
        .filter(([, value]) => Array.isArray(value) ? value.length : Boolean(value))
        .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`),
    ] : [],
    forbiddenElements: ['text','title','caption','typography','letters','words','logo','watermark','signature','advertising layout','future events','future costume','future artifact'],
  };
}
