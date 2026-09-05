import { Alert, Button, Card, CardContent, Grid, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useCampaign } from '../../app/CampaignProvider';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import { needSourceLabels } from '../../lib/labels';
import type { Activity, Need, Page, Parish } from './types';
import type { PublicItem } from '../public-intelligence/types';
type History = {
  id: string;
  event_type: string;
  event_date: string;
  description: string;
  metadata?: Record<string, string>;
}[];
const source: Record<string, string> = {
  ASSEMBLY: 'Asamblea comunitaria',
  COMMUNITY_MEETING: 'Reunión comunitaria',
  FIELD_VISIT: 'Visita territorial',
  CAMPAIGN_ACTIVITY: 'Actividad territorial',
  CITIZEN_REPORT: 'Reporte comunitario',
  TEAM_REPORT: 'Reporte del equipo',
  OTHER: 'Otro',
};
export default function NeedDetailPage() {
  const { campaignId = '', needId = '' } = useParams();
  const { active } = useCampaign();
  const need = useQuery({
    queryKey: ['need', campaignId, needId],
    queryFn: () => apiRequest<Need>(`/campaigns/${campaignId}/needs/${needId}`),
  });
  const history = useQuery({
    queryKey: ['need-history', campaignId, needId],
    queryFn: () => apiRequest<History>(`/campaigns/${campaignId}/needs/${needId}/history`),
  });
  const activities = useQuery({
    queryKey: ['need-activities', campaignId],
    queryFn: () => apiRequest<Page<Activity>>(`/campaigns/${campaignId}/activities?page_size=100`),
  });
  const parishes = useQuery({
    queryKey: ['parishes', active?.canton_id],
    queryFn: () => apiRequest<Parish[]>('/parishes?canton_id=' + active!.canton_id),
    enabled: Boolean(active?.canton_id),
  });
  const publicItems = useQuery({
    queryKey: ['need-public-items', campaignId, needId],
    queryFn: () =>
      apiRequest<PublicItem[]>(`/campaigns/${campaignId}/needs/${needId}/public-intelligence`),
  });
  if (need.isLoading) return <LoadingSkeleton />;
  if (need.isError || !need.data) return <ErrorState retry={() => need.refetch()} />;
  const n = need.data;
  const originActivity = activities.data?.items.find((x) => x.id === n.activity_id);
  const otherActivities = history.data
    ?.filter((event) => event.event_type === 'relate_activity' && event.metadata?.activity_title)
    .map((event) => event.metadata!.activity_title);
  return (
    <>
      <PageHeader
        title="Necesidad territorial"
        description={n.title}
        action={
          <Stack direction="row">
            <Button
              component={RouterLink}
              to={`/app/campaigns/${campaignId}/territory-ai?need_id=${needId}&question=${encodeURIComponent(`Resume la necesidad ${n.title}`)}`}
            >
              Preguntar sobre este registro
            </Button>
            <Button component={RouterLink} to={`/app/campaigns/${campaignId}/needs`}>
              Volver
            </Button>
          </Stack>
        }
      />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Card variant="outlined">
            <CardContent>
              <Stack spacing={1}>
                <Typography variant="h2">Necesidad</Typography>
                <Typography fontWeight={700}>{n.title}</Typography>
                <Typography>{n.description || 'Sin descripción'}</Typography>
                <Typography>
                  Parroquia:{' '}
                  {parishes.data?.find((p) => p.id === n.parish_id)?.name ?? 'No disponible'}
                </Typography>
                <Typography>Fecha de registro: {formatDateOnly(n.reported_date)}</Typography>
                <Typography>
                  {n.mentions_count === 1
                    ? 'Registrada en una actividad'
                    : `Mencionada en ${n.mentions_count} actividades`}
                </Typography>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h2">Origen</Typography>
              <Typography>
                {needSourceLabels[n.source_type] ?? source[n.source_type] ?? 'No disponible'}
              </Typography>
              <Typography>
                Actividad de origen:{' '}
                {originActivity?.title ??
                  (n.activity_id ? 'Actividad territorial' : 'Registro manual')}
              </Typography>
              <Typography variant="h3" sx={{ mt: 2 }}>
                Otras actividades relacionadas
              </Typography>
              {otherActivities?.length ? (
                otherActivities.map((title) => <Typography key={title}>{title}</Typography>)
              ) : (
                <Typography color="text.secondary">Sin otras actividades identificadas.</Typography>
              )}
              <Typography variant="h3" sx={{ mt: 2 }}>
                Observaciones
              </Typography>
              <Typography>{n.evidence_notes || 'Sin observaciones'}</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      <Typography variant="h2" sx={{ mt: 3 }}>
        Fuentes públicas relacionadas
      </Typography>
      {!publicItems.data?.length && (
        <Typography color="text.secondary">
          No existen fuentes públicas vinculadas manualmente.
        </Typography>
      )}
      {publicItems.data?.map((item) => (
        <Card variant="outlined" key={item.id} sx={{ mt: 1 }}>
          <CardContent>
            <Typography fontWeight={700}>{item.title}</Typography>
            <Typography>
              {item.source_name} · {item.publisher}
            </Typography>
            <Button
              component={RouterLink}
              to={`/app/campaigns/${campaignId}/public-intelligence/${item.id}`}
            >
              Ver fuente pública
            </Button>
          </CardContent>
        </Card>
      ))}
      <Typography variant="h2" sx={{ mt: 3 }}>
        Historial
      </Typography>
      <Stack spacing={1}>
        {history.data?.map((x) => (
          <Card variant="outlined" key={x.id}>
            <CardContent>
              <Typography fontWeight={700}>{formatDateOnly(x.event_date)}</Typography>
              <Typography>{x.description}</Typography>
              {x.metadata?.reason && <Alert severity="warning">Motivo: {x.metadata.reason}</Alert>}
            </CardContent>
          </Card>
        ))}
      </Stack>
    </>
  );
}
