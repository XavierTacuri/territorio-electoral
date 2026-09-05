import { useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Pagination, Stack, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { useCampaign } from '../../app/CampaignProvider';
import { useAuth } from '../../auth/AuthProvider';
import { canApproveActivity } from '../../auth/permissions';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { formatDateOnly } from '../../lib/dates';
import { ActivityForm, type ActivityFormValue } from './ActivityForm';
import { ActivityClosureDialog } from './ActivityClosureDialog';
import {
  APPROVAL_STATUS_LABELS,
  EXECUTION_STATUS_LABELS,
  operationStatusLabel,
} from './statusLabels';
import type { Activity, Catalog, Page, Parish } from './types';
export default function ActivitiesPage() {
  const { campaignId = '' } = useParams();
  const { active } = useCampaign();
  const { user } = useAuth();
  const canOperate = Boolean(user?.is_superuser || user?.roles.some((role) => ['ADMIN', 'CANDIDATE', 'CAMPAIGN_MANAGER', 'TERRITORIAL_COORDINATOR'].includes(role.code)));
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [approval, setApproval] = useState('');
  const [editing, setEditing] = useState<Activity | null>(null);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Activity | null>(null);
  const [actionMode, setActionMode] = useState<'approve' | 'reject' | null>(null);
  const [reason, setReason] = useState('');
  const [closure, setClosure] = useState<{ activity: Activity; mode: 'complete' | 'suspend' } | null>(null);
  const [successMessage, setSuccessMessage] = useState('');
  const approvalAction = useMutation({
    mutationFn: () => apiRequest(`/campaigns/${campaignId}/activities/${selected?.id}/${actionMode}`, {
      method: 'POST', body: actionMode === 'reject' ? JSON.stringify({ rejection_reason: reason }) : undefined,
    }),
    onSuccess: async () => {
      setActionMode(null); setSelected(null); setReason('');
      await queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'activities'] });
      await queryClient.invalidateQueries({ queryKey: ['operations-summary', campaignId] });
    },
  });
  const params = new URLSearchParams({ page: String(page), page_size: '20' });
  if (search) params.set('search', search);
  if (status) params.set('status', status);
  if (approval) params.set('approval_status', approval);
  const list = useQuery({
    queryKey: ['campaign', campaignId, 'activities', page, search, status, approval],
    queryFn: ({ signal }) =>
      apiRequest<Page<Activity>>('/campaigns/' + campaignId + '/activities?' + params, { signal }),
  });
  const types = useQuery({
    queryKey: ['activity-types'],
    queryFn: () => apiRequest<Catalog[]>('/activity-types'),
  });
  const parishes = useQuery({
    queryKey: ['parishes', active?.canton_id],
    queryFn: () => apiRequest<Parish[]>('/parishes?canton_id=' + active!.canton_id),
    enabled: Boolean(active?.canton_id),
  });
  const save = useMutation({
    mutationFn: (value: ActivityFormValue) =>
      apiRequest<Activity>(
        '/campaigns/' + campaignId + '/activities' + (editing ? '/' + editing.id : ''),
        {
          method: editing ? 'PATCH' : 'POST',
          body: JSON.stringify(value),
        },
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'activities'] }),
  });
  return (
    <>
      <PageHeader
        title="Actividades"
        description="Operación territorial sin listas de asistentes ni datos personales."
        action={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => {
              setEditing(null);
              setOpen(true);
            }}
          >
            Crear actividad
          </Button>
        }
      />
      {successMessage && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccessMessage('')}>{successMessage}</Alert>}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          label="Buscar"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
        <TextField
          select
          label="Estado"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {Object.entries(EXECUTION_STATUS_LABELS).map(([value, label]) => (
            <MenuItem key={value} value={value}>
              {label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Aprobación"
          value={approval}
          onChange={(e) => {
            setApproval(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">Todas</MenuItem>
          {Object.entries(APPROVAL_STATUS_LABELS).map(([value, label]) => (
            <MenuItem key={value} value={value}>
              {label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {list.isError ? (
        <ErrorState retry={() => list.refetch()} />
      ) : (
        <DataTable
          label="actividades"
          loading={list.isLoading}
          rows={list.data?.items ?? []}
          columns={[
            { key: 'title', label: 'Título', render: (x) => <>{x.title}</> },
            { key: 'date', label: 'Fecha', render: (x) => formatDateOnly(x.activity_date) },
            {
              key: 'status',
              label: 'Estado',
              render: (x) => <StatusBadge value={operationStatusLabel(x.status)} />,
            },
            {
              key: 'approval',
              label: 'Aprobación',
              render: (x) => <StatusBadge value={operationStatusLabel(x.approval_status)} />,
            },
            { key: 'parish', label: 'Parroquia', render: (x) => x.parish_name ?? 'No disponible' },
          ]}
          onView={(x) => navigate('/app/campaigns/' + campaignId + '/activities/' + x.id)}
          onEdit={canOperate ? async (x) => {
            const full = await apiRequest<Activity>(
              '/campaigns/' + campaignId + '/activities/' + x.id,
            );
            setEditing(full);
            setOpen(true);
          } : undefined}
          actions={(x) => canApproveActivity(user) && x.approval_status === 'PENDING_APPROVAL' ? (
            <>
              <Button size="small" onClick={() => { setSelected(x); setActionMode('approve'); }}>Aprobar</Button>
              <Button size="small" color="error" onClick={() => { setSelected(x); setActionMode('reject'); }}>Rechazar</Button>
            </>
          ) : null}
        />
      )}
      <Pagination
        sx={{ mt: 2 }}
        page={page}
        count={list.data?.total_pages ?? 0}
        onChange={(_, value) => setPage(value)}
      />
      <ActivityForm
        open={open}
        activity={editing}
        types={types.data ?? []}
        parishes={parishes.data ?? []}
        onClose={() => setOpen(false)}
        onSubmit={async (value) => {
          if (editing && value.status === 'COMPLETED' && editing.status !== 'COMPLETED') {
            setOpen(false); setClosure({ activity: editing, mode: 'complete' }); return;
          }
          if (editing && value.status === 'SUSPENDED' && editing.status !== 'SUSPENDED') {
            setOpen(false); setClosure({ activity: editing, mode: 'suspend' }); return;
          }
          if (editing && value.status === 'PLANNED' && editing.status === 'SUSPENDED') {
            setOpen(false);
            await apiRequest(`/campaigns/${campaignId}/activities/${editing.id}/resume`, { method: 'POST' });
            await queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'activities'] });
            return;
          }
          const saved = await save.mutateAsync(value);
          if (!editing && saved.approval_status === 'PENDING_APPROVAL') setSuccessMessage('Actividad enviada para aprobación.');
        }}
      />
      <ActivityClosureDialog campaignId={campaignId} activity={closure?.activity ?? null} mode={closure?.mode ?? null} onClose={() => setClosure(null)} onSaved={() => setClosure(null)} />
      <Dialog open={Boolean(actionMode)} onClose={() => setActionMode(null)} fullWidth>
        <DialogTitle>{actionMode === 'approve' ? 'Aprobar actividad' : 'Rechazar actividad'}</DialogTitle>
        <DialogContent>
          {actionMode === 'approve' ? <Alert severity="info">Confirma la aprobación de {selected?.title}.</Alert> : (
            <TextField autoFocus required fullWidth multiline minRows={3} sx={{ mt: 1 }} label="Motivo del rechazo" value={reason} onChange={(e) => setReason(e.target.value)} />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setActionMode(null)}>Cancelar</Button>
          <Button variant="contained" color={actionMode === 'reject' ? 'error' : 'primary'} disabled={approvalAction.isPending || (actionMode === 'reject' && !reason.trim())} onClick={() => approvalAction.mutate()}>Confirmar</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
