import { getFieldDb } from './db';
import { ownerKey, type CachedAssignment, type OwnerScope } from './types';

export async function cacheAssignments(
  scope: OwnerScope,
  parishes: { parish_id: number; parish_name: string }[],
): Promise<CachedAssignment> {
  const db = await getFieldDb();
  const entry: CachedAssignment = {
    owner_key: ownerKey(scope),
    organization_id: scope.organization_id,
    campaign_id: scope.campaign_id,
    user_id: scope.user_id,
    parishes,
    fetched_at: new Date().toISOString(),
  };
  await db.put('cachedAssignments', entry);
  return entry;
}

export async function getCachedAssignments(scope: OwnerScope): Promise<CachedAssignment | undefined> {
  const db = await getFieldDb();
  return db.get('cachedAssignments', ownerKey(scope));
}
