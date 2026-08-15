import { useState } from 'react';
import { Button, MenuItem, Pagination, Stack, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { useCampaign } from '../../app/CampaignProvider';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { formatDateOnly } from '../../lib/dates';
import { ActivityForm, type ActivityFormValue } from './ActivityForm';
import {
  APPROVAL_STATUS_LABELS,
  EXECUTION_STATUS_LABELS,
  operationStatusLabel,
} from './statusLabels';
import type { Activity, Catalog, Page, Parish } from './types';
export default function ActivitiesPage() {
  const { campaignId = '' } = useParams();
  const { active } = useCampaign();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [approval, setApproval] = useState('');
  const [editing, setEditing] = useState<Activity | null>(null);
  const [open, setOpen] = useState(false);
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
