import { useEffect, useState } from 'react';
import { apiRequest } from '../../api/client';
import { cacheCatalog, getCachedCatalog } from '../../offline/catalogRepository';
import { useOnlineStatus } from '../../offline/useOnlineStatus';

export function useOfflineCatalog(name: 'activity-types' | 'need-categories') {
  const online = useOnlineStatus();
  const [items, setItems] = useState<{ code: string; name: string }[]>([]);
  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (online) {
        try {
          const result = await apiRequest<{ code: string; name: string }[]>(`/${name}`);
          await cacheCatalog(name, result);
          if (!cancelled) setItems(result);
          return;
        } catch {
          // fall through to cache
        }
      }
      const cached = await getCachedCatalog(name);
      if (!cancelled) setItems(cached?.items ?? []);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [name, online]);
  return items;
}
