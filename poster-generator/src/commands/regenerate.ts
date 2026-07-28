import type { Command } from 'commander';
import type { Environment } from '../config/env.js';
import { loadProjectConfig } from '../config/project-config.js';
import { regenerateFromManifest } from '../pipeline.js';

export function registerRegenerateCommand(program: Command, env: Environment): void {
  program.command('regenerate').description('Sinh lại ảnh từ manifest và prompt đã khóa').requiredOption('--manifest <path>','manifest.json path').option('--new-seed','generate a new random seed').action(async ({manifest,newSeed}:{manifest:string;newSeed?:boolean}) => { const result = await regenerateFromManifest(manifest,Boolean(newSeed),env,await loadProjectConfig()); process.stdout.write(`Regenerated run ${result.runId}\n`); });
}
