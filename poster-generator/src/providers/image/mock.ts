import sharp from 'sharp';
import type { GeneratedImage, ImageGenerationInput, ImageGenerationProvider } from './types.js';

export class MockImageProvider implements ImageGenerationProvider {
  readonly name = 'mock'; readonly model = 'sharp-placeholder'; readonly supportsReferenceImages = true;
  async generate(input: ImageGenerationInput): Promise<GeneratedImage[]> {
    return Promise.all(Array.from({ length: input.variants }, async (_, index) => {
      const seed = input.seed === undefined ? index + 1 : input.seed + index;
      const hue = Math.abs(seed * 47) % 360;
      const svg = `<svg width="${input.width}" height="${input.height}" xmlns="http://www.w3.org/2000/svg"><defs><radialGradient id="g"><stop stop-color="hsl(${hue},65%,42%)"/><stop offset="1" stop-color="#090713"/></radialGradient></defs><rect width="100%" height="100%" fill="url(#g)"/><circle cx="50%" cy="43%" r="18%" fill="#d8c5ff" opacity=".30"/><path d="M0 ${input.height} L${input.width * .42} ${input.height * .50} L${input.width} ${input.height}Z" fill="#160d28" opacity=".8"/></svg>`;
      const buffer = await sharp(Buffer.from(svg)).png().toBuffer();
      return { buffer, mimeType: 'image/png', seed, providerMetadata: { mock: true, width: input.width, height: input.height, references: input.referenceImages?.length ?? 0 } } satisfies GeneratedImage;
    }));
  }
}
