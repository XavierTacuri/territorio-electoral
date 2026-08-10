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
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import type { Activity, Catalog, Need, Page } from './types';
type NeedForm = {
  activity_id: string;
  need_category_code: string;
  title: string;
  description: string;
  mentions_count: number;
  priority: string;
  status: string;
};
export default function NeedsPage() {
  const { campaignId = '' } = useParams();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Need | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const params = new URLSearchParams({ page: String(page), page_size: '20' });
  if (status) params.set('status', status);
  if (priority) params.set('priority', priority);
  if (search) params.set('search', search);
  const list = useQuery({
    queryKey: ['campaign', campaignId, 'needs', page, status, priority, search],
    queryFn: ({ signal }) =>
      apiRequest<Page<Need>>('/campaigns/' + campaignId + '/needs?' + params, { signal }),
  });
  const categories = useQuery({
    queryKey: ['need-categories'],
    queryFn: () => apiRequest<Catalog[]>('/need-categories'),
  });
  const activities = useQuery({
    queryKey: ['campaign', campaignId, 'activities-options'],
    queryFn: () =>
      apiRequest<Page<Activity>>('/campaigns/' + campaignId + '/activities?page_size=100'),
  });
  const {
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting },
  } = useForm<NeedForm>();
  useEffect(() => {
    if (open)
      reset(
        editing
          ? {
              activity_id: editing.activity_id,
              need_category_code:
                categories.data?.find((x) => x.id === editing.need_category_id)?.code ?? '',
              title: editing.title,
              description: editing.description ?? '',
              mentions_count: editing.mentions_count,
              priority: editing.priority,
              status: editing.status,
            }
          : {
              activity_id: activities.data?.items[0]?.id ?? '',
              need_category_code: categories.data?.[0]?.code ?? '',
              title: '',
              description: '',
              mentions_count: 1,
              priority: 'MEDIUM',
              status: 'IDENTIFIED',
            },
      );
    setError('');
  }, [open, editing, categories.data, activities.data, reset]);
  const save = useMutation({
    mutationFn: (v: NeedForm) =>
      apiRequest<Need>(
        editing
          ? '/campaigns/' + campaignId + '/needs/' + editing.id
          : '/campaigns/' + campaignId + '/activities/' + v.activity_id + '/needs',
        {
          method: editing ? 'PATCH' : 'POST',
          body: JSON.stringify(
            editing
              ? {
                  need_category_code: v.need_category_code,
                  title: v.title,
                  description: v.description || null,
                  mentions_count: Number(v.mentions_count),
                  priority: v.priority,
                  status: v.status,
                }
              : {
                  need_category_code: v.need_category_code,
                  title: v.title,
                  description: v.description || null,
                  mentions_count: Number(v.mentions_count),
                  priority: v.priority,
                  status: v.status,
                },
          ),
        },
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'needs'] }),
  });
  return (
    <>
      <PageHeader
        title="Necesidades"
        description="Necesidades agregadas; no representan intención de voto."
        action={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => {
              setEditing(null);
              setOpen(true);
            }}
          >
            Registrar necesidad
          </Button>
        }
      />
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField label="Buscar" value={search} onChange={(e) => setSearch(e.target.value)} />
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
        <TextField
          select
          label="Estado"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          sx={{ minWidth: 190 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {['IDENTIFIED', 'UNDER_REVIEW', 'INCLUDED_IN_PLAN', 'DISCARDED'].map((x) => (
            <MenuItem key={x} value={x}>
              {x}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {list.isError ? (
        <ErrorState retry={() => list.refetch()} />
      ) : (
        <DataTable
          label="necesidades"
          loading={list.isLoading}
          rows={list.data?.items ?? []}
          columns={[
            { key: 'title', label: 'Necesidad', render: (x) => x.title },
            { key: 'mentions', label: 'Menciones', render: (x) => x.mentions_count },
            {
              key: 'priority',
              label: 'Prioridad',
              render: (x) => <StatusBadge value={x.priority} />,
            },
            { key: 'status', label: 'Estado', render: (x) => <StatusBadge value={x.status} /> },
          ]}
          onView={async (x) => {
            setEditing(await apiRequest<Need>('/campaigns/' + campaignId + '/needs/' + x.id));
            setOpen(true);
          }}
          onEdit={async (x) => {
            setEditing(await apiRequest<Need>('/campaigns/' + campaignId + '/needs/' + x.id));
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
        <DialogTitle>{editing ? 'Editar necesidad' : 'Registrar necesidad'}</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error">{error}</Alert>}
          <Stack spacing={2} sx={{ mt: 1 }}>
            {!editing && (
              <TextField
                select
                label="Actividad"
                defaultValue=""
                {...register('activity_id')}
                InputLabelProps={{ shrink: true }}
              >
                {activities.data?.items.map((x) => (
                  <MenuItem key={x.id} value={x.id}>
                    {x.title}
                  </MenuItem>
                ))}
              </TextField>
            )}
            <TextField
              select
              label="Categoría"
              defaultValue=""
              {...register('need_category_code')}
              InputLabelProps={{ shrink: true }}
            >
              {categories.data?.map((x) => (
                <MenuItem key={x.id} value={x.code}>
                  {x.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField label="Título" {...register('title', { required: true })} />
            <TextField multiline minRows={3} label="Descripción" {...register('description')} />
            <TextField
              type="number"
              label="Conteo de menciones"
              {...register('mentions_count', { valueAsNumber: true, min: 1 })}
            />
            <TextField select label="Prioridad" defaultValue="MEDIUM" {...register('priority')}>
              {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((x) => (
                <MenuItem key={x} value={x}>
                  {x}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label="Estado" defaultValue="IDENTIFIED" {...register('status')}>
              {['IDENTIFIED', 'UNDER_REVIEW', 'INCLUDED_IN_PLAN', 'DISCARDED'].map((x) => (
                <MenuItem key={x} value={x}>
                  {x}
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
                setError('No se pudo guardar la necesidad.');
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
