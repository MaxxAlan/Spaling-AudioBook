import fs from 'node:fs/promises';
import path from 'node:path';
import { z } from 'zod';

const envelopeSchema = z.object({ sourceHash: z.string(), createdAt: z.string(), data: z.unknown() });
export async function readCache<T>(file: string, sourceHash: string, schema: z.ZodType<T>): Promise<T | undefined> {
  try {
    const envelope = envelopeSchema.parse(JSON.parse(await fs.readFile(file, 'utf8')));
    if (envelope.sourceHash !== sourceHash) return undefined;
    return schema.parse(envelope.data);
  } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined; return undefined; }
}
export async function writeCache<T>(file: string, sourceHash: string, data: T): Promise<void> {
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, `${JSON.stringify({ sourceHash, createdAt: new Date().toISOString(), data }, null, 2)}\n`, 'utf8');
}
