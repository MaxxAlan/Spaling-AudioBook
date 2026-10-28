# TypeScript / poster-generator Map

Package: `story-thumbnail` (pnpm, Node >= 20)

## Bin / Entry
- `storyboard-gen` → `src/storyboard-gen.ts`
- `poster-gen` → `src/poster-gen.ts`
- `scene-rerender` → `src/scene-rerender.ts`
- `story-thumbnail` → `src/cli.ts`

Build: `pnpm build` (tsc → dist/)

## src/ structure & key exports

### analysis/
- `analyzeFullChapter(...)` – chapter-analyzer.ts
- `mergeChunkAnalyses(...)` – analysis-merger.ts
- `AnalysisArtifactStore` – artifact-store.ts (job fingerprint, atomic write)
- `scene-ranker.ts`, `structural-segmenter.ts`, `chunk-analyzer.ts`
- `workflow-v3.ts` – groundedSceneUnits, narrative spine, extraction plans

### characters/
- `character-bible.ts`, `character-state.ts`
- `visual-resolver.ts`, `reference-loader.ts`

### sources/
- `loader.ts`, `chunker.ts`, `context-loader.ts`
- `cache.ts`, `hash.ts`, `line-index.ts`, `preflight.ts`

### providers/
- `factory.ts`
- text: `ollama.ts`, `mock.ts`, types
- image: `comfyui.ts`, `mock.ts`, types

### storyboard/
- `prompt-builder.ts`, `vision-reviewer.ts`, `image-quality.ts`

### thumbnail/
- `brief-builder.ts`, `concept-builder.ts`
- `platform-composer.ts`, `prompt-builder.ts`, `output-writer.ts`

### prompts/
- Templates: `canon-compiler.ts`, `chapter-chunk.ts`, `chapter-merge.ts`
- `character-visual.ts`, `master-locator.ts`, `scene-ranking.ts`
- `thumbnail-director.ts`, `tiktok-image-prompt.ts`, `youtube-image-prompt.ts`

### schemas/ (Zod)
- `analysis-v3.ts`, `canon.ts`, `chapter.ts`, `character.ts`
- `common.ts`, `manifest.ts`, `master.ts`, `scene.ts`, `thumbnail.ts`

### utils/
- `errors.ts`, `logger.ts` (pino), `paths.ts`, `retry.ts`

### config/
- `env.ts`, `model-profiles.ts`, `project-config.ts`

## Conventions
- ESM (`"type": "module"`)
- Zod cho validation mọi artifact
- Atomic write + content-addressed cache (sha256)
- Provider abstraction (text + image) dễ mock / swap
- Log qua pino, structured
