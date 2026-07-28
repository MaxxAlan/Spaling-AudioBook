import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';
import type { GeneratedImage } from '../providers/image/types.js';

export async function ensureOutputDirectory(directory: string, force: boolean): Promise<void> {
  try { const entries = await fs.readdir(directory); if (entries.length && !force) throw new Error(`Output đã tồn tại và không rỗng: ${directory}. Dùng --force để ghi đè.`); }
  catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  await fs.mkdir(directory, { recursive: true });
}
export async function writeJson(file: string, data: unknown): Promise<void> { await fs.mkdir(path.dirname(file), { recursive: true }); await fs.writeFile(file, `${JSON.stringify(data, null, 2)}\n`, 'utf8'); }
export async function writeText(file: string, data: string): Promise<void> { await fs.mkdir(path.dirname(file), { recursive: true }); await fs.writeFile(file, `${data.trim()}\n`, 'utf8'); }
export async function writeGeneratedImages(directory: string, platform: 'youtube'|'tiktok', images: GeneratedImage[], width: number, height: number, format: 'png'|'jpeg' = 'png', basename?: string): Promise<string[]> {
  const names: string[] = [];
  for (let index = 0; index < images.length; index += 1) { const extension=format==='jpeg'?'jpg':'png'; const prefix=basename ?? platform; const name = `${prefix}-${String(index + 1).padStart(2, '0')}.${extension}`; const pipeline=sharp(images[index]!.buffer).resize(width, height, { fit: 'cover', position: 'attention' }); if(format==='jpeg') await pipeline.jpeg({quality:94,chromaSubsampling:'4:4:4'}).toFile(path.join(directory,name)); else await pipeline.png().toFile(path.join(directory,name)); await writeJson(path.join(directory,`${name}.metadata.json`),{seed:images[index]!.seed,providerMetadata:images[index]!.providerMetadata}); names.push(name); }
  return names;
}
