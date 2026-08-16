import { ApiError } from '../../api/errors';
import { commercialErrorMessages } from '../../lib/labels';

export function organizationError(error: unknown) {
  if (!(error instanceof ApiError)) return 'No se pudo completar la operación.';
  const detail = error.detail as
    | { detail?: { code?: string; message?: string } | string }
    | undefined;
  const value = detail?.detail;
  const code = typeof value === 'object' ? value.code : undefined;
  return commercialErrorMessages[code ?? ''] ?? 'No se pudo completar la operación.';
}
