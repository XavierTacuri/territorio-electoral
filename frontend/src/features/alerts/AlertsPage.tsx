import { useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Pagination,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { StatusBadge } from '../../components/data-display/Common';
import { EmptyState } from '../../components/feedback/States';
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
  rule_code: string;
  evidence?: {
    theme?: string;
    previous_study_id?: string;
    new_study_id?: string;
    comparable_result?: boolean;
    option_label?: string;
    previous_percentage?: number;
    new_percentage?: number;
    difference_points?: number;
  };
};
const percent = (value: number) => `${(value * 100).toFixed(1).replace('.', ',')} %`;
export const SEVERITY_LABELS: Record<string, string> = {
  INFO: 'Información',
  WARNING: 'Requiere atención',
  CRITICAL: 'Crítica',
};
export const ALERT_STATUS_LABELS: Record<string, string> = {
  OPEN: 'Pendiente',
  ACKNOWLEDGED: 'Revisada',
  RESOLVED: 'Resuelta',
  DISMISSED: 'Descartada',
};
const MODULE_LABELS: Record<string, string> = {
  OPERATIONS: 'Operación',
  SURVEYS: 'Encuestas',
  DATA_IMPORTS: 'Datos',
  ELECTORAL_DATA: 'Datos electorales',
  DEMOGRAPHICS: 'Demografía',
  GEOMETRY: 'Geometrías',
  DATA_QUALITY: 'Calidad de datos',
  PUBLIC_INTELLIGENCE: 'Fuentes públicas',
  EVIDENCE: 'Evidencia',
  REPORTS: 'Informes',
};
export default function AlertsPage() {
  const { user } = useAuth();
  const { campaignId = '' } = useParams();
  const qc = useQueryClient();
  const [status, setStatus] = useState('');
  const [module, setModule] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Item | null>(null);
  const [note, setNote] = useState('');
  const [action, setAction] = useState('acknowledge');
  const pageSize = 50;
  const query = useQuery({
    queryKey: ['alerts', campaignId, status, module, page],
    queryFn: () =>
      apiRequest<{ items: Item[]; total: number }>(
        `/campaigns/${campaignId}/alerts?page=${page}&page_size=${pageSize}${status ? '&status=' + status : ''}${module ? '&module=' + module : ''}`,
      ),
  });
  const totalPages = Math.max(1, Math.ceil((query.data?.total ?? 0) / pageSize));
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
    {
      key: 'title',
      label: 'Alerta',
      render: (x) => (
        <Stack spacing={0.25}>
          <span>{x.title}</span>
          {x.rule_code === 'SURVEY_COMPARISON_CHANGE' && x.evidence?.comparable_result && (
            <Typography variant="caption" color="text.secondary">
              {x.evidence.option_label}: {percent(x.evidence.previous_percentage ?? 0)} →{' '}
              {percent(x.evidence.new_percentage ?? 0)} (cambio observado:{' '}
              {(x.evidence.difference_points ?? 0) >= 0 ? '+' : ''}
              {x.evidence.difference_points} puntos)
            </Typography>
          )}
        </Stack>
      ),
    },
    {
      key: 'severity',
      label: 'Severidad',
      render: (x) => <StatusBadge value={SEVERITY_LABELS[x.severity] ?? x.severity} />,
    },
    {
      key: 'status',
      label: 'Estado',
      render: (x) => <StatusBadge value={ALERT_STATUS_LABELS[x.status] ?? x.status} />,
    },
    { key: 'module', label: 'Módulo', render: (x) => MODULE_LABELS[x.module] ?? x.module },
    { key: 'detected_date', label: 'Detectada', render: (x) => formatDateOnly(x.detected_date) },
    {
      key: 'id',
      label: 'Acciones',
      render: (x) => (
        <Stack direction="row" spacing={1}>
          {canAcknowledgeAlert(user) || canResolveAlert(user) || canDismissAlert(user) ? (
            <Button size="small" onClick={() => setSelected(x)}>
              Gestionar
            </Button>
          ) : (
            'Solo lectura'
          )}
          {x.rule_code === 'NEEDS_TOPIC_RECURRENCE' && x.evidence?.theme && (
            <Button
              size="small"
              component={RouterLink}
              to={`/app/campaigns/${campaignId}/reports?type=THEMATIC_REPORT&theme=${x.evidence.theme}`}
            >
              Generar informe temático
            </Button>
          )}
          {x.rule_code === 'SURVEY_COMPARISON_CHANGE' &&
            x.evidence?.previous_study_id &&
            x.evidence?.new_study_id && (
              <Button
                size="small"
                component={RouterLink}
                to={`/app/campaigns/${campaignId}/survey-studies/compare?ids=${x.evidence.previous_study_id},${x.evidence.new_study_id}`}
              >
                Ver comparación
              </Button>
            )}
        </Stack>
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
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          label="Estado"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {Object.entries(ALERT_STATUS_LABELS).map(([code, label]) => (
            <MenuItem key={code} value={code}>
              {label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Módulo"
          value={module}
          onChange={(e) => {
            setModule(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {Object.entries(MODULE_LABELS).map(([code, label]) => (
            <MenuItem key={code} value={code}>
              {label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {mutate.isError && <Alert severity="error">No se pudo cambiar el estado.</Alert>}
      {!query.isLoading && !query.data?.items.length ? (
        <EmptyState
          title="No hay alertas que requieran atención."
          detail="Cuando exista una condición operativa relevante, aparecerá aquí."
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            rows={query.data?.items || []}
            loading={query.isLoading}
            label="Alertas operativas"
          />
          {totalPages > 1 && (
            <Stack direction="row" justifyContent="center" sx={{ mt: 2 }}>
              <Pagination
                count={totalPages}
                page={page}
                onChange={(_, value) => setPage(value)}
                aria-label="Paginación de alertas"
              />
            </Stack>
          )}
        </>
      )}
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
