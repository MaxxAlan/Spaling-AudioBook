import fs from 'node:fs/promises';
import path from 'node:path';
import { AppError } from '../utils/errors.js';

export interface LoadedSource { path: string; text: string; lines: string[]; }
export async function loadSource(inputPath: string): Promise<LoadedSource> {
  const absolute = path.resolve(inputPath);
  let bytes: Buffer;
  try { bytes = await fs.readFile(absolute); }
  catch (error) { throw new AppError('SOURCE_NOT_FOUND', `Không thể đọc source file: ${absolute}`, error); }
  let text: string;
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes).replace(/^\uFEFF/, ''); }
  catch (error) { throw new AppError('INVALID_ENCODING', `File không phải UTF-8 hợp lệ: ${absolute}`, error); }
  if (!text.trim()) throw new AppError('EMPTY_SOURCE', `Source file rỗng: ${absolute}`);
  return { path: absolute, text, lines: text.split(/\r?\n/) };
}
