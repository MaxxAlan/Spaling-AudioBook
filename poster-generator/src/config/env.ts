import 'dotenv/config';
import { z } from 'zod';

const envSchema = z.object({
  TEXT_AI_PROVIDER: z.enum(['ollama', 'mock']).default('ollama'),
  TEXT_AI_MODEL: z.string().default('qwen2.5:7b'), OLLAMA_BASE_URL: z.string().default('http://127.0.0.1:11435'),
  ANALYSIS_PROFILE: z.enum(['fast', 'balanced', 'quality', 'all-7b']).default('balanced'),
  DIRECTOR_MODEL: z.string().default('qwen2.5:7b'), WORKER_MODEL: z.string().default('qwen2.5:1.5b'),
  DIRECTOR_TIMEOUT_MS: z.coerce.number().int().positive().default(600000),
  WORKER_TIMEOUT_MS: z.coerce.number().int().positive().default(600000),
  DIRECTOR_CONTEXT_TOKENS: z.coerce.number().int().min(4096).default(16384),
  WORKER_CONTEXT_TOKENS: z.coerce.number().int().min(4096).default(16384),
  IMAGE_AI_PROVIDER: z.enum(['mock', 'comfyui']).default('comfyui'),
  IMAGE_AI_MODEL: z.string().default(''),
  COMFYUI_BASE_URL: z.string().default('http://127.0.0.1:8188'), COMFYUI_PATH: z.string().default(''),
  COMFYUI_WORKFLOW: z.string().default(''), COMFYUI_PYTHON: z.string().default('python'),
  IMAGE_MODEL_PROFILE: z.string().default('medium'),
  THUMBNAIL_OUTPUT_DIR: z.string().default('./output'), THUMBNAIL_DEFAULT_PLATFORM: z.enum(['youtube','tiktok','both']).default('both'),
  THUMBNAIL_DEFAULT_VARIANTS: z.coerce.number().int().min(1).max(10).default(3), THUMBNAIL_DEFAULT_STYLE: z.string().default('cinematic-dark-fantasy'),
  LOG_LEVEL: z.string().default('info'),
});
export type Environment = z.infer<typeof envSchema>;
export function loadEnvironment(source: NodeJS.ProcessEnv = process.env): Environment { return envSchema.parse(source); }
