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
import { Navigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { useAuth } from '../../auth/AuthProvider';
import { canManageUsers } from '../../auth/permissions';
import { StatusBadge } from '../../components/data-display/Common';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { formatDateOnly } from '../../lib/dates';
import type { DataSource } from './SourcesPage';

const MILESTONE_TYPES = [
  'CONVOCATORIA',
  'CANDIDATE_REGISTRATION',
  'CAMPAIGN_PERIOD',
  'DEBATE',
  'ELECTORAL_SILENCE',
  'ELECTION_DAY',
  'VOTE_COUNT',
  'OTHER',
] as const;
const MILESTONE_TYPE_LABELS: Record<string, string> = {
  CONVOCATORIA: 'Convocatoria',
  CANDIDATE_REGISTRATION: 'Inscripción de candidaturas',
  CAMPAIGN_PERIOD: 'Campaña electoral',
  DEBATE: 'Debate',
  ELECTORAL_SILENCE: 'Silencio electoral',
  ELECTION_DAY: 'Elección',
  VOTE_COUNT: 'Escrutinio',
  OTHER: 'Otro hito',
};

type Process = { id: string; code: string; name: string };
type Milestone = {
  id: string;
  electoral_process_id: string;
  title: string;
  description: string | null;
  milestone_type: string;
  starts_at: string;
  ends_at: string | null;
  source_id: string;
  source_url: string | null;
  status: string;
};

function messageFor(error: unknown) {
  if (!(error instanceof ApiError)) return 'No se pudo guardar el hito electoral.';
  if (error.status === 409)
    return 'Ya existe un hito idéntico para este proceso (mismo tipo, fecha y título).';
  if (error.status === 422) return 'Revisa los campos indicados.';
  if (error.status === 403) return 'No tienes permisos para administrar el calendario oficial.';
  return 'No se pudo guardar el hito electoral.';
}

export default function ElectoralMilestonesPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    electoral_process_id: '',
    title: '',
    milestone_type: 'OTHER' as (typeof MILESTONE_TYPES)[number],
    starts_at: '',
    source_id: '',
    source_url: '',
  });
  const milestones = useQuery({
    queryKey: ['electoral-milestones'],
    queryFn: () => apiRequest<Milestone[]>('/electoral-milestones'),
  });
  const processes = useQuery({
    queryKey: ['electoral-processes-for-milestones'],
    queryFn: () => apiRequest<Process[]>('/electoral-processes'),
  });
  const sources = useQuery({
    queryKey: ['data-sources-for-milestones'],
    queryFn: () => apiRequest<DataSource[]>('/data-sources'),
  });
  const create = useMutation({
    mutationFn: () =>
      apiRequest<Milestone>('/electoral-milestones', {
        method: 'POST',
        body: JSON.stringify({
          electoral_process_id: form.electoral_process_id,
          title: form.title.trim(),
          milestone_type: form.milestone_type,
          starts_at: new Date(form.starts_at).toISOString(),
          source_id: form.source_id,
          source_url: form.source_url || null,
        }),
      }),
    onSuccess: async () => {
      setOpen(false);
      setForm({ ...form, title: '', starts_at: '' });
      await queryClient.invalidateQueries({ queryKey: ['electoral-milestones'] });
    },
    onError: (reason) => setError(messageFor(reason)),
  });
  const setStatus = useMutation({
    mutationFn: (payload: { id: string; status: 'ACTIVE' | 'ARCHIVED' }) =>
      apiRequest<Milestone>(
        `/electoral-milestones/${payload.id}/${payload.status === 'ACTIVE' ? 'activate' : 'archive'}`,
        { method: 'POST' },
      ),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['electoral-milestones'] }),
  });
  if (!canManageUsers(user)) return <Navigate to="/403" replace />;
  const processName = (id: string) => processes.data?.find((p) => p.id === id)?.name ?? id;
  return (
    <>
      <PageHeader
        title="Calendario electoral oficial"
        description="Hitos oficiales del proceso electoral, verificables y con procedencia (fuente y documento)."
        action={
          <Button
            variant="contained"
            disabled={!processes.data?.length || !sources.data?.length}
            onClick={() => {
              setError('');
              setOpen(true);
            }}
          >
            Nuevo hito
          </Button>
        }
      />
      {milestones.isLoading ? (
        <LoadingSkeleton />
      ) : milestones.isError ? (
        <ErrorState retry={() => milestones.refetch()} />
      ) : !milestones.data?.length ? (
        <EmptyState
          title="No hay hitos electorales registrados."
          detail="Crea el primer hito oficial para que aparezca en el calendario de las campañas correspondientes."
        />
      ) : (
        <DataTable
          label="hitos electorales"
          rows={milestones.data}
          columns={[
            { key: 'title', label: 'Título', render: (x) => x.title },
            {
              key: 'type',
              label: 'Tipo',
              render: (x) => MILESTONE_TYPE_LABELS[x.milestone_type] ?? x.milestone_type,
            },
            {
              key: 'process',
              label: 'Proceso',
              render: (x) => processName(x.electoral_process_id),
            },
            {
              key: 'starts',
              label: 'Fecha',
              render: (x) => formatDateOnly(x.starts_at.slice(0, 10)),
            },
            { key: 'status', label: 'Estado', render: (x) => <StatusBadge value={x.status} /> },
            {
              key: 'actions',
              label: 'Acciones',
              render: (x) => (
                <Button
                  size="small"
                  onClick={() =>
                    setStatus.mutate({
                      id: x.id,
                      status: x.status === 'ACTIVE' ? 'ARCHIVED' : 'ACTIVE',
                    })
                  }
                >
                  {x.status === 'ACTIVE' ? 'Archivar' : 'Activar'}
                </Button>
              ),
            },
          ]}
        />
      )}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Nuevo hito electoral oficial</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              select
              label="Proceso electoral"
              value={form.electoral_process_id}
              onChange={(e) => setForm({ ...form, electoral_process_id: e.target.value })}
            >
              {processes.data?.map((p) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.name} ({p.code})
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Título"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
            <TextField
              select
              label="Tipo de hito"
              value={form.milestone_type}
              onChange={(e) =>
                setForm({
                  ...form,
                  milestone_type: e.target.value as (typeof MILESTONE_TYPES)[number],
                })
              }
            >
              {MILESTONE_TYPES.map((t) => (
                <MenuItem key={t} value={t}>
                  {MILESTONE_TYPE_LABELS[t]}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Fecha y hora"
              type="datetime-local"
              InputLabelProps={{ shrink: true }}
              value={form.starts_at}
              onChange={(e) => setForm({ ...form, starts_at: e.target.value })}
            />
            <TextField
              select
              label="Fuente oficial"
              value={form.source_id}
              onChange={(e) => setForm({ ...form, source_id: e.target.value })}
            >
              {sources.data?.map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.institution} · {s.dataset_name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="URL del documento (opcional)"
              value={form.source_url}
              onChange={(e) => setForm({ ...form, source_url: e.target.value })}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={
              create.isPending ||
              !form.electoral_process_id ||
              !form.title.trim() ||
              !form.starts_at ||
              !form.source_id
            }
            onClick={() => create.mutate()}
          >
            {create.isPending ? 'Guardando…' : 'Crear hito'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
