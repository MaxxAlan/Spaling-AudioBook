#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { Command } from 'commander';
import { loadEnvironment } from './config/env.js';
import { loadProjectConfig } from './config/project-config.js';
import { runPipeline, type Platform } from './pipeline.js';
import { errorMessage } from './utils/errors.js';
import type { ComputeDevice, ImageQuality } from './providers/image/types.js';

interface PosterOptions { input:string[]; output:string; cpu?:boolean; gpu?:boolean; auto?:boolean; format:'png'|'jpeg'|'jpg'; quality:ImageQuality; platform:Platform; variants:string; seed?:string; force?:boolean; }
function normalizeLegacyFlags(argv:string[]):string[]{ const aliases:Record<string,string>={'-input':'--input','-output':'--output','-cpu':'--cpu','-gpu':'--gpu','-auto':'--auto','-format':'--format','-quality':'--quality','-platform':'--platform','-variants':'--variants','-seed':'--seed','-force':'--force'}; return argv.map((token)=>aliases[token] ?? token); }
async function classifyInputs(inputs:string[]):Promise<{master:string;rules:string;chapter:string}>{ if(inputs.length!==3) throw new Error(`-input cần đúng 3 file, nhận được ${inputs.length}.`); const absolute=inputs.map((value)=>path.resolve(value)); const chapter=absolute.find((file)=>path.extname(file).toLowerCase()==='.txt'); const markdown=absolute.filter((file)=>path.extname(file).toLowerCase()==='.md'); if(!chapter||markdown.length!==2) throw new Error('-input phải gồm hai file .md và một file .txt.'); let master=markdown.find((file)=>/master|outline|structure/i.test(path.basename(file))); let rules=markdown.find((file)=>/request|rule|canon|yêu.?cầu/i.test(path.basename(file))); if(!master||!rules){ const samples=await Promise.all(markdown.map(async(file)=>({file,text:(await fs.readFile(file,'utf8')).slice(0,8000)}))); master??=samples.find((item)=>/(?:Chương|Chapters?|Ch\.)\s*\d+\s*[–—-]\s*\d+/i.test(item.text))?.file; rules??=samples.find((item)=>/YÊU CẦU|CANON|luật|RULES|REQUIREMENTS/i.test(item.text))?.file; } if(!master||!rules||master===rules) throw new Error('Không phân biệt được master.md và request.md từ tên/nội dung file.'); return {master,rules,chapter}; }
function device(options:PosterOptions):ComputeDevice{ const selected=[options.cpu,options.gpu,options.auto].filter(Boolean).length; if(selected>1) throw new Error('Chỉ dùng một trong -cpu, -gpu hoặc -auto.'); return options.cpu?'cpu':options.gpu?'gpu':'auto'; }

const program=new Command().name('poster-gen').description('Đọc canon + chapter và sinh story artwork PNG/JPEG dùng trực tiếp với FFmpeg').requiredOption('--input <paths...>','hai file Markdown và một chapter TXT').requiredOption('--output <path>','thư mục output hoặc tên file ảnh').option('--cpu','buộc ComfyUI chạy CPU').option('--gpu','dùng GPU low-VRAM').option('--auto','tự chọn thiết bị').option('--format <png|jpeg>','định dạng ảnh','png').option('--quality <draft|standard|high>','chất lượng render Flux','high').option('--platform <youtube|tiktok|both>','bố cục đầu ra','youtube').option('--variants <number>','số ảnh mỗi nền tảng','1').option('--seed <number>','seed cố định').option('--force','ghi đè output đã tồn tại').showHelpAfterError();
program.parseAsync(normalizeLegacyFlags(process.argv)).then(async()=>{
  const options=program.opts<PosterOptions>(); const format=options.format==='jpg'?'jpeg':options.format;
  if(!['png','jpeg'].includes(format)) throw new Error(`Format không hợp lệ: ${options.format}`);
  if(!['draft','standard','high'].includes(options.quality)) throw new Error(`Quality không hợp lệ: ${options.quality}`);
  if(!['youtube','tiktok','both'].includes(options.platform)) throw new Error(`Platform không hợp lệ: ${options.platform}`);
  const variants=Number(options.variants); if(!Number.isInteger(variants)||variants<1||variants>10) throw new Error('-variants phải là số nguyên từ 1 đến 10.');
  const sources=await classifyInputs(options.input); const requested=path.resolve(options.output); const fileOutput=/\.(?:png|jpe?g)$/i.test(requested); const platform=fileOutput?'youtube':options.platform;
  if(fileOutput&&variants!==1) throw new Error('Khi -output là một file ảnh, -variants phải bằng 1.');
  const extension=format==='jpeg'?'jpg':'png'; const platforms=platform==='both'?['youtube','tiktok']:[platform]; const expectedTargets=fileOutput?[requested]:platforms.flatMap((name)=>Array.from({length:variants},(_,index)=>path.join(requested,`${name}-${String(index+1).padStart(2,'0')}.${extension}`)));
  if(!options.force) for(const target of expectedTargets) try{await fs.access(target);throw new Error(`Ảnh output đã tồn tại: ${target}. Dùng -force để ghi đè.`);}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
  const tempRoot=await fs.mkdtemp(path.join(os.tmpdir(),'poster-gen-')); const progress=(message:string)=>process.stdout.write(`[poster-gen] ${message}\n`); progress(`Bắt đầu; output: ${requested}`);
  try{
    const result=await runPipeline({chapter:sources.chapter,master:sources.master,rules:sources.rules,out:path.join(tempRoot,'pipeline'),platform,concept:'auto',variants,...(options.seed?{seed:Number(options.seed)}:{}),references:[],dryRun:false,verbose:false,force:true,device:device(options),quality:options.quality,format,onProgress:progress},loadEnvironment(),await loadProjectConfig());
    if(fileOutput){const generated=result.manifest.platforms.youtube?.images[0];if(!generated)throw new Error('Pipeline không tạo ảnh YouTube để ghi ra output file.');await fs.mkdir(path.dirname(requested),{recursive:true});await fs.copyFile(path.join(result.directory,generated),requested);progress(`Hoàn tất: ${requested}`);}
    else{await fs.mkdir(requested,{recursive:true});for(const details of Object.values(result.manifest.platforms))for(const image of details?.images??[]){const target=path.join(requested,path.basename(image));await fs.copyFile(path.join(result.directory,image),target);progress(`Hoàn tất: ${target}`);}}
  }finally{const resolvedTemp=path.resolve(tempRoot);const tempParent=`${path.resolve(os.tmpdir())}${path.sep}`;if(resolvedTemp.startsWith(tempParent))await fs.rm(resolvedTemp,{recursive:true,force:true});}
}).catch((error:unknown)=>{ process.stderr.write(`poster-gen: ${errorMessage(error)}\n`); process.exitCode=1; });
