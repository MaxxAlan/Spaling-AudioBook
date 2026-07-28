import fs from 'node:fs/promises';
import path from 'node:path';
import { characterStateSchema, type CharacterState, type CharacterVisual } from '../schemas/character.js';

function provisionalAppearance(characterId:string):CharacterVisual['canonicalAppearance'] {
  const seed=[...characterId].reduce((value,char)=>value+char.codePointAt(0)!,0);
  const pick=(values:string[])=>values[seed%values.length]!;
  return {
    face:pick(['distinct angular face','distinct oval face','distinct square face']),
    hair:pick(['straight dark hair','wavy dark-brown hair','short charcoal-black hair']),
    eyes:pick(['dark amber eyes','grey-blue eyes','deep brown eyes']),
    skin:pick(['neutral light-brown skin','neutral medium skin','neutral fair skin']),
    body:pick(['lean build','athletic build','slender build']),
    clothing:'plain source-neutral layered clothing without culture-specific motifs',
    accessories:[],
  };
}

function materializeProvisional(current:CharacterVisual):CharacterVisual {
  const fallback=provisionalAppearance(current.characterId);
  const canonicalAppearance={...current.canonicalAppearance};
  for(const key of ['face','hair','eyes','skin','body','clothing'] as const) {
    canonicalAppearance[key] ??= fallback[key];
  }
  return {
    ...current,
    canonicalAppearance,
    lockedAttributes:[...new Set([...current.lockedAttributes,'face','hair','eyes','skin','body','clothing'])],
  };
}

export async function loadCharacterState(projectRoot: string): Promise<CharacterState> {
  const file = path.join(projectRoot, '.story-thumbnail', 'state', 'characters.json');
  try { return characterStateSchema.parse(JSON.parse(await fs.readFile(file, 'utf8'))); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { version: 1, characters: {} }; throw error; }
}
export function mergeCharacterState(state: CharacterState, resolved: CharacterVisual[]): CharacterState {
  const next = structuredClone(state);
  for (const current of resolved) {
    const previous = next.characters[current.characterId];
    if (!previous) { next.characters[current.characterId] = { ...materializeProvisional(current), revisions: [] }; continue; }
    const appearance = { ...current.canonicalAppearance };
    for (const key of ['face','hair','eyes','skin','body','clothing'] as const) if (appearance[key] === null && previous.canonicalAppearance[key] !== null) appearance[key] = previous.canonicalAppearance[key];
    const revisions = [...previous.revisions];
    for (const key of ['hair','eyes','clothing'] as const) if (current.canonicalAppearance[key] && previous.canonicalAppearance[key] && current.canonicalAppearance[key] !== previous.canonicalAppearance[key]) revisions.push({ attribute: key, oldValue: previous.canonicalAppearance[key]!, newValue: current.canonicalAppearance[key]!, reason: 'new explicit canon overrides stored provisional/canon', source: current.evidence[0]?.sourcePath ?? 'canon', createdAt: new Date().toISOString() });
    next.characters[current.characterId] = { ...previous, ...current, identity: { realAge: current.identity.realAge ?? previous.identity.realAge, visibleAge: current.identity.visibleAge ?? previous.identity.visibleAge, gender: current.identity.gender ?? previous.identity.gender }, canonicalAppearance: appearance, provisionalAttributes: [...new Set([...previous.provisionalAttributes, ...current.provisionalAttributes])], revisions };
  }
  return next;
}
export async function saveCharacterState(projectRoot: string, state: CharacterState): Promise<void> {
  const file = path.join(projectRoot, '.story-thumbnail', 'state', 'characters.json'); await fs.mkdir(path.dirname(file), { recursive: true }); await fs.writeFile(file, `${JSON.stringify(state, null, 2)}\n`, 'utf8');
}
