import { describe, expect, it } from 'vitest';
import { createDraft } from './draftsRepository';
import {
  countPending,
  enqueue,
  listQueue,
  removeFromQueue,
  setQueueStatus,
} from './syncQueueRepository';
import type { OwnerScope } from './types';

const scope: OwnerScope = {
  user_id: 'queue-user',
  organization_id: 'org-1',
  campaign_id: 'campaign-queue',
};

describe('syncQueueRepository', () => {
  it('enqueues a draft once and counts it as pending', async () => {
    const draft = await createDraft(scope, 'ACTIVITY', 41, { title: 'Q1' }, 'queue-client-1');
    await enqueue(scope, draft.id, 'ACTIVITY');
    const again = await enqueue(scope, draft.id, 'ACTIVITY');
    const items = await listQueue(scope);
    expect(items.filter((i) => i.id === draft.id)).toHaveLength(1);
    expect(again.status).toBe('PENDING');
    expect(await countPending(scope)).toBeGreaterThanOrEqual(1);
  });

  it('re-enqueues a failed item back to pending without duplicating', async () => {
    const draft = await createDraft(scope, 'NEED', 41, { title: 'Q2' }, 'queue-client-2');
    await enqueue(scope, draft.id, 'NEED');
    await setQueueStatus(draft.id, 'FAILED', 'boom');
    const retried = await enqueue(scope, draft.id, 'NEED');
    expect(retried.status).toBe('PENDING');
    const items = await listQueue(scope);
    expect(items.filter((i) => i.id === draft.id)).toHaveLength(1);
  });

  it('does not re-enqueue an already synced item', async () => {
    const draft = await createDraft(scope, 'NEED', 41, { title: 'Q3' }, 'queue-client-3');
    await enqueue(scope, draft.id, 'NEED');
    await setQueueStatus(draft.id, 'SYNCED');
    const attempt = await enqueue(scope, draft.id, 'NEED');
    expect(attempt.status).toBe('SYNCED');
  });

  it('removes items from the queue', async () => {
    const draft = await createDraft(scope, 'NEED', 41, { title: 'Q4' }, 'queue-client-4');
    await enqueue(scope, draft.id, 'NEED');
    await removeFromQueue(draft.id);
    const items = await listQueue(scope);
    expect(items.some((i) => i.id === draft.id)).toBe(false);
  });
});
