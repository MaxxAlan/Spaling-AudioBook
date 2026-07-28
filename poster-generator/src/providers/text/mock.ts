import type { z } from 'zod';
import type { TextAIProvider } from './types.js';

export class MockTextProvider implements TextAIProvider {
  readonly name = 'mock'; readonly model = 'deterministic-mock';
  async generateStructured<T>(_systemPrompt: string, userPrompt: string, schema: z.ZodType<T>): Promise<T> {
    const marker = 'MOCK_RESULT_JSON\n'; const position = userPrompt.lastIndexOf(marker);
    if (position < 0) throw new Error('MockTextProvider requires MOCK_RESULT_JSON payload.');
    return schema.parse(JSON.parse(userPrompt.slice(position + marker.length)));
  }
}
