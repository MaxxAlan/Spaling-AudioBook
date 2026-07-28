import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { z } from 'zod';
import type { TextAIProvider } from './types.js';
import { AppError } from '../../utils/errors.js';
import { retry } from '../../utils/retry.js';

export interface OllamaTextOptions {
  model: string;
  baseUrl: string;
  timeoutMs?: number;
  maxTokens?: number;
  contextTokens?: number;
  retries?: number;
  rawOutputDirectory?: string;
}

const unlimited = (): boolean => process.env.AUDIOBOOK_OVERNIGHT === '1';

function postJson(url: string, payload: unknown, timeoutMs: number): Promise<{ status: number; body: string }> {
  const body = JSON.stringify(payload);
  return new Promise((resolve, reject) => {
    const req = http.request(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'content-length': Buffer.byteLength(body) },
    }, (response) => {
      const chunks: Buffer[] = [];
      response.on('data', (chunk: Buffer) => chunks.push(chunk));
      response.on('end', () => resolve({status: response.statusCode ?? 500, body: Buffer.concat(chunks).toString('utf8')}));
    });
    req.on('error', reject);
    if (!unlimited()) req.setTimeout(timeoutMs, () => req.destroy(Object.assign(new Error(`Ollama timeout after ${timeoutMs}ms`), {name: 'TimeoutError'})));
    req.end(body);
  });
}

export class OllamaTextProvider implements TextAIProvider {
  readonly name = 'ollama';
  readonly model: string;
  private readonly origin: string;

  constructor(private readonly options: OllamaTextOptions) {
    if (!options.model) throw new AppError('MISSING_MODEL', 'Thiếu model Ollama.');
    const match = options.baseUrl.match(/^(https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?)\/?$/);
    if (!match) throw new AppError('INVALID_OLLAMA_URL', 'Ollama chỉ được phép chạy local tại localhost.');
    this.model = options.model;
    this.origin = match[1]!;
  }

  async generateStructured<T>(systemPrompt: string, userPrompt: string, schema: z.ZodType<T>): Promise<T> {
    let repair = '';
    return retry(async () => {
      const response = await postJson(`${this.origin}/api/chat`, {
        model: this.model,
        messages: [
          {role: 'system', content: `${systemPrompt}\nReturn JSON only.`},
          {role: 'user', content: `${userPrompt}${repair}`},
        ],
        stream: false,
        format: z.toJSONSchema(schema),
        keep_alive: '5m',
        options: {temperature: 0.2, num_ctx: this.options.contextTokens ?? 32768, num_predict: this.options.maxTokens ?? 4096},
      }, this.options.timeoutMs ?? 120000);
      if (response.status < 200 || response.status >= 300) throw new AppError('TEXT_PROVIDER_ERROR', `Ollama lỗi ${response.status}: ${response.body}`);
      const parsed = JSON.parse(response.body) as {message?: {content?: string}};
      const raw = parsed.message?.content ?? '';
      if (this.options.rawOutputDirectory) {
        await fs.mkdir(this.options.rawOutputDirectory, {recursive: true});
        await fs.writeFile(path.join(this.options.rawOutputDirectory, `text-raw-${Date.now()}.json`), raw, 'utf8');
      }
      try {
        return schema.parse(JSON.parse(raw));
      } catch (error) {
        repair = `\nReturn corrected complete JSON. Validation error: ${String(error)}`;
        throw error;
      }
    }, unlimited() ? 10 : (this.options.retries ?? 2), 250, (error) => (error as {name?: string}).name !== 'TimeoutError');
  }

  async close(): Promise<void> {
    const response = await postJson(`${this.origin}/api/generate`, {model: this.model, prompt: '', keep_alive: 0, stream: false}, 15000);
    if (response.status < 200 || response.status >= 300) throw new AppError('TEXT_PROVIDER_UNLOAD_ERROR', `Không thể dỡ model ${this.model}: ${response.status}`);
  }
}
