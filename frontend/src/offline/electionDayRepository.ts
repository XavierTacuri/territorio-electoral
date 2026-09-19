import { getFieldDb } from './db';
import { ownerKey, type CachedElectionDayAssignments, type OwnerScope } from './types';

// Mirrors campaignInfoRepository: bridges the online→offline gap for the
// identifiers (asignación/recinto) un delegado necesita para hacer check-in o
// reportar una incidencia sin conectividad. Un delegado puede cubrir más de
// un recinto (§13): se cachea la lista completa, no una sola asignación.
export async function cacheMyElectionDayAssignments(
  scope: OwnerScope,
  assignments: CachedElectionDayAssignments['assignments'],
): Promise<CachedElectionDayAssignments> {
  const db = await getFieldDb();
  const entry: CachedElectionDayAssignments = {
    assignments,
    owner_key: ownerKey(scope),
    fetched_at: new Date().toISOString(),
  };
  await db.put('cachedElectionDayAssignment', entry);
  return entry;
}

export async function getCachedMyElectionDayAssignments(
  scope: OwnerScope,
): Promise<CachedElectionDayAssignments | undefined> {
  const db = await getFieldDb();
  return db.get('cachedElectionDayAssignment', ownerKey(scope));
}
