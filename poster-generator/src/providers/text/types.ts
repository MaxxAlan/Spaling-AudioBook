import type { z } from 'zod';
export interface TextAIProvider {
  readonly name: string; readonly model: string;
  generateStructured<T>(systemPrompt: string, userPrompt: string, schema: z.ZodType<T>): Promise<T>;
  close?(): Promise<void>;
}
