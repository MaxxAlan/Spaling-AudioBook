#!/usr/bin/env node
import { Command } from 'commander';
import { loadEnvironment } from './config/env.js';
import { registerInitCommand } from './commands/init.js';
import { registerAnalyzeCommand } from './commands/analyze.js';
import { registerGenerateCommand } from './commands/generate.js';
import { registerRegenerateCommand } from './commands/regenerate.js';
import { errorMessage } from './utils/errors.js';

const program = new Command().name('story-thumbnail').description('AI CLI tạo cinematic story episode thumbnail artwork không chữ').version('0.0.2').showHelpAfterError();
const env = loadEnvironment(); registerInitCommand(program); registerAnalyzeCommand(program,env); registerGenerateCommand(program,env); registerRegenerateCommand(program,env);
program.parseAsync(process.argv).catch((error: unknown) => { process.stderr.write(`story-thumbnail: ${errorMessage(error)}\n`); process.exitCode = 1; });
