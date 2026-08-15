import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Snackbar,
  Stack,
  TextField,
} from '@mui/material';
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { useCampaign } from '../../app/CampaignProvider';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { ErrorState } from '../../components/feedback/States';
import { formatDateOnly } from '../../lib/dates';
import type { Activity, Catalog, Page, Parish } from './types';
export default function ApprovalsPage() {
  const { campaignId = '' } = useParams();
  const { active } = useCampaign();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<Activity | null>(null);
  const [mode, setMode] = useState<'approve' | 'reject' | null>(null);
  const [reason, setReason] = useState('');
  const [feedback, setFeedback] = useState('');
  const list = useQuery({
    queryKey: ['approvals', campaignId],
    queryFn: () =>
      apiRequest<Page<Activity>>(
        `/campaigns/${campaignId}/activities?approval_status=PENDING_APPROVAL&page_size=100`,
      ),
  });
  const parishes = useQuery({
    queryKey: ['parishes', active?.canton_id],
    queryFn: () => apiRequest<Parish[]>('/parishes?canton_id=' + active!.canton_id),
    enabled: Boolean(active?.canton_id),
  });
  const types = useQuery({
    queryKey: ['activity-types'],
    queryFn: () => apiRequest<Catalog[]>('/activity-types'),
  });
  const action = useMutation({
    mutationFn: () =>
      apiRequest(`/campaigns/${campaignId}/activities/${selected?.id}/${mode}`, {
        method: 'POST',
        body: mode === 'reject' ? JSON.stringify({ rejection_reason: reason }) : undefined,
      }),
    onSuccess: async () => {
      setFeedback(mode === 'approve' ? 'Actividad aprobada.' : 'Actividad rechazada.');
      setMode(null);
      setSelected(null);
      setReason('');
      await queryClient.invalidateQueries({ queryKey: ['approvals', campaignId] });
      await queryClient.invalidateQueries({ queryKey: ['operations-summary', campaignId] });
    },
  });
  return (
    <>
      <PageHeader
        title="Actividades pendientes de aprobación"
        description="Revisión de solicitudes territoriales autorizadas."
      />
      {list.isError ? (
        <ErrorState retry={() => list.refetch()} />
      ) : (
        <DataTable
          label="actividades pendientes"
          loading={list.isLoading}
          rows={list.data?.items ?? []}
          columns={[
            { key: 'activity', label: 'Actividad', render: (x) => x.title },
            {
              key: 'parish',
              label: 'Parroquia',
              render: (x) => parishes.data?.find((p) => p.id === x.parish_id)?.name ?? '—',
            },
            {
              key: 'type',
              label: 'Tipo',
              render: (x) => types.data?.find((t) => t.id === x.activity_type_id)?.name ?? '—',
            },
            { key: 'date', label: 'Fecha', render: (x) => formatDateOnly(x.activity_date) },
            { key: 'time', label: 'Hora', render: (x) => x.start_time?.slice(0, 5) ?? '—' },
            { key: 'place', label: 'Lugar', render: (x) => x.location_name ?? '—' },
            {
              key: 'requested',
              label: 'Solicitada el',
              render: (x) =>
                x.submitted_for_approval_at
                  ? formatDateOnly(x.submitted_for_approval_at.slice(0, 10))
                  : '—',
            },
            {
              key: 'actions',
              label: 'Acciones',
              render: (x) => (
                <Stack direction="row" spacing={1}>
                  <Button
                    onClick={() => navigate(`/app/campaigns/${campaignId}/activities/${x.id}`)}
                  >
                    Ver detalle
                  </Button>
                  <Button
                    onClick={() => {
                      setSelected(x);
                      setMode('approve');
                    }}
                  >
                    Aprobar
                  </Button>
                  <Button
                    color="error"
                    onClick={() => {
                      setSelected(x);
                      setMode('reject');
                    }}
                  >
                    Rechazar
                  </Button>
                </Stack>
              ),
            },
          ]}
        />
      )}
      <Dialog open={!!mode} onClose={() => setMode(null)} fullWidth>
        <DialogTitle>{mode === 'approve' ? 'Aprobar actividad' : 'Rechazar actividad'}</DialogTitle>
        <DialogContent>
          {mode === 'approve' ? (
            <Alert severity="info">Confirma la aprobación de {selected?.title}.</Alert>
          ) : (
            <TextField
              autoFocus
              required
              fullWidth
              multiline
              minRows={3}
              sx={{ mt: 1 }}
              label="Motivo del rechazo"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMode(null)}>Cancelar</Button>
          <Button
            variant="contained"
            color={mode === 'reject' ? 'error' : 'primary'}
            disabled={action.isPending || (mode === 'reject' && !reason.trim())}
            onClick={() => action.mutate()}
          >
            Confirmar
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        open={!!feedback}
        autoHideDuration={4000}
        onClose={() => setFeedback('')}
        message={feedback}
      />
    </>
  );
}
