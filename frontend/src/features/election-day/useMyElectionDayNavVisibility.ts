import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import type { ElectionDayAssignment } from './types';

// "Mi Jornada"/"Validación de actas" solo pertenecen al menú lateral mientras
// el usuario tiene una ElectionDayAssignment activa del tipo correspondiente
// (§12) — nunca por rol de campaña. Cualquier miembro de campaña puede,
// legítimamente, tener ambas asignaciones a la vez.
export function useMyElectionDayNavVisibility(campaignId: string | null | undefined) {
  const assignments = useQuery({
    queryKey: ['campaign', campaignId, 'election-day', 'my-assignments', 'nav'],
    queryFn: () =>
      apiRequest<ElectionDayAssignment[]>(`/campaigns/${campaignId}/election-day/my-assignments`),
    enabled: !!campaignId,
    retry: false,
  });
  const items = assignments.data ?? [];
  return {
    delegateVisible: items.some((a) => a.assignment_role === 'POLLING_PLACE_DELEGATE'),
    validationVisible: items.some((a) => a.assignment_role === 'ACT_VALIDATOR'),
  };
}
