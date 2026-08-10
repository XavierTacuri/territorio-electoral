import { useState } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
  Grid,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { BASE_URL, tokenStore } from '../../api/client';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
type Source = {
  id: string;
  code: string;
  institution: string;
  dataset_name: string;
  dataset_type: string;
  is_active: boolean;
};
type ErrorRow = {
  row_number?: number | null;
  column_name?: string | null;
  error_code: string;
  message: string;
  rejected_value_preview?: string | null;
};
type Result = {
  job_id?: string;
  id?: string;
  status: string;
  features_read?: number;
  features_valid?: number;
  features_updated?: number;
  features_rejected?: number;
  rows_read?: number;
  rows_valid?: number;
  rows_inserted?: number;
  rows_updated?: number;
  rows_failed?: number;
  errors: ErrorRow[];
};
const DATASETS = [
  'CNE_ELECTORAL_RESULTS',
  'CNE_CANDIDATES',
  'CNE_POLITICAL_ORGANIZATIONS',
  'CNE_TURNOUT',
  'INEC_DEMOGRAPHIC_INDICATORS',
  'INEC_POPULATION_PROJECTIONS',
  'INEC_GEOGRAPHIC_CLASSIFIER',
  'OTHER_AGGREGATED_OFFICIAL',
];
export function appendMappingProfile(body: FormData, profile: string) {
  const normalized = profile.trim();
  if (normalized && normalized.toUpperCase() !== 'DEFAULT') {
    body.set('mapping_profile', normalized);
  }
}
export async function importErrorMessage(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === 'string' && payload.detail) return payload.detail;
  } catch {
    // La respuesta puede no ser JSON.
  }
  return 'No se pudo procesar el archivo. Revise formato, tamaño y permisos.';
}
export default function ImportPage({ geometry = false }: { geometry?: boolean }) {
  const [searchParams] = useSearchParams();
  const [source, setSource] = useState(searchParams.get('sourceId') ?? '');
  const [dataset, setDataset] = useState(DATASETS[0]);
  const [profile, setProfile] = useState('');
  const [level, setLevel] = useState('PARISH');
  const [dpa, setDpa] = useState('dpa_code');
  const [file, setFile] = useState<File | null>(null);
  const [allowMakeValid, setAllowMakeValid] = useState(false);
  const [force, setForce] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const sources = useQuery({
    queryKey: ['data-sources'],
    queryFn: () => apiRequest<Source[]>('/data-sources'),
  });
  const jobs = useQuery({
    queryKey: [geometry ? 'geometry-imports' : 'data-imports', source],
    queryFn: () =>
      apiRequest<any[]>(
        geometry ? '/geometry-imports' : '/data-imports' + (source ? `?source_id=${source}` : ''),
      ),
  });
  const run = async (execute: boolean) => {
    if (!file || !source) {
      setError('Seleccione fuente y archivo.');
      return;
    }
    setBusy(true);
    setError('');
    const body = new FormData();
    body.set('source_id', source);
    body.set('file', file);
    if (geometry) {
      body.set('territory_level', level);
      body.set('dpa_code_property', dpa);
      body.set('name_property', 'name');
      body.set('allow_make_valid', String(allowMakeValid));
      if (execute) body.set('force', String(force));
    } else {
      body.set('dataset_type', dataset);
      appendMappingProfile(body, profile);
      if (execute) body.set('force', String(force));
    }
    try {
      const response = await fetch(
        BASE_URL +
          (geometry ? '/geometry-imports/' : '/data-imports/') +
          (execute ? 'execute' : 'validate'),
        {
          method: 'POST',
          body,
          credentials: 'include',
          headers: tokenStore.get() ? { Authorization: 'Bearer ' + tokenStore.get() } : undefined,
        },
      );
      if (!response.ok) {
        throw new Error(await importErrorMessage(response));
      }
      setResult(await response.json());
      jobs.refetch();
    } catch (reason) {
      setError(
        reason instanceof Error && reason.message
          ? reason.message
          : 'No se pudo procesar el archivo. Revise formato, tamaño y permisos.',
      );
    } finally {
      setBusy(false);
    }
  };
  if (sources.isLoading) return <LoadingSkeleton />;
  if (sources.isError) return <ErrorState retry={() => sources.refetch()} />;
  return (
    <>
      <PageHeader
        title={geometry ? 'Importación GeoJSON' : 'Importación CSV'}
        description="La validación es obligatoria y nunca ejecuta automáticamente la importación."
      />
      <Paper variant="outlined" sx={{ p: 3, mb: 3 }}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField
              select
              fullWidth
              label="Fuente oficial"
              value={source}
              onChange={(e) => {
                const sourceId = e.target.value;
                setSource(sourceId);
                const selected = sources.data?.find((item) => item.id === sourceId);
                if (!geometry && selected) setDataset(selected.dataset_type);
              }}
            >
              {sources.data
                ?.filter((x) => x.is_active)
                .map((x) => (
                  <MenuItem key={x.id} value={x.id}>
                    {x.institution} · {x.dataset_name}
                  </MenuItem>
                ))}
            </TextField>
          </Grid>
          {geometry ? (
            <>
              <Grid size={{ xs: 12, md: 3 }}>
                <TextField
                  select
                  fullWidth
                  label="Nivel territorial"
                  value={level}
                  onChange={(e) => setLevel(e.target.value)}
                >
                  {['CANTON', 'PARISH', 'COMMUNITY', 'SECTOR'].map((x) => (
                    <MenuItem key={x} value={x}>
                      {x}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, md: 3 }}>
                <TextField
                  fullWidth
                  label="Propiedad DPA"
                  value={dpa}
                  onChange={(e) => setDpa(e.target.value)}
                />
              </Grid>
              <Grid size={{ xs: 12 }}>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={allowMakeValid}
                      onChange={(e) => setAllowMakeValid(e.target.checked)}
                    />
                  }
                  label="Intentar reparar geometrías inválidas (solo ADMIN)"
                />
              </Grid>
            </>
          ) : (
            <>
              <Grid size={{ xs: 12, md: 3 }}>
                <TextField
                  select
                  fullWidth
                  label="Tipo de conjunto"
                  value={dataset}
                  onChange={(e) => setDataset(e.target.value)}
                >
                  {DATASETS.map((x) => (
                    <MenuItem key={x} value={x}>
                      {x}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, md: 3 }}>
                <TextField
                  fullWidth
                  label="Perfil explícito (opcional)"
                  placeholder="Automático"
                  value={profile}
                  onChange={(e) => setProfile(e.target.value)}
                  helperText={
                    profile.trim() && profile.trim().toUpperCase() !== 'DEFAULT'
                      ? `Perfil explícito: ${profile.trim()}`
                      : 'Automático: el sistema seleccionará el perfil compatible con el tipo de conjunto.'
                  }
                />
              </Grid>
            </>
          )}
          <Grid size={{ xs: 12 }}>
            <FormControlLabel
              control={<Checkbox checked={force} onChange={(e) => setForce(e.target.checked)} />}
              label="Forzar actualización de un checksum ya importado"
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Button component="label" variant="outlined">
              Seleccionar archivo
              <input
                hidden
                type="file"
                accept={geometry ? '.geojson,.json' : 'text/csv,.csv'}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setResult(null);
                }}
              />
            </Button>
            <Typography component="span" sx={{ ml: 2 }}>
              {file?.name ?? 'Ningún archivo seleccionado'}
            </Typography>
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Stack direction="row" spacing={2}>
              <Button variant="contained" disabled={busy} onClick={() => run(false)}>
                1. Validar
              </Button>
              <Button
                variant="contained"
                color="secondary"
                disabled={busy || !result}
                onClick={() => run(true)}
              >
                2. Ejecutar
              </Button>
            </Stack>
          </Grid>
        </Grid>
      </Paper>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {result && (
        <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
          <Typography variant="h2">Resultado: {result.status}</Typography>
          <Typography>
            Leídos: {result.features_read ?? result.rows_read ?? 0} · Válidos:{' '}
            {result.features_valid ?? result.rows_valid ?? 0} · Actualizados:{' '}
            {result.features_updated ?? result.rows_updated ?? 0} · Rechazados:{' '}
            {result.features_rejected ?? result.rows_failed ?? 0}
          </Typography>
          {result.errors.slice(0, 20).map((x, index) => (
            <Alert key={index} severity="warning">
              {x.error_code}: {x.message}
              {x.column_name ? ' · campo ' + x.column_name : ''}
            </Alert>
          ))}
        </Paper>
      )}
      <Typography variant="h2">Historial</Typography>
      <Stack>
        {jobs.data?.map((job) => (
          <Paper key={job.id} variant="outlined" sx={{ p: 1, my: 0.5 }}>
            {job.original_filename} · {job.status} · {job.rows_valid ?? 0} válidos ·{' '}
            {job.rows_failed ?? 0} rechazados
          </Paper>
        ))}
      </Stack>
    </>
  );
}
