import { useState } from 'react';
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
import { useCampaign } from '../../app/CampaignProvider';
import { useAuth } from '../../auth/AuthProvider';
import { canResubmitActivity } from '../../auth/permissions';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import { evidenceTypeLabel, priorityLabel } from '../../lib/labels';
import { operationStatusLabel } from './statusLabels';
import { ActivityForm, type ActivityFormValue } from './ActivityForm';
import { activityDetailActions } from './activityDetailActions';
import { formatActivityActor } from './activityActors';
import type { Activity, Catalog, Need, Page, Parish } from './types';
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
  const { user } = useAuth();
  const { active } = useCampaign();
  const [dialog, setDialog] = useState<'participants' | 'need' | 'evidence' | null>(null);
  const [approvalDialog, setApprovalDialog] = useState<'approve' | 'reject' | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [editing, setEditing] = useState(false);
  const activity = useQuery({
    queryKey: ['campaign', campaignId, 'activity', activityId],
    queryFn: () => apiRequest<Activity>('/campaigns/' + campaignId + '/activities/' + activityId),
  });
  const participants = useQuery({
    queryKey: ['activity', campaignId, activityId, 'participants'],
    queryFn: () =>
      apiRequest<Participants>(
        '/campaigns/' + campaignId + '/activities/' + activityId + '/participant-summary',
      ),
    retry: false,
    enabled: activity.data?.approval_status === 'APPROVED',
  });
  const needs = useQuery({
    queryKey: ['activity', campaignId, activityId, 'needs'],
    queryFn: () =>
      apiRequest<Page<Need>>('/campaigns/' + campaignId + '/activities/' + activityId + '/needs'),
    enabled: activity.data?.approval_status === 'APPROVED',
  });
  const evidence = useQuery({
    queryKey: ['activity', campaignId, activityId, 'evidence'],
    queryFn: () =>
      apiRequest<Evidence[]>(
        '/campaigns/' + campaignId + '/activities/' + activityId + '/evidence',
      ),
    enabled: activity.data?.approval_status === 'APPROVED',
  });
  const categories = useQuery({
    queryKey: ['need-categories'],
    queryFn: () => apiRequest<Catalog[]>('/need-categories'),
    enabled: activity.data?.approval_status === 'APPROVED',
  });
  const types = useQuery({ queryKey: ['activity-types'], queryFn: () => apiRequest<Catalog[]>('/activity-types') });
  const parishes = useQuery({
    queryKey: ['parishes', active?.canton_id],
    queryFn: () => apiRequest<Parish[]>('/parishes?canton_id=' + active!.canton_id),
    enabled: Boolean(active?.canton_id),
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
      status: 'REPORTED',
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
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'activity', activityId] });
      await queryClient.invalidateQueries({
        queryKey: ['activity', campaignId, activityId, 'participants'],
      });
      await queryClient.invalidateQueries({
        queryKey: ['activity', campaignId, activityId, 'needs'],
      });
      await queryClient.invalidateQueries({
        queryKey: ['activity', campaignId, activityId, 'evidence'],
      });
      setDialog(null);
    },
  });
  const approvalAction = useMutation({
    mutationFn: (mode: 'approve' | 'reject') => apiRequest<Activity>(`/campaigns/${campaignId}/activities/${activityId}/${mode}`, {
      method: 'POST',
      body: mode === 'reject' ? JSON.stringify({ rejection_reason: rejectionReason.trim() }) : undefined,
    }),
    onSuccess: async () => {
      setApprovalDialog(null); setRejectionReason('');
      await queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'activity', activityId] });
      await queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'activities'] });
    },
  });
  if (activity.isLoading) return <LoadingSkeleton />;
  if (activity.isError || !activity.data) return <ErrorState retry={() => activity.refetch()} />;
  const item = activity.data;
  const detailActions = activityDetailActions(user, item);
  const canApprove = detailActions.approve;
  const canCorrect = detailActions.correctAndResubmit;
  const executionAvailable = detailActions.execution;
  return (
    <>
      <PageHeader
        title={item.title}
        description={'Actividad del ' + formatDateOnly(item.activity_date)}
        action={
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ width: { xs: '100%', sm: 'auto' } }}>
            {canApprove && <Button variant="contained" onClick={() => setApprovalDialog('approve')}>Aprobar</Button>}
            {canApprove && <Button color="error" variant="outlined" onClick={() => setApprovalDialog('reject')}>Rechazar</Button>}
            {canCorrect && <Button variant="contained" onClick={() => setEditing(true)}>Editar y corregir</Button>}
            <Button
              component={RouterLink}
              to={`/app/campaigns/${campaignId}/territory-ai?activity_id=${activityId}&question=${encodeURIComponent(`Resume la actividad ${item.title}`)}`}
            >
              Preguntar sobre este registro
            </Button>
            <Button component={RouterLink} to={'/app/campaigns/' + campaignId + '/activities'}>
              Volver
            </Button>
          </Stack>
        }
      />
      {item.approval_status === 'REJECTED' && (
        <Alert severity="error" sx={{ mb: 2 }}>
          <Typography><strong>Estado de aprobación:</strong> Rechazada</Typography>
          <Typography><strong>Motivo del rechazo:</strong> {item.rejection_reason || 'No disponible'}</Typography>
          <Typography><strong>Fecha:</strong> {item.rejected_at ? formatDateOnly(item.rejected_at.slice(0, 10)) : 'No disponible'}</Typography>
          <Typography><strong>Rechazado por:</strong> {formatActivityActor(item.rejected_by)}</Typography>
        </Alert>
      )}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 2 }}>
        {item.approval_status === 'DRAFT' && canResubmitActivity(user) && (
          <Button
            variant="contained"
            onClick={() =>
              mutate.mutateAsync({
                path: `/campaigns/${campaignId}/activities/${activityId}/submit-for-approval`,
                body: {},
              })
            }
          >
            Enviar a aprobación
          </Button>
        )}
        <StatusBadge value={operationStatusLabel(item.approval_status)} />
        <StatusBadge value={operationStatusLabel(item.status)} />
      </Stack>
      <Grid container spacing={2}>
        {(item.completion_summary || item.cancellation_reason || item.suspension_reason) && <Grid size={{ xs: 12 }}><Card variant="outlined"><CardContent><Typography variant="h2">Historial de actividad</Typography>{item.completion_summary && <><Typography><strong>Resumen</strong></Typography><Typography>{item.completion_summary}</Typography><Typography>Fecha de cierre: {item.completed_at ? formatDateOnly(item.completed_at.slice(0, 10)) : 'No disponible'}</Typography><Typography><strong>Completado por:</strong> {formatActivityActor(item.completed_by)}</Typography></>}{item.outcome_notes && <><Typography><strong>Resultados / observaciones</strong></Typography><Typography>{item.outcome_notes}</Typography></>}{item.suspension_reason && <><Typography><strong>Motivo de suspensión</strong></Typography><Typography>{item.suspension_reason}</Typography><Typography><strong>Suspendido por:</strong> {formatActivityActor(item.suspended_by)}</Typography>{item.resumed_by && <Typography><strong>Reanudado por:</strong> {formatActivityActor(item.resumed_by)}</Typography>}</>}{item.cancellation_reason && <><Typography><strong>Motivo de cancelación (legacy)</strong></Typography><Typography>{item.cancellation_reason}</Typography></>}</CardContent></Card></Grid>}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Stack spacing={1}>
                <StatusBadge value={operationStatusLabel(item.status)} />
                <Typography>{item.description || 'Sin descripción'}</Typography>
                <Typography>Parroquia: {item.parish_name ?? 'No disponible'}</Typography>
                <Typography>Ubicación: {item.location_name || 'No registrada'}</Typography>
                {item.approval_status === 'APPROVED' && <Typography><strong>Aprobado por:</strong> {formatActivityActor(item.approved_by)}</Typography>}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        {executionAvailable && <>
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
                <Typography key={x.id} component={RouterLink} to={`/app/campaigns/${campaignId}/needs/${x.id}`}>
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
                  {x.title} ({evidenceTypeLabel(x.evidence_type)})
                </Link>
              ))}
              {!evidence.data?.length && <Typography>No hay evidencias</Typography>}
              <Button onClick={() => setDialog('evidence')}>Agregar evidencia</Button>
            </CardContent>
          </Card>
        </Grid>
        </>}
      </Grid>
      <ActivityForm
        open={editing}
        activity={item}
        types={types.data ?? []}
        parishes={parishes.data ?? []}
        submitLabel="Guardar y reenviar"
        onClose={() => setEditing(false)}
        onSubmit={async (value: ActivityFormValue) => {
          await apiRequest(`/campaigns/${campaignId}/activities/${activityId}`, { method: 'PATCH', body: JSON.stringify(value) });
          await apiRequest(`/campaigns/${campaignId}/activities/${activityId}/submit-for-approval`, { method: 'POST' });
          await queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'activity', activityId] });
          await queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'activities'] });
        }}
      />
      <Dialog open={Boolean(approvalDialog)} onClose={() => setApprovalDialog(null)} fullWidth>
        <DialogTitle>{approvalDialog === 'approve' ? 'Aprobar actividad' : 'Rechazar actividad'}</DialogTitle>
        <DialogContent>
          {approvalDialog === 'approve' ? <Alert severity="info" sx={{ mt: 1 }}>Confirma la aprobación de {item.title}.</Alert> : <TextField autoFocus required fullWidth multiline minRows={3} sx={{ mt: 1 }} label="Motivo del rechazo" value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)} />}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setApprovalDialog(null)}>Cancelar</Button>
          <Button variant="contained" color={approvalDialog === 'reject' ? 'error' : 'primary'} disabled={approvalAction.isPending || (approvalDialog === 'reject' && !rejectionReason.trim())} onClick={() => approvalDialog && approvalAction.mutate(approvalDialog)}>Confirmar</Button>
        </DialogActions>
      </Dialog>
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
                  {priorityLabel(x)}
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
                body: {
                  ...body,
                  source_type: 'CAMPAIGN_ACTIVITY',
                  reported_date: item.activity_date,
                  urgency: body.priority,
                  scope: 'PARISH',
                },
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
                  {evidenceTypeLabel(x)}
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
