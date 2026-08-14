import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Pagination,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useForm } from 'react-hook-form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { formatDateOnly, todayDateOnly } from '../../lib/dates';
import { operationStatusLabel } from './statusLabels';
import type { Commitment, Page, Parish } from './types';
type Form = {
  title: string;
  description: string;
  priority: string;
  status: string;
  due_date: string;
  completed_date: string;
  parish_id: number;
  responsible_user_id: string;
};
const overdueDays = (date?: string | null, status?: string) => {
  if (!date || status === 'COMPLETED' || date >= todayDateOnly()) return 0;
  const [y, m, d] = date.split('-').map(Number);
  const [ty, tm, td] = todayDateOnly().split('-').map(Number);
  return Math.floor((Date.UTC(ty, tm - 1, td) - Date.UTC(y, m - 1, d)) / 86400000);
};
export default function CommitmentsPage() {
  const { campaignId = '' } = useParams();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const [overdue, setOverdue] = useState(false);
  const [editing, setEditing] = useState<Commitment | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const params = new URLSearchParams({
    page: String(page),
    page_size: '20',
    overdue: String(overdue),
  });
  if (status) params.set('status', status);
  if (priority) params.set('priority', priority);
  const list = useQuery({
    queryKey: ['campaign', campaignId, 'commitments', page, status, priority, overdue],
    queryFn: ({ signal }) =>
      apiRequest<Page<Commitment>>('/campaigns/' + campaignId + '/commitments?' + params, {
        signal,
      }),
  });
  const parishes = useQuery({
    queryKey: ['parishes'],
    queryFn: () => apiRequest<Parish[]>('/parishes'),
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
              priority: editing.priority,
              status: editing.status,
              due_date: editing.due_date ?? '',
              completed_date: editing.completed_date ?? '',
              parish_id: editing.parish_id,
              responsible_user_id: editing.responsible_user_id ?? '',
            }
          : {
              title: '',
              description: '',
              priority: 'MEDIUM',
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
          body: JSON.stringify({
            ...v,
            due_date: v.due_date || null,
            completed_date: v.status === 'COMPLETED' ? v.completed_date || todayDateOnly() : null,
            responsible_user_id: v.responsible_user_id || null,
          }),
        },
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'commitments'] }),
  });
  return (
    <>
      <PageHeader
        title="Compromisos"
        description="Seguimiento de fechas límite, responsables autorizados y cumplimiento."
        action={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => {
              setEditing(null);
              setOpen(true);
            }}
          >
            Crear compromiso
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
              {operationStatusLabel(x)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Prioridad"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">Todas</MenuItem>
          {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((x) => (
            <MenuItem key={x} value={x}>
              {x}
            </MenuItem>
          ))}
        </TextField>
        <FormControlLabel
          control={<Switch checked={overdue} onChange={(e) => setOverdue(e.target.checked)} />}
          label="Solo vencidos"
        />
      </Stack>
      {list.isError ? (
        <ErrorState retry={() => list.refetch()} />
      ) : (
        <DataTable
          label="compromisos"
          loading={list.isLoading}
          rows={list.data?.items ?? []}
          columns={[
            { key: 'title', label: 'Compromiso', render: (x) => x.title },
            {
              key: 'due',
              label: 'Fecha límite',
              render: (x) => (
                <>
                  {formatDateOnly(x.due_date)}
                  {overdueDays(x.due_date, x.status) > 0 && (
                    <Typography color="error" variant="caption" display="block">
                      {overdueDays(x.due_date, x.status)} días de retraso
                    </Typography>
                  )}
                </>
              ),
            },
            {
              key: 'priority',
              label: 'Prioridad',
              render: (x) => <StatusBadge value={x.priority} />,
            },
            {
              key: 'status',
              label: 'Estado',
              render: (x) => <StatusBadge value={operationStatusLabel(x.status)} />,
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
        <DialogTitle>{editing ? 'Editar compromiso' : 'Crear compromiso'}</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error">{error}</Alert>}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Título" {...register('title', { required: true })} />
            <TextField label="Descripción" multiline minRows={3} {...register('description')} />
            <TextField select label="Prioridad" defaultValue="MEDIUM" {...register('priority')}>
              {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((x) => (
                <MenuItem key={x} value={x}>
                  {x}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label="Estado" defaultValue="PENDING" {...register('status')}>
              {['PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'].map((x) => (
                <MenuItem key={x} value={x}>
                  {operationStatusLabel(x)}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              type="date"
              label="Fecha límite"
              InputLabelProps={{ shrink: true }}
              {...register('due_date')}
            />
            {formStatus === 'COMPLETED' && (
              <TextField
                type="date"
                label="Fecha de cumplimiento"
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
                  {x.name}
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
                setError('No se pudo guardar el compromiso.');
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
