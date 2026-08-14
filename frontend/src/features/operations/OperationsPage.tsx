import { Alert, Box, Button, Card, CardContent, Grid, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import type { Activity, Commitment } from './types';

type Overview = {
  activities: { upcoming: number; pending_approval: number; completed: number };
  needs: { open: number; under_review: number; validated: number; critical_unassigned: number };
  commitments: { pending: number; in_progress: number; overdue: number; completed: number };
  coverage: {
    total_parishes: number;
    with_activities: number;
    with_needs: number;
    with_commitments: number;
  };
  can_approve: boolean;
};
type Agenda = { activities: Activity[]; pending_approval: Activity[]; commitments: Commitment[] };
const Metric = ({ label, value }: { label: string; value: number | string }) => (
  <Card variant="outlined">
    <CardContent>
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
      <Typography variant="h3">{value}</Typography>
    </CardContent>
  </Card>
);
export default function OperationsPage() {
  const { campaignId = '' } = useParams();
  const summary = useQuery({
    queryKey: ['operations-summary', campaignId],
    queryFn: () => apiRequest<Overview>(`/campaigns/${campaignId}/operations/summary`),
  });
  const agenda = useQuery({
    queryKey: ['operations-agenda', campaignId],
    queryFn: () => apiRequest<Agenda>(`/campaigns/${campaignId}/operations/agenda`),
  });
  if (summary.isLoading || agenda.isLoading) return <LoadingSkeleton />;
  if (summary.isError || agenda.isError || !summary.data || !agenda.data)
    return (
      <ErrorState
        retry={() => {
          void summary.refetch();
          void agenda.refetch();
        }}
      />
    );
  const s = summary.data,
    a = agenda.data,
    base = `/app/campaigns/${campaignId}`;
  return (
    <>
      <PageHeader
        title="Operación territorial"
        description="Gestión diaria, agenda y cobertura operacional de campaña."
        action={
          <Button component={RouterLink} to={`${base}/activities`} variant="contained">
            Crear actividad
          </Button>
        }
      />
      {s.can_approve && s.activities.pending_approval > 0 && (
        <Alert
          severity="info"
          sx={{ mb: 2 }}
          action={
            <Button component={RouterLink} to={`${base}/approvals`}>
              Ver aprobaciones
            </Button>
          }
        >
          {s.activities.pending_approval} actividades pendientes de aprobación.
        </Alert>
      )}
      <Typography component="h2" variant="h2" sx={{ mb: 2 }}>
        Resumen operacional
      </Typography>
      <Grid container spacing={2}>
        {[
          ['Actividades próximas', s.activities.upcoming],
          ['Pendientes de aprobación', s.activities.pending_approval],
          ['Actividades completadas', s.activities.completed],
          ['Necesidades abiertas', s.needs.open],
          ['En revisión', s.needs.under_review],
          ['Necesidades validadas', s.needs.validated],
          ['Críticas sin responsable', s.needs.critical_unassigned],
          ['Compromisos pendientes', s.commitments.pending],
          ['En progreso', s.commitments.in_progress],
          ['Compromisos vencidos', s.commitments.overdue],
          ['Compromisos completados', s.commitments.completed],
        ].map(([label, value]) => (
          <Grid key={String(label)} size={{ xs: 12, sm: 6, md: 3 }}>
            <Metric label={String(label)} value={value} />
          </Grid>
        ))}
      </Grid>
      <Typography component="h2" variant="h2" sx={{ mt: 4, mb: 2 }}>
        Cobertura operacional
      </Typography>
      <Grid container spacing={2}>
        {[
          ['Parroquias con actividades', s.coverage.with_activities],
          ['Parroquias con necesidades', s.coverage.with_needs],
          ['Parroquias con compromisos', s.coverage.with_commitments],
        ].map(([label, value]) => (
          <Grid key={String(label)} size={{ xs: 12, md: 4 }}>
            <Metric label={String(label)} value={`${value} / ${s.coverage.total_parishes}`} />
          </Grid>
        ))}
      </Grid>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ my: 3 }}>
        <Button component={RouterLink} to={`${base}/operations/map`}>
          Mapa operacional
        </Button>
        <Button component={RouterLink} to={`${base}/operations/agenda`}>
          Agenda territorial
        </Button>
        <Button component={RouterLink} to={`${base}/needs`}>
          Ver necesidades
        </Button>
      </Stack>
      <Typography component="h2" variant="h2">
        Próximas actividades aprobadas
      </Typography>
      <Box sx={{ mt: 1 }}>
        {a.activities.slice(0, 5).map((x) => (
          <Card variant="outlined" key={x.id} sx={{ mb: 1 }}>
            <CardContent>
              <Typography fontWeight={700}>{x.title}</Typography>
              <Typography>
                {formatDateOnly(x.activity_date)} ·{' '}
                {x.start_time?.slice(0, 5) ?? 'Hora no registrada'}
              </Typography>
            </CardContent>
          </Card>
        ))}
        {!a.activities.length && (
          <Typography color="text.secondary">No hay actividades aprobadas próximas.</Typography>
        )}
      </Box>
    </>
  );
}
