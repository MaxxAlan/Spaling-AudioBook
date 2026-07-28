export interface LineMatch { line: number; text: string; }
export class LineIndex {
  constructor(readonly lines: readonly string[]) {}
  slice(startLine: number, endLine: number): string { return this.lines.slice(startLine - 1, endLine).join('\n'); }
  find(pattern: RegExp): LineMatch[] {
    return this.lines.flatMap((text, index) => { pattern.lastIndex = 0; return pattern.test(text) ? [{ line: index + 1, text }] : []; });
  }
}
