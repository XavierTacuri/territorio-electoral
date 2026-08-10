import { useState } from 'react';
import { Button, MenuItem, Pagination, Stack, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { formatDateOnly } from '../../lib/dates';
import { ActivityForm, type ActivityFormValue } from './ActivityForm';
import type { Activity, Catalog, Page, Parish } from './types';
export default function ActivitiesPage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [editing, setEditing] = useState<Activity | null>(null);
  const [open, setOpen] = useState(false);
  const params = new URLSearchParams({ page: String(page), page_size: '20' });
  if (search) params.set('search', search);
  if (status) params.set('status', status);
  const list = useQuery({
    queryKey: ['campaign', campaignId, 'activities', page, search, status],
    queryFn: ({ signal }) =>
      apiRequest<Page<Activity>>('/campaigns/' + campaignId + '/activities?' + params, { signal }),
  });
  const types = useQuery({
    queryKey: ['activity-types'],
    queryFn: () => apiRequest<Catalog[]>('/activity-types'),
  });
  const parishes = useQuery({
    queryKey: ['parishes'],
    queryFn: () => apiRequest<Parish[]>('/parishes'),
  });
  const save = useMutation({
    mutationFn: (value: ActivityFormValue) =>
      apiRequest<Activity>(
        '/campaigns/' + campaignId + '/activities' + (editing ? '/' + editing.id : ''),
        {
          method: editing ? 'PATCH' : 'POST',
          body: JSON.stringify({
            ...value,
            latitude: value.latitude === '' ? null : value.latitude,
            longitude: value.longitude === '' ? null : value.longitude,
          }),
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
          {['PLANNED', 'COMPLETED', 'CANCELLED'].map((x) => (
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
          label="actividades"
          loading={list.isLoading}
          rows={list.data?.items ?? []}
          columns={[
            { key: 'title', label: 'Título', render: (x) => <>{x.title}</> },
            { key: 'date', label: 'Fecha', render: (x) => formatDateOnly(x.activity_date) },
            { key: 'status', label: 'Estado', render: (x) => <StatusBadge value={x.status} /> },
            { key: 'parish', label: 'Parroquia', render: (x) => x.parish_id },
          ]}
          onView={(x) => navigate('/app/campaigns/' + campaignId + '/activities/' + x.id)}
          onEdit={async (x) => {
            const full = await apiRequest<Activity>(
              '/campaigns/' + campaignId + '/activities/' + x.id,
            );
            setEditing(full);
            setOpen(true);
          }}
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
          await save.mutateAsync(value);
        }}
      />
    </>
  );
}
