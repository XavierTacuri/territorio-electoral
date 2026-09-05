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
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { useCampaign } from '../../app/CampaignProvider';
import { ErrorState } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { needSourceLabels } from '../../lib/labels';
import type { Activity, Catalog, Need, Page, Parish } from './types';
import { parishOptionLabel } from '../../lib/territoryLabels';
type NeedForm = {
  activity_id: string;
  need_category_code: string;
  title: string;
  description: string;
  parish_id: number;
  source_type: string;
  reported_date: string;
  urgency: string;
  scope: string;
  local_sector_description: string;
  evidence_notes: string;
};
export const NEED_TABLE_HEADERS = ['Necesidad', 'Parroquia', 'Origen', 'Acciones'] as const;
export default function NeedsPage() {
  const { campaignId = '' } = useParams();
  const { active } = useCampaign();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [parishFilter, setParishFilter] = useState(searchParams.get('parish_id') ?? '');
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Need | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const params = new URLSearchParams({ page: String(page), page_size: '20' });
  if (search) params.set('search', search);
  if (parishFilter) params.set('parish_id', parishFilter);
  const list = useQuery({
    queryKey: ['campaign', campaignId, 'needs', page, search, parishFilter],
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
    queryKey: ['parishes', active?.canton_id],
    queryFn: () => apiRequest<Parish[]>('/parishes?canton_id=' + active!.canton_id),
    enabled: Boolean(active?.canton_id),
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
                }
              : {
                  need_category_code: v.need_category_code,
                  title: v.title,
                  description: v.description || null,
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
        description="Temas registrados por el equipo durante el trabajo territorial de la campaña."
        action={
          <Stack direction={{ xs: 'column', sm: 'row' }} gap={1}>
            <Button component={RouterLink} to={`/app/campaigns/${campaignId}/reports?type=THEMATIC_REPORT`}>
              Generar informe temático
            </Button>
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
          </Stack>
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
              {parishOptionLabel(x, parishes.data ?? [])}
            </MenuItem>
          ))}
        </TextField>
        <TextField label="Buscar" value={search} onChange={(e) => setSearch(e.target.value)} />
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
            {
              key: 'parish',
              label: 'Parroquia',
              render: (x) => parishes.data?.find((p) => p.id === x.parish_id)?.name ?? 'No disponible',
            },
            {
              key: 'source',
              label: 'Origen',
              render: (x) => x.activity_id ? 'Actividad relacionada' : (needSourceLabels[x.source_type] ?? 'Registro manual'),
            },
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
                    {parishOptionLabel(x, parishes.data ?? [])}
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
                    {needSourceLabels[x] ?? 'No disponible'}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  type="date"
                  label="Fecha"
                  InputLabelProps={{ shrink: true }}
                  {...register('reported_date')}
                />
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
