import { Alert, Button, Chip, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { formatDateOnly } from '../../lib/dates';
import { operationStatusLabel } from '../operations/statusLabels';
import { useOnlineStatus } from '../../offline/useOnlineStatus';

type ActivityDetail = {
  id: string;
  title: string;
  description: string | null;
  activity_date: string;
  status: string;
  approval_status: string;
  parish_id: number;
  parish_name?: string | null;
  location_name: string | null;
};

export default function FieldActivityDetailPage() {
  const { campaignId = '', activityId = '' } = useParams();
  const online = useOnlineStatus();
  const query = useQuery({
    queryKey: ['field-activity', campaignId, activityId],
    queryFn: () => apiRequest<ActivityDetail>(`/campaigns/${campaignId}/activities/${activityId}`),
    enabled: online,
  });

  if (!online)
    return (
      <Alert severity="info">
        El detalle de esta actividad necesita conexión a internet la primera vez que se abre.
      </Alert>
    );
  if (query.isLoading) return <LoadingSkeleton />;
  if (query.isError || !query.data) return <ErrorState retry={() => void query.refetch()} />;
  const activity = query.data;

  return (
    <Stack spacing={2}>
      <Typography variant="h2" sx={{ fontSize: '1.2rem' }}>
        {activity.title}
      </Typography>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1}>
          <Row label="Parroquia" value={activity.parish_name ?? 'No disponible'} />
          <Row label="Fecha" value={formatDateOnly(activity.activity_date)} />
          <Row
            label="Estado"
            value={
              <Chip
                size="small"
                label={operationStatusLabel(
                  activity.approval_status === 'PENDING_APPROVAL'
                    ? activity.approval_status
                    : activity.status,
                )}
              />
            }
          />
          <Row label="Lugar" value={activity.location_name ?? 'No registrado'} />
          <Row label="Observaciones" value={activity.description ?? 'Sin observaciones'} />
        </Stack>
      </Paper>
      <Button
        href={`/app/campaigns/${campaignId}/territory-ai?question=${encodeURIComponent(`Resume la actividad ${activity.title}`)}`}
      >
        Preguntar a Territorio IA
      </Button>
    </Stack>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap">
      <Typography color="text.secondary">{label}</Typography>
      <Typography fontWeight={600}>{value}</Typography>
    </Stack>
  );
}
