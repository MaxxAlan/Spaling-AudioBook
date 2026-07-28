import fs from 'node:fs/promises';
import path from 'node:path';
import type { Command } from 'commander';
import { DEFAULT_CONFIG } from '../config/project-config.js';
import { writeJson } from '../thumbnail/output-writer.js';

export function registerInitCommand(program: Command): void {
  program.command('init').description('Khởi tạo cấu trúc project story-thumbnail').option('--force','ghi đè config/state mặc định').action(async ({ force }: { force?: boolean }) => {
    const root = process.cwd(); const base = path.join(root,'.story-thumbnail'); await Promise.all(['state','cache','references'].map((name) => fs.mkdir(path.join(base,name),{recursive:true}))); await fs.mkdir(path.join(root,'output'),{recursive:true});
    const files: Array<[string,unknown]> = [[path.join(base,'config.json'),DEFAULT_CONFIG],[path.join(base,'state','characters.json'),{version:1,characters:{}}],[path.join(base,'state','visual-style.json'),{version:1,style:'cinematic-dark-fantasy',rendering:'painterly realism',typography:false}]];
    for (const [file,data] of files) { try { if (!force) await fs.access(file); else throw Object.assign(new Error(),{code:'ENOENT'}); } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') await writeJson(file,data); else throw error; } }
    process.stdout.write(`Đã khởi tạo ${base}\n`);
  });
}
