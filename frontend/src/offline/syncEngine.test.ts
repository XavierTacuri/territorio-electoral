import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
  return {
    ...actual,
    listAttachmentsForOwner: vi.fn(),
    setAttachmentStatus: vi.fn(),
    listAttachments: vi.fn(),
  };
});
import {
  listAttachments,
  listAttachmentsForOwner,
  setAttachmentStatus,
} from './attachmentsRepository';

const mockedApiRequest = vi.mocked(apiRequest);
const mockedListAttachmentsForOwner = vi.mocked(listAttachmentsForOwner);
const mockedSetAttachmentStatus = vi.mocked(setAttachmentStatus);
const mockedListAttachments = vi.mocked(listAttachments);

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
  mockedListAttachments.mockReset().mockResolvedValue([]);
});

describe('syncEngine.syncQueue', () => {
  it('syncs a successful activity and marks the draft SYNCED with the server id', async () => {
    const scope = scopeFor('sync-success');
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Asamblea' },
      'sync-success-client',
    );
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
    const draft = await createDraft(
      scope,
      'NEED',
      41,
      { title: 'Necesidad' },
      'sync-double-client',
    );
    await enqueue(scope, draft.id, 'NEED');
    mockedApiRequest.mockResolvedValueOnce({ id: 'server-need-1' });

    await syncQueue(scope);
    const secondPass = await syncQueue(scope);

    expect(mockedApiRequest).toHaveBeenCalledTimes(1);
    expect(secondPass.synced).toBe(0);
  });

  it('marks a 403 as requiring review with a friendly message, never the raw error', async () => {
    const scope = scopeFor('sync-403');
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Sin acceso' },
      'sync-403-client',
    );
    await enqueue(scope, draft.id, 'ACTIVITY');
    mockedApiRequest.mockRejectedValueOnce(new ApiError(403, 'Forbidden'));

    const summary = await syncQueue(scope);

    expect(summary.failed).toBe(1);
    const updated = await getDraft(draft.id);
    expect(updated?.sync_status).toBe('REQUIRES_REVIEW');
    expect(updated?.last_error).toBe(
      'Ya no tienes acceso a este territorio. Este registro requiere revisión.',
    );
  });

  it('marks a network failure as a friendly, non-raw sync error', async () => {
    const scope = scopeFor('sync-network');
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Red caída' },
      'sync-network-client',
    );
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
    const activityDraft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Actividad padre' },
      'sync-order-activity',
    );
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
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Con evidencia' },
      'sync-attachment-success-client',
    );
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
    expect(uploadUrl).toBe(
      '/campaigns/sync-attachment-success/activities/server-activity-evidence/evidence/upload',
    );
    expect((uploadInit as RequestInit).body).toBeInstanceOf(FormData);
  });

  it('keeps an attachment PENDING (not FAILED) when the activity is not approved yet, for a later retry', async () => {
    const scope = scopeFor('sync-attachment-not-approved');
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Sin aprobar' },
      'sync-attachment-pending-client',
    );
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
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Acceso perdido' },
      'sync-attachment-403-client',
    );
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
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Aún local' },
      'sync-attachment-not-yet-client',
    );
    // Deliberately not enqueued: the activity draft stays in DRAFT status.
    const attachment = fakeAttachment({ draft_id: draft.id });
    mockedListAttachmentsForOwner.mockResolvedValue([attachment]);

    const summary = await syncQueue(scope);

    expect(mockedApiRequest).not.toHaveBeenCalled();
    expect(summary.attachmentsPending).toBe(1);
  });
});

describe('syncEngine.syncQueue — política de reintentos (Fase 4B)', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('reintenta tras una falla de red (TypeError) y termina SYNCED sin exponer el error crudo', async () => {
    const scope = scopeFor('retry-network');
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Reintento de red' },
      'retry-network-client',
    );
    await enqueue(scope, draft.id, 'ACTIVITY');
    mockedApiRequest
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce({ id: 'server-activity-retried' });

    // Los timers se falsean recién aquí, ya escrito todo el setup de
    // IndexedDB (createDraft/enqueue): fake-indexeddb resuelve sus
    // transacciones vía un timer real, así que falsearlos antes de que ese
    // setup termine los deja esperando un tick que nunca llega.
    vi.useFakeTimers();
    const pending = syncQueue(scope);
    await vi.runAllTimersAsync();
    const summary = await pending;
    vi.useRealTimers();

    expect(summary.synced).toBe(1);
    expect(summary.failed).toBe(0);
    expect(mockedApiRequest).toHaveBeenCalledTimes(3);
    const updated = await getDraft(draft.id);
    expect(updated?.sync_status).toBe('SYNCED');
    expect(updated?.server_id).toBe('server-activity-retried');
    // La política de reintentos siempre reenvía la MISMA petición (mismo
    // client_generated_id) — el UNIQUE/idempotencia del backend es lo que
    // garantiza que esto nunca duplica el registro en el servidor.
    const bodies = mockedApiRequest.mock.calls.map(
      (call) => JSON.parse((call[1] as RequestInit).body as string).client_generated_id,
    );
    expect(new Set(bodies)).toEqual(new Set(['retry-network-client']));
  });

  it.each([502, 503, 504])('reintenta un %i transitorio y termina SYNCED', async (status) => {
    const scope = scopeFor(`retry-${status}`);
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: `Reintento ${status}` },
      `retry-${status}-client`,
    );
    await enqueue(scope, draft.id, 'ACTIVITY');
    mockedApiRequest
      .mockRejectedValueOnce(new ApiError(status, 'Service error'))
      .mockResolvedValueOnce({ id: `server-activity-${status}` });

    vi.useFakeTimers();
    const pending = syncQueue(scope);
    await vi.runAllTimersAsync();
    const summary = await pending;

    expect(summary.synced).toBe(1);
    expect(mockedApiRequest).toHaveBeenCalledTimes(2);
  });

  it('honra Retry-After en un 429 antes de reintentar', async () => {
    const scope = scopeFor('retry-429');
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Reintento 429' },
      'retry-429-client',
    );
    await enqueue(scope, draft.id, 'ACTIVITY');
    mockedApiRequest
      .mockRejectedValueOnce(new ApiError(429, 'Too many requests', undefined, 2))
      .mockResolvedValueOnce({ id: 'server-activity-429' });

    vi.useFakeTimers();
    const pending = syncQueue(scope);
    // Antes de que transcurran los 2s indicados por Retry-After, el segundo
    // intento no debe haber ocurrido todavía.
    await vi.advanceTimersByTimeAsync(1000);
    expect(mockedApiRequest).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1500);
    const summary = await pending;

    expect(summary.synced).toBe(1);
    expect(mockedApiRequest).toHaveBeenCalledTimes(2);
  });

  it('agota los reintentos ante fallas 503 persistentes y termina en ERROR, no en un ciclo infinito', async () => {
    const scope = scopeFor('retry-exhausted');
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Nunca se recupera' },
      'retry-exhausted-client',
    );
    await enqueue(scope, draft.id, 'ACTIVITY');
    mockedApiRequest.mockRejectedValue(new ApiError(503, 'Service unavailable'));

    vi.useFakeTimers();
    const pending = syncQueue(scope);
    await vi.runAllTimersAsync();
    const summary = await pending;
    vi.useRealTimers();

    expect(summary.synced).toBe(0);
    expect(summary.failed).toBe(1);
    // MAX_SYNC_ATTEMPTS = 5 intentos, nunca más.
    expect(mockedApiRequest).toHaveBeenCalledTimes(5);
    const updated = await getDraft(draft.id);
    expect(updated?.sync_status).toBe('ERROR');
  });

  it.each([400, 401, 403, 409, 422])(
    'NO reintenta un %i — es una respuesta definitiva del servidor',
    async (status) => {
      const scope = scopeFor(`no-retry-${status}`);
      const draft = await createDraft(
        scope,
        'ACTIVITY',
        41,
        { title: `Sin reintento ${status}` },
        `no-retry-${status}-client`,
      );
      await enqueue(scope, draft.id, 'ACTIVITY');
      mockedApiRequest.mockRejectedValueOnce(new ApiError(status, 'Definitive error'));

      const summary = await syncQueue(scope);

      expect(summary.synced).toBe(0);
      expect(mockedApiRequest).toHaveBeenCalledTimes(1);
    },
  );

  it('preserva el draft y su client_generated_id en IndexedDB tras una sincronización con reintentos', async () => {
    const scope = scopeFor('retry-preserve-draft');
    const draft = await createDraft(
      scope,
      'ACTIVITY',
      41,
      { title: 'Se conserva' },
      'retry-preserve-draft-client',
    );
    await enqueue(scope, draft.id, 'ACTIVITY');
    mockedApiRequest
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce({ id: 'server-activity-preserved' });

    vi.useFakeTimers();
    const pending = syncQueue(scope);
    await vi.runAllTimersAsync();
    await pending;
    vi.useRealTimers();

    // Simula "recargar la página": una lectura fresca del mismo id de
    // IndexedDB, no un objeto en memoria retenido por el motor de sync.
    const reloaded = await getDraft(draft.id);
    expect(reloaded?.id).toBe(draft.id);
    expect(reloaded?.client_generated_id).toBe('retry-preserve-draft-client');
    expect(reloaded?.sync_status).toBe('SYNCED');
    expect(reloaded?.server_id).toBe('server-activity-preserved');
  });
});

describe('syncEngine.syncQueue — actas electorales (Fase 2)', () => {
  it('registra un acta, sube su evidencia y la envía en una sola pasada', async () => {
    const scope = scopeFor('sync-act');
    const draft = await createDraft(
      scope,
      'ELECTION_ACT_SUBMIT',
      0,
      {
        is_correction: false,
        polling_place_id: 'place-1',
        electoral_board_id: 'board-1',
        electoral_contest_id: 'contest-1',
        blank_ballots: 1,
        null_ballots: 1,
        valid_ballots: 10,
        ballots_counted: 12,
        results: [{ electoral_candidate_id: 'cand-1', votes: 10 }],
      },
      'sync-act-client',
    );
    mockedListAttachments.mockResolvedValueOnce([fakeAttachment({ draft_id: draft.id })]);
    await enqueue(scope, draft.id, 'ELECTION_ACT_SUBMIT');
    mockedApiRequest.mockResolvedValueOnce({
      act: { id: 'act-server-1' },
      revision: { id: 'rev-server-1', status: 'DRAFT' },
    });
    // provider=local in this environment: upload-intent authorizes API_PROXY.
    mockedApiRequest.mockResolvedValueOnce({
      mode: 'API_PROXY',
      url: null,
      fields: null,
      upload_token: null,
      expires_at: null,
      max_file_mb: 15,
      allowed_mime_types: ['image/jpeg', 'image/png'],
      evidence_id: null,
    });
    mockedApiRequest.mockResolvedValueOnce({ id: 'evidence-server-1' });
    mockedApiRequest.mockResolvedValueOnce(undefined);

    const summary = await syncQueue(scope);

    const updated = await getDraft(draft.id);
    expect(summary.synced).toBe(1);
    expect(updated?.sync_status).toBe('SYNCED');
    expect(updated?.server_id).toBe('act-server-1');

    expect(mockedApiRequest.mock.calls[0][0]).toBe('/campaigns/sync-act/election-day/acts/drafts');
    expect(mockedApiRequest.mock.calls[1][0]).toBe(
      '/campaigns/sync-act/election-day/acts/act-server-1/revisions/rev-server-1/evidence/upload-intent',
    );
    const [evidenceUrl, evidenceInit] = mockedApiRequest.mock.calls[2];
    expect(evidenceUrl).toBe(
      '/campaigns/sync-act/election-day/acts/act-server-1/revisions/rev-server-1/evidence',
    );
    expect((evidenceInit as RequestInit).body).toBeInstanceOf(FormData);
    expect(mockedApiRequest.mock.calls[3][0]).toBe(
      '/campaigns/sync-act/election-day/acts/act-server-1/revisions/rev-server-1/submit',
    );
  });

  function presignedIntent(overrides: Partial<Record<string, unknown>> = {}) {
    return {
      mode: 'PRESIGNED_S3',
      url: 'https://test-bucket.s3.amazonaws.com/',
      fields: { key: 'evidence/pending/abc.jpg', 'Content-Type': 'image/jpeg' },
      upload_token: 'opaque-upload-token',
      expires_at: '2026-01-01T00:05:00Z',
      max_file_mb: 15,
      allowed_mime_types: ['image/jpeg', 'image/png'],
      evidence_id: null,
      ...overrides,
    };
  }

  it('provider=s3: sube la fotografía directo a la URL firmada (no vía apiRequest) y confirma con /complete', async () => {
    const scope = scopeFor('sync-act-s3');
    const draft = await createDraft(
      scope,
      'ELECTION_ACT_SUBMIT',
      0,
      {
        is_correction: false,
        polling_place_id: 'place-1',
        electoral_board_id: 'board-1',
        electoral_contest_id: 'contest-1',
        blank_ballots: 0,
        null_ballots: 0,
        valid_ballots: 5,
        ballots_counted: 5,
        results: [],
      },
      'sync-act-s3-client',
    );
    mockedListAttachments.mockResolvedValueOnce([fakeAttachment({ draft_id: draft.id })]);
    await enqueue(scope, draft.id, 'ELECTION_ACT_SUBMIT');
    mockedApiRequest.mockResolvedValueOnce({
      act: { id: 'act-server-2' },
      revision: { id: 'rev-server-2', status: 'DRAFT' },
    });
    mockedApiRequest.mockResolvedValueOnce(presignedIntent());
    mockedApiRequest.mockResolvedValueOnce({ id: 'evidence-server-2' });
    mockedApiRequest.mockResolvedValueOnce(undefined);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);

    const summary = await syncQueue(scope);

    expect(summary.synced).toBe(1);
    // The presigned POST goes straight to S3 via fetch, never apiRequest —
    // no Authorization header, no /api/v1 base path.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [s3Url, s3Init] = fetchMock.mock.calls[0];
    expect(s3Url).toBe('https://test-bucket.s3.amazonaws.com/');
    expect((s3Init as RequestInit).body).toBeInstanceOf(FormData);
    expect((s3Init as RequestInit).headers).toBeUndefined();
    // Then /complete carries only the opaque token, never the S3 URL/fields.
    const [completeUrl, completeInit] = mockedApiRequest.mock.calls[2];
    expect(completeUrl).toBe(
      '/campaigns/sync-act-s3/election-day/acts/act-server-2/revisions/rev-server-2/evidence/complete',
    );
    expect(JSON.parse((completeInit as RequestInit).body as string)).toEqual({
      upload_token: 'opaque-upload-token',
    });
    vi.unstubAllGlobals();
  });

  it('provider=s3: si el presigned expira a mitad de subida, pide un intent nuevo y reintenta una vez', async () => {
    const scope = scopeFor('sync-act-s3-retry');
    const draft = await createDraft(
      scope,
      'ELECTION_ACT_SUBMIT',
      0,
      {
        is_correction: false,
        polling_place_id: 'place-1',
        electoral_board_id: 'board-1',
        electoral_contest_id: 'contest-1',
        blank_ballots: 0,
        null_ballots: 0,
        valid_ballots: 5,
        ballots_counted: 5,
        results: [],
      },
      'sync-act-s3-retry-client',
    );
    mockedListAttachments.mockResolvedValueOnce([fakeAttachment({ draft_id: draft.id })]);
    await enqueue(scope, draft.id, 'ELECTION_ACT_SUBMIT');
    mockedApiRequest.mockResolvedValueOnce({
      act: { id: 'act-server-3' },
      revision: { id: 'rev-server-3', status: 'DRAFT' },
    });
    mockedApiRequest.mockResolvedValueOnce(presignedIntent({ upload_token: 'expired-token' }));
    mockedApiRequest.mockResolvedValueOnce(presignedIntent({ upload_token: 'fresh-token' }));
    mockedApiRequest.mockResolvedValueOnce({ id: 'evidence-server-3' });
    mockedApiRequest.mockResolvedValueOnce(undefined);
    // First S3 POST (the expired policy) fails; the retry's succeeds.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 403 })
      .mockResolvedValueOnce({ ok: true });
    vi.stubGlobal('fetch', fetchMock);

    const summary = await syncQueue(scope);

    expect(summary.synced).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // Same client_generated_id both times — the server never sees a
    // duplicate even though two intents were issued (§16/§23/§24).
    const firstIntentBody = JSON.parse(mockedApiRequest.mock.calls[1][1]!.body as string);
    const secondIntentBody = JSON.parse(mockedApiRequest.mock.calls[2][1]!.body as string);
    expect(firstIntentBody.client_generated_id).toBe(secondIntentBody.client_generated_id);
    const [completeUrl, completeInit] = mockedApiRequest.mock.calls[3];
    expect(completeUrl).toContain('/evidence/complete');
    expect(JSON.parse((completeInit as RequestInit).body as string).upload_token).toBe(
      'fresh-token',
    );
    vi.unstubAllGlobals();
  });

  it('provider=s3: ALREADY_COMPLETED evita una nueva subida y usa la evidencia existente', async () => {
    const scope = scopeFor('sync-act-s3-already');
    const draft = await createDraft(
      scope,
      'ELECTION_ACT_SUBMIT',
      0,
      {
        is_correction: false,
        polling_place_id: 'place-1',
        electoral_board_id: 'board-1',
        electoral_contest_id: 'contest-1',
        blank_ballots: 0,
        null_ballots: 0,
        valid_ballots: 5,
        ballots_counted: 5,
        results: [],
      },
      'sync-act-s3-already-client',
    );
    mockedListAttachments.mockResolvedValueOnce([fakeAttachment({ draft_id: draft.id })]);
    await enqueue(scope, draft.id, 'ELECTION_ACT_SUBMIT');
    mockedApiRequest.mockResolvedValueOnce({
      act: { id: 'act-server-4' },
      revision: { id: 'rev-server-4', status: 'DRAFT' },
    });
    mockedApiRequest.mockResolvedValueOnce({
      mode: 'ALREADY_COMPLETED',
      url: null,
      fields: null,
      upload_token: null,
      expires_at: null,
      max_file_mb: 15,
      allowed_mime_types: ['image/jpeg', 'image/png'],
      evidence_id: 'evidence-existing',
    });
    mockedApiRequest.mockResolvedValueOnce(undefined);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const summary = await syncQueue(scope);

    expect(summary.synced).toBe(1);
    expect(fetchMock).not.toHaveBeenCalled();
    // No third call to a plain '.../evidence' or '.../evidence/complete' —
    // only intent then submit.
    expect(mockedApiRequest).toHaveBeenCalledTimes(3);
    vi.unstubAllGlobals();
  });

  it('no reenvía ni resube evidencia si la revisión ya llegó SUBMITTED (reintento idempotente)', async () => {
    const scope = scopeFor('sync-act-idempotent');
    const draft = await createDraft(
      scope,
      'ELECTION_ACT_SUBMIT',
      0,
      {
        is_correction: false,
        polling_place_id: 'place-1',
        electoral_board_id: 'board-1',
        electoral_contest_id: 'contest-1',
        blank_ballots: 0,
        null_ballots: 0,
        valid_ballots: 5,
        ballots_counted: 5,
        results: [],
      },
      'sync-act-idempotent-client',
    );
    await enqueue(scope, draft.id, 'ELECTION_ACT_SUBMIT');
    mockedApiRequest.mockResolvedValueOnce({
      act: { id: 'act-server-2' },
      revision: { id: 'rev-server-2', status: 'SUBMITTED' },
    });

    const summary = await syncQueue(scope);

    expect(summary.synced).toBe(1);
    expect(mockedApiRequest).toHaveBeenCalledTimes(1);
  });

  it('mapea un 409 de carrera de junta al mensaje específico de actas', async () => {
    const scope = scopeFor('sync-act-conflict');
    const draft = await createDraft(
      scope,
      'ELECTION_ACT_SUBMIT',
      0,
      {
        is_correction: false,
        polling_place_id: 'place-1',
        electoral_board_id: 'board-1',
        electoral_contest_id: 'contest-1',
        blank_ballots: 0,
        null_ballots: 0,
        valid_ballots: 5,
        ballots_counted: 5,
        results: [],
      },
      'sync-act-conflict-client',
    );
    await enqueue(scope, draft.id, 'ELECTION_ACT_SUBMIT');
    mockedApiRequest.mockRejectedValueOnce(new ApiError(409, 'Conflict'));

    const summary = await syncQueue(scope);

    expect(summary.conflicts).toBe(1);
    const updated = await getDraft(draft.id);
    expect(updated?.sync_status).toBe('REQUIRES_REVIEW');
    expect(updated?.last_error).toBe(
      'Ya existe un acta recibida para esta junta. Revisa antes de continuar.',
    );
  });
});
