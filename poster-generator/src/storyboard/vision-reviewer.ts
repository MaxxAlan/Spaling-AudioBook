import { z } from 'zod';
import type { ThumbnailBrief } from '../schemas/thumbnail.js';

const requiredBoolean = z.preprocess(
  (value) => value === true || value === 'yes' || value === 'true' || (Array.isArray(value) && value.length > 0),
  z.boolean(),
).catch(false);
const optionalBoolean = z.preprocess(
  (value) => value == null ? null : value === true || value === 'yes' || value === 'true',
  z.boolean().nullable(),
).catch(null);
const reviewSchema = z.object({
  location_match: requiredBoolean,
  action_match: requiredBoolean,
  character_match: requiredBoolean,
  combat_match: optionalBoolean,
  magic_match: optionalBoolean,
  cultural_drift: requiredBoolean,
  reasons: z.array(z.string()).catch([]),
});

export type VisionReview = z.infer<typeof reviewSchema> & {
  approved: boolean;
  model: string;
  judgeModel?: string;
  caption?: string;
};

const COMBAT = /(?:combat|battle|fight|attack|strike|clash|duel|chiến|đánh|tấn công|va chạm|đối đầu|chém|bắn|nổ)/iu;
const MAGIC = /(?:magic|spell|ritual|curse|mana|abyss|void|ma thuật|phép|ma lực|nghi lễ|lời nguyền|vực thẳm|ấn)/iu;

export function finalizeVisionReview(
  value: z.infer<typeof reviewSchema>,
  model: string,
  expectsCombat: boolean,
  expectsMagic: boolean,
): VisionReview {
  const reasons = [...value.reasons];
  if (!value.location_match) reasons.push('wrong_location');
  if (!value.action_match) reasons.push('missing_action');
  if (!value.character_match) reasons.push('wrong_character_state');
  if (expectsCombat && value.combat_match !== true) reasons.push('missing_combat');
  if (expectsMagic && value.magic_match !== true) reasons.push('missing_magic_effect');
  if (value.cultural_drift) reasons.push('cultural_drift');
  const unique = [...new Set(reasons)];
  return { ...value, reasons: unique, approved: unique.length === 0, model };
}

function settingCategory(value: string): string | undefined {
  const categories: Array<[string, RegExp]> = [
    ['cave', /(?:cave|cavern|hang động|động băng)/iu],
    ['forest', /(?:forest|woods|trees|jungle|rừng|cây cối)/iu],
    ['desert', /(?:desert|dunes|sa mạc|cồn cát)/iu],
    ['city', /(?:city|street|buildings|thành phố|đường phố)/iu],
    ['interior', /(?:room|hall|chamber|phòng|đại sảnh)/iu],
  ];
  return categories.find(([, pattern]) => pattern.test(value))?.[0];
}

export function correctReviewFromCaption(
  review: z.infer<typeof reviewSchema>,
  caption: string,
  brief: ThumbnailBrief,
): z.infer<typeof reviewSchema> {
  const expectedSetting = settingCategory(brief.environment);
  const actualSetting = settingCategory(caption);
  const expectedPeople = 1 + brief.secondarySubjects.length;
  const captionHasMultiple = /(?:two|three|several|multiple|men|women|people|hai|ba|nhiều người)/iu.test(caption);
  const unsupportedCulture = /(?:superman|superhero|samurai|kimono|hanfu|áo dài|nón lá|chinese imperial|japanese traditional)/iu.test(caption)
    && !/(?:superman|superhero|samurai|kimono|hanfu|áo dài|nón lá|chinese imperial|japanese traditional)/iu.test(
      `${brief.mainSubject.visualDescription} ${brief.environment} ${(brief.requiredVisuals ?? []).join(' ')}`,
    );
  return {
    ...review,
    location_match: expectedSetting && actualSetting && expectedSetting !== actualSetting
      ? false : review.location_match,
    character_match: expectedPeople > 1 && !captionHasMultiple
      ? false : review.character_match,
    cultural_drift: review.cultural_drift || unsupportedCulture,
  };
}

export async function reviewStoryboardImage(
  buffer: Buffer,
  brief: ThumbnailBrief,
  options: {
    baseUrl?: string;
    model?: string;
    fetcher?: typeof fetch;
  } = {},
): Promise<VisionReview> {
  const model = options.model || process.env.VISION_QA_MODEL || 'moondream';
  const judgeModel = process.env.VISION_QA_JUDGE_MODEL || 'qwen2.5:1.5b';
  const baseUrl = (options.baseUrl || process.env.OLLAMA_BASE_URL || 'http://127.0.0.1:11434').replace(/\/$/, '');
  const fetcher = options.fetcher ?? fetch;
  const visibleFacts = (brief.requiredVisuals ?? [brief.coreVisualIdea]).join('; ');
  const expectation = [brief.coreVisualIdea, visibleFacts, ...brief.magicEffects].join(' ');
  const expectsCombat = COMBAT.test(expectation);
  const expectsMagic = MAGIC.test(expectation);
  const captionResponse = await fetcher(`${baseUrl}/api/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      model,
      stream: false,
      keep_alive: '5m',
      options: { temperature: 0, seed: 42, num_gpu: 0 },
      messages: [{
        role: 'user',
        content: 'Describe this image in detail. State the setting, number and appearance of people, visible action, combat, magic effects, lighting, colors, clothing and culture-specific symbols. Do not guess names.',
        images: [buffer.toString('base64')],
      }],
    }),
    signal: AbortSignal.timeout(300_000),
  });
  if (!captionResponse.ok) {
    throw new Error(`Vision QA ${model} failed: HTTP ${captionResponse.status} ${await captionResponse.text()}`);
  }
  const captionPayload = await captionResponse.json() as { message?: { content?: string } };
  const caption = captionPayload.message?.content?.trim();
  if (!caption) throw new Error(`Vision QA ${model} returned an empty caption.`);
  const contract = `Location: ${brief.environment}
Visible event: ${brief.coreVisualIdea}
Characters: ${brief.mainSubject.visualDescription}; ${brief.secondarySubjects.map((item) => typeof item === 'string' ? item : item.name).join(', ')}
Required facts: ${visibleFacts}
Magic/effects: ${brief.magicEffects.join('; ')}
Combat expected: ${expectsCombat}. Magic expected: ${expectsMagic}.`;
  const judgePrompt = `You are a strict validator. Compare CAPTION to CONTRACT. Output ONE JSON object and nothing else. location_match, action_match, character_match and cultural_drift MUST be booleans. combat_match and magic_match MUST be booleans, or null only when CONTRACT says that feature is not expected. reasons MUST be an array of short reason codes.
Example: {"location_match":false,"action_match":false,"character_match":false,"combat_match":null,"magic_match":false,"cultural_drift":true,"reasons":["wrong_location","missing_magic_effect"]}
CONTRACT:
${contract}
CAPTION:
${caption}`;
  const judgeResponse = await fetcher(`${baseUrl}/api/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      model: judgeModel,
      stream: false,
      format: 'json',
      keep_alive: '5m',
      options: { temperature: 0, seed: 42, num_gpu: 0 },
      messages: [{ role: 'user', content: judgePrompt }],
    }),
    signal: AbortSignal.timeout(300_000),
  });
  if (!judgeResponse.ok) {
    throw new Error(`Vision QA judge ${judgeModel} failed: HTTP ${judgeResponse.status} ${await judgeResponse.text()}`);
  }
  const payload = await judgeResponse.json() as { message?: { content?: string } };
  const content = payload.message?.content?.trim();
  if (!content) throw new Error(`Vision QA judge ${judgeModel} returned an empty response.`);
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    const match = content.match(/\{[\s\S]*\}/);
    if (!match) throw new Error(`Vision QA ${model} returned invalid JSON.`);
    parsed = JSON.parse(match[0]);
  }
  const reviewed = correctReviewFromCaption(reviewSchema.parse(parsed), caption, brief);
  return {
    ...finalizeVisionReview(reviewed, model, expectsCombat, expectsMagic),
    judgeModel,
    caption,
  };
}
