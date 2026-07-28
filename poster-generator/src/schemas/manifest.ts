import { z } from 'zod';

const platform = z.object({ width: z.number(), height: z.number(), prompt: z.string(), negativePrompt: z.string(), images: z.array(z.string()) });
const storyboardPlatform = z.object({ prompt: z.string(), image: z.string() });
const storyboardScene = z.object({
  index: z.number().int().positive(), sceneId: z.string(), startLine: z.number().int().positive(),
  endLine: z.number().int().positive(), location: z.string(), action: z.string(),
  platforms: z.object({ youtube: storyboardPlatform.optional(), tiktok: storyboardPlatform.optional() }),
});
export const manifestSchema = z.object({
  runId: z.string(), createdAt: z.string(), chapterNumber: z.number().int().positive(), chapterTitle: z.string(),
  sourceHashes: z.object({ chapter: z.string(), master: z.string(), rules: z.string() }), selectedSceneId: z.string(), selectedConcept: z.string(),
  textProvider: z.string(), textModel: z.string(), imageProvider: z.string(), imageModel: z.string(),
  platforms: z.object({ youtube: platform.optional(), tiktok: platform.optional() }),
  storyboard: z.array(storyboardScene).optional(), referenceImages: z.array(z.string()), warnings: z.array(z.string()),
});
export type Manifest = z.infer<typeof manifestSchema>;
