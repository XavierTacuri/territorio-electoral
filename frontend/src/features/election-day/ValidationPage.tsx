import { Alert } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { EmptyState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import type { ElectionDayValidationStatus } from './types';

// Fase 1 (§14): esta pantalla solo queda preparada — autorización por
// asignación ACT_VALIDATOR y una cola siempre vacía. El modelo de actas
// llega en Fase 2.
export default function ValidationPage() {
  const { campaignId = '' } = useParams();

  const status = useQuery({
    queryKey: ['election-day-validation', campaignId],
    queryFn: () =>
      apiRequest<ElectionDayValidationStatus>(`/campaigns/${campaignId}/election-day/validation`),
    retry: false,
  });

  if (status.isLoading) return <LoadingSkeleton />;

  if (status.isError) {
    const forbidden = status.error instanceof ApiError && status.error.status === 403;
    return (
      <>
        <PageHeader title="Validación de actas" />
        <Alert severity={forbidden ? 'warning' : 'error'}>
          {forbidden
            ? 'No tienes una asignación de validador de actas en esta jornada.'
            : 'No fue posible cargar la validación de actas.'}
        </Alert>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Validación de actas"
        description="Cola de revisión de actas de la jornada electoral."
      />
      <EmptyState
        title="No existen actas pendientes de revisión."
        detail="Este módulo se ampliará en una fase posterior con el modelo formal de actas."
      />
    </>
  );
}
