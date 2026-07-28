import path from 'node:path';

export const PROJECT_DIR = '.story-thumbnail';
export function chapterDirectory(out: string, chapterNumber: number): string {
  return path.resolve(out, `chapter-${String(chapterNumber).padStart(3, '0')}`);
}
export function resolveFrom(base: string, value: string): string { return path.resolve(base, value); }
export function slugify(value: string): string {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/đ/g, 'd').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}
