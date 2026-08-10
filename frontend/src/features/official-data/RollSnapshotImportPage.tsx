import { useState } from 'react';
import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { useAuth } from '../../auth/AuthProvider';
import { canRunImports } from '../../auth/permissions';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { parseDateOnly } from '../../lib/dates';
import type { DataSource } from '../admin/SourcesPage';
import { runOfficialImport } from './importApi';
import type { ElectoralProcess, ImportResult } from './types';

export const ROLL_HEADERS = [
  'snapshot_date',
  'process_code',
  'geography_level',
  'province_dpa',
  'canton_dpa',
  'parish_dpa',
  'registered_voters',
  'male_voters',
  'female_voters',
  'electoral_zones',
  'juntas',
] as const;

function readCsv(text: string) {
  const lines = text
    .replace(/^\uFEFF/, '')
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .filter(Boolean);
  const delimiter =
    (lines[0]?.match(/;/g)?.length ?? 0) > (lines[0]?.match(/,/g)?.length ?? 0) ? ';' : ',';
  const parse = (line: string) =>
    line.split(delimiter).map((part) => part.trim().replace(/^"|"$/g, ''));
  const headers = parse(lines[0] ?? '').map((header) => header.toLowerCase());
  return {
    headers,
    rows: lines
      .slice(1)
      .map((line) =>
        Object.fromEntries(headers.map((header, index) => [header, parse(line)[index] ?? ''])),
      ),
  };
}

async function fileText(file: File) {
  if (typeof file.text === 'function') return file.text();
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error ?? new Error('No se pudo leer el CSV.'));
    reader.readAsText(file);
  });
}

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

export default function RollSnapshotImportPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [sourceId, setSourceId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [processCode, setProcessCode] = useState('');
  const [processName, setProcessName] = useState('');
  const [electionDate, setElectionDate] = useState('');
  const [processStatus, setProcessStatus] = useState('DRAFT');
  const sources = useQuery({
    queryKey: ['data-sources'],
    queryFn: () => apiRequest<DataSource[]>('/data-sources'),
  });
  const processes = useQuery({
    queryKey: ['electoral-processes'],
    queryFn: () => apiRequest<ElectoralProcess[]>('/electoral-processes'),
  });
  if (!canRunImports(user)) return <Navigate to="/403" replace />;
  if (sources.isLoading || processes.isLoading) return <LoadingSkeleton />;
  if (sources.isError || processes.isError)
    return (
      <ErrorState
        retry={() => {
          void sources.refetch();
          void processes.refetch();
        }}
      />
    );
  const cneSources = (sources.data ?? []).filter(
    (source) => source.is_active && source.dataset_type.startsWith('CNE_'),
  );
  const process = (processes.data ?? []).find(
    (item) => item.code.toUpperCase() === processCode.toUpperCase(),
  );
  const processResolved = !!process;
  const processCodes = processCode ? [processCode] : [];
  const canCreate =
    !!processCode &&
    !!sourceId &&
    !!processName.trim() &&
    !!parseDateOnly(electionDate) &&
    !processResolved;
  const inspect = async (candidate: File | null) => {
    if (!candidate) return;
    setFile(candidate);
    setResult(null);
    setError('');
    setProcessCode('');
    const parsed = readCsv(await fileText(candidate));
    const missing = ROLL_HEADERS.filter((header) => !parsed.headers.includes(header));
    if (missing.length) {
      setError(`Headers faltantes: ${missing.join(', ')}`);
      return;
    }
    const codes = [...new Set(parsed.rows.map((row) => row.process_code).filter(Boolean))];
    if (codes.length > 1) {
      setError('El archivo contiene más de un proceso electoral.');
      return;
    }
    const detected = codes[0] ?? '';
    setProcessCode(detected);
    const existing = (processes.data ?? []).find(
      (item) => item.code.toUpperCase() === detected.toUpperCase(),
    );
    if (existing) setError('');
    else setProcessName('');
  };
  const createProcess = async () => {
    if (!canCreate) return;
    setBusy(true);
    setError('');
    try {
      await apiRequest('/electoral-processes', {
        method: 'POST',
        body: JSON.stringify({
          code: processCode,
          name: processName.trim(),
          process_type: 'SECTIONAL',
          election_date: parseDateOnly(electionDate),
          year: Number(parseDateOnly(electionDate)!.slice(0, 4)),
          status: processStatus,
          is_final: false,
          source_id: sourceId,
        }),
      });
      await queryClient.invalidateQueries({ queryKey: ['electoral-processes'] });
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409)
        await queryClient.invalidateQueries({ queryKey: ['electoral-processes'] });
      else
        setError(
          reason instanceof Error ? reason.message : 'No se pudo crear el proceso electoral.',
        );
    } finally {
      setBusy(false);
    }
  };
  const run = async (action: 'validate' | 'execute') => {
    if (!file || !sourceId || error || !processResolved) return;
    setBusy(true);
    try {
      setResult(await runOfficialImport(action, sourceId, 'CNE_ELECTORAL_ROLL_SNAPSHOT', file));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'No se pudo procesar el snapshot.');
    } finally {
      setBusy(false);
    }
  };
  const errors = result ? groupedErrors(result) : [];
  return (
    <>
      <PageHeader
        title="Registro electoral preelectoral"
        description="Electores habilitados según un corte oficial del CNE. No representa participación ni resultados."
      />
      <Paper variant="outlined" sx={{ p: 3, maxWidth: 900 }}>
        <Stack spacing={2}>
          <TextField
            select
            label="Fuente CNE"
            value={sourceId}
            onChange={(event) => setSourceId(event.target.value)}
          >
            <MenuItem value="">Seleccione una fuente</MenuItem>
            {cneSources.map((source) => (
              <MenuItem key={source.id} value={source.id}>
                {source.institution} · {source.dataset_name}
              </MenuItem>
            ))}
          </TextField>
          <Typography>Dataset: CNE_ELECTORAL_ROLL_SNAPSHOT</Typography>
          <Typography>Perfil: CANONICAL_ELECTORAL_ROLL_SNAPSHOT</Typography>
          <Typography variant="caption">Headers: {ROLL_HEADERS.join(', ')}</Typography>
          <Button component="label" variant="outlined" disabled={!sourceId}>
            Seleccionar CSV
            <input
              hidden
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => void inspect(event.target.files?.[0] ?? null)}
            />
          </Button>
          <Typography>{file?.name ?? 'Ningún archivo seleccionado'}</Typography>
          {processCodes.length > 0 && (
            <Alert severity="info">
              <Typography>
                Proceso detectado: <strong>{processCode}</strong>
              </Typography>
              {processResolved ? (
                <Typography>
                  Proceso electoral · {process.code} · Existente ✅. Se reutilizará.
                </Typography>
              ) : (
                <>
                  <Typography>
                    Este archivo requiere un proceso electoral que todavía no existe.
                  </Typography>
                  <Button>CREAR PROCESO ELECTORAL</Button>
                </>
              )}
            </Alert>
          )}
          {!!processCode && !processResolved && (
            <Stack spacing={2} sx={{ p: 2, border: 1, borderColor: 'divider' }}>
              <Typography variant="h3">Crear proceso electoral</Typography>
              <TextField label="Código" value={processCode} disabled />
              <TextField
                label="Nombre"
                value={processName}
                onChange={(event) => setProcessName(event.target.value)}
                required
              />
              <TextField select label="Tipo" value="SECTIONAL" disabled>
                <MenuItem value="SECTIONAL">SECTIONAL</MenuItem>
              </TextField>
              <TextField
                label="Fecha electoral (DD/MM/AAAA)"
                placeholder="DD/MM/AAAA"
                value={electionDate}
                onChange={(event) => setElectionDate(event.target.value)}
                required
              />
              <TextField
                label="Año"
                value={parseDateOnly(electionDate)?.slice(0, 4) ?? ''}
                disabled
              />
              <TextField
                select
                label="Estado"
                value={processStatus}
                onChange={(event) => setProcessStatus(event.target.value)}
              >
                {['DRAFT', 'IMPORTED', 'VALIDATED', 'PUBLISHED', 'ARCHIVED'].map((value) => (
                  <MenuItem key={value} value={value}>
                    {value}
                  </MenuItem>
                ))}
              </TextField>
              <Typography>Resultado final: No</Typography>
              <Typography>
                Fuente:{' '}
                {cneSources.find((source) => source.id === sourceId)?.dataset_name ?? sourceId}
              </Typography>
              <Button
                variant="contained"
                onClick={() => void createProcess()}
                disabled={!canCreate || busy}
              >
                CREAR PROCESO ELECTORAL
              </Button>
            </Stack>
          )}
          <Stack direction="row" spacing={2}>
            <Button
              variant="contained"
              disabled={busy || !file || !sourceId || !!error || !processResolved}
              onClick={() => void run('validate')}
            >
              VALIDAR SNAPSHOT
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
                <Alert severity="success">Snapshot importado correctamente.</Alert>
              )}
            </Paper>
          )}
          <Alert severity="info">
            Los registros electorales se almacenan como snapshots y nunca como ElectoralTurnout.
          </Alert>
        </Stack>
      </Paper>
    </>
  );
}
