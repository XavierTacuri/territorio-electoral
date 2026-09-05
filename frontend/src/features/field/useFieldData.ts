import { useCallback, useEffect, useState } from 'react';
import { listAttachmentsForOwner } from '../../offline/attachmentsRepository';
import { listDrafts } from '../../offline/draftsRepository';
import { onQueueChanged } from '../../offline/offlineEvents';
import { listQueue } from '../../offline/syncQueueRepository';
import {
  ownerKey,
  type OfflineDraft,
  type OwnerScope,
  type PendingAttachment,
  type SyncQueueItem,
} from '../../offline/types';

export function useFieldData(scope: OwnerScope | null) {
  const [drafts, setDrafts] = useState<OfflineDraft[]>([]);
  const [queue, setQueue] = useState<SyncQueueItem[]>([]);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [refreshToken, setRefreshToken] = useState(0);
  const refresh = useCallback(() => setRefreshToken((n) => n + 1), []);
  const scopeKey = scope ? ownerKey(scope) : null;

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!scope) {
        setDrafts([]);
        setQueue([]);
        setAttachments([]);
        return;
      }
      const [d, q, a] = await Promise.all([
        listDrafts(scope),
        listQueue(scope),
        listAttachmentsForOwner(scope),
      ]);
      if (!cancelled) {
        setDrafts(d);
        setQueue(q);
        setAttachments(a);
      }
    }
    void load();
    const unsubscribe = onQueueChanged(() => void load());
    return () => {
      cancelled = true;
      unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeKey, refreshToken]);

  const queuePendingCount = queue.filter(
    (item) => item.status === 'PENDING' || item.status === 'FAILED',
  ).length;
  const attachmentsPendingCount = attachments.filter(
    (item) => item.sync_status === 'PENDING' || item.sync_status === 'FAILED',
  ).length;
  // "Pendientes de sincronizar" combines queued records and attachments still
  // waiting to upload, so Sincronizar ahora stays enabled while either kind
  // has work left (e.g. only an attachment retry is outstanding).
  const pendingCount = queuePendingCount + attachmentsPendingCount;
  return {
    drafts,
    queue,
    attachments,
    pendingCount,
    queuePendingCount,
    attachmentsPendingCount,
    refresh,
  };
}
