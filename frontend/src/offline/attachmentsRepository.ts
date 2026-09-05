import { getFieldDb } from './db';
import { notifyQueueChanged } from './offlineEvents';
import { ownerKey, type AttachmentSyncStatus, type OwnerScope, type PendingAttachment } from './types';
import { validateAttachment } from './attachmentLimits';

// Blobs are stored as-is in IndexedDB (structured clone supports Blob
// natively) — never base64-encoded into a JSON payload, which would bloat
// the draft record and defeat streaming reads.
export async function addPendingAttachment(
  scope: OwnerScope,
  draftId: string,
  file: File,
  title: string,
): Promise<{ attachment?: PendingAttachment; error?: string }> {
  const error = validateAttachment(file);
  if (error) return { error };
  const db = await getFieldDb();
  const attachment: PendingAttachment = {
    id: crypto.randomUUID(),
    client_generated_id: crypto.randomUUID(),
    draft_id: draftId,
    owner_key: ownerKey(scope),
    evidence_type: file.type === 'application/pdf' ? 'DOCUMENT' : 'PHOTO',
    title,
    file_name: file.name,
    mime_type: file.type,
    size_bytes: file.size,
    blob: file,
    created_at: new Date().toISOString(),
    sync_status: 'PENDING',
    last_error: null,
    server_id: null,
  };
  await db.put('pendingAttachments', attachment);
  notifyQueueChanged();
  return { attachment };
}

export async function listAttachments(draftId: string): Promise<PendingAttachment[]> {
  const db = await getFieldDb();
  return db.getAllFromIndex('pendingAttachments', 'draft', draftId);
}

export async function listAttachmentsForOwner(scope: OwnerScope): Promise<PendingAttachment[]> {
  const db = await getFieldDb();
  return db.getAllFromIndex('pendingAttachments', 'owner', ownerKey(scope));
}

export async function getAttachment(id: string): Promise<PendingAttachment | undefined> {
  const db = await getFieldDb();
  return db.get('pendingAttachments', id);
}

export async function setAttachmentStatus(
  id: string,
  status: AttachmentSyncStatus,
  options: { lastError?: string | null; serverId?: string | null } = {},
): Promise<void> {
  const db = await getFieldDb();
  const existing = await db.get('pendingAttachments', id);
  if (!existing) return;
  await db.put('pendingAttachments', {
    ...existing,
    sync_status: status,
    last_error: options.lastError !== undefined ? options.lastError : existing.last_error,
    server_id: options.serverId !== undefined ? options.serverId : existing.server_id,
  });
  notifyQueueChanged();
}

export async function removeAttachment(id: string): Promise<void> {
  const db = await getFieldDb();
  await db.delete('pendingAttachments', id);
  notifyQueueChanged();
}
