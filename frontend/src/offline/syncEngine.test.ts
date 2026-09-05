import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/errors';
import { createDraft, getDraft } from './draftsRepository';
import { syncQueue } from './syncEngine';
import { enqueue, listQueue } from './syncQueueRepository';
import type { OwnerScope, PendingAttachment } from './types';

vi.mock('../api/client', () => ({ apiRequest: vi.fn() }));
import { apiRequest } from '../api/client';

// fake-indexeddb (used by draftsRepository/syncQueueRepository in these
// tests) does not faithfully preserve real Blob/File objects through its
// structured-clone emulation in Node — a known test-environment gap, not a
// real app bug (actual browsers round-trip Blob/File through IndexedDB
// correctly). listAttachmentsForOwner/setAttachmentStatus are mocked here so
// the attachment-sync tests exercise syncEngine's real orchestration logic
// against a genuine in-memory Blob, instead of one that failed to survive a
// fake IndexedDB round-trip.
vi.mock('./attachmentsRepository', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./attachmentsRepository')>();
  return { ...actual, listAttachmentsForOwner: vi.fn(), setAttachmentStatus: vi.fn() };
});
import { listAttachmentsForOwner, setAttachmentStatus } from './attachmentsRepository';

const mockedApiRequest = vi.mocked(apiRequest);
const mockedListAttachmentsForOwner = vi.mocked(listAttachmentsForOwner);
const mockedSetAttachmentStatus = vi.mocked(setAttachmentStatus);

function scopeFor(campaignId: string): OwnerScope {
  return { user_id: 'sync-user', organization_id: 'org-1', campaign_id: campaignId };
}

function fakeAttachment(overrides: Partial<PendingAttachment> = {}): PendingAttachment {
  return {
    id: 'attachment-1',
    client_generated_id: 'attachment-client-1',
    draft_id: 'ACTIVITY:placeholder',
    owner_key: 'sync-user::org-1::placeholder',
    evidence_type: 'PHOTO',
    title: 'Evidencia de campo',
    file_name: 'foto.jpg',
    mime_type: 'image/jpeg',
    size_bytes: 6,
    blob: new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 0])], { type: 'image/jpeg' }),
    created_at: new Date().toISOString(),
    sync_status: 'PENDING',
    last_error: null,
    server_id: null,
    ...overrides,
  };
}

beforeEach(() => {
  mockedApiRequest.mockReset();
  mockedListAttachmentsForOwner.mockReset().mockResolvedValue([]);
  mockedSetAttachmentStatus.mockReset().mockResolvedValue(undefined);
});

describe('syncEngine.syncQueue', () => {
  it('syncs a successful activity and marks the draft SYNCED with the server id', async () => {
    const scope = scopeFor('sync-success');
    const draft = await createDraft(scope, 'ACTIVITY', 41, { title: 'Asamblea' }, 'sync-success-client');
    await enqueue(scope, draft.id, 'ACTIVITY');
    mockedApiRequest.mockResolvedValueOnce({ id: 'server-activity-1' });

    const summary = await syncQueue(scope);

    expect(summary.synced).toBe(1);
    const updated = await getDraft(draft.id);
    expect(updated?.sync_status).toBe('SYNCED');
    expect(updated?.server_id).toBe('server-activity-1');
    const queueItems = await listQueue(scope);
    expect(queueItems.find((i) => i.id === draft.id)?.status).toBe('SYNCED');
  });

  it('does not resend an already-synced item on a second sync pass (double sync)', async () => {
    const scope = scopeFor('sync-double');
    const draft = await createDraft(scope, 'NEED', 41, { title: 'Necesidad' }, 'sync-double-client');
    await enqueue(scope, draft.id, 'NEED');
    mockedApiRequest.mockResolvedValueOnce({ id: 'server-need-1' });

    await syncQueue(scope);
    const secondPass = await syncQueue(scope);

    expect(mockedApiRequest).toHaveBeenCalledTimes(1);
    expect(secondPass.synced).toBe(0);
  });

  it('marks a 403 as requiring review with a friendly message, never the raw error', async () => {
    const scope = scopeFor('sync-403');
    const draft = await createDraft(scope, 'ACTIVITY', 41, { title: 'Sin acceso' }, 'sync-403-client');
    await enqueue(scope, draft.id, 'ACTIVITY');
    mockedApiRequest.mockRejectedValueOnce(new ApiError(403, 'Forbidden'));

    const summary = await syncQueue(scope);

    expect(summary.failed).toBe(1);
    const updated = await getDraft(draft.id);
    expect(updated?.sync_status).toBe('REQUIRES_REVIEW');
    expect(updated?.last_error).toBe('Ya no tienes acceso a este territorio. Este registro requiere revisión.');
  });

  it('marks a network failure as a friendly, non-raw sync error', async () => {
    const scope = scopeFor('sync-network');
    const draft = await createDraft(scope, 'ACTIVITY', 41, { title: 'Red caída' }, 'sync-network-client');
    await enqueue(scope, draft.id, 'ACTIVITY');
    mockedApiRequest.mockRejectedValueOnce(new TypeError('Failed to fetch'));

    const summary = await syncQueue(scope);

    expect(summary.failed).toBe(1);
    const updated = await getDraft(draft.id);
    expect(updated?.sync_status).toBe('ERROR');
    expect(updated?.last_error).toBe('No fue posible sincronizar este registro.');
    expect(updated?.last_error).not.toContain('Failed to fetch');
  });

  it('syncs an activity before a need linked to it, resolving the real server id', async () => {
    const scope = scopeFor('sync-order');
    const activityDraft = await createDraft(scope, 'ACTIVITY', 41, { title: 'Actividad padre' }, 'sync-order-activity');
    const needDraft = await createDraft(
      scope,
      'NEED',
      41,
      { title: 'Necesidad hija', _local_activity_draft_id: activityDraft.id },
      'sync-order-need',
    );
    await enqueue(scope, needDraft.id, 'NEED');
    await enqueue(scope, activityDraft.id, 'ACTIVITY');
    mockedApiRequest.mockResolvedValueOnce({ id: 'server-activity-parent' });
    mockedApiRequest.mockResolvedValueOnce({ id: 'server-need-child' });

    const summary = await syncQueue(scope);

    expect(summary.synced).toBe(2);
    const needUrl = mockedApiRequest.mock.calls[1][0] as string;
    expect(needUrl).toContain('/activities/server-activity-parent/needs');
  });

  it('uploads a pending attachment once its activity has a real server id, and marks it SYNCED', async () => {
    const scope = scopeFor('sync-attachment-success');
    const draft = await createDraft(scope, 'ACTIVITY', 41, { title: 'Con evidencia' }, 'sync-attachment-success-client');
    await enqueue(scope, draft.id, 'ACTIVITY');
    const attachment = fakeAttachment({ draft_id: draft.id });
    mockedListAttachmentsForOwner.mockResolvedValue([attachment]);
    mockedApiRequest.mockResolvedValueOnce({ id: 'server-activity-evidence' });
    mockedApiRequest.mockResolvedValueOnce({ id: 'server-evidence-1' });

    const summary = await syncQueue(scope);

    expect(summary.synced).toBe(1);
    expect(summary.attachmentsSynced).toBe(1);
    expect(mockedSetAttachmentStatus).toHaveBeenCalledWith(
      attachment.id,
      'SYNCED',
      expect.objectContaining({ serverId: 'server-evidence-1' }),
    );
    const [uploadUrl, uploadInit] = mockedApiRequest.mock.calls[1];
    expect(uploadUrl).toBe('/campaigns/sync-attachment-success/activities/server-activity-evidence/evidence/upload');
    expect((uploadInit as RequestInit).body).toBeInstanceOf(FormData);
  });

  it('keeps an attachment PENDING (not FAILED) when the activity is not approved yet, for a later retry', async () => {
    const scope = scopeFor('sync-attachment-not-approved');
    const draft = await createDraft(scope, 'ACTIVITY', 41, { title: 'Sin aprobar' }, 'sync-attachment-pending-client');
    await enqueue(scope, draft.id, 'ACTIVITY');
    const attachment = fakeAttachment({ draft_id: draft.id });
    mockedListAttachmentsForOwner.mockResolvedValue([attachment]);
    mockedApiRequest.mockResolvedValueOnce({ id: 'server-activity-not-approved' });
    mockedApiRequest.mockRejectedValueOnce(new ApiError(400, 'Bad Request'));

    const summary = await syncQueue(scope);

    expect(summary.attachmentsPending).toBe(1);
    expect(summary.attachmentsFailed).toBe(0);
    expect(mockedSetAttachmentStatus).toHaveBeenCalledWith(
      attachment.id,
      'PENDING',
      expect.objectContaining({ lastError: 'Se subirá cuando la actividad esté aprobada.' }),
    );
  });

  it('marks an attachment REQUIRES_REVIEW on 403 without downgrading the already-synced activity draft', async () => {
    const scope = scopeFor('sync-attachment-403');
    const draft = await createDraft(scope, 'ACTIVITY', 41, { title: 'Acceso perdido' }, 'sync-attachment-403-client');
    await enqueue(scope, draft.id, 'ACTIVITY');
    const attachment = fakeAttachment({ draft_id: draft.id });
    mockedListAttachmentsForOwner.mockResolvedValue([attachment]);
    mockedApiRequest.mockResolvedValueOnce({ id: 'server-activity-403' });
    mockedApiRequest.mockRejectedValueOnce(new ApiError(403, 'Forbidden'));

    await syncQueue(scope);

    expect(mockedSetAttachmentStatus).toHaveBeenCalledWith(
      attachment.id,
      'REQUIRES_REVIEW',
      expect.objectContaining({ lastError: expect.stringContaining('Ya no tienes acceso') }),
    );
    const updatedDraft = await getDraft(draft.id);
    expect(updatedDraft?.sync_status).toBe('SYNCED');
  });

  it('does not attempt to upload an attachment whose activity draft has not synced yet', async () => {
    const scope = scopeFor('sync-attachment-not-yet');
    const draft = await createDraft(scope, 'ACTIVITY', 41, { title: 'Aún local' }, 'sync-attachment-not-yet-client');
    // Deliberately not enqueued: the activity draft stays in DRAFT status.
    const attachment = fakeAttachment({ draft_id: draft.id });
    mockedListAttachmentsForOwner.mockResolvedValue([attachment]);

    const summary = await syncQueue(scope);

    expect(mockedApiRequest).not.toHaveBeenCalled();
    expect(summary.attachmentsPending).toBe(1);
  });
});
