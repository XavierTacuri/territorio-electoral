import { useState } from 'react';
import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { apiRequest, BASE_URL, tokenStore } from '../../api/client';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { importErrorMessage } from '../imports/ImportPage';
import type { DataSource } from '../admin/SourcesPage';

type GeometryError = { row_number?: number | null; error_code: string; message: string };
type GeometryResult = {
  job_id: string;
  status: string;
  features_read: number;
  features_valid: number;
  features_updated: number;
  features_rejected: number;
  errors: GeometryError[];
};

async function submitGeometry(
  action: 'validate' | 'execute',
  sourceId: string,
  file: File,
): Promise<GeometryResult> {
  const body = new FormData();
  body.set('source_id', sourceId);
  body.set('file', file);
  body.set('territory_level', 'PARISH');
  body.set('dpa_code_property', 'dpa_code');
  body.set('name_property', 'name');
  body.set('allow_make_valid', 'false');
  if (action === 'execute') body.set('force', 'false');
  const response = await fetch(`${BASE_URL}/geometry-imports/${action}`, {
    method: 'POST',
    body,
    credentials: 'include',
    headers: tokenStore.get() ? { Authorization: `Bearer ${tokenStore.get()}` } : undefined,
  });
  if (!response.ok) throw new Error(await importErrorMessage(response));
  return response.json() as Promise<GeometryResult>;
}

export default function GeographyImportPage() {
  const [sourceId, setSourceId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<GeometryResult | null>(null);
  const [validatedSignature, setValidatedSignature] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const sources = useQuery({
    queryKey: ['data-sources'],
    queryFn: () => apiRequest<DataSource[]>('/data-sources'),
  });
  if (sources.isLoading) return <LoadingSkeleton />;
  if (sources.isError) return <ErrorState retry={() => void sources.refetch()} />;

  const signature = file ? `${sourceId}:${file.name}:${file.size}:${file.lastModified}` : '';
  const validationPassed =
    !!result &&
    result.status === 'VALIDATED' &&
    result.features_read > 0 &&
    result.features_valid === result.features_read &&
    result.features_rejected === 0 &&
    validatedSignature === signature;
  const run = async (action: 'validate' | 'execute') => {
    if (!sourceId || !file) return;
    setBusy(true);
    setError('');
    try {
      const next = await submitGeometry(action, sourceId, file);
      setResult(next);
      setValidatedSignature(
        action === 'validate' && next.status === 'VALIDATED' && next.features_rejected === 0
          ? signature
          : '',
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'No fue posible procesar el archivo.');
      if (action === 'validate') setValidatedSignature('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Límites territoriales"
        description="Validación e importación manual de límites administrativos oficiales mediante DPA."
      />
      <Paper variant="outlined" sx={{ p: 3, maxWidth: 900 }}>
        <Stack spacing={2}>
          <Alert severity="info">
            La validación no modifica PostGIS. Las geometrías inválidas se rechazan y no se corrigen
            automáticamente.
          </Alert>
          <TextField
            select
            label="Fuente oficial"
            value={sourceId}
            onChange={(event) => {
              setSourceId(event.target.value);
              setResult(null);
              setValidatedSignature('');
            }}
          >
            <MenuItem value="">Seleccione una fuente</MenuItem>
            {(sources.data ?? [])
              .filter((source) => source.is_active && source.is_official)
              .map((source) => (
                <MenuItem key={source.id} value={source.id}>
                  {source.institution} · {source.dataset_name}
                </MenuItem>
              ))}
          </TextField>
          <Typography>
            Nivel territorial: <strong>PARISH</strong>
          </Typography>
          <Typography>
            Propiedad de unión: <strong>dpa_code</strong>
          </Typography>
          <Typography variant="body2">
            Se aceptan FeatureCollection `.geojson` y `.json` con geometrías Polygon o MultiPolygon
            en EPSG:4326.
          </Typography>
          <Button component="label" variant="outlined" disabled={!sourceId}>
            SELECCIONAR GEOJSON
            <input
              hidden
              type="file"
              accept=".geojson,.json,application/geo+json,application/json"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setResult(null);
                setValidatedSignature('');
                setError('');
              }}
            />
          </Button>
          <Typography aria-live="polite">{file?.name ?? 'Ningún archivo seleccionado'}</Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <Button
              variant="contained"
              disabled={busy || !sourceId || !file}
              onClick={() => void run('validate')}
            >
              VALIDAR
            </Button>
            <Button
              color="secondary"
              variant="contained"
              disabled={busy || !validationPassed}
              onClick={() => void run('execute')}
            >
              EJECUTAR
            </Button>
          </Stack>
          {busy && <Typography>Procesando archivo…</Typography>}
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </Paper>
      {result && (
        <Paper variant="outlined" sx={{ p: 3, mt: 2, maxWidth: 900 }}>
          <Typography variant="h2">Resultado · {result.status}</Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} sx={{ my: 2 }}>
            <Typography>
              Features leídas: <strong>{result.features_read}</strong>
            </Typography>
            <Typography>
              Válidas: <strong>{result.features_valid}</strong>
            </Typography>
            <Typography>
              Rechazadas: <strong>{result.features_rejected}</strong>
            </Typography>
            <Typography>
              Actualizadas: <strong>{result.features_updated}</strong>
            </Typography>
          </Stack>
          {result.errors.map((item, index) => (
            <Alert severity="warning" key={`${item.row_number}-${index}`}>
              Feature {item.row_number ?? '—'} · {item.error_code}: {item.message}
            </Alert>
          ))}
          {validationPassed && (
            <Alert severity="success">
              Validación correcta. Puede ejecutar la importación manualmente.
            </Alert>
          )}
        </Paper>
      )}
    </>
  );
}
