import fs from 'node:fs/promises';
import path from 'node:path';
import { z } from 'zod';
import { PROJECT_DIR } from '../utils/paths.js';

export const projectConfigSchema = z.object({
  version: z.literal(1), style: z.string(), chunkLines: z.number().int().min(20), chunkOverlap: z.number().int().min(0),
  textTimeoutMs: z.number().int().positive(), imageTimeoutMs: z.number().int().positive(),
});
export type ProjectConfig = z.infer<typeof projectConfigSchema>;
export const DEFAULT_CONFIG: ProjectConfig = { version: 1, style: 'cinematic-dark-fantasy', chunkLines: 160, chunkOverlap: 20, textTimeoutMs: 3600000, imageTimeoutMs: 13500000 };

export async function loadProjectConfig(cwd = process.cwd()): Promise<ProjectConfig> {
  try { return projectConfigSchema.parse(JSON.parse(await fs.readFile(path.join(cwd, PROJECT_DIR, 'config.json'), 'utf8'))); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return DEFAULT_CONFIG; throw error; }
}
