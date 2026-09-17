import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import type { ElectionDayAssignment, ElectionDayOperation } from './types';

// "Mi Jornada" only belongs in the sidebar while there is something for the
// user to do there: an ACTIVE ElectionDayOperation for the campaign and a
// valid (non-replaced) ElectionDayAssignment for the current user.
export function useMyElectionDayNavVisibility(campaignId: string | null | undefined) {
  const operation = useQuery({
    queryKey: ['campaign', campaignId, 'election-day', 'operation', 'nav'],
    queryFn: () =>
      apiRequest<ElectionDayOperation>(`/campaigns/${campaignId}/election-day/operation`),
    enabled: !!campaignId,
    retry: false,
  });
  const assignment = useQuery({
    queryKey: ['campaign', campaignId, 'election-day', 'my-assignment', 'nav'],
    queryFn: () =>
      apiRequest<ElectionDayAssignment | null>(
        `/campaigns/${campaignId}/election-day/my-assignment`,
      ),
    enabled: !!campaignId,
    retry: false,
  });
  return operation.data?.status === 'ACTIVE' && !!assignment.data;
}
