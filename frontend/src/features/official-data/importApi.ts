import { BASE_URL, tokenStore } from '../../api/client';
import { importErrorMessage } from '../imports/ImportPage';
import type { ImportResult, OfficialDataset } from './types';

export async function runOfficialImport(
  action: 'validate' | 'execute',
  sourceId: string,
  dataset: OfficialDataset | 'INEC_DEMOGRAPHIC_INDICATORS',
  file: File,
  force = false,
  mappingProfile?: string,
): Promise<ImportResult> {
  const body = new FormData();
  body.set('source_id', sourceId);
  body.set('dataset_type', dataset);
  body.set('file', file);
  if (mappingProfile) body.set('mapping_profile', mappingProfile);
  if (action === 'execute') body.set('force', String(force));
  const response = await fetch(`${BASE_URL}/data-imports/${action}`, {
    method: 'POST',
    body,
    credentials: 'include',
    headers: tokenStore.get() ? { Authorization: `Bearer ${tokenStore.get()}` } : undefined,
  });
  if (!response.ok) throw new Error(await importErrorMessage(response));
  return response.json() as Promise<ImportResult>;
}
