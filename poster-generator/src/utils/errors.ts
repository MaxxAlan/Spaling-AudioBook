export class AppError extends Error {
  constructor(public readonly code: string, message: string, public readonly details?: unknown) {
    super(message); this.name = 'AppError';
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
