import fs from 'node:fs/promises';
import path from 'node:path';
import { slugify } from '../utils/paths.js';
import { AppError } from '../utils/errors.js';

const imageExtensions = new Set(['.png', '.jpg', '.jpeg', '.webp']);
export async function loadReferences(projectRoot: string, explicit: string[] = []): Promise<string[]> {
  const directory = path.join(projectRoot, '.story-thumbnail', 'references'); let automatic: string[] = [];
  try { automatic = (await fs.readdir(directory, { withFileTypes: true })).filter((entry) => entry.isFile() && imageExtensions.has(path.extname(entry.name).toLowerCase())).map((entry) => path.join(directory, entry.name)); }
  catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  const resolved = [...automatic, ...explicit.map((item) => path.resolve(item))];
  for (const file of resolved) { try { await fs.access(file); } catch { throw new AppError('REFERENCE_NOT_FOUND', `Không tìm thấy reference image: ${file}`); } }
  return [...new Set(resolved)];
}
export function mapReferences(characterName: string, references: string[]): string[] {
  const slug = slugify(characterName); return references.filter((file) => slugify(path.basename(file, path.extname(file))).includes(slug));
}
