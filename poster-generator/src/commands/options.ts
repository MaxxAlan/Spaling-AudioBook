import type { Command } from 'commander';
import type { PipelineOptions, Platform } from '../pipeline.js';
import type { ConceptType } from '../schemas/thumbnail.js';
import type { Environment } from '../config/env.js';

export interface RawOptions { chapter: string; master: string; rules: string; chapterNumber?: string; out?: string; platform?: Platform; concept?: ConceptType|'auto'; variants?: string; seed?: string; reference?: string[]; dryRun?: boolean; verbose?: boolean; force?: boolean; }
function collect(value: string, previous: string[]): string[] { return [...previous,value]; }
export function addPipelineOptions(command: Command, env: Environment, generation: boolean): Command {
  command.requiredOption('--chapter <path>','chapter.txt path').requiredOption('--master <path>','master.md path').requiredOption('--rules <path>','request.md / canon rules path').option('--chapter-number <number>','explicit chapter number').option('--out <directory>','output directory',env.THUMBNAIL_OUTPUT_DIR).option('--platform <youtube|tiktok|both>','target platform',env.THUMBNAIL_DEFAULT_PLATFORM).option('--concept <auto|character|climax|mystery|symbolic>','thumbnail concept','auto').option('--variants <number>','image variants',String(env.THUMBNAIL_DEFAULT_VARIANTS)).option('--seed <number>','generation seed').option('--reference <path>','reference image; repeatable',collect,[]).option('--dry-run','analyze and write prompts without image API').option('--verbose','store raw text-provider responses').option('--force','allow writing into an existing chapter output');
  if (!generation) command.description('Phân tích đầy đủ chapter/canon/master và tạo brief').setOptionValueWithSource('dryRun',true,'default'); return command;
}
export function normalizeOptions(raw: RawOptions, analyzeOnly = false): PipelineOptions {
  const variants = Number(raw.variants ?? 3); if (!Number.isInteger(variants) || variants < 1 || variants > 10) throw new Error('--variants phải là số nguyên từ 1 đến 10.'); const platform = raw.platform ?? 'both'; if (!['youtube','tiktok','both'].includes(platform)) throw new Error(`Platform không hợp lệ: ${platform}`); const concept = raw.concept ?? 'auto'; if (!['auto','character','climax','mystery','symbolic'].includes(concept)) throw new Error(`Concept không hợp lệ: ${concept}`);
  return { chapter: raw.chapter, master: raw.master, rules: raw.rules, ...(raw.chapterNumber !== undefined ? { chapterNumber: Number(raw.chapterNumber) } : {}), out: raw.out ?? './output', platform, concept, variants, ...(raw.seed !== undefined ? { seed: Number(raw.seed) } : {}), references: raw.reference ?? [], dryRun: analyzeOnly || Boolean(raw.dryRun), verbose: Boolean(raw.verbose), force: Boolean(raw.force) };
}
