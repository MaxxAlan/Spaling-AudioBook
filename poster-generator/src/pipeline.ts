import path from 'node:path';
import { randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import { loadSource } from './sources/loader.js';
import { assertSingleChapterSource } from './sources/preflight.js';
import { sha256 } from './sources/hash.js';
import { compileCanon, compileMaster } from './canon/compiler.js';
import { detectChapterNumber, locateMaster } from './canon/master-locator.js';
import { runAnalysisV3 } from './analysis/workflow-v3.js';
import { resolveContinuity } from './canon/continuity-resolver.js';
import { loadReferences } from './characters/reference-loader.js';
import { resolveCharacterVisuals } from './characters/visual-resolver.js';
import { loadCharacterState, mergeCharacterState, saveCharacterState } from './characters/character-state.js';
import { rankScenes, type SceneWeights } from './analysis/scene-ranker.js';
import { buildConcepts, selectConcept } from './thumbnail/concept-builder.js';
import { buildBrief } from './thumbnail/brief-builder.js';
import { assertBriefSpoilerSafe } from './canon/spoiler-filter.js';
import { buildTiktokPrompt, buildYoutubePrompt, NEGATIVE_PROMPT } from './thumbnail/prompt-builder.js';
import { buildStoryboardNegativePrompt, buildStoryboardPrompt, storyboardTone } from './storyboard/prompt-builder.js';
import { inspectStoryboardImage } from './storyboard/image-quality.js';
import { reviewStoryboardImage } from './storyboard/vision-reviewer.js';
import { chapterDirectory } from './utils/paths.js';
import { ensureOutputDirectory, writeGeneratedImages, writeJson, writeText } from './thumbnail/output-writer.js';
import type { Environment } from './config/env.js';
import type { ProjectConfig } from './config/project-config.js';
import { createImageProvider, createTextProvider } from './providers/factory.js';
import type { ConceptType } from './schemas/thumbnail.js';
import type { Manifest } from './schemas/manifest.js';
import type { ComputeDevice, ImageQuality } from './providers/image/types.js';
import type { SceneCandidate } from './schemas/scene.js';
import { loadContextFiles, buildImageContextPrompt, extractChapterSummary, type ContextData } from './sources/context-loader.js';

export type Platform = 'youtube'|'tiktok'|'both';
export interface PipelineOptions { chapter: string; master: string; rules: string; chapterNumber?: number; out: string; platform: Platform; concept: ConceptType|'auto'; variants: number; seed?: number; references: string[]; dryRun: boolean; verbose: boolean; force: boolean; device?: ComputeDevice; quality?: ImageQuality; format?: 'png'|'jpeg'; storyboardCount?: number; sceneWeights?:SceneWeights; imageWorkers?:number; contextDir?: string; analysisDir?: string; onProgress?: (message:string)=>void; }
function activePlatforms(platform: Platform): Array<'youtube'|'tiktok'> { return platform === 'both' ? ['youtube','tiktok'] : [platform]; }
function compactCanonForChapter(canon: unknown, chapterText: string): unknown {
  if (!canon || typeof canon !== 'object') return canon;
  const ignored=new Set(['của','cho','với','trong','không','được','những','một','các','the','and','from','that','this']);
  const tokens=(value:string)=>value.normalize('NFD').replace(/\p{M}/gu,'').toLocaleLowerCase('vi').split(/[^\p{L}\p{N}]+/u).filter((token)=>token.length>=4&&!ignored.has(token));
  const chapterTokens=new Set(tokens(chapterText));
  return Object.fromEntries(Object.entries(canon as Record<string,unknown>).map(([key,value])=>{
    if(!Array.isArray(value)) return [key,value];
    const ranked=value.map((entry,index)=>{
      const text=typeof entry==='object'&&entry&&'value' in entry?String((entry as {value:unknown}).value):String(entry);
      return {entry,index,score:new Set(tokens(text).filter((token)=>chapterTokens.has(token))).size};
    }).filter((item)=>item.score>=2).sort((a,b)=>b.score-a.score||a.index-b.index).slice(0,12).map((item)=>item.entry);
    return [key,ranked];
  }));
}async function mapConcurrent<T>(count:number, workers:number, operation:(index:number)=>Promise<T>):Promise<T[]> {
  const results=new Array<T>(count); let cursor=0;
  const worker=async():Promise<void>=>{ while(true){ const index=cursor; cursor+=1; if(index>=count)return; results[index]=await operation(index); } };
  await Promise.all(Array.from({length:Math.max(1,Math.min(workers,count))},()=>worker()));
  return results;
}
export function selectStoryboardScenes(candidates: SceneCandidate[], requested: number): SceneCandidate[] {
  const usable=candidates.filter((item)=>item.scores?.visualImpact === undefined || item.scores.visualImpact >= 6);
  const ordered=[...usable].sort((a,b)=>a.scene.startLine-b.scene.startLine);
  if(!ordered.length) return [];
  const requestedCount=Math.max(1,requested);
  if(ordered.length<=requestedCount) return ordered;
  const count=Math.min(requestedCount,ordered.length);
  if(ordered.length<=count) return ordered;
  const selected:SceneCandidate[]=[];
  for(let index=0;index<count;index+=1){
    const start=Math.floor(index*ordered.length/count); const end=Math.max(start+1,Math.floor((index+1)*ordered.length/count));
    const bucket=ordered.slice(start,end).sort((a,b)=>b.weightedScore-a.weightedScore);
    if(bucket[0]) selected.push(bucket[0]);
  }
  return selected.sort((a,b)=>a.scene.startLine-b.scene.startLine);
}
function autoStoryboardCount(candidates: SceneCandidate[], quality: ImageQuality = 'standard'): number {
  if (!candidates.length) return 0;
  const ratio = quality === 'high' ? .7 : quality === 'draft' ? .35 : .5;
  return Math.max(1, Math.min(candidates.length, Math.round(candidates.length * ratio)));
}
export async function runPipeline(options: PipelineOptions, env: Environment, config: ProjectConfig, projectRoot = process.cwd()): Promise<{ directory: string; manifest: Manifest }> {
  options.onProgress?.('Đang đọc toàn bộ master, request và chapter...');
  const [chapter, masterSource, rulesSource] = await Promise.all([loadSource(options.chapter), loadSource(options.master), loadSource(options.rules)]);
  assertSingleChapterSource(chapter);
  const chapterNumber = detectChapterNumber(chapter, options.chapterNumber); const directory = chapterDirectory(options.out, chapterNumber); await ensureOutputDirectory(directory, options.force);

  // Load .md context files for enhanced accuracy
  const contextDir = options.contextDir || path.join(projectRoot, '.md');
  let contextData: ContextData = { characters: '', glossary: '', timeline: '', chapterSummaries: '', loadedFiles: [] };
  try {
    contextData = await loadContextFiles(contextDir);
    if (contextData.loadedFiles.length) {
      options.onProgress?.(`Đã tải context: ${contextData.loadedFiles.join(', ')}`);
    }
  } catch { /* Context files optional */ }

  const [canon, master] = await Promise.all([compileCanon(rulesSource, projectRoot), compileMaster(masterSource, projectRoot)]); const position = locateMaster(master, chapterNumber);
  options.onProgress?.(`Đã khóa canon: chương ${chapterNumber}, ${position.timeline}. Đang chạy analysis v3...`);

  // Enrich context with .md files
  const relevantContext = { ...contextData, chapterSummaries: extractChapterSummary(contextData.chapterSummaries, chapterNumber) };
  const contextJson = { canon: compactCanonForChapter(canon,chapter.text), masterPosition: position, relevantContext: buildImageContextPrompt(relevantContext) };
  const context = JSON.stringify(contextJson);
  const rawDirectory=options.verbose ? path.join(directory,'raw') : undefined;
  const analysisV3=await runAnalysisV3({
    source:chapter, chapterNumber, timeline:position.timeline, context,
    directory:options.analysisDir ?? path.join(directory,'analysis'),
    profile:env.ANALYSIS_PROFILE, directorModel:env.DIRECTOR_MODEL, workerModel:env.WORKER_MODEL,
    targetSceneCount:options.storyboardCount && options.storyboardCount > 0 ? options.storyboardCount : Math.max(1, chapter.lines.length),
    directorContextTokens:env.DIRECTOR_CONTEXT_TOKENS, directorMaxTokens:2048,
    createDirector:()=>createTextProvider(env,config,rawDirectory,env.DIRECTOR_MODEL,env.DIRECTOR_TIMEOUT_MS,2048,env.DIRECTOR_CONTEXT_TOKENS,2),
    createWorker:()=>createTextProvider(env,config,rawDirectory,env.WORKER_MODEL,env.WORKER_TIMEOUT_MS,10000,env.WORKER_CONTEXT_TOKENS,2),
    ...(options.onProgress?{onProgress:options.onProgress}:{}),
  });
  const analysis=analysisV3.chapterAnalysis;
  const chapterLower=chapter.text.toLocaleLowerCase('vi');
  const contextCharacterNames=[...contextData.characters.matchAll(/^#{2,}\s+(.+)$/gm)]
    .map((match)=>match[1]!.replace(/\s*\([^)]*\)\s*$/, '').trim())
    .filter((name)=>name!==name.toLocaleUpperCase('vi')&&chapterLower.includes(name.toLocaleLowerCase('vi')));
  analysis.charactersPresent=[...new Set([...contextCharacterNames,...analysis.charactersPresent])];
  const resolved = resolveContinuity(canon, position, analysis); const references = await loadReferences(projectRoot, options.references); const detectedCharacters = resolveCharacterVisuals(analysis, chapter, canon, references); const state = mergeCharacterState(await loadCharacterState(projectRoot), detectedCharacters); await saveCharacterState(projectRoot, state);
  const characters = detectedCharacters.map((character) => state.characters[character.characterId] ?? character);
  const candidates = rankScenes(analysis.scenes,options.sceneWeights); const concepts = buildConcepts(candidates); const selected = selectConcept(concepts, options.concept); const brief = buildBrief(analysis, selected, candidates, characters); assertBriefSpoilerSafe(brief, chapter.text);
  const requestedStoryboardCount = options.storyboardCount && options.storyboardCount > 0 ? options.storyboardCount : autoStoryboardCount(candidates, options.quality);
  options.onProgress?.(`[storyboard] AI chon ${requestedStoryboardCount} canh uu tien tu ${candidates.length} canh co bang chung.`);
  const storyboardCandidates=selectStoryboardScenes(candidates, requestedStoryboardCount);
  if(storyboardCandidates.length<requestedStoryboardCount) {
    const message=`Chi tim thay ${storyboardCandidates.length}/${requestedStoryboardCount} canh co bang chung trong chuong; khong nhan ban hoac tu bia canh.`;
    options.onProgress?.(message);
  }
  const storyboard:NonNullable<Manifest['storyboard']>=storyboardCandidates.map((candidate,index)=>({index:index+1,sceneId:candidate.scene.sceneId,startLine:candidate.scene.startLine,endLine:candidate.scene.endLine,location:candidate.scene.location,action:candidate.scene.action,platforms:{}}));
  options.onProgress?.(`Đã chọn ${selected.type} / ${selected.sceneId}. Đang tạo prompt ${options.platform}...`);
  const youtubePrompt = buildYoutubePrompt(brief); const tiktokPrompt = buildTiktokPrompt(brief); const platforms: Manifest['platforms'] = {}; const warnings = resolved.warnings.map((item) => item.reason);
  const sourceManifest = { chapter: chapter.path, master: masterSource.path, rules: rulesSource.path, readCompletely: true, lineCounts: { chapter: chapter.lines.length, master: masterSource.lines.length, rules: rulesSource.lines.length } };
  await Promise.all([writeJson(path.join(directory,'source-manifest.json'),sourceManifest), writeJson(path.join(directory,'canon-context.json'),canon), writeJson(path.join(directory,'master-position.json'),position), writeJson(path.join(directory,'chapter-analysis.json'),analysis), writeJson(path.join(directory,'resolved-context.json'),resolved), writeJson(path.join(directory,'continuity-warnings.json'),resolved.warnings), writeJson(path.join(directory,'characters-used.json'),characters), writeJson(path.join(directory,'scene-candidates.json'),candidates), writeJson(path.join(directory,'thumbnail-concepts.json'),concepts), writeJson(path.join(directory,'thumbnail-brief.json'),brief)]);
  const imageProvider=options.dryRun?undefined:createImageProvider(env,config);
  const storyboardQa:Array<{sceneId:string;platform:'youtube'|'tiktok';attempt:number;approved:boolean;meanLuma?:number;reasons:string[];vision?:unknown}>= [];
  const storyboardSeedBase=options.seed??Math.floor(Math.random()*2_000_000_000);
  try { for (const platform of activePlatforms(options.platform)) {
    const width = platform === 'youtube' ? 1920 : 1080; const height = platform === 'youtube' ? 1080 : 1920; const prompt = platform === 'youtube' ? youtubePrompt : tiktokPrompt;
    await Promise.all([writeText(path.join(directory,`${platform}-prompt.txt`),prompt), writeText(path.join(directory,`${platform}-negative-prompt.txt`),NEGATIVE_PROMPT)]);
    const request = { prompt, negativePrompt: NEGATIVE_PROMPT, width, height, variants: options.variants, ...(options.seed !== undefined ? { seed: options.seed } : {}), referenceImages: references, device: options.device ?? 'auto', quality:options.quality ?? 'high', outputFormat: options.format ?? 'png' };
    await writeJson(path.join(directory,`${platform}-request.json`),request); let imageNames: string[] = [];
    if (!options.dryRun) {
      if(!imageProvider) throw new Error('Image provider was not initialized.'); let providerRequest = request;
      if (references.length && !imageProvider.supportsReferenceImages) { warnings.push(`${imageProvider.name} không hỗ trợ reference image; visual description trong prompt được dùng thay thế.`); providerRequest = { ...request, referenceImages: [] }; }
      imageNames = await writeGeneratedImages(directory, platform, await imageProvider.generate({...providerRequest,...(options.onProgress?{onProgress:options.onProgress}:{})}), width, height, options.format ?? 'png');
      options.onProgress?.(`Đã ghi ${imageNames.length} ảnh ${platform} ${width}×${height}.`);
    }
    platforms[platform] = { width, height, prompt, negativePrompt: NEGATIVE_PROMPT, images: imageNames };
    let completedStoryboard = 0;
    await mapConcurrent(storyboardCandidates.length,options.imageWorkers??1,async(index)=>{
      const candidate=storyboardCandidates[index]!; const sceneConcept=buildConcepts([candidate])[0]!; const sceneBrief=buildBrief(analysis,sceneConcept,[candidate],characters); assertBriefSpoilerSafe(sceneBrief,chapter.text);
      const sceneNames=new Set(candidate.scene.characters.map((name)=>name.toLocaleLowerCase('vi')));
      const sceneReferences=[...new Set(characters
        .filter((character)=>sceneNames.has(character.name.toLocaleLowerCase('vi')))
        .flatMap((character)=>character.referenceImages))];
      const basePrompt=buildStoryboardPrompt(sceneBrief,platform); const negativePrompt=buildStoryboardNegativePrompt(sceneBrief); const label=`${platform}-scene-${String(index+1).padStart(4,'0')}`;
      let scenePrompt=basePrompt; let sceneImage=''; let finalRequest:Record<string,unknown>={};
      if(!options.dryRun){
        if(!imageProvider) throw new Error('Image provider was not initialized.');
        for(let attempt=1;attempt<=2;attempt+=1){
          scenePrompt=attempt===1?basePrompt:`${basePrompt}\nCorrection: previous render failed visual QA. Use darker low-key exposure, stronger physical action, visible target and environmental consequence; avoid cheerful portrait staging.`;
          const sceneRequest={prompt:scenePrompt,negativePrompt,width,height,variants:1,seed:storyboardSeedBase+index+1+(attempt-1)*1_000_003,referenceImages:sceneReferences,referenceWeight:0.72,device:options.device??'auto',quality:options.quality??'high',outputFormat:options.format??'png'};
          const usableRequest=sceneReferences.length&&!imageProvider.supportsReferenceImages?{...sceneRequest,referenceImages:[]}:sceneRequest;
          options.onProgress?.(`Đang sinh cảnh ${index+1}/${storyboardCandidates.length} cho ${platform}${attempt>1?' (QA retry)':''}...`);
          const generated=await imageProvider.generate({...usableRequest,...(options.onProgress?{onProgress:options.onProgress}:{})});
          const toneQa=imageProvider.name==='mock'
            ? {approved:true,meanLuma:0,reasons:[] as string[]}
            : await inspectStoryboardImage(generated[0]!.buffer,storyboardTone(sceneBrief));
          const visionQa=imageProvider.name==='mock'||!toneQa.approved
            ? undefined
            : await reviewStoryboardImage(generated[0]!.buffer,sceneBrief);
          const qa={
            approved:toneQa.approved&&(visionQa?.approved??true),
            meanLuma:toneQa.meanLuma,
            reasons:[...toneQa.reasons,...(visionQa?.reasons??[])],
            ...(visionQa?{vision:visionQa}:{}),
          };
          storyboardQa.push({sceneId:candidate.scene.sceneId,platform,attempt,...qa});
          finalRequest={...sceneRequest,visualQa:qa};
          if(qa.approved){
            sceneImage=(await writeGeneratedImages(directory,platform,generated,width,height,options.format??'png',label))[0]??'';
            break;
          }
          options.onProgress?.(`Cảnh ${index+1} bị QA từ chối: ${qa.reasons.join(', ')}.`);
          if(attempt===2) throw new Error(`Storyboard visual QA failed for ${candidate.scene.sceneId}: ${qa.reasons.join(', ')}`);
        }
      } else {
        finalRequest={prompt:scenePrompt,negativePrompt,width,height,variants:1,seed:storyboardSeedBase+index+1,referenceImages:sceneReferences,referenceWeight:0.72,device:options.device??'auto',quality:options.quality??'high',outputFormat:options.format??'png'};
      }
      await Promise.all([writeText(path.join(directory,`${label}-prompt.txt`),scenePrompt),writeJson(path.join(directory,`${label}-request.json`),finalRequest)]);
      const entry=storyboard[index]!; entry.platforms[platform]={prompt:scenePrompt,image:sceneImage};
      completedStoryboard += 1;
      options.onProgress?.(`Đã sinh cảnh ${completedStoryboard}/${storyboardCandidates.length} cho ${platform}.`);
      return sceneImage;
    });
  }} finally { await imageProvider?.close?.(); }
  await writeJson(path.join(directory,'storyboard-qa.json'),storyboardQa);
  const imageProviderInfo = imageProvider ?? { name: env.IMAGE_AI_PROVIDER, model: env.IMAGE_AI_MODEL || (env.IMAGE_AI_PROVIDER === 'mock' ? 'sharp-placeholder' : '') };
  const manifest: Manifest = { runId: randomUUID(), createdAt: new Date().toISOString(), chapterNumber, chapterTitle: analysis.chapterTitle, sourceHashes: { chapter: sha256(chapter.text), master: sha256(masterSource.text), rules: sha256(rulesSource.text) }, selectedSceneId: selected.sceneId, selectedConcept: selected.type, textProvider: env.TEXT_AI_PROVIDER, textModel: `${env.DIRECTOR_MODEL} -> ${env.WORKER_MODEL} -> ${env.DIRECTOR_MODEL}`, imageProvider: imageProviderInfo.name, imageModel: imageProviderInfo.model, platforms, ...(storyboard.length?{storyboard}:{}), referenceImages: references, warnings };
  await writeJson(path.join(directory,'manifest.json'),manifest); await writeText(path.join(directory,'run.log'),JSON.stringify({ runId: manifest.runId, completedAt: new Date().toISOString(), dryRun: options.dryRun, platforms: activePlatforms(options.platform) }));
  return { directory, manifest };
}

export async function regenerateFromManifest(manifestPath: string, newSeed: boolean, env: Environment, config: ProjectConfig): Promise<Manifest> {
  const absolute = path.resolve(manifestPath); const directory = path.dirname(absolute); const manifest = (await import('./schemas/manifest.js')).manifestSchema.parse(JSON.parse(await fs.readFile(absolute,'utf8'))); const provider = createImageProvider(env, config);
  try { for (const platform of ['youtube','tiktok'] as const) { const details = manifest.platforms[platform]; if (!details) continue; const requestFile = path.join(directory,`${platform}-request.json`); const request = JSON.parse(await fs.readFile(requestFile,'utf8')) as { seed?: number; referenceImages?: string[]; device?:ComputeDevice; quality?:ImageQuality; outputFormat?:'png'|'jpeg' }; const seed = newSeed ? Math.floor(Math.random() * 2_147_483_647) : request.seed; let refs = request.referenceImages ?? manifest.referenceImages; if (refs.length && !provider.supportsReferenceImages) { manifest.warnings.push(`${provider.name} không hỗ trợ reference image trong regenerate.`); refs = []; } const generated = await provider.generate({ prompt: details.prompt, negativePrompt: details.negativePrompt, width: details.width, height: details.height, variants: details.images.length || 3, ...(seed !== undefined ? { seed } : {}), referenceImages: refs,device:request.device ?? 'auto',quality:request.quality ?? 'high' }); details.images = await writeGeneratedImages(directory,platform,generated,details.width,details.height,request.outputFormat ?? 'png'); await writeJson(requestFile,{ prompt: details.prompt, negativePrompt: details.negativePrompt, width: details.width, height: details.height, variants: generated.length, ...(seed !== undefined ? { seed } : {}), referenceImages: request.referenceImages ?? [],device:request.device ?? 'auto',quality:request.quality ?? 'high',outputFormat:request.outputFormat ?? 'png' }); }} finally { await provider.close?.(); }
  manifest.runId = randomUUID(); manifest.createdAt = new Date().toISOString(); manifest.imageProvider = provider.name; manifest.imageModel = provider.model; await writeJson(absolute,manifest); return manifest;
}
