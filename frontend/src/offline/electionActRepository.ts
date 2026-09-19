import { getFieldDb } from './db';
import { ownerKey, type CachedElectionActContext, type OwnerScope } from './types';

function contextKey(scope: OwnerScope, pollingPlaceId: string): string {
  return `${ownerKey(scope)}::${pollingPlaceId}`;
}

export async function cacheElectionActContext(
  scope: OwnerScope,
  pollingPlaceId: string,
  data: Omit<CachedElectionActContext, 'key' | 'owner_key' | 'polling_place_id' | 'fetched_at'>,
): Promise<CachedElectionActContext> {
  const db = await getFieldDb();
  const entry: CachedElectionActContext = {
    ...data,
    key: contextKey(scope, pollingPlaceId),
    owner_key: ownerKey(scope),
    polling_place_id: pollingPlaceId,
    fetched_at: new Date().toISOString(),
  };
  await db.put('cachedElectionActContext', entry);
  return entry;
}

export async function getCachedElectionActContext(
  scope: OwnerScope,
  pollingPlaceId: string,
): Promise<CachedElectionActContext | undefined> {
  const db = await getFieldDb();
  return db.get('cachedElectionActContext', contextKey(scope, pollingPlaceId));
}
