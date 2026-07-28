import type { Command } from 'commander';
import type { Environment } from '../config/env.js';
import { loadProjectConfig } from '../config/project-config.js';
import { runPipeline } from '../pipeline.js';
import { addPipelineOptions, normalizeOptions, type RawOptions } from './options.js';

export function registerAnalyzeCommand(program: Command, env: Environment): void {
  const command = addPipelineOptions(program.command('analyze'),env,false); command.action(async (raw: RawOptions) => { const result = await runPipeline(normalizeOptions(raw,true),env,await loadProjectConfig()); process.stdout.write(`Analysis: ${result.directory}\n`); });
}
