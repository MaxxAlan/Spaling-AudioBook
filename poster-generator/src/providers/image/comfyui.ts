import { randomUUID } from 'node:crypto';
import { spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import type { GeneratedImage, ImageGenerationInput, ImageGenerationProvider } from './types.js';
import { AppError } from '../../utils/errors.js';
import { retry } from '../../utils/retry.js';
import { getModelProfile, type ModelProfile } from '../../config/model-profiles.js';

interface ComfyUIOptions {
  baseUrl: string;
  comfyPath: string;
  workflowPath: string;
  python: string;
  model: string;
  modelProfile?: string;
  timeoutMs?: number;
}

type WorkflowNode = { class_type: string; inputs: Record<string, unknown> };
type Workflow = Record<string, WorkflowNode>;

export function resolveCheckpointName(requested: string, available: string[]): string {
  return available.includes(requested) ? requested : (available[0] ?? requested);
}

const unlimited = (): boolean => process.env.AUDIOBOOK_OVERNIGHT === '1';
const requestSignal = (timeoutMs: number): AbortSignal | null =>
  unlimited() ? null : AbortSignal.timeout(timeoutMs);

export class ComfyUIImageProvider implements ImageGenerationProvider {
  readonly name = 'comfyui';
  readonly model: string;
  readonly supportsReferenceImages = true;
  private child?: ChildProcess;
  private device: 'cpu' | 'gpu' | 'auto' = 'auto';
  private profile: ModelProfile;
  private availableCheckpoint?: string[];
  private objectInfo?: Record<string, unknown>;
  private uploadedReferences = new Map<string, string>();

  constructor(private readonly options: ComfyUIOptions) {
    if (!options.comfyPath) throw new AppError('COMFYUI_PATH_MISSING', 'Thiếu COMFYUI_PATH cho local image provider.');
    if (!options.workflowPath) throw new AppError('COMFYUI_WORKFLOW_MISSING', 'Thiếu COMFYUI_WORKFLOW cho local image provider.');
    const profileId = options.modelProfile || process.env.IMAGE_MODEL_PROFILE || 'medium';
    this.profile = getModelProfile(profileId);
    this.model = options.model || this.profile.checkpoint;
  }

  private async reachable(): Promise<boolean> {
    try {
      const response = await fetch(`${this.options.baseUrl}/system_stats`, { signal: requestSignal(1500) });
      return response.ok;
    } catch {
      return false;
    }
  }

  private async ensureServer(device: 'cpu' | 'gpu' | 'auto', progress?: (message: string) => void): Promise<void> {
    this.device = device;
    if (await this.reachable()) {
      progress?.('ComfyUI đã chạy và sẵn sàng.');
      return;
    }

    progress?.(`Đang khởi động ComfyUI (${device}${device === 'gpu' ? ' low-VRAM' : ''}), thường mất 30–60 giây...`);
    const url = new URL(this.options.baseUrl);
    const args = ['main.py', '--listen', url.hostname, '--port', url.port || '8188', '--disable-auto-launch'];
    if (device === 'cpu') args.push('--cpu');
    if (device === 'gpu') args.push('--lowvram');
    this.child = spawn(this.options.python, args, {
      cwd: this.options.comfyPath,
      stdio: 'ignore',
      windowsHide: true,
    });

    const deadline = Date.now() + Math.min(this.options.timeoutMs ?? 1_500_000, 900_000);
    while (unlimited() || Date.now() < deadline) {
      if (this.child.exitCode !== null) {
        throw new AppError('COMFYUI_START_FAILED', `ComfyUI thoát với mã ${this.child.exitCode} khi khởi động chế độ ${device}.`);
      }
      if (await this.reachable()) {
        progress?.('ComfyUI đã sẵn sàng.');
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    throw new AppError('COMFYUI_START_TIMEOUT', `ComfyUI không sẵn sàng tại ${this.options.baseUrl} sau thời gian chờ.`);
  }

  private async comfyObjectInfo(): Promise<Record<string, unknown>> {
    if (this.objectInfo) return this.objectInfo;
    try {
      const response = await fetch(`${this.options.baseUrl}/object_info`, { signal: requestSignal(15_000) });
      if (response.ok) this.objectInfo = await response.json() as Record<string, unknown>;
    } catch {
      // Reference conditioning remains optional; the base workflow still works.
    }
    return this.objectInfo ?? {};
  }

  private async uploadReference(file: string): Promise<string> {
    const absolute = path.resolve(file);
    const cached = this.uploadedReferences.get(absolute);
    if (cached) return cached;
    const body = new FormData();
    body.append('image', new Blob([await fs.readFile(absolute)]), path.basename(absolute));
    body.append('type', 'input');
    body.append('overwrite', 'true');
    const response = await fetch(`${this.options.baseUrl}/upload/image`, {
      method: 'POST', body, signal: requestSignal(60_000),
    });
    if (!response.ok) throw new Error(`upload reference HTTP ${response.status}`);
    const uploaded = await response.json() as { name?: string; subfolder?: string };
    if (!uploaded.name) throw new Error('ComfyUI did not return an uploaded reference name');
    const name = uploaded.subfolder ? `${uploaded.subfolder}/${uploaded.name}` : uploaded.name;
    this.uploadedReferences.set(absolute, name);
    return name;
  }

  private choice(
    objectInfo: Record<string, unknown>,
    node: string,
    input: string,
    preferred: string,
  ): string | undefined {
    const values = (objectInfo[node] as {
      input?: { required?: Record<string, [unknown, unknown]> };
    } | undefined)?.input?.required?.[input]?.[0];
    if (!Array.isArray(values)) return undefined;
    const available = values.filter((item): item is string => typeof item === 'string');
    return available.includes(preferred) ? preferred : available[0];
  }

  private async applyReference(
    workflow: Workflow,
    input: ImageGenerationInput,
  ): Promise<boolean> {
    const reference = input.referenceImages?.[0];
    if (!reference) return false;
    const info = await this.comfyObjectInfo();
    const required = ['LoadImage', 'CLIPVisionLoader', 'IPAdapterModelLoader', 'IPAdapterAdvanced'];
    if (required.some((node) => !(node in info))) {
      input.onProgress?.('[identity] IP-Adapter chưa được cài trong ComfyUI; dùng continuity prompt.');
      return false;
    }
    const clip = this.choice(info, 'CLIPVisionLoader', 'clip_name', 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors');
    const adapter = this.choice(info, 'IPAdapterModelLoader', 'ipadapter_file', 'ip-adapter_sd15.safetensors');
    if (!clip || !adapter) {
      input.onProgress?.('[identity] Thiếu model IP-Adapter/CLIP Vision; dùng continuity prompt.');
      return false;
    }
    try {
      const checkpoint = Object.entries(workflow).find(([, node]) => node.class_type === 'CheckpointLoaderSimple');
      if (!checkpoint) return false;
      const image = await this.uploadReference(reference);
      const ids = ['9101', '9102', '9103', '9104'];
      if (ids.some((id) => id in workflow)) throw new Error('reserved IP-Adapter node id is already used');
      workflow[ids[0]!] = { class_type: 'LoadImage', inputs: { image, upload: 'image' } };
      workflow[ids[1]!] = { class_type: 'CLIPVisionLoader', inputs: { clip_name: clip } };
      workflow[ids[2]!] = { class_type: 'IPAdapterModelLoader', inputs: { ipadapter_file: adapter } };
      workflow[ids[3]!] = {
        class_type: 'IPAdapterAdvanced',
        inputs: {
          model: [checkpoint[0], 0], ipadapter: [ids[2], 0], image: [ids[0], 0],
          clip_vision: [ids[1], 0], weight: input.referenceWeight ?? 0.72,
          weight_type: 'linear', combine_embeds: 'concat', start_at: 0, end_at: 0.88,
          embeds_scaling: 'V only',
        },
      };
      for (const node of Object.values(workflow)) {
        if (node.class_type === 'KSampler' || node.class_type === 'BasicScheduler') {
          node.inputs.model = [ids[3], 0];
        }
      }
      input.onProgress?.(`[identity] IP-Adapter SD1.5 khóa nhân vật bằng ${path.basename(reference)}.`);
      return true;
    } catch (error) {
      input.onProgress?.(`[identity] Không áp được reference (${String(error)}); dùng continuity prompt.`);
      return false;
    }
  }

  private async workflow(input: ImageGenerationInput, variant: number): Promise<{ workflow: Workflow; referenceApplied: boolean }> {
    const workflow = JSON.parse(await fs.readFile(path.resolve(this.options.workflowPath), 'utf8')) as Workflow;
    const textEncoders = Object.values(workflow).filter((node) => node.class_type === 'CLIPTextEncode');
    const positive = textEncoders[0];
    const negative = textEncoders[1];
    const latent = Object.values(workflow).find((node) => node.class_type === 'EmptyLatentImage');
    const sampler = Object.values(workflow).find((node) => node.class_type === 'KSampler');
    const save = Object.values(workflow).find((node) => node.class_type === 'SaveImage');
    const checkpoint = Object.values(workflow).find((node) => node.class_type === 'CheckpointLoaderSimple');
    if (!positive || !negative || !latent || !sampler || !save) {
      throw new AppError(
        'COMFYUI_WORKFLOW_INVALID',
        'Workflow cần CLIPTextEncode, EmptyLatentImage, BasicScheduler, RandomNoise và SaveImage.',
      );
    }

    // Use profile settings
    const profile = this.profile;
    const landscape = input.width > input.height;
    const quality = input.quality ?? 'high';
    const preset = quality === 'draft'
      ? { long: 512, short: 384, steps: Math.max(4, Math.floor(profile.steps * 0.5)) }
      : quality === 'standard'
        ? { long: profile.width || 512, short: profile.height || 768, steps: profile.steps }
        : { long: (profile.width || 512) * 1.5, short: (profile.height || 768) * 1.5, steps: Math.min(30, profile.steps + 5) };
    const compact = input.prompt.replace(/\s+/g, ' ').trim();
    positive.inputs.text = `${compact}. No text, no title, no letters, no words, no logo, no watermark, no signature, no advertising layout.`;
    negative.inputs.text = input.negativePrompt?.trim() || profile.negativePrompt;
    const longSide = Math.max(preset.long, preset.short);
    const shortSide = Math.min(preset.long, preset.short);
    latent.inputs.width = landscape ? Math.round(longSide) : Math.round(shortSide);
    latent.inputs.height = landscape ? Math.round(shortSide) : Math.round(longSide);
    latent.inputs.batch_size = 1;
    sampler.inputs.seed = (input.seed ?? Math.floor(Math.random() * 2_147_483_647)) + variant;
    sampler.inputs.steps = preset.steps;
    sampler.inputs.cfg = profile.cfg;
    sampler.inputs.sampler_name = profile.sampler;
    sampler.inputs.scheduler = profile.scheduler;
    sampler.inputs.denoise = 1;

    // Set checkpoint if workflow has one
    if (checkpoint?.inputs) {
      checkpoint.inputs.ckpt_name = await this.resolveCheckpoint();
    }

    save.inputs.filename_prefix = `poster_gen_${Date.now()}_${variant + 1}`;
    const referenceApplied = await this.applyReference(workflow, input);
    return { workflow, referenceApplied };
  }

  private async resolveCheckpoint(): Promise<string> {
    if (this.availableCheckpoint) return resolveCheckpointName(this.model, this.availableCheckpoint);
    try {
      const response = await fetch(`${this.options.baseUrl}/object_info/CheckpointLoaderSimple`, {
        signal: requestSignal(10_000),
      });
      if (response.ok) {
        const body = await response.json() as {
          CheckpointLoaderSimple?: { input?: { required?: { ckpt_name?: [unknown, unknown] } } };
        };
        const values = body.CheckpointLoaderSimple?.input?.required?.ckpt_name?.[0];
        if (Array.isArray(values)) this.availableCheckpoint = values.filter((value): value is string => typeof value === 'string');
      }
    } catch {
      // Keep the configured checkpoint as a fallback when ComfyUI metadata is unavailable.
    }
    return resolveCheckpointName(this.model, this.availableCheckpoint ?? []);
  }

  private async queue(workflow: Workflow): Promise<string> {
    const response = await fetch(`${this.options.baseUrl}/prompt`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ prompt: workflow, client_id: randomUUID() }),
      signal: requestSignal(30_000),
    });
    if (!response.ok) {
      throw new AppError('COMFYUI_QUEUE_ERROR', `ComfyUI /prompt lỗi ${response.status}: ${await response.text()}`);
    }
    const body = await response.json() as { prompt_id?: string; error?: unknown };
    if (!body.prompt_id) {
      throw new AppError('COMFYUI_QUEUE_ERROR', `ComfyUI không trả prompt_id: ${JSON.stringify(body.error ?? body)}`);
    }
    return body.prompt_id;
  }

  private async waitForImage(
    promptId: string,
    timeoutMs: number,
    progress?: (message: string) => void,
  ): Promise<{ filename: string; subfolder: string; type: string }> {
    const started = Date.now();
    const deadline = started + timeoutMs;
    let nextHeartbeat = started + 60_000;
    while (unlimited() || Date.now() < deadline) {
      const response = await fetch(`${this.options.baseUrl}/history/${promptId}`, { signal: requestSignal(10_000) });
      if (response.ok) {
        const body = await response.json() as Record<string, {
          status?: { status_str?: string; messages?: unknown[] };
          outputs?: Record<string, { images?: Array<{ filename: string; subfolder?: string; type?: string }> }>;
        }>;
        const entry = body[promptId];
        const image = entry?.outputs && Object.values(entry.outputs).flatMap((output) => output.images ?? [])[0];
        if (image) {
          return { filename: image.filename, subfolder: image.subfolder ?? '', type: image.type ?? 'output' };
        }
        if (entry?.status?.status_str === 'error') {
          throw new AppError('COMFYUI_GENERATION_ERROR', `ComfyUI generation lỗi: ${JSON.stringify(entry.status.messages ?? [])}`);
        }
      }
      if (Date.now() >= nextHeartbeat) {
        const elapsed = Math.max(1, Math.floor((Date.now() - started) / 60_000));
        progress?.(`ComfyUI vẫn đang render (${elapsed} phút), tiếp tục chờ...`);
        nextHeartbeat += 60_000;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    const minutes = Math.round(timeoutMs / 60_000);
    throw new AppError('COMFYUI_TIMEOUT', `ComfyUI không hoàn tất prompt ${promptId} sau ${minutes} phút.`);
  }

  async generate(input: ImageGenerationInput): Promise<GeneratedImage[]> {
    await this.ensureServer(input.device ?? 'auto', input.onProgress);
    const results: GeneratedImage[] = [];
    const quality = input.quality ?? 'high';
    const profile = this.profile;
    const preset = quality === 'draft'
      ? { size: '512×384', steps: Math.max(4, Math.floor(profile.steps * 0.5)), timeout: 60 * 60_000 }
      : quality === 'standard'
        ? { size: `${profile.width}×${profile.height}`, steps: profile.steps, timeout: 180 * 60_000 }
        : { size: `${Math.round(profile.width * 1.5)}×${Math.round(profile.height * 1.5)}`, steps: Math.min(30, profile.steps + 5), timeout: 300 * 60_000 };

    for (let index = 0; index < input.variants; index += 1) {
      const startedAt = Date.now();
      const generated = await retry(async () => {
        const size = input.width > input.height ? preset.size : preset.size.split('×').reverse().join('×');
        input.onProgress?.(
          `[${profile.name}] Đang sinh ảnh ${index + 1}/${input.variants}: ${quality}, ${preset.steps} bước tại ${size}...`,
        );
        const { workflow: resolvedWorkflow, referenceApplied } = await this.workflow(input, index);
        const promptId = await this.queue(resolvedWorkflow);
        const image = await this.waitForImage(
          promptId,
          Math.max(this.options.timeoutMs ?? 0, preset.timeout),
          input.onProgress,
        );
        input.onProgress?.(`[${profile.name}] Ho\u00e0n t\u1ea5t \u1ea3nh ${index + 1}/${input.variants} sau ${((Date.now() - startedAt) / 1000).toFixed(1)}s; \u0111ang t\u1ea3i...`);
        const response = await fetch(`${this.options.baseUrl}/view?${new URLSearchParams(image)}`, {
          signal: requestSignal(60_000),
        });
        if (!response.ok) {
          throw new AppError('COMFYUI_IMAGE_ERROR', `Không tải được ảnh ComfyUI: HTTP ${response.status}`);
        }
        return {
          buffer: Buffer.from(await response.arrayBuffer()),
          mimeType: response.headers.get('content-type') ?? 'image/png',
          seed: (input.seed ?? 0) + index,
          providerMetadata: { promptId, device: this.device, quality, profile: profile.id, source: image, referenceApplied, resolvedWorkflow },
        } satisfies GeneratedImage;
      }, unlimited() ? 10 : 3, 1500);
      results.push(generated);
    }
    return results;
  }

  async close(): Promise<void> {
    if (this.child && this.child.exitCode === null) {
      this.child.kill();
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
}
