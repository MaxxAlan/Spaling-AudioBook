import path from 'node:path';
import type { LoadedSource } from '../sources/loader.js';
import { sha256 } from '../sources/hash.js';
import { readCache, writeCache } from '../sources/cache.js';
import { canonSchema, type CanonRules } from '../schemas/canon.js';
import { masterSchema, type MasterIndex } from '../schemas/master.js';

function clean(line: string): string { return line.replace(/^\s*(?:[-*]|\d+[.)])\s*/, '').replace(/[*_`#>]/g, '').trim(); }
function provenance(source: LoadedSource, line: number) { return { sourcePath: source.path, lineStart: line, lineEnd: line }; }
function headingLevel(line: string): number { return line.match(/^(#{1,6})\s/)?.[1]?.length ?? 0; }
function sectionPath(headings: string[]): string { return headings.filter(Boolean).join(' / ').toLocaleLowerCase('vi'); }
function categorizedCanon(source: LoadedSource): CanonRules {
  const result: CanonRules = { timelineRules: [], hardCanon: [], worldRules: [], magicRules: [], characters: [], factions: [], locations: [], visualMotifs: [], forbiddenContradictions: [] };
  const headings: string[] = [];
  source.lines.forEach((raw, index) => {
    const value = clean(raw); if (!value || /^---+$/.test(value)) return;
    const level = headingLevel(raw);
    if (level) { headings[level - 1] = value; headings.length = level; }
    const section = sectionPath(headings);
    const entry = { value, provenance: provenance(source, index + 1) };
    if (/không được|cấm|bất biến|bắt buộc|tuyệt đối/i.test(value)) result.forbiddenContradictions.push(entry);
    if (/timeline|niên đại|mốc thời gian|thời gian|năm\s+\d+|year\s+\d+|cold open|hồi tưởng|quá khứ|hiện tại/i.test(`${section} ${value}`)) result.timelineRules.push(entry);
    if (/ma lực|ma thuật|phép|sức mạnh|cái giá|nguyên tố|hệ thống năng lực|magic|power system/i.test(section)) result.magicRules.push(entry);
    else if (/nhân vật|hồ sơ nhân vật|danh sách nhân vật|character|characters|cast/i.test(section)) result.characters.push(entry);
    else if (/địa lý|địa điểm|bối cảnh|khu vực|vùng đất|location|locations|setting|geography/i.test(section)) result.locations.push(entry);
    else if (/gia tộc|phe|tổ chức|hoàng tộc|faction|organization|clan|guild/i.test(section)) result.factions.push(entry);
    else if (/thế giới|world|worldbuilding|lore/i.test(section)) result.worldRules.push(entry);
    else result.hardCanon.push(entry);
    if (/màu|biểu tượng|hình ảnh|motif|ngoại hình|tóc|mắt/i.test(value)) result.visualMotifs.push(entry);
  });
  return canonSchema.parse(result);
}

function matchRange(text: string): { start: number; end: number } | undefined {
  const normalized = text.replace(/[.,](?=\d{3}\b)/g, '');
  const match = normalized.match(/(?:Chương|Chapters?|Ch\.)\s*(\d+)\s*[–—-]\s*(\d+)/i);
  return match?.[1] && match[2] ? { start: Number(match[1]), end: Number(match[2]) } : undefined;
}
export function compileMasterSource(source: LoadedSource): MasterIndex {
  const result: MasterIndex = { grandArcs: [], volumes: [], miniArcs: [], chapterRanges: [], lockedMilestones: [], timelineTransitions: [] };
  const headings: string[] = [];
  let purpose = '', conflict = '';
  source.lines.forEach((raw, index) => {
    const value = clean(raw); if (!value) return; const prov = provenance(source, index + 1); const entry = { value, provenance: prov };
    const level = headingLevel(raw);
    if (level) { headings[level - 1] = value; headings.length = level; }
    if (level && /đại thiên|đại arc|grand arc|saga/i.test(value)) result.grandArcs.push(entry);
    if (level && /quyển|tập|volume|book/i.test(value)) result.volumes.push(entry);
    if (/mục tiêu|chức năng|purpose|objective/i.test(value)) purpose = value.replace(/^.*?:\s*/, '');
    if (/xung đột trung tâm|central conflict|core conflict/i.test(value)) conflict = value.replace(/^.*?:\s*/, '');
    if (/điểm chốt|không thể đảo|bất biến|locked milestone|point of no return/i.test(value)) result.lockedMilestones.push(entry);
    if (/cold open|hồi tưởng|quay về|nối tiếp|timeline|niên đại|mốc thời gian|năm\s+\d+|year\s+\d+/i.test(value)) result.timelineTransitions.push(entry);
    const range = matchRange(value);
    const structuralRange = level > 0 || /^\s*\d+[.)]\s*/.test(raw) || /(?:mini|tiểu)?\s*arc|hồi|chặng|phase/i.test(value);
    if (range && structuralRange) {
      const parents = headings.slice(0, Math.max(0, level - 1)).filter(Boolean);
      const grandArc = [...parents].reverse().find((item) => /đại thiên|đại arc|grand arc|saga/i.test(item)) ?? parents[0] ?? '';
      const volume = [...parents, ...(level ? [value] : [])].reverse().find((item) => /quyển|tập|volume|book/i.test(item)) ?? '';
      const miniArc = level && volume === value ? '' : value;
      if (miniArc) result.miniArcs.push(entry);
      const timeline = /hồi tưởng|quay về|timeline|niên đại|mốc thời gian|năm\s+\d+|year\s+\d+/i.test(value) ? value : '';
      result.chapterRanges.push({ ...range, grandArc, volume, miniArc, timeline, arcPurpose: purpose, centralConflict: conflict, provenance: prov });
    }
  });
  return masterSchema.parse(result);
}

export async function compileCanon(source: LoadedSource, projectRoot: string): Promise<CanonRules> {
  const hash = sha256(`story-scoped-canon-v2\0${source.text}`); const file = path.join(projectRoot, '.story-thumbnail', 'cache', 'canon-rules.json');
  const cached = await readCache(file, hash, canonSchema); if (cached) return cached;
  const data = categorizedCanon(source); await writeCache(file, hash, data); return data;
}
export async function compileMaster(source: LoadedSource, projectRoot: string): Promise<MasterIndex> {
  const hash = sha256(`story-scoped-master-v2\0${source.text}`); const file = path.join(projectRoot, '.story-thumbnail', 'cache', 'master-index.json');
  const cached = await readCache(file, hash, masterSchema); if (cached) return cached;
  const data = compileMasterSource(source); await writeCache(file, hash, data); return data;
}
