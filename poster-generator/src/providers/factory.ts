import type { Environment } from '../config/env.js';
import type { ProjectConfig } from '../config/project-config.js';
import type { TextAIProvider } from './text/types.js';
import type { ImageGenerationProvider } from './image/types.js';
import { MockTextProvider } from './text/mock.js';
import { OllamaTextProvider } from './text/ollama.js';
import { MockImageProvider } from './image/mock.js';
import { ComfyUIImageProvider } from './image/comfyui.js';

export function createTextProvider(env: Environment, config: ProjectConfig, rawOutputDirectory?: string, model = env.TEXT_AI_MODEL, timeoutMs = config.textTimeoutMs, maxTokens = 4096, contextTokens = 32768, retries = 2): TextAIProvider {
  return env.TEXT_AI_PROVIDER === 'mock' ? new MockTextProvider() : new OllamaTextProvider({ model, baseUrl: env.OLLAMA_BASE_URL, timeoutMs, maxTokens, contextTokens, retries, ...(rawOutputDirectory ? { rawOutputDirectory } : {}) });
}
export function createImageProvider(env: Environment, config: ProjectConfig): ImageGenerationProvider {
  if (env.IMAGE_AI_PROVIDER === 'mock') return new MockImageProvider();
  return new ComfyUIImageProvider({ baseUrl: env.COMFYUI_BASE_URL, comfyPath: env.COMFYUI_PATH, workflowPath: env.COMFYUI_WORKFLOW, python: env.COMFYUI_PYTHON, model: env.IMAGE_AI_MODEL, modelProfile: env.IMAGE_MODEL_PROFILE, timeoutMs: Math.max(config.imageTimeoutMs,3000000) });
}
