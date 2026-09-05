import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';

type AlertSummary = { by_severity: { severity: string; count: number }[] };

// Deliberately excludes INFO severity: a badge that counts purely informational
// alerts (e.g. "nueva versión de datos disponible") would just be noise, per
// the product requirement that only WARNING/CRITICAL drive the bell count.
export function useAlertBadgeCount(campaignId: string | null | undefined) {
  const query = useQuery({
    queryKey: ['campaign', campaignId, 'alerts-summary-badge'],
    queryFn: () => apiRequest<AlertSummary>(`/campaigns/${campaignId}/alerts/summary`),
    enabled: !!campaignId,
    refetchInterval: 5 * 60 * 1000,
    retry: false,
  });
  return (query.data?.by_severity ?? [])
    .filter((x) => x.severity !== 'INFO')
    .reduce((total, x) => total + x.count, 0);
}
