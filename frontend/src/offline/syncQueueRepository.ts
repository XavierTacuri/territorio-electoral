import { getFieldDb } from './db';
import { setDraftStatus } from './draftsRepository';
import { notifyQueueChanged } from './offlineEvents';
import { ownerKey, type DraftEntityType, type OwnerScope, type SyncQueueItem } from './types';

export async function enqueue(
  scope: OwnerScope,
  draftId: string,
  entityType: DraftEntityType,
): Promise<SyncQueueItem> {
  const db = await getFieldDb();
  const existing = await db.get('syncQueue', draftId);
  if (existing && existing.status !== 'FAILED') return existing;
  const now = new Date().toISOString();
  const item: SyncQueueItem = {
    id: draftId,
    owner_key: ownerKey(scope),
    draft_id: draftId,
    entity_type: entityType,
    organization_id: scope.organization_id,
    campaign_id: scope.campaign_id,
    user_id: scope.user_id,
    status: 'PENDING',
    attempts: existing?.attempts ?? 0,
    last_error: null,
    created_at: existing?.created_at ?? now,
    updated_at: now,
  };
  await db.put('syncQueue', item);
  // Keep the draft's own displayed status (drafts list, home tile) in sync
  // with the fact that it's now queued — otherwise it stays stuck showing
  // "Borrador" even though it is actually pending sync.
  await setDraftStatus(draftId, 'PENDING');
  notifyQueueChanged();
  return item;
}

export async function listQueue(scope: OwnerScope): Promise<SyncQueueItem[]> {
  const db = await getFieldDb();
  const all = await db.getAllFromIndex('syncQueue', 'owner', ownerKey(scope));
  return all.sort((a, b) => a.created_at.localeCompare(b.created_at));
}

export async function countPending(scope: OwnerScope): Promise<number> {
  const items = await listQueue(scope);
  return items.filter((item) => item.status === 'PENDING' || item.status === 'FAILED').length;
}

export async function setQueueStatus(
  id: string,
  status: SyncQueueItem['status'],
  lastError: string | null = null,
): Promise<void> {
  const db = await getFieldDb();
  const existing = await db.get('syncQueue', id);
  if (!existing) return;
  await db.put('syncQueue', {
    ...existing,
    status,
    last_error: lastError,
    attempts: status === 'SYNCING' ? existing.attempts + 1 : existing.attempts,
    updated_at: new Date().toISOString(),
  });
  notifyQueueChanged();
}

export async function removeFromQueue(id: string): Promise<void> {
  const db = await getFieldDb();
  await db.delete('syncQueue', id);
  notifyQueueChanged();
}
