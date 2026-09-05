import { getFieldDb } from './db';
import { ownerKey, type CachedAgenda, type FieldAgendaItem, type OwnerScope } from './types';

export async function cacheAgenda(
  scope: OwnerScope,
  items: FieldAgendaItem[],
): Promise<CachedAgenda> {
  const db = await getFieldDb();
  const entry: CachedAgenda = {
    owner_key: ownerKey(scope),
    organization_id: scope.organization_id,
    campaign_id: scope.campaign_id,
    user_id: scope.user_id,
    items,
    fetched_at: new Date().toISOString(),
  };
  await db.put('cachedAgenda', entry);
  return entry;
}

export async function getCachedAgenda(scope: OwnerScope): Promise<CachedAgenda | undefined> {
  const db = await getFieldDb();
  return db.get('cachedAgenda', ownerKey(scope));
}
