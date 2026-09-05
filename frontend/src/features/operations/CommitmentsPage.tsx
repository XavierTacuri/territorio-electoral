import { useEffect, useState } from 'react';
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
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useForm } from 'react-hook-form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { useCampaign } from '../../app/CampaignProvider';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { todayDateOnly } from '../../lib/dates';
import { followUpStatusLabel } from './statusLabels';
import type { Commitment, Page, Parish } from './types';
import { parishOptionLabel } from '../../lib/territoryLabels';
type Form = {
  title: string;
  description: string;
  status: string;
  due_date: string;
  completed_date: string;
  parish_id: number;
  responsible_user_id: string;
};
export const FOLLOW_UP_TABLE_HEADERS = [
  'Seguimiento',
  'Responsable',
  'Origen',
  'Estado',
  'Acciones',
] as const;

export function followUpPayload(v: Form) {
  return {
    ...v,
    due_date: v.due_date || null,
    completed_date: v.status === 'COMPLETED' ? v.completed_date || todayDateOnly() : null,
    responsible_user_id: v.responsible_user_id || null,
  };
}
export default function CommitmentsPage() {
  const { campaignId = '' } = useParams();
  const { active } = useCampaign();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [editing, setEditing] = useState<Commitment | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const params = new URLSearchParams({
    page: String(page),
    page_size: '20',
  });
  if (status) params.set('status', status);
  const list = useQuery({
    queryKey: ['campaign', campaignId, 'commitments', page, status],
    queryFn: ({ signal }) =>
      apiRequest<Page<Commitment>>('/campaigns/' + campaignId + '/commitments?' + params, {
        signal,
      }),
  });
  const parishes = useQuery({
    queryKey: ['parishes', active?.canton_id],
    queryFn: () => apiRequest<Parish[]>('/parishes?canton_id=' + active!.canton_id),
    enabled: Boolean(active?.canton_id),
  });
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { isSubmitting },
  } = useForm<Form>();
  const formStatus = watch('status');
  useEffect(() => {
    if (open)
      reset(
        editing
          ? {
              title: editing.title,
              description: editing.description ?? '',
              status: editing.status,
              due_date: editing.due_date ?? '',
              completed_date: editing.completed_date ?? '',
              parish_id: editing.parish_id,
              responsible_user_id: editing.responsible_user_id ?? '',
            }
          : {
              title: '',
              description: '',
              status: 'PENDING',
              due_date: '',
              completed_date: '',
              parish_id: parishes.data?.[0]?.id ?? 0,
              responsible_user_id: '',
            },
      );
    setError('');
  }, [open, editing, parishes.data, reset]);
  const save = useMutation({
    mutationFn: (v: Form) =>
      apiRequest<Commitment>(
        '/campaigns/' + campaignId + '/commitments' + (editing ? '/' + editing.id : ''),
        {
          method: editing ? 'PATCH' : 'POST',
          body: JSON.stringify(followUpPayload(v)),
        },
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'commitments'] }),
  });
  return (
    <>
      <PageHeader
        title="Seguimientos de campaña"
        description="Acciones internas para que el equipo revise y dé continuidad a asuntos del territorio."
        action={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => {
              setEditing(null);
              setOpen(true);
            }}
          >
            Crear seguimiento
          </Button>
        }
      />
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          label="Estado"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {['PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'].map((x) => (
            <MenuItem key={x} value={x}>
              {followUpStatusLabel(x)}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {list.isError ? (
        <ErrorState retry={() => list.refetch()} />
      ) : (
        <DataTable
          label="seguimientos de campaña"
          loading={list.isLoading}
          rows={list.data?.items ?? []}
          columns={[
            { key: 'title', label: 'Seguimiento', render: (x) => x.title },
            {
              key: 'responsible',
              label: 'Responsable',
              render: (x) =>
                x.responsible_name ??
                (x.responsible_user_id ? 'Responsable asignado' : 'Sin asignar'),
            },
            {
              key: 'origin',
              label: 'Origen',
              render: (x) =>
                x.activity_id
                  ? 'Actividad relacionada'
                  : x.need_id
                    ? 'Necesidad registrada'
                    : 'Registro manual',
            },
            {
              key: 'status',
              label: 'Estado',
              render: (x) => <StatusBadge value={followUpStatusLabel(x.status)} />,
            },
          ]}
          onEdit={async (x) => {
            setEditing(
              await apiRequest<Commitment>('/campaigns/' + campaignId + '/commitments/' + x.id),
            );
            setOpen(true);
          }}
        />
      )}
      <Pagination
        sx={{ mt: 2 }}
        page={page}
        count={list.data?.total_pages ?? 0}
        onChange={(_, v) => setPage(v)}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth>
        <DialogTitle>{editing ? 'Editar seguimiento' : 'Crear seguimiento'}</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error">{error}</Alert>}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Título" {...register('title', { required: true })} />
            <TextField label="Descripción" multiline minRows={3} {...register('description')} />
            <TextField select label="Estado" defaultValue="PENDING" {...register('status')}>
              {['PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'].map((x) => (
                <MenuItem key={x} value={x}>
                  {followUpStatusLabel(x)}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              type="date"
              label="Fecha de seguimiento (opcional)"
              InputLabelProps={{ shrink: true }}
              {...register('due_date')}
            />
            {formStatus === 'COMPLETED' && (
              <TextField
                type="date"
                label="Fecha de realización"
                InputLabelProps={{ shrink: true }}
                {...register('completed_date')}
              />
            )}
            <TextField
              select
              label="Parroquia"
              defaultValue=""
              {...register('parish_id', { valueAsNumber: true })}
            >
              {parishes.data?.map((x) => (
                <MenuItem key={x.id} value={x.id}>
                  {parishOptionLabel(x, parishes.data ?? [])}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={isSubmitting}
            onClick={handleSubmit(async (v) => {
              try {
                await save.mutateAsync(v);
                setOpen(false);
              } catch {
                setError('No se pudo guardar el seguimiento.');
              }
            })}
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
