#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import { Command } from 'commander';
import { loadEnvironment } from './config/env.js';
import { loadProjectConfig } from './config/project-config.js';
import { createImageProvider } from './providers/factory.js';
import { NEGATIVE_PROMPT } from './thumbnail/prompt-builder.js';
import { writeGeneratedImages } from './thumbnail/output-writer.js';
import { inspectStoryboardImage } from './storyboard/image-quality.js';
import type { ImageQuality } from './providers/image/types.js';

type Scene = {
  index:number; scene_id:string; action:string;
  images:Record<string,string>; prompts:Record<string,string>;
};
type Storyboard = {
  quality:ImageQuality; format:'png'|'jpeg'; scenes:Scene[];
};
type Override = {
  prompts?:Record<string,string>; reference_images?:string[]; tone?:string; camera?:string;
};

async function main():Promise<void> {
  const program=new Command().name('scene-rerender')
    .requiredOption('--storyboard <path>')
    .requiredOption('--overrides <path>')
    .requiredOption('--scene <id>')
    .requiredOption('--platform <youtube|tiktok>');
  await program.parseAsync(process.argv);
  const options=program.opts<{storyboard:string;overrides:string;scene:string;platform:'youtube'|'tiktok'}>();
  const storyboardPath=path.resolve(options.storyboard);
  const directory=path.dirname(storyboardPath);
  const storyboard=JSON.parse(await fs.readFile(storyboardPath,'utf8')) as Storyboard;
  const overrides=JSON.parse(await fs.readFile(path.resolve(options.overrides),'utf8')) as {
    scenes?:Record<string,Override>;
  };
  const scene=storyboard.scenes.find((item)=>item.scene_id===options.scene);
  if(!scene) throw new Error(`Scene not found: ${options.scene}`);
  const override=overrides.scenes?.[scene.scene_id]??{};
  const basePrompt=override.prompts?.[options.platform]?.trim()||scene.prompts[options.platform]?.trim();
  if(!basePrompt) throw new Error(`Scene ${scene.scene_id} has no ${options.platform} prompt`);
  const directives=[
    override.tone==='dark'?'dark low-key source-faithful lighting':override.tone==='neutral'?'neutral source-faithful lighting':'',
    override.camera&&override.camera!=='source'?`${override.camera} camera shot`:'',
  ].filter(Boolean);
  const prompt=directives.length?`${basePrompt}\nEditor directives: ${directives.join('; ')}.`:basePrompt;
  const target=path.resolve(scene.images[options.platform]??'');
  if(!target||!target.startsWith(`${directory}${path.sep}`)) throw new Error('Scene image target is outside storyboard directory');
  const references=(override.reference_images??[]).map((item)=>path.resolve(item));
  for(const reference of references) await fs.access(reference);
  const provider=createImageProvider(loadEnvironment(),await loadProjectConfig());
  try {
    const width=options.platform==='youtube'?1920:1080;
    const height=options.platform==='youtube'?1080:1920;
    const generated=await provider.generate({
      prompt,negativePrompt:NEGATIVE_PROMPT,width,height,variants:1,
      seed:Math.floor(Math.random()*2_147_483_647),referenceImages:references,
      referenceWeight:0.72,device:'gpu',quality:storyboard.quality,
      onProgress:(message)=>process.stdout.write(`${message}\n`),
    });
    if(provider.name!=='mock'){
      const qa=await inspectStoryboardImage(generated[0]!.buffer,override.tone==='dark'?'dark':'neutral');
      if(!qa.approved) throw new Error(`Rerender QA failed: ${qa.reasons.join(', ')}`);
    }
    const label=`.rerender-${scene.index}-${Date.now()}`;
    const temporary=(await writeGeneratedImages(directory,options.platform,generated,width,height,storyboard.format,label))[0];
    if(!temporary) throw new Error('Image provider returned no image');
    const temporaryPath=path.join(directory,temporary);
    await fs.rename(temporaryPath,target);
    await fs.rm(`${temporaryPath}.metadata.json`,{force:true});
    scene.prompts[options.platform]=basePrompt;
    storyboard.scenes=storyboard.scenes.map((item)=>item.scene_id===scene.scene_id?scene:item);
    const next=`${storyboardPath}.tmp`;
    await fs.writeFile(next,`${JSON.stringify(storyboard,null,2)}\n`,'utf8');
    await fs.rename(next,storyboardPath);
  } finally {
    await provider.close?.();
  }
}

main().catch((error:unknown)=>{
  process.stderr.write(`scene-rerender: ${error instanceof Error?error.message:String(error)}\n`);
  process.exitCode=1;
});
