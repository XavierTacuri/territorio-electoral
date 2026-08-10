import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Link,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Navigate, Link as RouterLink } from 'react-router-dom';
import { z } from 'zod';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { useAuth } from '../../auth/AuthProvider';
import { canManageUsers } from '../../auth/permissions';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { formatDateOnly, parseDateOnly } from '../../lib/dates';

export const DATASET_TYPES = [
  'CNE_ELECTORAL_RESULTS',
  'CNE_CANDIDATES',
  'CNE_POLITICAL_ORGANIZATIONS',
  'CNE_TURNOUT',
  'CNE_ELECTORAL_ROLL_SNAPSHOT',
  'INEC_DEMOGRAPHIC_INDICATORS',
  'INEC_POPULATION_PROJECTIONS',
  'INEC_GEOGRAPHIC_CLASSIFIER',
  'OTHER_AGGREGATED_OFFICIAL',
] as const;
type DatasetType = (typeof DATASET_TYPES)[number];
export const datasetLabels: Record<DatasetType, string> = {
  CNE_ELECTORAL_ROLL_SNAPSHOT: 'CNE · Registro electoral preelectoral',
  CNE_ELECTORAL_RESULTS: 'CNE · Resultados electorales',
  CNE_CANDIDATES: 'CNE · Candidaturas',
  CNE_POLITICAL_ORGANIZATIONS: 'CNE · Organizaciones políticas',
  CNE_TURNOUT: 'CNE · Participación electoral',
  INEC_DEMOGRAPHIC_INDICATORS: 'INEC · Indicadores demográficos',
  INEC_POPULATION_PROJECTIONS: 'INEC · Proyecciones poblacionales',
  INEC_GEOGRAPHIC_CLASSIFIER: 'INEC · Clasificador geográfico',
  OTHER_AGGREGATED_OFFICIAL: 'Otra fuente oficial agregada',
};
export type DataSource = {
  id: string;
  code: string;
  institution: string;
  dataset_name: string;
  dataset_type: DatasetType;
  official_url: string | null;
  publication_date: string | null;
  reference_date: string | null;
  reference_year: number | null;
  license_or_terms: string | null;
  description: string | null;
  is_official: boolean;
  is_active: boolean;
};

const optionalDate = z
  .string()
  .refine((value) => !value || parseDateOnly(value), 'Usa DD/MM/AAAA.');
export const sourceSchema = z.object({
  code: z.string().trim().min(1, 'El código es obligatorio.'),
  institution: z.string().trim().min(1, 'La institución es obligatoria.'),
  dataset_name: z.string().trim().min(1, 'El nombre del conjunto es obligatorio.'),
  dataset_type: z.enum(DATASET_TYPES),
  official_url: z.union([z.literal(''), z.string().url('Ingresa una URL válida.')]),
  publication_date: optionalDate,
  reference_date: optionalDate,
  reference_year: z.union([z.literal(''), z.string().regex(/^\d{4}$/, 'Ingresa un año válido.')]),
  license_or_terms: z.string(),
  description: z.string(),
  is_official: z.boolean(),
  is_active: z.boolean(),
});
type SourceForm = z.infer<typeof sourceSchema>;
const defaults: SourceForm = {
  code: '',
  institution: '',
  dataset_name: '',
  dataset_type: 'OTHER_AGGREGATED_OFFICIAL',
  official_url: '',
  publication_date: '',
  reference_date: '',
  reference_year: '',
  license_or_terms: '',
  description: '',
  is_official: true,
  is_active: true,
};

export function sourcePayload(values: SourceForm, editing: boolean) {
  const common = {
    institution: values.institution.trim(),
    dataset_name: values.dataset_name.trim(),
    official_url: values.official_url || null,
    publication_date: values.publication_date ? parseDateOnly(values.publication_date) : null,
    reference_date: values.reference_date ? parseDateOnly(values.reference_date) : null,
    reference_year: values.reference_year ? Number(values.reference_year) : null,
    license_or_terms: values.license_or_terms.trim() || null,
    description: values.description.trim() || null,
    is_official: values.is_official,
  };
  return editing
    ? { ...common, is_active: values.is_active }
    : { ...common, code: values.code.trim(), dataset_type: values.dataset_type };
}

function messageFor(error: unknown) {
  if (!(error instanceof ApiError)) return 'No se pudo guardar la fuente de datos.';
  if (error.status === 409) return 'Ya existe una fuente con este código.';
  if (error.status === 422) return 'Revisa los campos indicados.';
  if (error.status === 403) return 'No tienes permisos para administrar fuentes de datos.';
  if (error.status === 404) return 'La fuente de datos no existe.';
  const detail = (error.detail as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' ? detail : error.message;
}

export default function SourcesPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<DataSource | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const sources = useQuery({
    queryKey: ['data-sources'],
    queryFn: () => apiRequest<DataSource[]>('/data-sources'),
  });
  const form = useForm<SourceForm>({
    resolver: zodResolver(sourceSchema),
    defaultValues: defaults,
  });
  const show = (source?: DataSource) => {
    setEditing(source ?? null);
    setError('');
    form.reset(
      source
        ? {
            code: source.code,
            institution: source.institution,
            dataset_name: source.dataset_name,
            dataset_type: source.dataset_type,
            official_url: source.official_url ?? '',
            publication_date: source.publication_date
              ? formatDateOnly(source.publication_date)
              : '',
            reference_date: source.reference_date ? formatDateOnly(source.reference_date) : '',
            reference_year: source.reference_year ? String(source.reference_year) : '',
            license_or_terms: source.license_or_terms ?? '',
            description: source.description ?? '',
            is_official: source.is_official,
            is_active: source.is_active,
          }
        : defaults,
    );
    setOpen(true);
  };
  const save = useMutation({
    mutationFn: (values: SourceForm) =>
      apiRequest<DataSource>(editing ? `/data-sources/${editing.id}` : '/data-sources', {
        method: editing ? 'PATCH' : 'POST',
        body: JSON.stringify(sourcePayload(values, !!editing)),
      }),
    onSuccess: async () => {
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: ['data-sources'] });
    },
    onError: (reason) => {
      if (reason instanceof ApiError && reason.status === 422) {
        const issues = (reason.detail as { detail?: Array<{ loc?: unknown[]; msg?: string }> })
          ?.detail;
        issues?.forEach((issue) => {
          const field = issue.loc?.at(-1);
          if (typeof field === 'string' && field in defaults)
            form.setError(field as keyof SourceForm, { message: issue.msg ?? 'Valor inválido.' });
        });
      }
      setError(messageFor(reason));
    },
  });
  const toggle = async (source: DataSource) => {
    await apiRequest(`/data-sources/${source.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: !source.is_active }),
    });
    await queryClient.invalidateQueries({ queryKey: ['data-sources'] });
  };
  if (!canManageUsers(user)) return <Navigate to="/403" replace />;
  return (
    <>
      <PageHeader
        title="Fuentes de datos"
        description="Origen, tipo, vigencia y trazabilidad de conjuntos oficiales."
        action={
          <Button variant="contained" onClick={() => show()}>
            Crear fuente
          </Button>
        }
      />
      {sources.isLoading ? (
        <LoadingSkeleton />
      ) : sources.isError ? (
        <ErrorState retry={() => sources.refetch()} />
      ) : !sources.data?.length ? (
        <Stack spacing={2}>
          <EmptyState
            title="No existen fuentes de datos registradas."
            detail="Registra la primera fuente oficial para habilitar las importaciones."
          />
          <Button variant="contained" sx={{ alignSelf: 'center' }} onClick={() => show()}>
            Crear primera fuente
          </Button>
        </Stack>
      ) : (
        <DataTable
          label="fuentes de datos"
          rows={sources.data}
          columns={[
            { key: 'code', label: 'Código', render: (x) => x.code },
            {
              key: 'name',
              label: 'Nombre',
              render: (x) => (
                <>
                  <strong>{x.institution}</strong>
                  <br />
                  {x.dataset_name}
                </>
              ),
            },
            { key: 'type', label: 'Tipo', render: (x) => datasetLabels[x.dataset_type] },
            { key: 'description', label: 'Descripción', render: (x) => x.description || '—' },
            {
              key: 'url',
              label: 'URL oficial',
              render: (x) =>
                x.official_url ? (
                  <Link href={x.official_url} target="_blank" rel="noreferrer">
                    Abrir fuente
                  </Link>
                ) : (
                  '—'
                ),
            },
            {
              key: 'publication',
              label: 'Publicación',
              render: (x) => formatDateOnly(x.publication_date),
            },
            {
              key: 'reference',
              label: 'Referencia',
              render: (x) =>
                x.reference_date ? formatDateOnly(x.reference_date) : (x.reference_year ?? '—'),
            },
            {
              key: 'status',
              label: 'Estado',
              render: (x) => (x.is_active ? 'Activa' : 'Inactiva'),
            },
            {
              key: 'actions',
              label: 'Acciones',
              render: (x) => (
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  <Button size="small" onClick={() => show(x)}>
                    Editar
                  </Button>
                  <Button
                    size="small"
                    color={x.is_active ? 'warning' : 'success'}
                    onClick={() => toggle(x)}
                  >
                    {x.is_active ? 'Desactivar' : 'Activar'}
                  </Button>
                  <Button
                    size="small"
                    component={RouterLink}
                    to={`/app/admin/data-imports?sourceId=${x.id}`}
                  >
                    Ver importaciones
                  </Button>
                </Stack>
              ),
            },
          ]}
        />
      )}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>{editing ? 'Editar fuente de datos' : 'Crear fuente de datos'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Código"
              disabled={!!editing}
              {...form.register('code')}
              error={!!form.formState.errors.code}
              helperText={
                editing ? 'El código no puede modificarse.' : form.formState.errors.code?.message
              }
            />
            <TextField
              label="Institución"
              {...form.register('institution')}
              error={!!form.formState.errors.institution}
              helperText={form.formState.errors.institution?.message}
            />
            <TextField
              label="Nombre del conjunto"
              {...form.register('dataset_name')}
              error={!!form.formState.errors.dataset_name}
              helperText={form.formState.errors.dataset_name?.message}
            />
            <TextField
              select
              label="Tipo de conjunto"
              disabled={!!editing}
              value={form.watch('dataset_type')}
              onChange={(event) => form.setValue('dataset_type', event.target.value as DatasetType)}
            >
              {DATASET_TYPES.map((type) => (
                <MenuItem key={type} value={type}>
                  {datasetLabels[type]}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Descripción"
              multiline
              minRows={3}
              {...form.register('description')}
            />
            <TextField
              label="URL oficial"
              {...form.register('official_url')}
              error={!!form.formState.errors.official_url}
              helperText={form.formState.errors.official_url?.message}
            />
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                fullWidth
                label="Fecha de publicación"
                placeholder="DD/MM/AAAA"
                {...form.register('publication_date')}
                error={!!form.formState.errors.publication_date}
                helperText={form.formState.errors.publication_date?.message}
              />
              <TextField
                fullWidth
                label="Fecha de referencia"
                placeholder="DD/MM/AAAA"
                {...form.register('reference_date')}
                error={!!form.formState.errors.reference_date}
                helperText={form.formState.errors.reference_date?.message}
              />
              <TextField
                fullWidth
                label="Año de referencia"
                {...form.register('reference_year')}
                error={!!form.formState.errors.reference_year}
                helperText={form.formState.errors.reference_year?.message}
              />
            </Stack>
            <TextField
              label="Licencia o términos"
              multiline
              minRows={2}
              {...form.register('license_or_terms')}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.watch('is_official')}
                  onChange={(event) => form.setValue('is_official', event.target.checked)}
                />
              }
              label="Fuente oficial"
            />
            {editing && (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={form.watch('is_active')}
                    onChange={(event) => form.setValue('is_active', event.target.checked)}
                  />
                }
                label="Fuente activa"
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={save.isPending}
            onClick={form.handleSubmit((values) => save.mutate(values))}
          >
            {save.isPending ? 'Guardando…' : 'Guardar fuente'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
