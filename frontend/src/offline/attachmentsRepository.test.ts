import { describe, expect, it } from 'vitest';
import {
  addPendingAttachment,
  listAttachments,
  listAttachmentsForOwner,
  removeAttachment,
  setAttachmentStatus,
} from './attachmentsRepository';
import { createDraft } from './draftsRepository';
import type { OwnerScope } from './types';

const userA: OwnerScope = {
  user_id: 'attach-user-a',
  organization_id: 'org-1',
  campaign_id: 'campaign-attach',
};
const userB: OwnerScope = {
  user_id: 'attach-user-b',
  organization_id: 'org-1',
  campaign_id: 'campaign-attach',
};

function jpegFile(name = 'foto.jpg') {
  return new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 0])], name, { type: 'image/jpeg' });
}

describe('attachmentsRepository', () => {
  it('rejects a disallowed MIME type before ever touching IndexedDB', async () => {
    const draft = await createDraft(userA, 'ACTIVITY', 41, { title: 'A' }, 'attach-client-1');
    const badFile = new File([new Uint8Array([1, 2, 3])], 'archivo.exe', {
      type: 'application/x-msdownload',
    });
    const result = await addPendingAttachment(userA, draft.id, badFile, 'Evidencia');
    expect(result.error).toBeTruthy();
    expect(result.attachment).toBeUndefined();
    expect(await listAttachments(draft.id)).toHaveLength(0);
  });

  it('stores the real Blob (not base64) with a fresh client_generated_id per attachment', async () => {
    const draft = await createDraft(userA, 'ACTIVITY', 41, { title: 'A' }, 'attach-client-2');
    const { attachment } = await addPendingAttachment(
      userA,
      draft.id,
      jpegFile(),
      'Evidencia de campo',
    );
    expect(attachment).toBeDefined();
    expect(attachment!.blob).toBeInstanceOf(Blob);
    expect(attachment!.client_generated_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(attachment!.sync_status).toBe('PENDING');
  });

  it('isolates attachments between users on the same campaign', async () => {
    const draftA = await createDraft(userA, 'ACTIVITY', 41, { title: 'A' }, 'attach-client-iso-a');
    const draftB = await createDraft(userB, 'ACTIVITY', 41, { title: 'B' }, 'attach-client-iso-b');
    await addPendingAttachment(userA, draftA.id, jpegFile('a.jpg'), 'De A');
    await addPendingAttachment(userB, draftB.id, jpegFile('b.jpg'), 'De B');

    const forA = await listAttachmentsForOwner(userA);
    const forB = await listAttachmentsForOwner(userB);
    expect(forA.some((x) => x.title === 'De A')).toBe(true);
    expect(forA.some((x) => x.title === 'De B')).toBe(false);
    expect(forB.some((x) => x.title === 'De B')).toBe(true);
    expect(forB.some((x) => x.title === 'De A')).toBe(false);
  });

  it('updates sync status and clears it from listings after removal', async () => {
    const draft = await createDraft(userA, 'ACTIVITY', 41, { title: 'A' }, 'attach-client-status');
    const { attachment } = await addPendingAttachment(userA, draft.id, jpegFile(), 'Evidencia');
    await setAttachmentStatus(attachment!.id, 'SYNCED', { serverId: 'server-evidence-1' });
    const [current] = await listAttachments(draft.id);
    expect(current.sync_status).toBe('SYNCED');
    expect(current.server_id).toBe('server-evidence-1');

    await removeAttachment(attachment!.id);
    expect(await listAttachments(draft.id)).toHaveLength(0);
  });
});
