import { describe, expect, it } from 'vitest';
import { createDraft, deleteDraft, getDraft, listDrafts, pruneSyncedDrafts, setDraftStatus, updateDraftPayload } from './draftsRepository';
import type { OwnerScope } from './types';

const userA: OwnerScope = { user_id: 'user-a', organization_id: 'org-1', campaign_id: 'campaign-1' };
const userB: OwnerScope = { user_id: 'user-b', organization_id: 'org-1', campaign_id: 'campaign-1' };
const campaignB: OwnerScope = { user_id: 'user-a', organization_id: 'org-1', campaign_id: 'campaign-2' };

describe('draftsRepository', () => {
  it('creates a draft with a stable id derived from entity type and client_generated_id', async () => {
    const draft = await createDraft(userA, 'ACTIVITY', 41, { title: 'Asamblea' }, 'client-id-1');
    expect(draft.id).toBe('ACTIVITY:client-id-1');
    expect(draft.sync_status).toBe('DRAFT');
    const fetched = await getDraft(draft.id);
    expect(fetched?.payload.title).toBe('Asamblea');
  });

  it('updates payload and status independently, preserving the rest', async () => {
    const draft = await createDraft(userA, 'NEED', 41, { title: 'Necesidad v1' }, 'client-id-2');
    await updateDraftPayload(draft.id, { title: 'Necesidad v2' });
    const afterUpdate = await getDraft(draft.id);
    expect(afterUpdate?.payload.title).toBe('Necesidad v2');
    expect(afterUpdate?.sync_status).toBe('DRAFT');

    await setDraftStatus(draft.id, 'SYNCED', { serverId: 'server-123' });
    const afterSync = await getDraft(draft.id);
    expect(afterSync?.sync_status).toBe('SYNCED');
    expect(afterSync?.server_id).toBe('server-123');
    expect(afterSync?.payload.title).toBe('Necesidad v2');
  });

  it('isolates drafts between users on the same campaign', async () => {
    await createDraft(userA, 'ACTIVITY', 41, { title: 'Draft A' }, 'client-id-iso-a');
    await createDraft(userB, 'ACTIVITY', 41, { title: 'Draft B' }, 'client-id-iso-b');
    const forA = await listDrafts(userA);
    const forB = await listDrafts(userB);
    expect(forA.some((d) => d.payload.title === 'Draft A')).toBe(true);
    expect(forA.some((d) => d.payload.title === 'Draft B')).toBe(false);
    expect(forB.some((d) => d.payload.title === 'Draft B')).toBe(true);
    expect(forB.some((d) => d.payload.title === 'Draft A')).toBe(false);
  });

  it('isolates drafts between campaigns for the same user', async () => {
    await createDraft(userA, 'ACTIVITY', 41, { title: 'Campaign 1 draft' }, 'client-id-camp-1');
    await createDraft(campaignB, 'ACTIVITY', 41, { title: 'Campaign 2 draft' }, 'client-id-camp-2');
    const forCampaign1 = await listDrafts(userA);
    const forCampaign2 = await listDrafts(campaignB);
    expect(forCampaign1.some((d) => d.payload.title === 'Campaign 2 draft')).toBe(false);
    expect(forCampaign2.some((d) => d.payload.title === 'Campaign 1 draft')).toBe(false);
  });

  it('refuses to delete a draft belonging to a different owner', async () => {
    const draft = await createDraft(userA, 'NEED', 41, { title: 'Protected' }, 'client-id-protect');
    const deletedByWrongOwner = await deleteDraft(draft.id, userB);
    expect(deletedByWrongOwner).toBe(false);
    expect(await getDraft(draft.id)).toBeDefined();
    const deletedByOwner = await deleteDraft(draft.id, userA);
    expect(deletedByOwner).toBe(true);
    expect(await getDraft(draft.id)).toBeUndefined();
  });

  it('prunes only synced drafts, keeping failed/requires-review ones', async () => {
    const scope: OwnerScope = { user_id: 'prune-user', organization_id: 'org-1', campaign_id: 'campaign-prune' };
    const synced = await createDraft(scope, 'ACTIVITY', 41, { title: 'Synced' }, 'prune-synced');
    const failed = await createDraft(scope, 'ACTIVITY', 41, { title: 'Failed' }, 'prune-failed');
    await setDraftStatus(synced.id, 'SYNCED');
    await setDraftStatus(failed.id, 'ERROR', { lastError: 'network' });
    const removed = await pruneSyncedDrafts(scope);
    expect(removed).toBe(1);
    expect(await getDraft(synced.id)).toBeUndefined();
    expect(await getDraft(failed.id)).toBeDefined();
  });
});
