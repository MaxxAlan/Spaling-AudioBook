import type { Command } from 'commander';
import type { Environment } from '../config/env.js';
import { loadProjectConfig } from '../config/project-config.js';
import { runPipeline } from '../pipeline.js';
import { addPipelineOptions, normalizeOptions, type RawOptions } from './options.js';

export function registerGenerateCommand(program: Command, env: Environment): void {
  addPipelineOptions(program.command('generate').description('Phân tích và sinh artwork YouTube/TikTok'),env,true).action(async (raw: RawOptions) => { const result = await runPipeline(normalizeOptions(raw),env,await loadProjectConfig()); process.stdout.write(`Generated: ${result.directory}\n`); });
}
