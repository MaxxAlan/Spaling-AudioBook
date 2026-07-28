import type { SourceChunk } from '../sources/chunker.js';
import type { ChunkAnalysis, Scene, Dialogue, ImportantObject, ImportantEvent } from '../schemas/chapter.js';

function evidence(chunk: SourceChunk, line: number, quote: string) { return [{ source: 'chapter' as const, sourcePath: '', lineStart: line, lineEnd: line, quote }]; }

function extractDialogues(chunk: SourceChunk): Dialogue[] {
  const lines = chunk.text.split(/\r?\n/);
  const dialogues: Dialogue[] = [];
  const seen = new Set<string>();

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';
    // Match quoted text
    const matches = line.match(/[\u201C\u201D"].+?[\u201C\u201D"]/g) || [];
    for (const match of matches) {
      const text = match.replace(/[""""]/g, '').trim();
      if (text.length < 5 || seen.has(text)) continue;
      seen.add(text);

      // Try to find speaker from surrounding context
      const context = lines.slice(Math.max(0, i - 2), Math.min(lines.length, i + 2)).join(' ');
      const speakerMatch = context.match(/([A-ZÀ-Ỹ][a-zà-ỹ]+)\s+(?:nói|trả lời|hỏi|la|thét|thì thầm|bảo|nhắc|cười|khóc)/);
      const speaker = speakerMatch?.[1] ?? 'unknown';

      // Detect emotion from context
      let emotion = 'neutral';
      if (/la|thét|hét/i.test(context)) emotion = 'shouting';
      else if (/thì thầm|nhẹ nhàng/i.test(context)) emotion = 'whispering';
      else if (/cười/i.test(context)) emotion = 'laughing';
      else if (/khóc|nước mắt/i.test(context)) emotion = 'crying';
      else if (/giận|căm/i.test(context)) emotion = 'angry';

      dialogues.push({
        speaker,
        text,
        emotion,
        context: context.slice(0, 200),
      });
    }
  }
  return dialogues;
}

function extractImportantObjects(chunk: SourceChunk): ImportantObject[] {
  const text = chunk.text;
  const objects: ImportantObject[] = [];
  const seen = new Set<string>();

  // Detect objects by patterns
  const patterns: Array<{ regex: RegExp; name: string; desc: string }> = [
    { regex: /(?:cầm|giữ|nắm|tay)[^.!?…]{0,60}(?:kiếm|dao|gậy|đũa|bút|thước)/i, name: 'vũ khí/công cụ', desc: 'held in hand' },
    { regex: /(?:cuốn|tập|trang|sách|tài liệu|cổ thư)/i, name: 'sách/tài liệu', desc: 'ancient text or document' },
    { regex: /(?:vòng tròn|chú thuật|phù chú|dấu hiệu)/i, name: 'ph chú/biện pháp', desc: 'magical symbol or circle' },
    { regex: /(?:đèn|ngọn lửa|nến|đom đóm|ánh sáng)/i, name: 'nguồn sáng', desc: 'light source' },
    { regex: /(?:cánh cửa|cổng|lối vào|lối ra)/i, name: 'cửa/lối vào', desc: 'doorway or entrance' },
  ];

  for (const p of patterns) {
    const match = text.match(p.regex);
    if (match && !seen.has(p.name)) {
      seen.add(p.name);
      objects.push({
        name: p.name,
        description: match[0].slice(0, 100),
        significance: 'visually present in scene',
        visualDetails: match[0].slice(0, 100),
      });
    }
  }
  return objects;
}

function extractImportantEvents(chunk: SourceChunk): ImportantEvent[] {
  const text = chunk.text;
  const events: ImportantEvent[] = [];

  // Detect key events
  if (/(?:chiến đấu|đánh nhau|tấn công|phòng thủ)/i.test(text)) {
    events.push({ event: 'combat scene', impact: 'action turning point', visualMoment: 'dynamic action pose' });
  }
  if (/(?:chết|tử vong|hy sinh|giết)/i.test(text)) {
    events.push({ event: 'death/kill event', impact: 'dramatic impact', visualMoment: 'emotional reaction' });
  }
  if (/(?:tìm thấy|phát hiện|tiết lộ|biết được)/i.test(text)) {
    events.push({ event: 'discovery/revelation', impact: 'plot advancement', visualMoment: 'surprised expression' });
  }
  if (/(?:chạy trốn|thoát|trốn|bỏ chạy)/i.test(text)) {
    events.push({ event: 'escape/chase', impact: 'tension building', visualMoment: 'running motion' });
  }

  return events;
}

function extractLocation(text: string): string {
  const locations: Array<{ pattern: RegExp; name: string }> = [
    { pattern: /phòng|căn phòng|gian phòng/i, name: 'căn phòng' },
    { pattern: /đồng|cánh đồng|đồng cỏ/i, name: 'đồng' },
    { pattern: /rừng|khu rừng|forest/i, name: 'rừng' },
    { pattern: /núi|đỉnh|sườn núi/i, name: 'núi' },
    { pattern: /sông|bờ sông|sông ngòi/i, name: 'sông' },
    { pattern: /biển|bờ biển|đại dương/i, name: 'biển' },
    { pattern: /thành phố|phố|đường phố/i, name: 'đường phố' },
    { pattern: /lâu đài|thành|tường thành/i, name: 'lâu đài' },
    { pattern: /nhà|nhà ở|căn hộ/i, name: 'nhà' },
    { pattern: /chợ|siêu thị|cửa hàng/i, name: 'chợ' },
    { pattern: /sân|vườn|khuôn viên/i, name: 'sân' },
    { pattern: /hẻm|ngõ|alley/i, name: 'hẻm' },
    { pattern: /đền|thánh|chùa|nhà thờ/i, name: 'đền/thánh' },
    { pattern: /hang|động|hang động/i, name: 'hang' },
    { pattern: /sa mạc|hoang mạc|cát/i, name: 'sa mạc' },
  ];
  for (const loc of locations) {
    if (loc.pattern.test(text)) return loc.name;
  }
  return '';
}

function extractTime(text: string): string {
  if (/(?:bình minh|sáng sớm|rạng đông|mặt trời mọc)/i.test(text)) return 'bình minh';
  if (/(?:hoàng hôn|chiều tà|xế chiều|mặt trời lặn)/i.test(text)) return 'hoàng hôn';
  if (/(?:đêm|khuya|nửa đêm|trăng|sao|tối)/i.test(text)) return 'đêm khuya';
  return 'ban ngày';
}

function extractMood(text: string): string {
  if (/(?:căng thẳng|lo lắng|sợ hãi|hoảng loạn)/i.test(text)) return 'căng thẳng';
  if (/(?:vui vẻ|hạnh phúc|cười|nở nụ cười)/i.test(text)) return 'vui vẻ';
  if (/(?:buồn|rầu|rơi nước mắt|khóc)/i.test(text)) return 'buồn bã';
  if (/(?:giận dữ|căm thù|phẫn nộ)/i.test(text)) return 'giận dữ';
  if (/(?:bí ẩn|kỳ lạ|đáng ngờ)/i.test(text)) return 'bí ẩn';
  if (/(?:hào hùng|vĩ đại|oai nghiêm)/i.test(text)) return 'hào hùng';
  return 'trung tính';
}

function extractLighting(text: string): string {
  if (/(?:đèn|nến|ngọn lửa|torches)/i.test(text)) return 'ánh đèn';
  if (/(?:mặt trời|nắng|ánh sáng tự nhiên)/i.test(text)) return 'ánh sáng tự nhiên';
  if (/(?:mặt trăng|ánh trăng|moonlight)/i.test(text)) return 'ánh trăng';
  if (/(?:tia sét|chớp|lightning)/i.test(text)) return 'tia sét';
  if (/(?:ma thuật|phép thuật|glow|phosphorescent)/i.test(text)) return 'ánh sáng ma thuật';
  return 'ánh sáng tự nhiên';
}

function extractColors(text: string): string[] {
  const colors: string[] = [];
  if (/(?:đỏ| crimson|blood)/i.test(text)) colors.push('đỏ');
  if (/(?:xanh|blue|green)/i.test(text)) colors.push('xanh');
  if (/(?:tím|purple|violet)/i.test(text)) colors.push('tím');
  if (/(?:vàng|gold|golden)/i.test(text)) colors.push('vàng');
  if (/(?:đen|black|dark)/i.test(text)) colors.push('đen');
  if (/(?:trắng|white|light)/i.test(text)) colors.push('trắng');
  return colors.length ? colors : ['tông tối'];
}

function sceneFromLine(chunk: SourceChunk, local: number, id: number): Scene {
  const lines = chunk.text.split(/\r?\n/); const raw = lines[local] ?? ''; const globalLine = chunk.startLine + local;
  const context = lines.slice(Math.max(0, local - 4), Math.min(lines.length, local + 4)).join(' ');
  const action = raw.trim().slice(0, 600);
  const ignoredNames = new Set(['chuong','trong','nhung','mot','con','tren','duoi','sau','truoc','khi','va','nhung','ca','ba','hai','cuoi']);
  const normalizeName = (name: string): string => name.normalize('NFD').replace(/\p{M}/gu, '').replace(/[\u0110\u0111]/g, 'd').toLowerCase();
  const capitalized = [...raw.matchAll(/\b\p{Lu}\p{Ll}{2,}\b/gu)];
  const characters = capitalized.filter((match) => {
    const name = match[0];
    if (ignoredNames.has(normalizeName(name))) return false;
    const occurrences = context.match(new RegExp(`\\b${name}\\b`, 'gu'))?.length ?? 0;
    return match.index !== 0 || occurrences > 1 || capitalized.length === 1;
  }).map((match) => match[0]);
  const lineChunk = { ...chunk, startLine: globalLine, endLine: globalLine, text: raw, previousContext: '' };

  return {
    sceneId: `chunk-${chunk.chunkIndex}-scene-${id}`,
    startLine: globalLine, endLine: globalLine,
    location: extractLocation(context),
    time: extractTime(context),
    characters: [...new Set(characters)].slice(0, 4),
    objective: '',
    opposition: /chiến|đánh|tấn công|đối mặt/i.test(context) ? 'mối nguy hiểm' : '',
    action,
    turningPoint: action,
    result: '',
    emotion: extractMood(context),
    sensoryDetails: [],
    visualElements: [action].filter(Boolean),
    thumbnailPotential: ['clear visual moment'],
    spoilerLevel: 'low',
    mood: extractMood(context),
    lighting: extractLighting(context),
    dominantColors: extractColors(context),
    evidence: evidence(chunk, globalLine, action),
    dialogues: extractDialogues(lineChunk),
  };
}

export function analyzeChunkHeuristically(chunk: SourceChunk): ChunkAnalysis {
  const lines = chunk.text.split(/\r?\n/); const found: Scene[] = []; const used = new Set<number>();

  // Each substantial paragraph is grounded source material for one possible image.
  lines.forEach((line,index)=>{
    if(line.trim().length<60 || /^\s*(?:#+\s*)?(?:Ch\u01b0\u01a1ng|Chapter)\s+\d+/i.test(line) || /^\s*\*{3}\s*$/.test(line)) return;
    used.add(index); found.push(sceneFromLine(chunk,index,found.length+1));
  });

  // Fallback: use longest line
  if (!found.length) {
    const local = lines.findIndex((line) => line.trim().length > 60); if (local >= 0) found.push(sceneFromLine(chunk, local, 1));
  }

  const text = chunk.text;

  return {
    chunkIndex: chunk.chunkIndex, startLine: chunk.startLine, endLine: chunk.endLine,
    summary: text.replace(/\s+/g, ' ').slice(0, 500),
    povCharacters: [],
    charactersPresent: [...new Set(found.flatMap((scene) => scene.characters))],
    locations: [...new Set(found.map((scene) => scene.location).filter(Boolean))],
    events: found.map((scene) => scene.action),
    revealedFacts: [],
    emotionalArc: found.map((scene) => scene.emotion),
    magicUsed: lines.filter((line) => /ma lực|ma thuật|phép|nghi lễ|magic|spell/i.test(line)).slice(0, 12).map((line) => line.trim()),
    objects: lines.filter((line) => /kiếm|sách|tài liệu|vòng tròn|phù chú|đèn/i.test(line)).slice(0, 12).map((line) => line.trim()),
    creatures: /(?:quái|creature|beast|monster|kinh)/i.test(text) ? ['creature'] : [],
    visualMotifs: lines.filter((line) => /ánh sáng|màu sắc|đèn|nến|tia|glow/i.test(line)).slice(0, 12).map((line) => line.trim()),
    scenes: found,
    dialogues: extractDialogues(chunk),
    importantObjects: extractImportantObjects(chunk),
    importantEvents: extractImportantEvents(chunk),
  };
}
