import { useEffect, useState } from 'react';
import { onQueueChanged } from './offlineEvents';
import { countPending } from './syncQueueRepository';
import type { OwnerScope } from './types';

// Best-effort: only counts the current campaign context (there is no single
// "all campaigns" view in this app), which is enough for the logout warning
// this backs. A missing organization_id/campaign_id yields 0, never a
// blocking false positive. Recomputes whenever the queue changes anywhere in
// the app (e.g. a draft was queued on a different page) via onQueueChanged —
// IndexedDB has no native subscription, so a fixed scope alone would go
// stale the moment something outside this hook mutated the queue.
export function usePendingSyncCount(scope: OwnerScope | null): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    if (!scope || !scope.organization_id || !scope.campaign_id) {
      setCount(0);
      return;
    }
    const refresh = () => {
      void countPending(scope).then((value) => {
        if (!cancelled) setCount(value);
      });
    };
    refresh();
    const unsubscribe = onQueueChanged(refresh);
    return () => {
      cancelled = true;
      unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope?.user_id, scope?.organization_id, scope?.campaign_id]);
  return count;
}
