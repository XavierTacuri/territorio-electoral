import { useState } from 'react';
import {
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  Link,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useForm } from 'react-hook-form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import type { Activity, Catalog, Need, Page } from './types';
type Participants = {
  estimated_attendees: number;
  organizations_count: number;
  community_leaders_count: number;
  campaign_team_count: number;
  notes?: string | null;
};
type Evidence = {
  id: string;
  title: string;
  evidence_type: string;
  url: string;
  evidence_date?: string | null;
};
export default function ActivityDetailPage() {
  const { campaignId = '', activityId = '' } = useParams();
  const [dialog, setDialog] = useState<'participants' | 'need' | 'evidence' | null>(null);
  const activity = useQuery({
    queryKey: ['campaign', campaignId, 'activity', activityId],
    queryFn: () => apiRequest<Activity>('/campaigns/' + campaignId + '/activities/' + activityId),
  });
  const participants = useQuery({
    queryKey: ['activity', activityId, 'participants'],
    queryFn: () =>
      apiRequest<Participants>(
        '/campaigns/' + campaignId + '/activities/' + activityId + '/participant-summary',
      ),
    retry: false,
  });
  const needs = useQuery({
    queryKey: ['activity', activityId, 'needs'],
    queryFn: () =>
      apiRequest<Page<Need>>('/campaigns/' + campaignId + '/activities/' + activityId + '/needs'),
  });
  const evidence = useQuery({
    queryKey: ['activity', activityId, 'evidence'],
    queryFn: () =>
      apiRequest<Evidence[]>(
        '/campaigns/' + campaignId + '/activities/' + activityId + '/evidence',
      ),
  });
  const categories = useQuery({
    queryKey: ['need-categories'],
    queryFn: () => apiRequest<Catalog[]>('/need-categories'),
  });
  const participantForm = useForm<Participants>({
    values: participants.data ?? {
      estimated_attendees: 0,
      organizations_count: 0,
      community_leaders_count: 0,
      campaign_team_count: 0,
      notes: '',
    },
  });
  const needForm = useForm<{
    need_category_code: string;
    title: string;
    description: string;
    mentions_count: number;
    priority: string;
    status: string;
  }>({
    defaultValues: {
      need_category_code: '',
      title: '',
      description: '',
      mentions_count: 1,
      priority: 'MEDIUM',
      status: 'IDENTIFIED',
    },
  });
  const evidenceForm = useForm<{
    evidence_type: string;
    title: string;
    description: string;
    url: string;
    evidence_date: string;
  }>({
    defaultValues: {
      evidence_type: 'PHOTO',
      title: '',
      description: '',
      url: '',
      evidence_date: '',
    },
  });
  const mutate = useMutation({
    mutationFn: ({
      path,
      method = 'POST',
      body,
    }: {
      path: string;
      method?: string;
      body: unknown;
    }) => apiRequest(path, { method, body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['activity', activityId] });
      setDialog(null);
    },
  });
  if (activity.isLoading) return <LoadingSkeleton />;
  if (activity.isError || !activity.data) return <ErrorState retry={() => activity.refetch()} />;
  const item = activity.data;
  return (
    <>
      <PageHeader
        title={item.title}
        description={'Actividad del ' + formatDateOnly(item.activity_date)}
        action={
          <Button component={RouterLink} to={'/app/campaigns/' + campaignId + '/activities'}>
            Volver
          </Button>
        }
      />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Stack spacing={1}>
                <StatusBadge value={item.status} />
                <Typography>{item.description || 'Sin descripción'}</Typography>
                <Typography>Parroquia: {item.parish_id}</Typography>
                <Typography>Ubicación: {item.location_name || 'No registrada'}</Typography>
                {item.latitude != null && item.longitude != null && (
                  <Typography>
                    Coordenadas: {item.latitude}, {item.longitude}
                  </Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h2">Participantes agregados</Typography>
              {participants.data ? (
                <Stack>
                  <Typography>
                    Asistentes estimados: {participants.data.estimated_attendees}
                  </Typography>
                  <Typography>Organizaciones: {participants.data.organizations_count}</Typography>
                  <Typography>
                    Líderes comunitarios: {participants.data.community_leaders_count}
                  </Typography>
                  <Typography>
                    Equipo de campaña: {participants.data.campaign_team_count}
                  </Typography>
                </Stack>
              ) : (
                <Typography>No registrados</Typography>
              )}
              <Button onClick={() => setDialog('participants')}>Registrar resumen</Button>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h2">Necesidades</Typography>
              {needs.data?.items.map((x) => (
                <Typography key={x.id}>
                  {x.title} · {x.mentions_count} menciones
                </Typography>
              ))}
              {!needs.data?.items.length && <Typography>No hay necesidades</Typography>}
              <Button onClick={() => setDialog('need')}>Registrar necesidad</Button>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h2">Evidencias URL</Typography>
              {evidence.data?.map((x) => (
                <Link
                  key={x.id}
                  href={x.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  display="block"
                >
                  {x.title} ({x.evidence_type})
                </Link>
              ))}
              {!evidence.data?.length && <Typography>No hay evidencias</Typography>}
              <Button onClick={() => setDialog('evidence')}>Agregar evidencia</Button>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      <Dialog open={dialog === 'participants'} onClose={() => setDialog(null)} fullWidth>
        <DialogTitle>Participantes agregados</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {[
              ['estimated_attendees', 'Asistentes estimados'],
              ['organizations_count', 'Organizaciones'],
              ['community_leaders_count', 'Líderes comunitarios'],
              ['campaign_team_count', 'Equipo de campaña'],
            ].map(([name, label]) => (
              <TextField
                key={name}
                type="number"
                label={label}
                {...participantForm.register(name as keyof Participants, {
                  valueAsNumber: true,
                  min: 0,
                })}
              />
            ))}
            <TextField label="Notas autorizadas" multiline {...participantForm.register('notes')} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog(null)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={participantForm.handleSubmit((body) =>
              mutate.mutateAsync({
                path:
                  '/campaigns/' + campaignId + '/activities/' + activityId + '/participant-summary',
                method: 'PUT',
                body: {
                  estimated_attendees: body.estimated_attendees,
                  organizations_count: body.organizations_count,
                  community_leaders_count: body.community_leaders_count,
                  campaign_team_count: body.campaign_team_count,
                  notes: body.notes || null,
                },
              }),
            )}
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={dialog === 'need'} onClose={() => setDialog(null)} fullWidth>
        <DialogTitle>Registrar necesidad</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Categoría"
              defaultValue=""
              {...needForm.register('need_category_code', { required: true })}
            >
              {categories.data?.map((x) => (
                <MenuItem key={x.id} value={x.code}>
                  {x.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField label="Título" {...needForm.register('title', { required: true })} />
            <TextField label="Descripción" multiline {...needForm.register('description')} />
            <TextField
              label="Menciones"
              type="number"
              {...needForm.register('mentions_count', { valueAsNumber: true, min: 1 })}
            />
            <TextField
              select
              label="Prioridad"
              defaultValue="MEDIUM"
              {...needForm.register('priority')}
            >
              {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((x) => (
                <MenuItem key={x} value={x}>
                  {x}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog(null)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={needForm.handleSubmit((body) =>
              mutate.mutateAsync({
                path: '/campaigns/' + campaignId + '/activities/' + activityId + '/needs',
                body,
              }),
            )}
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={dialog === 'evidence'} onClose={() => setDialog(null)} fullWidth>
        <DialogTitle>Agregar evidencia URL</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Tipo"
              defaultValue="PHOTO"
              {...evidenceForm.register('evidence_type')}
            >
              {['PHOTO', 'VIDEO', 'DOCUMENT', 'NEWS_LINK', 'SOCIAL_LINK', 'OTHER'].map((x) => (
                <MenuItem key={x} value={x}>
                  {x}
                </MenuItem>
              ))}
            </TextField>
            <TextField label="Título" {...evidenceForm.register('title', { required: true })} />
            <TextField
              label="URL HTTPS"
              type="url"
              {...evidenceForm.register('url', { required: true })}
            />
            <TextField
              label="Fecha"
              type="date"
              InputLabelProps={{ shrink: true }}
              {...evidenceForm.register('evidence_date')}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog(null)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={evidenceForm.handleSubmit((body) =>
              mutate.mutateAsync({
                path: '/campaigns/' + campaignId + '/activities/' + activityId + '/evidence',
                body: { ...body, evidence_date: body.evidence_date || null },
              }),
            )}
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
