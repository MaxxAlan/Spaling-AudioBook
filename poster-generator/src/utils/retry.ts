export async function retry<T>(operation: () => Promise<T>, attempts = 3, delayMs = 300, shouldRetry: (error: unknown) => boolean = () => true): Promise<T> {
  let last: unknown;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try { return await operation(); } catch (error) {
      last = error;
      if (!shouldRetry(error)) throw error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, delayMs * attempt));
    }
  }
  throw last;
}
