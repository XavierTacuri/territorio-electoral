import { getFieldDb } from './db';
import type { CachedCatalog } from './types';

// System-wide reference catalogs (activity types, need categories) are not
// tenant data, so they are cached without user/campaign scoping — only so a
// field form still has its dropdown options after an offline reload.
export async function cacheCatalog(name: string, items: { code: string; name: string }[]): Promise<void> {
  const db = await getFieldDb();
  await db.put('catalogs', { name, items, fetched_at: new Date().toISOString() });
}

export async function getCachedCatalog(name: string): Promise<CachedCatalog | undefined> {
  const db = await getFieldDb();
  return db.get('catalogs', name);
}
