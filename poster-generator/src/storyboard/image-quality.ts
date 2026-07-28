import sharp from 'sharp';
import type { StoryboardTone } from './prompt-builder.js';

export interface ImageQualityResult {
  approved: boolean;
  meanLuma: number;
  reasons: string[];
}

export async function inspectStoryboardImage(
  buffer: Buffer,
  tone: StoryboardTone,
): Promise<ImageQualityResult> {
  const stats = await sharp(buffer).stats();
  const channels = stats.channels.slice(0, 3);
  const meanLuma = channels.length
    ? channels.reduce((sum, channel) => sum + channel.mean, 0) / channels.length
    : 255;
  const deviation = channels.length
    ? channels.reduce((sum, channel) => sum + channel.stdev, 0) / channels.length
    : 0;
  const reasons: string[] = [];
  if (deviation < 2) reasons.push('near_blank_image');
  if (tone === 'dark' && meanLuma > 205) reasons.push('too_bright_for_source');
  return { approved: reasons.length === 0, meanLuma: Number(meanLuma.toFixed(1)), reasons };
}
