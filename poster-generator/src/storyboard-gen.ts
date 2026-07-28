#!/usr/bin/env node
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { Command } from 'commander';
import { loadEnvironment } from './config/env.js';
import { loadProjectConfig } from './config/project-config.js';
import { runPipeline, type Platform } from './pipeline.js';
import type { ConceptType } from './schemas/thumbnail.js';
import { errorMessage } from './utils/errors.js';
import type { ComputeDevice, ImageQuality } from './providers/image/types.js';

interface Options {
  master:string; rules:string; chapter:string; output:string; images:string;
  platform:Platform; format:'png'|'jpeg'; quality:ImageQuality;
  device:ComputeDevice; imageProvider?:'mock'|'comfyui';
  seed?:string; sceneWeights?:string; renderMode:'sequential'|'parallel'; parallelWorkers:string; force?:boolean;
  contextDir?:string; modelProfile?:string;
  projectRoot?:string;
}

function validateOptions(options:Options):number {
  const count=Number(options.images);
  if(!Number.isSafeInteger(count)||count<0) throw new Error('--images must be a non-negative integer (0 = AI auto).');
  if(!['youtube','tiktok','both'].includes(options.platform)) throw new Error(`Platform không hợp lệ: ${options.platform}`);
  if(!['png','jpeg'].includes(options.format)) throw new Error(`Format không hợp lệ: ${options.format}`);
  if(!['draft','standard','high'].includes(options.quality)) throw new Error(`Quality không hợp lệ: ${options.quality}`);
  if(!['cpu','gpu','auto'].includes(options.device)) throw new Error(`Thiết bị không hợp lệ: ${options.device}`);
  if(!['sequential','parallel'].includes(options.renderMode)) throw new Error(`Chế độ render không hợp lệ: ${options.renderMode}`);
  const workers=Number(options.parallelWorkers);
  if(!Number.isInteger(workers)||workers<1||workers>8) throw new Error('--parallel-workers phải từ 1 đến 8.');
  return count;
}

async function ensureInputs(options:Options):Promise<void> {
  for(const [label,file] of [['master',options.master],['request',options.rules],['chapter',options.chapter]] as const){
    const stat=await fs.stat(path.resolve(file)).catch(()=>undefined);
    if(!stat?.isFile()) throw new Error(`Không tìm thấy ${label}: ${file}`);
  }
}

async function main():Promise<void> {
  const program=new Command().name('storyboard-gen').description('Sinh ảnh bìa và nhiều cảnh tuần tự cho audiobook')
    .requiredOption('--master <path>','file master.md')
    .requiredOption('--rules <path>','file request.md')
    .requiredOption('--chapter <path>','file chapter.txt')
    .requiredOption('--output <directory>','thư mục ảnh đầu ra')
    .option('--images <number>','scene count (0 = AI selects by importance)','0')
    .option('--platform <youtube|tiktok|both>','tỷ lệ ảnh','youtube')
    .option('--format <png|jpeg>','định dạng ảnh','jpeg')
    .option('--quality <draft|standard|high>','chất lượng render','standard')
    .option('--device <cpu|gpu|auto>','thiết bị ComfyUI','auto')
    .option('--image-provider <mock|comfyui>','ghi đè provider trong .env')
    .option('--seed <number>','seed cố định')
    .option('--scene-weights <json>','trọng số chọn cảnh dạng JSON')
    .option('--render-mode <sequential|parallel>','chế độ sinh ảnh','sequential')
    .option('--parallel-workers <number>','số ảnh xử lý đồng thời','2')
    .option('--context-dir <directory>','thư mục .md context files (characters, glossary, timeline...)')
    .option('--project-root <directory>','thư mục state riêng của bộ truyện')
    .option('--model-profile <id>','chất lượng ảnh: low, medium, high, max','medium')
    .option('--force','ghi đè file đầu ra của storyboard')
    .showHelpAfterError();
  await program.parseAsync(process.argv); const options=program.opts<Options>(); const count=validateOptions(options); await ensureInputs(options);
  const output=path.resolve(options.output); await fs.mkdir(output,{recursive:true});
  const manifestTarget=path.join(output,'storyboard.json');
  if(!options.force) try{await fs.access(manifestTarget);throw new Error(`Output đã tồn tại: ${manifestTarget}. Dùng --force để ghi đè.`);}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
  const tempRoot=await fs.mkdtemp(path.join(os.tmpdir(),'storyboard-gen-'));
  const progressStartedAt=Date.now();
  const progress=(message:string):void=>{
    process.stdout.write(`[storyboard] ${message}\n`);
    const scene=message.match(/(Đang|Đã) sinh cảnh\s+(\d+)\/(\d+)/iu);
    const completed=scene ? Math.max(0, Number(scene[2])-(scene[1]==='Đang'?1:0)) : 0;
    const total=scene ? Number(scene[3]) : 0;
    const percent=total ? completed/total*100 : message.startsWith('Hoàn tất') ? 100 : 0;
    process.stdout.write(`@@progress ${JSON.stringify({stage:'storyboard',percent,completed,total,elapsed:(Date.now()-progressStartedAt)/1000,message})}\n`);
  };
  try{
    const env=loadEnvironment({...process.env,...(options.imageProvider?{IMAGE_AI_PROVIDER:options.imageProvider}:{}),...(options.modelProfile?{IMAGE_MODEL_PROFILE:options.modelProfile}:{})});
    let sceneWeights:Record<string,number>|undefined;
    if(options.sceneWeights){
      const parsed=JSON.parse(options.sceneWeights) as Record<string,unknown>;
      const allowed=new Set(['chapterRelevance','visualImpact','smallScreenReadability','mainSubjectClarity','emotionalImpact','curiosity','platformAdaptability','continuityAccuracy','spoilerSafety']);
      sceneWeights={};
      for(const [key,value] of Object.entries(parsed)){
        if(!allowed.has(key)||typeof value!=='number'||!Number.isFinite(value)||value<0) throw new Error(`Trọng số cảnh không hợp lệ: ${key}`);
        sceneWeights[key]=value;
      }
    }
    const imageWorkers=options.renderMode==='parallel'?Number(options.parallelWorkers):1;
    const contextDirPath = options.contextDir ? path.resolve(options.contextDir) : undefined;
    const pipelineOpts = {
      chapter:path.resolve(options.chapter),master:path.resolve(options.master),rules:path.resolve(options.rules),
      out:path.join(tempRoot,'pipeline'),platform:options.platform,concept:'auto' as ConceptType,variants:1,
      ...(options.seed!==undefined?{seed:Number(options.seed)}:{}),
      ...(sceneWeights?{sceneWeights}:{}),
      ...(contextDirPath?{contextDir:contextDirPath}:{}),
      analysisDir:path.join(output,'analysis'),
      references:[],dryRun:false,verbose:false,force:true,
      device:options.device,quality:options.quality,format:options.format,
      storyboardCount:count,imageWorkers,onProgress:progress,
    };
    const result=await runPipeline(pipelineOpts,env,await loadProjectConfig(),options.projectRoot?path.resolve(options.projectRoot):path.dirname(output));
    const extension=options.format==='jpeg'?'jpg':'png'; const platforms=options.platform==='both'?['youtube','tiktok'] as const:[options.platform] as Array<'youtube'|'tiktok'>;
    const covers:Record<string,string>={};
    for(const platform of platforms){
      const source=result.manifest.platforms[platform]?.images[0]; if(!source) throw new Error(`Pipeline không tạo ảnh bìa ${platform}.`);
      const target=path.join(output,`cover-${platform}.${extension}`); await fs.copyFile(path.join(result.directory,source),target); covers[platform]=path.resolve(target);
    }
    const scenes=[];
    for(const item of result.manifest.storyboard??[]){
      const images:Record<string,string>={}; const prompts:Record<string,string>={};
      for(const platform of platforms){
        const details=item.platforms[platform]; if(!details?.image) continue;
        const target=path.join(output,`scene-${String(item.index).padStart(4,'0')}-${platform}.${extension}`);
        await fs.copyFile(path.join(result.directory,details.image),target); images[platform]=path.resolve(target); prompts[platform]=details.prompt;
      }
      scenes.push({index:item.index,scene_id:item.sceneId,start_line:item.startLine,end_line:item.endLine,location:item.location,action:item.action,images,prompts});
    }
    if(scenes.length<1) throw new Error('Chương không cung cấp cảnh có bằng chứng để tạo storyboard.');
    const chapterText=await fs.readFile(path.resolve(options.chapter),'utf8');
    const manifest={version:'1.0',created_at:new Date().toISOString(),chapter_number:result.manifest.chapterNumber,chapter_title:result.manifest.chapterTitle,chapter_line_count:chapterText.split(/\r?\n/).length,requested_scenes:count||scenes.length,generated_scenes:scenes.length,render_mode:options.renderMode,image_workers:imageWorkers,platform:options.platform,format:options.format,quality:options.quality,image_provider:result.manifest.imageProvider,image_model:result.manifest.imageModel,covers,scenes,warnings:result.manifest.warnings};
    await fs.writeFile(manifestTarget,`${JSON.stringify(manifest,null,2)}\n`,'utf8');
    for(const artifact of ['storyboard-qa.json','characters-used.json','continuity-warnings.json','scene-candidates.json']){
      const source=path.join(result.directory,artifact);
      try{await fs.copyFile(source,path.join(output,artifact));}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
    }
    progress(`Hoàn tất ${scenes.length} cảnh + ${Object.keys(covers).length} ảnh bìa: ${output}`);
  } finally { await fs.rm(tempRoot,{recursive:true,force:true}); }
}

main().catch((error:unknown)=>{process.stderr.write(`storyboard-gen: ${errorMessage(error)}\n`);process.exitCode=1;});
