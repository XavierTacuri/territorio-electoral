import { useState } from 'react';
import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { downloadReport } from '../../api/downloads';
import { useAuth } from '../../auth/AuthProvider';
import { canRunImports } from '../../auth/permissions';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import type { DataSource } from '../admin/SourcesPage';
import { runOfficialImport } from './importApi';
import type { ImportResult, OfficialDataset } from './types';

function groupedErrors(result: ImportResult) {
  const groups = new Map<string, { count: number; rows: number[]; error_code: string }>();
  (result.errors ?? []).forEach((error) => {
    const key = `${error.error_code}|${error.message}`;
    const current = groups.get(key) ?? { count: 0, rows: [], error_code: error.error_code };
    current.count += 1;
    if (error.row_number != null) current.rows.push(error.row_number);
    groups.set(key, current);
  });
  return [...groups.entries()].map(([key, value]) => ({
    key,
    message: key.split('|').slice(1).join('|'),
    ...value,
  }));
}

// One shared upload screen reutilizado por cualquier dataset de perfil
// simple (fuente + CSV + validar/ejecutar), en vez de construir una pantalla
// de carga nueva por cada tipo de conjunto de datos.
export function SimpleDatasetImportPage({
  title,
  description,
  datasetType,
  mappingProfile,
  headers,
  helperNote,
  successMessage,
}: {
  title: string;
  description: string;
  datasetType: OfficialDataset;
  mappingProfile: string;
  headers: readonly string[];
  helperNote?: string;
  successMessage: string;
}) {
  const { user } = useAuth();
  const [sourceId, setSourceId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const sources = useQuery({
    queryKey: ['data-sources'],
    queryFn: () => apiRequest<DataSource[]>('/data-sources'),
  });
  if (!canRunImports(user)) return <Navigate to="/403" replace />;
  if (sources.isLoading) return <LoadingSkeleton />;
  if (sources.isError) return <ErrorState retry={() => sources.refetch()} />;
  const matchingSources = (sources.data ?? []).filter(
    (source) => source.is_active && source.dataset_type === datasetType,
  );
  const run = async (action: 'validate' | 'execute') => {
    if (!file || !sourceId) return;
    setBusy(true);
    setError('');
    try {
      setResult(await runOfficialImport(action, sourceId, datasetType, file, false, mappingProfile));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'No se pudo procesar el archivo.');
    } finally {
      setBusy(false);
    }
  };
  const errors = result ? groupedErrors(result) : [];
  return (
    <>
      <PageHeader title={title} description={description} />
      <Paper variant="outlined" sx={{ p: 3, maxWidth: 900 }}>
        <Stack spacing={2}>
          <TextField
            select
            label="Fuente"
            value={sourceId}
            onChange={(event) => {
              setSourceId(event.target.value);
              setResult(null);
              setError('');
            }}
          >
            <MenuItem value="">Seleccione una fuente</MenuItem>
            {matchingSources.map((source) => (
              <MenuItem key={source.id} value={source.id}>
                {source.institution} · {source.dataset_name}
              </MenuItem>
            ))}
          </TextField>
          {matchingSources.length === 0 && (
            <Alert severity="warning">
              No existe una fuente activa de este tipo. Cree una en Administración → Fuentes de
              datos.
            </Alert>
          )}
          <Typography variant="caption">Columnas: {headers.join(', ')}</Typography>
          <Alert severity="info">
            Los códigos DPA contienen ceros iniciales. Trátelos como texto.
          </Alert>
          {helperNote && <Alert severity="info">{helperNote}</Alert>}
          <Button
            variant="outlined"
            onClick={() =>
              void downloadReport(
                `/data-import-profiles/${datasetType}/template`,
                `plantilla_${datasetType.toLowerCase()}.csv`,
              )
            }
          >
            DESCARGAR PLANTILLA
          </Button>
          <Button component="label" variant="outlined" disabled={!sourceId}>
            Seleccionar CSV
            <input
              hidden
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setResult(null);
                setError('');
              }}
            />
          </Button>
          <Typography>{file?.name ?? 'Ningún archivo seleccionado'}</Typography>
          <Stack direction="row" spacing={2}>
            <Button
              variant="contained"
              disabled={busy || !file || !sourceId}
              onClick={() => void run('validate')}
            >
              VALIDAR
            </Button>
            <Button
              variant="contained"
              color="secondary"
              disabled={busy || result?.status !== 'VALIDATED'}
              onClick={() => void run('execute')}
            >
              EJECUTAR
            </Button>
          </Stack>
          {error && <Alert severity="error">{error}</Alert>}
          {result && (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography>
                Estado: <strong>{result.status}</strong>
              </Typography>
              <Typography>Leídas: {result.rows_read}</Typography>
              <Typography>Válidas: {result.rows_valid}</Typography>
              <Typography>Rechazadas: {result.rows_failed}</Typography>
              {errors.length > 0 && (
                <Stack spacing={1} sx={{ mt: 1 }}>
                  <Typography>Errores</Typography>
                  {errors.map((item) => (
                    <Alert key={item.key} severity="error">
                      {item.message} · {item.count} filas afectadas
                      {item.rows.length ? ` (${item.rows.join(', ')})` : ''}
                    </Alert>
                  ))}
                </Stack>
              )}
              {result.status === 'COMPLETED' && (
                <Alert severity="success">{successMessage}</Alert>
              )}
            </Paper>
          )}
        </Stack>
      </Paper>
    </>
  );
}
