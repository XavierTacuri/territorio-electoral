import { useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { DataTable, type Column } from '../../components/tables/DataTable';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly, todayDateOnly } from '../../lib/dates';
import { useAuth } from '../../auth/AuthProvider';
import {
  canAcknowledgeAlert,
  canDismissAlert,
  canEvaluateAlerts,
  canResolveAlert,
} from '../../auth/permissions';
type Item = {
  id: string;
  title: string;
  severity: string;
  status: string;
  module: string;
  detected_date: string;
  message: string;
};
export default function AlertsPage() {
  const { user } = useAuth();
  const { campaignId = '' } = useParams();
  const qc = useQueryClient();
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState<Item | null>(null);
  const [note, setNote] = useState('');
  const [action, setAction] = useState('acknowledge');
  const query = useQuery({
    queryKey: ['alerts', campaignId, status],
    queryFn: () =>
      apiRequest<{ items: Item[] }>(
        `/campaigns/${campaignId}/alerts?page=1&page_size=50${status ? '&status=' + status : ''}`,
      ),
  });
  const mutate = useMutation({
    mutationFn: () =>
      apiRequest(`/campaigns/${campaignId}/alerts/${selected?.id}/${action}`, {
        method: 'POST',
        body: JSON.stringify({ action_date: todayDateOnly(), note: note || null }),
      }),
    onSuccess: () => {
      setSelected(null);
      setNote('');
      qc.invalidateQueries({ queryKey: ['alerts', campaignId] });
    },
  });
  const evaluate = useMutation({
    mutationFn: () =>
      apiRequest(`/campaigns/${campaignId}/alerts/evaluate`, {
        method: 'POST',
        body: JSON.stringify({ rule_codes: [], as_of_date: todayDateOnly() }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts', campaignId] }),
  });
  const columns: Column<Item>[] = [
    { key: 'title', label: 'Alerta', render: (x) => x.title },
    { key: 'severity', label: 'Severidad', render: (x) => x.severity },
    { key: 'status', label: 'Estado', render: (x) => x.status },
    { key: 'module', label: 'Módulo', render: (x) => x.module },
    { key: 'detected_date', label: 'Detectada', render: (x) => formatDateOnly(x.detected_date) },
    {
      key: 'id',
      label: 'Acciones',
      render: (x) =>
        canAcknowledgeAlert(user) || canResolveAlert(user) || canDismissAlert(user) ? (
          <Button size="small" onClick={() => setSelected(x)}>
            Gestionar
          </Button>
        ) : (
          'Solo lectura'
        ),
    },
  ];
  return (
    <>
      <PageHeader
        title="Alertas"
        description="Alertas operativas explicables; no son recomendaciones políticas."
        action={
          canEvaluateAlerts(user) ? (
            <Button
              variant="contained"
              disabled={evaluate.isPending}
              onClick={() => evaluate.mutate()}
            >
              Evaluar reglas
            </Button>
          ) : undefined
        }
      />
      <TextField
        select
        label="Estado"
        value={status}
        onChange={(e) => setStatus(e.target.value)}
        sx={{ mb: 2, minWidth: 220 }}
      >
        <MenuItem value="">Todos</MenuItem>
        {['OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'DISMISSED'].map((x) => (
          <MenuItem key={x} value={x}>
            {x}
          </MenuItem>
        ))}
      </TextField>
      {mutate.isError && <Alert severity="error">No se pudo cambiar el estado.</Alert>}
      <DataTable
        columns={columns}
        rows={query.data?.items || []}
        loading={query.isLoading}
        label="Alertas operativas"
      />
      <Dialog open={!!selected} onClose={() => setSelected(null)} fullWidth>
        <DialogTitle>Gestionar alerta</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Alert severity={selected?.severity === 'CRITICAL' ? 'error' : 'warning'}>
              {selected?.message}
            </Alert>
            <TextField
              select
              label="Acción"
              value={action}
              onChange={(e) => setAction(e.target.value)}
            >
              {[
                ...(canAcknowledgeAlert(user) ? [['acknowledge', 'Reconocer']] : []),
                ...(canResolveAlert(user) ? [['resolve', 'Resolver']] : []),
                ...(canDismissAlert(user) ? [['dismiss', 'Descartar']] : []),
              ].map((x) => (
                <MenuItem key={x[0]} value={x[0]}>
                  {x[1]}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              multiline
              minRows={3}
              label="Nota"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelected(null)}>Cancelar</Button>
          <Button variant="contained" onClick={() => mutate.mutate()}>
            Confirmar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
