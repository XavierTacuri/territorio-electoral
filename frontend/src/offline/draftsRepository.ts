import { getFieldDb } from './db';
import {
  ownerKey,
  type ConflictReason,
  type DraftEntityType,
  type OfflineDraft,
  type OwnerScope,
} from './types';

function draftId(entityType: DraftEntityType, clientGeneratedId: string) {
  return `${entityType}:${clientGeneratedId}`;
}

export async function createDraft(
  scope: OwnerScope,
  entityType: DraftEntityType,
  parishId: number,
  payload: Record<string, unknown>,
  clientGeneratedId: string,
): Promise<OfflineDraft> {
  const now = new Date().toISOString();
  const draft: OfflineDraft = {
    id: draftId(entityType, clientGeneratedId),
    owner_key: ownerKey(scope),
    client_generated_id: clientGeneratedId,
    entity_type: entityType,
    organization_id: scope.organization_id,
    campaign_id: scope.campaign_id,
    parish_id: parishId,
    user_id: scope.user_id,
    payload,
    created_offline_at: now,
    updated_offline_at: now,
    sync_status: 'DRAFT',
    last_error: null,
    conflict_reason: null,
    server_id: null,
  };
  const db = await getFieldDb();
  await db.put('drafts', draft);
  return draft;
}

export async function updateDraftPayload(
  id: string,
  payload: Record<string, unknown>,
): Promise<OfflineDraft | undefined> {
  const db = await getFieldDb();
  const existing = await db.get('drafts', id);
  if (!existing) return undefined;
  const updated: OfflineDraft = {
    ...existing,
    payload,
    updated_offline_at: new Date().toISOString(),
  };
  await db.put('drafts', updated);
  return updated;
}

export async function setDraftStatus(
  id: string,
  status: OfflineDraft['sync_status'],
  options: {
    lastError?: string | null;
    serverId?: string | null;
    conflictReason?: ConflictReason;
  } = {},
): Promise<OfflineDraft | undefined> {
  const db = await getFieldDb();
  const existing = await db.get('drafts', id);
  if (!existing) return undefined;
  const updated: OfflineDraft = {
    ...existing,
    sync_status: status,
    updated_offline_at: new Date().toISOString(),
    last_error: options.lastError !== undefined ? options.lastError : existing.last_error,
    server_id: options.serverId !== undefined ? options.serverId : existing.server_id,
    conflict_reason:
      options.conflictReason !== undefined ? options.conflictReason : existing.conflict_reason,
  };
  await db.put('drafts', updated);
  return updated;
}

export async function getDraft(id: string): Promise<OfflineDraft | undefined> {
  const db = await getFieldDb();
  return db.get('drafts', id);
}

export async function listDrafts(scope: OwnerScope): Promise<OfflineDraft[]> {
  const db = await getFieldDb();
  const all = await db.getAllFromIndex('drafts', 'owner', ownerKey(scope));
  return all.sort((a, b) => b.updated_offline_at.localeCompare(a.updated_offline_at));
}

export async function deleteDraft(id: string, scope: OwnerScope): Promise<boolean> {
  const db = await getFieldDb();
  const existing = await db.get('drafts', id);
  if (!existing || existing.owner_key !== ownerKey(scope)) return false;
  await db.delete('drafts', id);
  const attachments = await db.getAllFromIndex('pendingAttachments', 'draft', id);
  for (const attachment of attachments) await db.delete('pendingAttachments', attachment.id);
  return true;
}

// Data-retention: drafts already confirmed SYNCED can be pruned locally once
// the coordinator has moved on, so the device store doesn't grow forever.
// Failed/requires-review drafts are always kept until resolved.
export async function pruneSyncedDrafts(scope: OwnerScope, olderThanMs = 0): Promise<number> {
  const db = await getFieldDb();
  const all = await db.getAllFromIndex('drafts', 'owner', ownerKey(scope));
  const cutoff = Date.now() - olderThanMs;
  let removed = 0;
  for (const draft of all) {
    if (draft.sync_status === 'SYNCED' && new Date(draft.updated_offline_at).getTime() <= cutoff) {
      await db.delete('drafts', draft.id);
      removed += 1;
    }
  }
  return removed;
}
