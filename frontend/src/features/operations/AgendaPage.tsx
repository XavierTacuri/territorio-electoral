import { Alert, Card, CardContent, Chip, Grid, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly, todayDateOnly } from '../../lib/dates';
import { operationStatusLabel } from './statusLabels';
import type { Activity, Commitment } from './types';
type Agenda = { activities: Activity[]; pending_approval: Activity[]; commitments: Commitment[] };
export default function AgendaPage() {
  const { campaignId = '' } = useParams();
  const query = useQuery({
    queryKey: ['operations-agenda', campaignId],
    queryFn: () => apiRequest<Agenda>(`/campaigns/${campaignId}/operations/agenda`),
  });
  if (query.isLoading) return <LoadingSkeleton />;
  if (query.isError || !query.data) return <ErrorState retry={() => query.refetch()} />;
  const { activities, pending_approval, commitments } = query.data;
  return (
    <>
      <PageHeader
        title="Agenda territorial"
        description="Actividades aprobadas y compromisos próximos o vencidos."
      />
      <Typography variant="h2" component="h2" sx={{ mb: 2 }}>
        Actividades confirmadas
      </Typography>
      <Grid container spacing={2}>
        {activities.map((x) => (
          <Grid key={x.id} size={{ xs: 12, md: 6 }}>
            <Card variant="outlined">
              <CardContent>
                <Typography fontWeight={700}>{x.title}</Typography>
                <Typography>
                  {formatDateOnly(x.activity_date)} ·{' '}
                  {x.start_time?.slice(0, 5) ?? 'Hora no registrada'}
                </Typography>
                <Chip size="small" label={operationStatusLabel(x.status)} />
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
      {!activities.length && <Alert severity="info">No hay actividades aprobadas próximas.</Alert>}
      <Typography variant="h2" component="h2" sx={{ mt: 4, mb: 2 }}>
        Compromisos
      </Typography>
      <Stack spacing={1}>
        {commitments.map((x) => (
          <Card variant="outlined" key={x.id}>
            <CardContent>
              <Typography fontWeight={700}>{x.title}</Typography>
              <Typography>{x.due_date ? formatDateOnly(x.due_date) : 'Sin vencimiento'}</Typography>
              <Chip
                color={x.due_date && x.due_date < todayDateOnly() ? 'error' : 'default'}
                label={
                  x.due_date && x.due_date < todayDateOnly()
                    ? 'Vencido'
                    : operationStatusLabel(x.status)
                }
              />
            </CardContent>
          </Card>
        ))}
      </Stack>
      {pending_approval.length > 0 && (
        <Alert severity="warning" sx={{ mt: 3 }}>
          {pending_approval.length} actividades permanecen pendientes de aprobación y no se muestran
          como confirmadas.
        </Alert>
      )}
    </>
  );
}
