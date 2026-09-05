import { getFieldDb } from './db';
import { ownerKey, type CachedElectionDayAssignment, type OwnerScope } from './types';

// Mirrors campaignInfoRepository: bridges the online→offline gap for the
// identifiers (assignment/recinto/junta) a coordinator needs to check in or
// report an incident without connectivity, cached the first time "Mi
// Jornada" loads online.
export async function cacheMyElectionDayAssignment(
  scope: OwnerScope,
  data: Omit<CachedElectionDayAssignment, 'owner_key' | 'fetched_at'>,
): Promise<CachedElectionDayAssignment> {
  const db = await getFieldDb();
  const entry: CachedElectionDayAssignment = {
    ...data,
    owner_key: ownerKey(scope),
    fetched_at: new Date().toISOString(),
  };
  await db.put('cachedElectionDayAssignment', entry);
  return entry;
}

export async function getCachedMyElectionDayAssignment(
  scope: OwnerScope,
): Promise<CachedElectionDayAssignment | undefined> {
  const db = await getFieldDb();
  return db.get('cachedElectionDayAssignment', ownerKey(scope));
}
