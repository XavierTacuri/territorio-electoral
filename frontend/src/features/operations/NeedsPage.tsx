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
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import type { Activity, Catalog, Need, Page, Parish } from './types';
type NeedForm = {
  activity_id: string;
  need_category_code: string;
  title: string;
  description: string;
  mentions_count: number;
  priority: string;
  status: string;
  parish_id: number;
  source_type: string;
  reported_date: string;
  urgency: string;
  scope: string;
  local_sector_description: string;
  evidence_notes: string;
};
export default function NeedsPage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [parishFilter, setParishFilter] = useState(searchParams.get('parish_id') ?? '');
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
  if (parishFilter) params.set('parish_id', parishFilter);
  const list = useQuery({
    queryKey: ['campaign', campaignId, 'needs', page, status, priority, search, parishFilter],
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
  const parishes = useQuery({
    queryKey: ['parishes'],
    queryFn: () => apiRequest<Parish[]>('/parishes'),
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
              activity_id: editing.activity_id ?? '',
              need_category_code:
                categories.data?.find((x) => x.id === editing.need_category_id)?.code ?? '',
              title: editing.title,
              description: editing.description ?? '',
              mentions_count: editing.mentions_count,
              priority: editing.priority,
              status: editing.status,
              parish_id: editing.parish_id,
              source_type: editing.source_type,
              reported_date: editing.reported_date,
              urgency: editing.urgency,
              scope: editing.scope,
              local_sector_description: '',
              evidence_notes: '',
            }
          : {
              activity_id: activities.data?.items[0]?.id ?? '',
              need_category_code: categories.data?.[0]?.code ?? '',
              title: '',
              description: '',
              mentions_count: 1,
              priority: 'MEDIUM',
              status: 'REPORTED',
              parish_id: parishes.data?.[0]?.id ?? 0,
              source_type: 'OTHER',
              reported_date: new Date().toISOString().slice(0, 10),
              urgency: 'MEDIUM',
              scope: 'PARISH',
              local_sector_description: '',
              evidence_notes: '',
            },
      );
    setError('');
  }, [open, editing, categories.data, activities.data, parishes.data, reset]);
  const save = useMutation({
    mutationFn: (v: NeedForm) =>
      apiRequest<Need>(
        editing
          ? '/campaigns/' + campaignId + '/needs/' + editing.id
          : v.activity_id
            ? '/campaigns/' + campaignId + '/activities/' + v.activity_id + '/needs'
            : '/campaigns/' + campaignId + '/needs',
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
                }
              : {
                  need_category_code: v.need_category_code,
                  title: v.title,
                  description: v.description || null,
                  mentions_count: Number(v.mentions_count),
                  priority: v.priority,
                  status: 'REPORTED',
                  parish_id: Number(v.parish_id),
                  source_type: v.source_type,
                  reported_date: v.reported_date,
                  urgency: v.urgency,
                  scope: v.scope,
                  local_sector_description: v.scope === 'LOCAL' ? v.local_sector_description : null,
                  evidence_notes: v.evidence_notes || null,
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
        <TextField
          select
          label="Parroquia"
          value={parishFilter}
          onChange={(e) => setParishFilter(e.target.value)}
          sx={{ minWidth: 190 }}
        >
          <MenuItem value="">Todas</MenuItem>
          {parishes.data?.map((x) => (
            <MenuItem key={x.id} value={String(x.id)}>
              {x.name}
            </MenuItem>
          ))}
        </TextField>
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
          {['REPORTED', 'UNDER_REVIEW', 'VALIDATED', 'IN_PLAN', 'CLOSED', 'ARCHIVED'].map((x) => (
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
          onView={(x) => navigate(`/app/campaigns/${campaignId}/needs/${x.id}`)}
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
                label="Parroquia"
                defaultValue=""
                {...register('parish_id', { valueAsNumber: true })}
                InputLabelProps={{ shrink: true }}
              >
                {parishes.data?.map((x) => (
                  <MenuItem key={x.id} value={x.id}>
                    {x.name}
                  </MenuItem>
                ))}
              </TextField>
            )}
            {!editing && (
              <TextField
                select
                label="Actividad relacionada (opcional)"
                defaultValue=""
                {...register('activity_id')}
                InputLabelProps={{ shrink: true }}
              >
                <MenuItem value="">Registro directo</MenuItem>
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
            {!editing && (
              <>
                <TextField select label="Origen" defaultValue="OTHER" {...register('source_type')}>
                  {[
                    'ASSEMBLY',
                    'COMMUNITY_MEETING',
                    'FIELD_VISIT',
                    'CAMPAIGN_ACTIVITY',
                    'CITIZEN_REPORT',
                    'TEAM_REPORT',
                    'OTHER',
                  ].map((x) => (
                    <MenuItem key={x} value={x}>
                      {x}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  type="date"
                  label="Fecha"
                  InputLabelProps={{ shrink: true }}
                  {...register('reported_date')}
                />
                <TextField select label="Urgencia" defaultValue="MEDIUM" {...register('urgency')}>
                  {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((x) => (
                    <MenuItem key={x} value={x}>
                      {x}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField select label="Alcance" defaultValue="PARISH" {...register('scope')}>
                  <MenuItem value="LOCAL">Sector/local</MenuItem>
                  <MenuItem value="PARISH">Parroquial</MenuItem>
                  <MenuItem value="CANTON">Cantonal</MenuItem>
                </TextField>
                <TextField
                  label="Sector (si el alcance es local)"
                  {...register('local_sector_description')}
                />
                <TextField multiline label="Evidencia o notas" {...register('evidence_notes')} />
              </>
            )}
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
