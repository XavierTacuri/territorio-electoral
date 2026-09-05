import { apiRequest } from '../api/client';
import { ApiError } from '../api/errors';
import {
  listAttachments,
  listAttachmentsForOwner,
  setAttachmentStatus,
} from './attachmentsRepository';
import { getDraft, setDraftStatus } from './draftsRepository';
import { listQueue, removeFromQueue, setQueueStatus } from './syncQueueRepository';
import type {
  DraftEntityType,
  OfflineDraft,
  OwnerScope,
  PendingAttachment,
  SyncQueueItem,
} from './types';

export type SyncProgress = { index: number; total: number; item: SyncQueueItem };
export type SyncSummary = {
  synced: number;
  failed: number;
  conflicts: number;
  skipped: number;
  attachmentsSynced: number;
  attachmentsPending: number;
  attachmentsFailed: number;
};

const ELECTION_DAY_ENTITY_TYPES: DraftEntityType[] = [
  'ELECTION_DAY_CHECK_IN',
  'ELECTION_DAY_INCIDENT',
  'ELECTION_DAY_DOCUMENT',
];

function friendlyError(error: unknown, entityType?: DraftEntityType): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      // §51: para jornada, un 403 en sync casi siempre significa que el
      // manager reemplazó la asignación antes de que este registro offline
      // llegara al servidor — mensaje específico en vez del genérico de
      // "territorio" (que no aplica a check-in/incidencia/documento de junta).
      return ELECTION_DAY_ENTITY_TYPES.includes(entityType as DraftEntityType)
        ? 'Tu asignación cambió. Este registro requiere revisión.'
        : 'Ya no tienes acceso a este territorio. Este registro requiere revisión.';
    }
    if (error.status === 409)
      return 'Este registro requiere revisión: ya existe un registro similar en el servidor.';
    return 'No fue posible sincronizar este registro.';
  }
  return 'No fue posible sincronizar este registro.';
}

async function syncActivity(draft: OfflineDraft): Promise<{ id: string }> {
  return apiRequest<{ id: string }>(`/campaigns/${draft.campaign_id}/activities`, {
    method: 'POST',
    body: JSON.stringify({ ...draft.payload, client_generated_id: draft.client_generated_id }),
  });
}

async function syncNeed(
  draft: OfflineDraft,
  linkedActivityServerId: string | null,
): Promise<{ id: string }> {
  const body = { ...draft.payload, client_generated_id: draft.client_generated_id };
  if (linkedActivityServerId) {
    return apiRequest<{ id: string }>(
      `/campaigns/${draft.campaign_id}/activities/${linkedActivityServerId}/needs`,
      { method: 'POST', body: JSON.stringify(body) },
    );
  }
  return apiRequest<{ id: string }>(`/campaigns/${draft.campaign_id}/needs`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

async function syncCheckIn(draft: OfflineDraft): Promise<{ id: string }> {
  const assignmentId = draft.payload.assignment_id as string;
  await apiRequest(
    `/campaigns/${draft.campaign_id}/election-day/assignments/${assignmentId}/check-in`,
    {
      method: 'POST',
      body: JSON.stringify({
        latitude: draft.payload.latitude ?? null,
        longitude: draft.payload.longitude ?? null,
        client_generated_id: draft.client_generated_id,
        offline_created_at: draft.created_offline_at,
      }),
    },
  );
  return { id: assignmentId };
}

async function syncIncident(draft: OfflineDraft): Promise<{ id: string }> {
  return apiRequest<{ id: string }>(`/campaigns/${draft.campaign_id}/election-day/incidents`, {
    method: 'POST',
    body: JSON.stringify({
      polling_place_id: draft.payload.polling_place_id,
      board_id: draft.payload.board_id ?? null,
      category: draft.payload.category,
      description: draft.payload.description,
      client_generated_id: draft.client_generated_id,
      offline_created_at: draft.created_offline_at,
    }),
  });
}

// El documento de jornada es la propia foto/PDF, no un adjunto de otro
// registro (a diferencia de la evidencia de actividad): se reutiliza el
// mismo almacén de pendingAttachments (§21, "no crear una segunda cola"),
// pero un draft de este tipo siempre tiene exactamente un adjunto asociado.
async function syncElectionDayDocument(draft: OfflineDraft): Promise<{ id: string }> {
  const [attachment] = await listAttachments(draft.id);
  if (!attachment) throw new Error('El documento no tiene un archivo adjunto pendiente.');
  const form = new FormData();
  form.append('file', attachment.blob, attachment.file_name);
  form.append('polling_place_id', draft.payload.polling_place_id as string);
  if (draft.payload.board_id) form.append('board_id', draft.payload.board_id as string);
  form.append('document_type', draft.payload.document_type as string);
  form.append('client_generated_id', draft.client_generated_id);
  const result = await apiRequest<{ id: string }>(
    `/campaigns/${draft.campaign_id}/election-day/documents/upload`,
    {
      method: 'POST',
      body: form,
    },
  );
  await setAttachmentStatus(attachment.id, 'SYNCED', { serverId: result.id });
  return result;
}

async function syncAttachment(
  campaignId: string,
  activityServerId: string,
  attachment: PendingAttachment,
): Promise<{ id: string }> {
  const form = new FormData();
  form.append('file', attachment.blob, attachment.file_name);
  form.append('evidence_type', attachment.evidence_type);
  form.append('title', attachment.title);
  form.append('client_generated_id', attachment.client_generated_id);
  return apiRequest<{ id: string }>(
    `/campaigns/${campaignId}/activities/${activityServerId}/evidence/upload`,
    {
      method: 'POST',
      body: form,
    },
  );
}

// Uploads any attachments belonging to activities that already resolved a
// real server id. Evidence can only be attached to an APPROVED activity
// (existing, unrelated-to-offline business rule) — a freshly
// coordinator-synced activity is PENDING_APPROVAL, so its attachments stay
// PENDING (never FAILED) until a later manual sync, after staff approval,
// retries them. This never blocks or downgrades the activity draft's own
// SYNCED status: the activity record and its evidence are synced
// independently, since nothing in this app's contract makes evidence a
// precondition for the activity itself being considered synced.
async function syncAttachments(scope: OwnerScope, summary: SyncSummary): Promise<void> {
  const attachments = await listAttachmentsForOwner(scope);
  for (const attachment of attachments) {
    if (attachment.sync_status !== 'PENDING' && attachment.sync_status !== 'FAILED') continue;
    const draft = await getDraft(attachment.draft_id);
    if (!draft || draft.sync_status !== 'SYNCED' || !draft.server_id) {
      summary.attachmentsPending += 1;
      continue;
    }
    await setAttachmentStatus(attachment.id, 'SYNCING');
    try {
      const result = await syncAttachment(draft.campaign_id, draft.server_id, attachment);
      await setAttachmentStatus(attachment.id, 'SYNCED', { serverId: result.id, lastError: null });
      summary.attachmentsSynced += 1;
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        await setAttachmentStatus(attachment.id, 'REQUIRES_REVIEW', {
          lastError: 'Ya no tienes acceso a este territorio. Este registro requiere revisión.',
        });
        summary.attachmentsFailed += 1;
      } else if (error instanceof ApiError && error.status === 400) {
        // Business-rule retry case (typically: activity not yet approved).
        await setAttachmentStatus(attachment.id, 'PENDING', {
          lastError: 'Se subirá cuando la actividad esté aprobada.',
        });
        summary.attachmentsPending += 1;
      } else {
        await setAttachmentStatus(attachment.id, 'FAILED', {
          lastError: 'No fue posible sincronizar este adjunto.',
        });
        summary.attachmentsFailed += 1;
      }
    }
  }
}

// Processes one owner's queue sequentially (never in parallel — a burst of
// concurrent mutations is exactly what section 20 rules out). Activities are
// always resolved before needs that reference them, and a local
// (client-generated) id is never sent to the server as if it were a real one:
// a linked need waits for its activity's real server id first.
export async function syncQueue(
  scope: OwnerScope,
  onProgress?: (progress: SyncProgress) => void,
): Promise<SyncSummary> {
  const all = await listQueue(scope);
  const pending = all.filter((item) => item.status === 'PENDING' || item.status === 'FAILED');
  // §50: la incidencia (o actividad) siempre se sincroniza antes que su
  // evidencia/documento; NEED ya dependía de ACTIVITY vía server id, así que
  // conserva la misma prioridad relativa que antes.
  const SYNC_PRIORITY: Record<string, number> = {
    ACTIVITY: 0,
    ELECTION_DAY_CHECK_IN: 0,
    ELECTION_DAY_INCIDENT: 0,
    NEED: 1,
    ELECTION_DAY_DOCUMENT: 1,
  };
  const ordered = [...pending].sort((a, b) => {
    const priorityDiff = (SYNC_PRIORITY[a.entity_type] ?? 0) - (SYNC_PRIORITY[b.entity_type] ?? 0);
    return priorityDiff !== 0 ? priorityDiff : a.created_at.localeCompare(b.created_at);
  });
  const summary: SyncSummary = {
    synced: 0,
    failed: 0,
    conflicts: 0,
    skipped: 0,
    attachmentsSynced: 0,
    attachmentsPending: 0,
    attachmentsFailed: 0,
  };
  for (let i = 0; i < ordered.length; i++) {
    const item = ordered[i];
    onProgress?.({ index: i + 1, total: ordered.length, item });
    const draft = await getDraft(item.draft_id);
    if (!draft) {
      await removeFromQueue(item.id);
      continue;
    }
    let linkedActivityServerId: string | null = null;
    if (draft.entity_type === 'NEED') {
      const linkedDraftId = draft.payload._local_activity_draft_id as string | undefined;
      if (linkedDraftId) {
        const activityDraft = await getDraft(linkedDraftId);
        if (
          !activityDraft ||
          activityDraft.sync_status === 'REQUIRES_REVIEW' ||
          activityDraft.sync_status === 'ERROR'
        ) {
          await setQueueStatus(
            item.id,
            'FAILED',
            'La actividad vinculada aún no se pudo sincronizar.',
          );
          summary.skipped += 1;
          continue;
        }
        if (activityDraft.sync_status !== 'SYNCED' || !activityDraft.server_id) {
          // Its turn hasn't come yet within this batch (or it failed above it) — retry on the next manual sync.
          await setQueueStatus(
            item.id,
            'FAILED',
            'Pendiente: la actividad vinculada aún no está sincronizada.',
          );
          summary.skipped += 1;
          continue;
        }
        linkedActivityServerId = activityDraft.server_id;
      }
    }
    await setQueueStatus(item.id, 'SYNCING');
    await setDraftStatus(draft.id, 'SYNCING');
    try {
      const result =
        draft.entity_type === 'ACTIVITY'
          ? await syncActivity(draft)
          : draft.entity_type === 'NEED'
            ? await syncNeed(draft, linkedActivityServerId)
            : draft.entity_type === 'ELECTION_DAY_CHECK_IN'
              ? await syncCheckIn(draft)
              : draft.entity_type === 'ELECTION_DAY_INCIDENT'
                ? await syncIncident(draft)
                : await syncElectionDayDocument(draft);
      await setDraftStatus(draft.id, 'SYNCED', {
        serverId: result.id,
        lastError: null,
        conflictReason: null,
      });
      await setQueueStatus(item.id, 'SYNCED');
      summary.synced += 1;
    } catch (error) {
      const message = friendlyError(error, draft.entity_type);
      const isForbidden = error instanceof ApiError && error.status === 403;
      const isConflict409 = error instanceof ApiError && error.status === 409;
      const needsReview = isForbidden || isConflict409;
      await setDraftStatus(draft.id, needsReview ? 'REQUIRES_REVIEW' : 'ERROR', {
        lastError: message,
        conflictReason: isForbidden ? 'FORBIDDEN' : isConflict409 ? 'CONFLICT' : null,
      });
      await setQueueStatus(
        item.id,
        needsReview ? (isConflict409 ? 'CONFLICT' : 'FAILED') : 'FAILED',
        message,
      );
      if (isConflict409) summary.conflicts += 1;
      else summary.failed += 1;
    }
  }
  await syncAttachments(scope, summary);
  return summary;
}
