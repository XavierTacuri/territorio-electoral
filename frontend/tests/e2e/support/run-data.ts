import { randomUUID } from 'node:crypto';

const configuredRunId = process.env.E2E_RUN_ID?.replace(/[^a-zA-Z0-9_-]/g, '-');

export const e2eRunId = configuredRunId || randomUUID().replaceAll('-', '');

export function uniqueE2eValue(base: string) {
  return `${base}-${e2eRunId}`;
}
