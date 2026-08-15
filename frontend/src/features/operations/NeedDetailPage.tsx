import {
  Alert,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { useCampaign } from '../../app/CampaignProvider';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import type { Commitment, Need, Page, Parish } from './types';
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
  const [commit, setCommit] = useState(false);
  const [title, setTitle] = useState('');
  const need = useQuery({
    queryKey: ['need', campaignId, needId],
    queryFn: () => apiRequest<Need>(`/campaigns/${campaignId}/needs/${needId}`),
  });
  const history = useQuery({
    queryKey: ['need-history', campaignId, needId],
    queryFn: () => apiRequest<History>(`/campaigns/${campaignId}/needs/${needId}/history`),
  });
  const commitments = useQuery({
    queryKey: ['need-commitments', campaignId, needId],
    queryFn: () =>
      apiRequest<Page<Commitment>>(`/campaigns/${campaignId}/commitments?page_size=100`),
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
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) =>
      apiRequest(`/campaigns/${campaignId}${path}`, {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
      }),
    onSuccess: async () => {
      setCommit(false);
      await queryClient.invalidateQueries({ queryKey: ['need', campaignId, needId] });
      await queryClient.invalidateQueries({ queryKey: ['need-history', campaignId, needId] });
    },
  });
  if (need.isLoading) return <LoadingSkeleton />;
  if (need.isError || !need.data) return <ErrorState retry={() => need.refetch()} />;
  const n = need.data;
  const related = commitments.data?.items.filter((x) => x.need_id === n.id) ?? [];
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
                <StatusBadge value={n.status} />
                <Typography>
                  Parroquia:{' '}
                  {parishes.data?.find((p) => p.id === n.parish_id)?.name ?? 'No disponible'}
                </Typography>
                <Typography>Urgencia: {n.urgency}</Typography>
                <Typography>Alcance: {n.scope}</Typography>
                <Typography>{n.description || 'Sin descripción'}</Typography>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h2">Origen</Typography>
              <Typography>{source[n.source_type] ?? n.source_type}</Typography>
              <Typography>Fecha: {formatDateOnly(n.reported_date)}</Typography>
              <Typography>
                {n.activity_id ? 'Vinculada a una actividad territorial' : 'Registro directo'}
              </Typography>
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
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ my: 2 }}>
        {['REPORTED', 'IDENTIFIED'].includes(n.status) && (
          <Button
            variant="contained"
            onClick={() => action.mutate({ path: `/needs/${n.id}/start-review` })}
          >
            Iniciar revisión
          </Button>
        )}
        {n.status === 'UNDER_REVIEW' && (
          <Button
            variant="contained"
            onClick={() =>
              action.mutate({
                path: `/needs/${n.id}/validate`,
                body: { validation_notes: 'Validación operativa registrada' },
              })
            }
          >
            Validar
          </Button>
        )}
        {n.status === 'VALIDATED' && (
          <Button
            variant="contained"
            onClick={() => {
              setTitle(`Atender: ${n.title}`);
              setCommit(true);
            }}
          >
            Crear compromiso
          </Button>
        )}
      </Stack>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Typography variant="h2">Validación y responsable</Typography>
          <Typography>{n.validation_notes || 'Sin notas de validación'}</Typography>
          <Typography>
            {n.assigned_to_user_id ? 'Responsable asignado' : 'Sin responsable asignado'}
          </Typography>
          <Typography variant="h2" sx={{ mt: 3 }}>
            Compromiso relacionado
          </Typography>
          {related.map((x) => (
            <Typography key={x.id}>
              {x.title} · {x.status}
            </Typography>
          ))}
          {!related.length && (
            <Typography color="text.secondary">No existe compromiso relacionado.</Typography>
          )}
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Typography variant="h2">Historial</Typography>
          <Stack spacing={1}>
            {history.data?.map((x) => (
              <Card variant="outlined" key={x.id}>
                <CardContent>
                  <Typography fontWeight={700}>{formatDateOnly(x.event_date)}</Typography>
                  <Typography>{x.description}</Typography>
                  {x.metadata?.reason && (
                    <Alert severity="warning">Motivo: {x.metadata.reason}</Alert>
                  )}
                </CardContent>
              </Card>
            ))}
          </Stack>
        </Grid>
      </Grid>
      <Dialog open={commit} onClose={() => setCommit(false)} fullWidth>
        <DialogTitle>Crear compromiso</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            sx={{ mt: 1 }}
            label="Título"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCommit(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={!title.trim()}
            onClick={() =>
              action.mutate({
                path: '/commitments',
                body: {
                  need_id: n.id,
                  activity_id: n.activity_id,
                  title,
                  description: n.description,
                  priority: n.urgency,
                  status: 'PENDING',
                  parish_id: n.parish_id,
                },
              })
            }
          >
            Crear
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
