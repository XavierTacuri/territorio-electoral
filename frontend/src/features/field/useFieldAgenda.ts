import { useEffect, useState } from 'react';
import { apiRequest } from '../../api/client';
import { cacheAgenda, getCachedAgenda } from '../../offline/agendaRepository';
import type { FieldAgendaItem, OwnerScope } from '../../offline/types';
import { useOnlineStatus } from '../../offline/useOnlineStatus';

type AgendaActivity = {
  id: string;
  title: string;
  activity_date: string;
  start_time: string | null;
  status: string;
  approval_status: string;
  parish_id: number;
  parish_name?: string | null;
};
type AgendaResponse = { activities: AgendaActivity[]; pending_approval: AgendaActivity[] };

export function useFieldAgenda(scope: OwnerScope | null) {
  const online = useOnlineStatus();
  const [items, setItems] = useState<FieldAgendaItem[]>([]);
  const [fromCache, setFromCache] = useState(false);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!scope) return;
      setLoading(true);
      if (online) {
        try {
          const data = await apiRequest<AgendaResponse>(`/campaigns/${scope.campaign_id}/operations/agenda`);
          const merged = [...data.activities, ...data.pending_approval].map(toFieldItem);
          await cacheAgenda(scope, merged);
          if (!cancelled) {
            setItems(merged);
            setFromCache(false);
            setFetchedAt(new Date().toISOString());
            setLoading(false);
          }
          return;
        } catch {
          // fall through to cache
        }
      }
      const cached = await getCachedAgenda(scope);
      if (!cancelled) {
        setItems(cached?.items ?? []);
        setFromCache(true);
        setFetchedAt(cached?.fetched_at ?? null);
        setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope?.campaign_id, scope?.user_id, online]);

  return { items, fromCache, fetchedAt, loading };
}

function toFieldItem(activity: AgendaActivity): FieldAgendaItem {
  return {
    id: activity.id,
    title: activity.title,
    activity_date: activity.activity_date,
    start_time: activity.start_time,
    status: activity.status,
    approval_status: activity.approval_status,
    parish_id: activity.parish_id,
    parish_name: activity.parish_name ?? null,
  };
}
