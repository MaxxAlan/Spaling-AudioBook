import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import type { z } from 'zod';

export type JobState = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';

export interface AnalysisJobRecord {
  jobId: string;
  jobType: string;
  dependencies: string[];
  output: string;
  backend: string;
  promptVersion: string;
  schemaVersion: string;
  fingerprint: string;
  state: JobState;
  outputHash?: string;
  startedAt?: string;
  completedAt?: string;
  durationMs?: number;
  error?: string;
  provenance: {
    requestedBackend: string;
    actualBackend: string;
    fallbackReason: string | null;
  };
}

interface AnalysisManifest {
  version: 3;
  updatedAt: string;
  jobs: Record<string, AnalysisJobRecord>;
}

export interface JobSpec<T> {
  jobId: string;
  jobType: string;
  dependencies?: string[];
  output: string;
  inputHashes: Record<string, string>;
  config: unknown;
  backend: string;
  promptVersion: string;
  schemaVersion: string;
  implementationVersion?: string;
  targetScenePolicy?: unknown;
  schema: z.ZodType<T>;
  execute: () => Promise<T>;
}

export interface ResumeExplanation {
  reusable: boolean;
  storedFingerprint: string | null;
  currentFingerprint: string;
  artifactExists: boolean;
  artifactHashValid: boolean;
  schemaValid: boolean;
  partialExists: boolean;
  reason: string;
}

function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${stable(item)}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

export function fullSha256(value: string | Buffer): string {
  return createHash('sha256').update(value).digest('hex');
}

export function jobFingerprint(spec: Omit<JobSpec<unknown>, 'schema' | 'execute'>): string {
  return fullSha256(stable({
    fingerprintSchemaVersion: 1,
    jobType: spec.jobType,
    inputHashes: spec.inputHashes,
    config: spec.config,
    modelIdentity: spec.backend,
    promptVersion: spec.promptVersion,
    outputSchemaVersion: spec.schemaVersion,
    implementationVersion: spec.implementationVersion ?? 'analysis-v3.0.0',
    targetScenePolicy: spec.targetScenePolicy ?? null,
  }));
}

async function atomicWrite(file: string, data: string): Promise<void> {
  await fs.mkdir(path.dirname(file), { recursive: true });
  const temporary = `${file}.partial-${randomUUID()}`;
  const handle = await fs.open(temporary, 'wx');
  try {
    await handle.writeFile(data, 'utf8');
    await handle.sync();
  } finally {
    await handle.close();
  }
  await fs.rename(temporary, file);
}

export class AnalysisArtifactStore {
  private manifest: AnalysisManifest = { version: 3, updatedAt: new Date(0).toISOString(), jobs: {} };
  private readonly manifestPath: string;

  constructor(readonly directory: string) {
    this.manifestPath = path.join(directory, 'manifest.json');
  }

  async load(): Promise<void> {
    await fs.mkdir(this.directory, { recursive: true });
    try {
      const parsed = JSON.parse(await fs.readFile(this.manifestPath, 'utf8')) as AnalysisManifest;
      if (parsed.version === 3 && parsed.jobs) this.manifest = parsed;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    }
  }

  private async saveManifest(): Promise<void> {
    this.manifest.updatedAt = new Date().toISOString();
    await atomicWrite(this.manifestPath, `${JSON.stringify(this.manifest, null, 2)}\n`);
  }

  private outputPath(relative: string): string {
    return path.join(this.directory, relative);
  }

  private async partialExists(relative: string): Promise<boolean> {
    const file = this.outputPath(relative);
    const directory = path.dirname(file);
    const prefix = `${path.basename(file)}.partial-`;
    try { return (await fs.readdir(directory)).some((name) => name.startsWith(prefix)); }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return false;
      throw error;
    }
  }

  async explain<T>(spec: JobSpec<T>): Promise<ResumeExplanation> {
    const fingerprint = jobFingerprint(spec);
    const record = this.manifest.jobs[spec.jobId];
    const output = this.outputPath(spec.output);
    const partialExists = await this.partialExists(spec.output);
    let bytes: Buffer | null = null;
    try { bytes = await fs.readFile(output); } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    }
    const artifactExists = bytes !== null;
    const artifactHashValid = Boolean(bytes && record?.outputHash && fullSha256(bytes) === record.outputHash);
    let schemaValid = false;
    if (bytes) {
      try { spec.schema.parse(JSON.parse(bytes.toString('utf8'))); schemaValid = true; } catch { schemaValid = false; }
    }
    const dependencyFailed = (spec.dependencies ?? []).some((id) => this.manifest.jobs[id]?.state !== 'SUCCEEDED');
    const checks: Array<[boolean, string]> = [
      [!dependencyFailed, 'dependency_not_succeeded'],
      [record?.state === 'SUCCEEDED', 'job_not_succeeded'],
      [record?.fingerprint === fingerprint, 'fingerprint_changed'],
      [artifactExists, 'artifact_missing'],
      [artifactHashValid, 'artifact_hash_mismatch'],
      [schemaValid, 'artifact_schema_invalid'],
      [!partialExists, 'partial_artifact_exists'],
    ];
    const failed = checks.find(([ok]) => !ok);
    return {
      reusable: !failed,
      storedFingerprint: record?.fingerprint ?? null,
      currentFingerprint: fingerprint,
      artifactExists,
      artifactHashValid,
      schemaValid,
      partialExists,
      reason: failed?.[1] ?? 'all_resume_checks_passed',
    };
  }

  async run<T>(spec: JobSpec<T>): Promise<{ value: T; resumed: boolean; explanation: ResumeExplanation }> {
    const explanation = await this.explain(spec);
    const output = this.outputPath(spec.output);
    if (explanation.reusable) {
      return { value: spec.schema.parse(JSON.parse(await fs.readFile(output, 'utf8'))), resumed: true, explanation };
    }

    const started = Date.now();
    const fingerprint = explanation.currentFingerprint;
    this.manifest.jobs[spec.jobId] = {
      jobId: spec.jobId,
      jobType: spec.jobType,
      dependencies: spec.dependencies ?? [],
      output: spec.output,
      backend: spec.backend,
      promptVersion: spec.promptVersion,
      schemaVersion: spec.schemaVersion,
      fingerprint,
      state: 'RUNNING',
      startedAt: new Date(started).toISOString(),
      provenance: { requestedBackend: spec.backend, actualBackend: spec.backend, fallbackReason: null },
    };
    await this.saveManifest();

    const targetDirectory = path.dirname(output);
    const prefix = `${path.basename(output)}.partial-`;
    try {
      for (const name of await fs.readdir(targetDirectory)) {
        if (name.startsWith(prefix)) await fs.unlink(path.join(targetDirectory, name));
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    }

    try {
      const value = spec.schema.parse(await spec.execute());
      const serialized = `${JSON.stringify(value, null, 2)}\n`;
      await atomicWrite(output, serialized);
      const verified = spec.schema.parse(JSON.parse(await fs.readFile(output, 'utf8')));
      const completed = Date.now();
      const actualBackend = typeof verified === 'object' && verified && 'actualBackend' in verified
        ? String((verified as { actualBackend: unknown }).actualBackend)
        : spec.backend;
      const fallbackReason = typeof verified === 'object' && verified && 'fallbackReason' in verified
        ? ((verified as { fallbackReason: string | null }).fallbackReason ?? null)
        : null;
      this.manifest.jobs[spec.jobId] = {
        ...this.manifest.jobs[spec.jobId]!,
        state: 'SUCCEEDED',
        outputHash: fullSha256(Buffer.from(serialized)),
        completedAt: new Date(completed).toISOString(),
        durationMs: completed - started,
        provenance: { requestedBackend: spec.backend, actualBackend, fallbackReason },
      };
      await this.saveManifest();
      return { value: verified, resumed: false, explanation };
    } catch (error) {
      this.manifest.jobs[spec.jobId] = {
        ...this.manifest.jobs[spec.jobId]!,
        state: 'FAILED',
        completedAt: new Date().toISOString(),
        durationMs: Date.now() - started,
        error: String(error),
      };
      await this.saveManifest();
      throw error;
    }
  }

  snapshot(): Readonly<AnalysisManifest> {
    return this.manifest;
  }
}
