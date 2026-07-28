export type ComputeDevice = 'cpu' | 'gpu' | 'auto';
export type ImageQuality = 'draft' | 'standard' | 'high';
export interface ImageGenerationInput { prompt: string; negativePrompt?: string; width: number; height: number; variants: number; seed?: number; referenceImages?: string[]; referenceWeight?: number; device?: ComputeDevice; quality?: ImageQuality; onProgress?: (message:string)=>void; }
export interface GeneratedImage { buffer: Buffer; mimeType: string; seed?: number; revisedPrompt?: string; providerMetadata: Record<string, unknown>; }
export interface ImageGenerationProvider { readonly name: string; readonly model: string; readonly supportsReferenceImages: boolean; generate(input: ImageGenerationInput): Promise<GeneratedImage[]>; close?(): Promise<void>; }
