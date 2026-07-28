/**
 * Image model profiles for different use cases.
 * Each profile maps to a specific checkpoint + generation settings.
 */

export interface ModelProfile {
  id: string;
  name: string;
  description: string;
  checkpoint: string;          // Filename in ComfyUI models/checkpoints/
  checkpointUrl: string;       // HuggingFace download URL
  checkpointHash?: string;     // SHA256 for verification
  type: 'sd15' | 'sdxl' | 'flux';
  steps: number;               // Default inference steps
  cfg: number;                 // CFG scale
  sampler: string;             // e.g. 'euler_ancestral', 'dpmpp_2m'
  scheduler: string;           // 'normal', 'karras', 'sgm_uniform'
  width: number;               // Default width
  height: number;              // Default height
  lora?: string;               // Optional LoRA filename
  loraUrl?: string;
  loraStrength?: number;
  clipSkip?: number;
  negativePrompt: string;
}

export const MODEL_PROFILES: Record<string, ModelProfile> = {
  // ── Low: Nhanh, tiết kiệm ──
  low: {
    id: 'low',
    name: 'Nhanh',
    description: 'Tạo ảnh nhanh, chất lượng cơ bản — phù hợp preview',
    checkpoint: 'DreamShaper_8_pruned.safetensors',
    checkpointUrl: 'https://huggingface.co/Lykon/DreamShaper/resolve/main/dreamshaper_8_pruned.safetensors',
    type: 'sd15',
    steps: 8,
    cfg: 2.0,
    sampler: 'euler',
    scheduler: 'sgm_uniform',
    width: 512,
    height: 384,
    lora: 'Hyper-SD15-8step-lora-v1.safetensors',
    loraUrl: 'https://huggingface.co/ByteDance/Hyper-FLUX-8Step-LoRA/resolve/main/Hyper-SD15-8step-lora-v1.safetensors',
    loraStrength: 0.85,
    clipSkip: 2,
    negativePrompt: 'low quality, blurry, duplicate, malformed hands, distorted face, watermark, logo, text, letters, words, oversaturated, cropped',
  },

  // ── Medium: Cân bằng ──
  medium: {
    id: 'medium',
    name: 'Cân bằng',
    description: 'Chất lượng tốt, thời gian hợp lý — phù hợp sử dụng chung',
    checkpoint: 'DreamShaper_8_pruned.safetensors',
    checkpointUrl: 'https://huggingface.co/Lykon/DreamShaper/resolve/main/dreamshaper_8_pruned.safetensors',
    type: 'sd15',
    steps: 20,
    cfg: 7.5,
    sampler: 'euler_ancestral',
    scheduler: 'karras',
    width: 512,
    height: 768,
    clipSkip: 2,
    negativePrompt: 'low quality, blurry, duplicate, malformed hands, distorted face, watermark, logo, text, letters, words, oversaturated, cropped, deformed, ugly, bad anatomy, bad proportions, extra limbs, disfigured',
  },

  // ── High: Chất lượng cao ──
  high: {
    id: 'high',
    name: 'Chất lượng cao',
    description: 'Ảnh đẹp, chi tiết tốt — phù hợp sản phẩm cuối',
    checkpoint: 'Realistic_Vision_V6.0_NV_B1_fp16.safetensors',
    checkpointUrl: 'https://huggingface.co/SG161222/Realistic_Vision_V6.0_B1_noVAE/resolve/main/Realistic_Vision_V6.0_NV_B1_fp16.safetensors',
    type: 'sd15',
    steps: 25,
    cfg: 7.0,
    sampler: 'dpmpp_2m',
    scheduler: 'karras',
    width: 768,
    height: 1024,
    clipSkip: 2,
    negativePrompt: 'low quality, blurry, duplicate, malformed hands, distorted face, watermark, logo, text, letters, words, cartoon, anime, drawing, illustration, oversaturated, cropped, deformed, ugly, bad anatomy',
  },

  // ── Max: Tốt nhất, chậm ──
  max: {
    id: 'max',
    name: 'Tốt nhất',
    description: 'Chất lượng tối đa — chậm, phù hợp cover/quan trọng',
    checkpoint: 'Realistic_Vision_V6.0_NV_B1_fp16.safetensors',
    checkpointUrl: 'https://huggingface.co/SG161222/Realistic_Vision_V6.0_B1_noVAE/resolve/main/Realistic_Vision_V6.0_NV_B1_fp16.safetensors',
    type: 'sd15',
    steps: 28,
    cfg: 7.0,
    sampler: 'dpmpp_2m',
    scheduler: 'karras',
    width: 768,
    height: 1024,
    negativePrompt: 'low quality, blurry, duplicate, malformed hands, distorted face, watermark, logo, text, letters, words, cartoon, anime, drawing, illustration, oversaturated, cropped, deformed, ugly, bad anatomy, bad proportions',
  },
};

export type ModelProfileId = keyof typeof MODEL_PROFILES;

export function getModelProfile(id: string): ModelProfile {
  const profile = MODEL_PROFILES[id];
  if (!profile) {
    throw new Error(`Model profile không tồn tại: ${id}. Chọn: ${Object.keys(MODEL_PROFILES).join(', ')}`);
  }
  return profile;
}

export function listModelProfiles(): Array<{ id: string; name: string; description: string }> {
  return Object.values(MODEL_PROFILES).map((p) => ({
    id: p.id,
    name: p.name,
    description: p.description,
  }));
}
