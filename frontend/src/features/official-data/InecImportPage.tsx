import { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Chip,
  Link,
  MenuItem,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, Navigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { useCampaign } from '../../app/CampaignProvider';
import { useAuth } from '../../auth/AuthProvider';
import { canRunImports } from '../../auth/permissions';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import type { DataSource } from '../admin/SourcesPage';
import { inspectInecCsv, INEC_INDICATOR_HEADERS, INEC_OBSERVATION_HEADERS } from './csv';
import { runOfficialImport } from './importApi';
import type { ImportResult } from './types';

const OBSERVATION_PROFILE = 'CANONICAL_DEMOGRAPHIC_OBSERVATION';
type StepResult = ImportResult | null;
type Indicator = { id: string; code: string; name: string; unit: string; category: string };
type Observation = {
  id: string;
  demographic_indicator_id: string;
  reference_year: number;
  geography_level: string;
  parish_id: number | null;
  canton_id: number | null;
  source_id: string;
  value: string;
};
type TerritoryProvince = { id: number; code: string; name: string };
type TerritoryCanton = { id: number; province_id: number; dpa_code: string; name: string };
type TerritoryParish = { id: number; canton_id: number; dpa_code: string; name: string };

function apiMessage(error: unknown, fallback: string) {
  if (!(error instanceof ApiError)) return fallback;
  const detail = (error.detail as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' ? detail : error.message;
}

export default function InecImportPage() {
  const { user } = useAuth();
  const { active: activeCampaign } = useCampaign();
  const queryClient = useQueryClient();
  const [sourceId, setSourceId] = useState('');
  const [indicatorFile, setIndicatorFile] = useState<File | null>(null);
  const [observationFile, setObservationFile] = useState<File | null>(null);
  const [indicatorResult, setIndicatorResult] = useState<StepResult>(null);
  const [observationResult, setObservationResult] = useState<StepResult>(null);
  const [indicatorInspection, setIndicatorInspection] = useState<ReturnType<
    typeof inspectInecCsv
  > | null>(null);
  const [observationInspection, setObservationInspection] = useState<ReturnType<
    typeof inspectInecCsv
  > | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [finished, setFinished] = useState(false);
  const sources = useQuery({
    queryKey: ['data-sources'],
    queryFn: () => apiRequest<DataSource[]>('/data-sources'),
  });
  const indicators = useQuery({
    queryKey: ['demographic-indicators'],
    queryFn: () => apiRequest<Indicator[]>('/demographic-indicators'),
    enabled: !!sourceId,
  });
  const observations = useQuery({
    queryKey: ['demographic-observations', sourceId],
    queryFn: () => apiRequest<Observation[]>(`/demographic-observations?source_id=${sourceId}`),
    enabled: !!sourceId && finished,
  });
  const importJobs = useQuery({
    queryKey: ['inec-import-jobs', sourceId],
    queryFn: () =>
      apiRequest<ImportResult[]>(
        `/data-imports?dataset_type=INEC_DEMOGRAPHIC_INDICATORS&source_id=${sourceId}`,
      ),
    enabled: !!sourceId,
  });
  const provinces = useQuery({
    queryKey: ['inec-provinces'],
    queryFn: () => apiRequest<TerritoryProvince[]>('/provinces'),
    enabled: !!sourceId,
  });
  const cantons = useQuery({
    queryKey: ['inec-cantons'],
    queryFn: () => apiRequest<TerritoryCanton[]>('/cantons'),
    enabled: !!sourceId,
  });
  const parishes = useQuery({
    queryKey: ['inec-parishes'],
    queryFn: () => apiRequest<TerritoryParish[]>('/parishes'),
    enabled: !!sourceId,
  });
  const inecSources = useMemo(
    () =>
      (sources.data ?? []).filter(
        (source) => source.is_active && source.dataset_type === 'INEC_DEMOGRAPHIC_INDICATORS',
      ),
    [sources.data],
  );
  const selectedSource = inecSources.find((source) => source.id === sourceId);
  const usedIndicators = useMemo(
    () => new Set(observationInspection?.indicatorCodes ?? []),
    [observationInspection],
  );
  const missingIndicators = useMemo(() => {
    if (!observationInspection || !indicators.data) return [];
    const existing = new Set(indicators.data.map((indicator) => indicator.code.toUpperCase()));
    return [...usedIndicators].filter((code) => !existing.has(code.toUpperCase()));
  }, [indicators.data, observationInspection, usedIndicators]);
  const territoryErrors = useMemo(() => {
    if (!observationInspection) return [];
    const provinceByCode = new Map((provinces.data ?? []).map((item) => [item.code, item]));
    const cantonByCode = new Map((cantons.data ?? []).map((item) => [item.dpa_code, item]));
    const parishByCode = new Map((parishes.data ?? []).map((item) => [item.dpa_code, item]));
    return observationInspection.rows.flatMap((row) => {
      if (row.geography_level?.toUpperCase() !== 'PARISH') return [];
      const province = provinceByCode.get(row.province_dpa);
      const canton = cantonByCode.get(row.canton_dpa);
      const parish = parishByCode.get(row.parish_dpa);
      if (
        !province ||
        !canton ||
        !parish ||
        canton.province_id !== province.id ||
        parish.canton_id !== canton.id
      )
        return [`Territorio no mapeado: ${row.parish_dpa}`];
      return [];
    });
  }, [cantons.data, observationInspection, parishes.data, provinces.data]);

  if (!canRunImports(user)) return <Navigate to="/403" replace />;
  if (sources.isLoading) return <LoadingSkeleton />;
  if (sources.isError) return <ErrorState retry={() => sources.refetch()} />;

  const createOrReuseSource = async () => {
    const existing = inecSources.find((source) => source.code.toUpperCase() === 'INEC_ECUADOR');
    if (existing) {
      setSourceId(existing.id);
      setNotice('Fuente INEC existente. Se reutilizará.');
      return;
    }
    try {
      const source = await apiRequest<DataSource>('/data-sources', {
        method: 'POST',
        body: JSON.stringify({
          code: 'INEC_ECUADOR',
          institution: 'Instituto Nacional de Estadística y Censos',
          dataset_name: 'CPV 2022',
          description: 'Información estadística y censal oficial del Ecuador.',
          dataset_type: 'INEC_DEMOGRAPHIC_INDICATORS',
          is_official: true,
        }),
      });
      await queryClient.invalidateQueries({ queryKey: ['data-sources'] });
      setSourceId(source.id);
      setNotice('Fuente INEC creada correctamente.');
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        const refreshed = await queryClient.fetchQuery({
          queryKey: ['data-sources'],
          queryFn: () => apiRequest<DataSource[]>('/data-sources'),
        });
        const source = refreshed.find(
          (item) => item.code.toUpperCase() === 'INEC_ECUADOR' && item.is_active,
        );
        if (source) {
          setSourceId(source.id);
          setNotice('Fuente INEC existente. Se reutilizará.');
          return;
        }
      }
      setError(apiMessage(reason, 'No se pudo crear la fuente INEC.'));
    }
  };

  const chooseFile = async (file: File | null, kind: 'indicator' | 'observation') => {
    if (!file) return;
    setError('');
    const units = Object.fromEntries(
      (indicators.data ?? []).map((indicator) => [indicator.code.toUpperCase(), indicator.unit]),
    );
    const inspection = inspectInecCsv(await file.text(), kind, units);
    if (inspection.missingHeaders.length)
      setError(`Headers faltantes: ${inspection.missingHeaders.join(', ')}`);
    else if (inspection.errors.length) setError(inspection.errors[0]);
    else if (inspection.duplicateKeys.length)
      setError('Existen claves lógicas duplicadas en el CSV.');
    if (kind === 'indicator') {
      setIndicatorFile(file);
      setIndicatorInspection(inspection);
      setIndicatorResult(null);
    } else {
      setObservationFile(file);
      setObservationInspection(inspection);
      setObservationResult(null);
      setFinished(false);
    }
  };

  const run = async (kind: 'indicator' | 'observation', action: 'validate' | 'execute') => {
    const file = kind === 'indicator' ? indicatorFile : observationFile;
    const inspection = kind === 'indicator' ? indicatorInspection : observationInspection;
    if (
      !file ||
      !sourceId ||
      !inspection ||
      inspection.missingHeaders.length ||
      inspection.errors.length ||
      inspection.duplicateKeys.length
    )
      return;
    const catalogCompleted =
      indicatorResult?.status === 'COMPLETED' ||
      importJobs.data?.some(
        (job) =>
          job.mapping_profile === 'CANONICAL_DEMOGRAPHIC_INDICATOR' && job.status === 'COMPLETED',
      ) === true;
    if (kind === 'observation' && !catalogCompleted) {
      setError('Debe completar Indicadores antes de ejecutar Observaciones.');
      return;
    }
    if (kind === 'observation' && missingIndicators.length) {
      setError(`Indicador inexistente: ${missingIndicators[0]}`);
      return;
    }
    if (kind === 'observation' && territoryErrors.length) {
      setError(territoryErrors[0]);
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await runOfficialImport(
        action,
        sourceId,
        'INEC_DEMOGRAPHIC_INDICATORS',
        file,
        false,
        kind === 'observation' ? OBSERVATION_PROFILE : undefined,
      );
      if (kind === 'indicator') {
        setIndicatorResult(result);
        if (result.status === 'COMPLETED')
          await queryClient.invalidateQueries({ queryKey: ['demographic-indicators'] });
      } else setObservationResult(result);
      if (kind === 'observation' && result.status === 'COMPLETED') {
        setFinished(true);
        await queryClient.invalidateQueries({ queryKey: ['demographic-observations'] });
      }
    } catch (reason) {
      setError(apiMessage(reason, 'No se pudo procesar el archivo CSV.'));
    } finally {
      setBusy(false);
    }
  };

  const indicatorDone =
    indicatorResult?.status === 'COMPLETED' ||
    importJobs.data?.some(
      (job) =>
        job.mapping_profile === 'CANONICAL_DEMOGRAPHIC_INDICATOR' && job.status === 'COMPLETED',
    ) === true;
  const observationDone = observationResult?.status === 'COMPLETED';
  const finalTerritories = new Set(
    (observations.data ?? []).map((item) => item.parish_id ?? item.canton_id).filter(Boolean),
  );
  const finalYears = [
    ...new Set((observations.data ?? []).map((item) => item.reference_year)),
  ].sort();
  return (
    <>
      <PageHeader
        title="Importar datos oficiales INEC"
        description="Carga CPV 2022 en dos archivos CSV, con validación y trazabilidad."
      />
      <Stepper
        activeStep={observationDone ? 3 : indicatorDone ? 2 : sourceId ? 1 : 0}
        sx={{ mb: 3 }}
      >
        {[
          'Fuente INEC',
          'Indicadores demográficos',
          'Observaciones demográficas',
          'Verificación final',
        ].map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>
      <Stack spacing={3}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h2">Paso 1 — Fuente INEC</Typography>
            <TextField
              select
              label="Fuente oficial INEC"
              value={sourceId}
              onChange={(event) => setSourceId(event.target.value)}
            >
              <MenuItem value="">Seleccione una fuente</MenuItem>
              {inecSources.map((source) => (
                <MenuItem key={source.id} value={source.id}>
                  {source.institution} · {source.dataset_name}
                </MenuItem>
              ))}
            </TextField>
            {!inecSources.length && (
              <Button variant="outlined" onClick={() => void createOrReuseSource()}>
                Crear fuente INEC_ECUADOR
              </Button>
            )}
            {selectedSource && <Chip label="Fuente ✅" color="success" />}
          </Stack>
        </Paper>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h2">Paso 2 — Indicadores demográficos</Typography>
            <Typography>Dataset: INEC_DEMOGRAPHIC_INDICATORS · Perfil automático</Typography>
            <Typography variant="caption">Headers: {INEC_INDICATOR_HEADERS.join(', ')}</Typography>
            <Button component="label" variant="outlined" disabled={!sourceId}>
              Seleccionar archivo de indicadores
              <input
                hidden
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => void chooseFile(event.target.files?.[0] ?? null, 'indicator')}
              />
            </Button>
            <Typography>{indicatorFile?.name ?? 'Ningún archivo seleccionado'}</Typography>
            {indicatorInspection && (
              <Typography>
                Filas detectadas: {indicatorInspection.rows.length} · Headers válidos:{' '}
                {indicatorInspection.missingHeaders.length ? 'no' : 'sí'}
              </Typography>
            )}
            <Stack direction="row" spacing={2}>
              <Button
                variant="contained"
                disabled={busy || !indicatorFile || !sourceId}
                onClick={() => void run('indicator', 'validate')}
              >
                Validar
              </Button>
              <Button
                variant="contained"
                color="secondary"
                disabled={busy || indicatorResult?.status !== 'VALIDATED'}
                onClick={() => void run('indicator', 'execute')}
              >
                Ejecutar
              </Button>
            </Stack>
            {indicatorResult && (
              <Alert severity={indicatorDone ? 'success' : 'info'}>
                Filas: {indicatorResult.rows_read} · Válidas: {indicatorResult.rows_valid} ·
                Rechazadas: {indicatorResult.rows_failed} · Estado: {indicatorResult.status}
              </Alert>
            )}
          </Stack>
        </Paper>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h2">Paso 3 — Observaciones demográficas</Typography>
            <Typography>
              Dataset: INEC_DEMOGRAPHIC_INDICATORS · Perfil: {OBSERVATION_PROFILE}
            </Typography>
            <Typography variant="caption">
              Headers: {INEC_OBSERVATION_HEADERS.join(', ')}
            </Typography>
            {!indicatorDone && (
              <Alert severity="info">
                Indicadores ⏳ — complete el paso anterior para ejecutar observaciones.
              </Alert>
            )}
            <Button component="label" variant="outlined" disabled={!indicatorDone}>
              Seleccionar archivo de observaciones
              <input
                hidden
                type="file"
                accept=".csv,text/csv"
                onChange={(event) =>
                  void chooseFile(event.target.files?.[0] ?? null, 'observation')
                }
              />
            </Button>
            <Typography>{observationFile?.name ?? 'Ningún archivo seleccionado'}</Typography>
            {observationInspection && (
              <Typography>
                Indicadores utilizados: {observationInspection.indicatorCodes.length} · Territorios:{' '}
                {observationInspection.territoryCodes.length} · Años:{' '}
                {observationInspection.years.join(', ') || '—'} · Observaciones:{' '}
                {observationInspection.rows.length}
              </Typography>
            )}
            {missingIndicators.map((code) => (
              <Alert key={code} severity="error">
                Indicador inexistente: {code}
              </Alert>
            ))}
            {observationInspection?.duplicateKeys.length ? (
              <Alert severity="error">
                Claves lógicas duplicadas: {observationInspection.duplicateKeys.length}
              </Alert>
            ) : null}
            <Stack direction="row" spacing={2}>
              <Button
                variant="contained"
                disabled={busy || !observationFile || !indicatorDone}
                onClick={() => void run('observation', 'validate')}
              >
                Validar
              </Button>
              <Button
                variant="contained"
                color="secondary"
                disabled={
                  busy || observationResult?.status !== 'VALIDATED' || missingIndicators.length > 0
                }
                onClick={() => void run('observation', 'execute')}
              >
                Ejecutar
              </Button>
            </Stack>
            {observationResult && (
              <Alert severity={observationDone ? 'success' : 'info'}>
                Filas: {observationResult.rows_read} · Válidas: {observationResult.rows_valid} ·
                Rechazadas: {observationResult.rows_failed} · Estado: {observationResult.status}
              </Alert>
            )}
          </Stack>
        </Paper>
        {error && <Alert severity="error">{error}</Alert>}
        {notice && <Alert severity="info">{notice}</Alert>}
        {observationDone && (
          <Paper variant="outlined" sx={{ p: 3 }}>
            <Stack spacing={1}>
              <Typography variant="h2">IMPORTACIÓN INEC COMPLETADA</Typography>
              <Typography>Fuente: {selectedSource?.code ?? sourceId}</Typography>
              <Typography>Indicadores: {indicators.data?.length ?? 0}</Typography>
              <Typography>Observaciones: {observations.data?.length ?? 0}</Typography>
              <Typography>Territorios: {finalTerritories.size}</Typography>
              <Typography>Años disponibles: {finalYears.join(', ') || '—'}</Typography>
              {activeCampaign && (
                <Link
                  component={RouterLink}
                  to={`/app/campaigns/${activeCampaign.id}/demographics`}
                >
                  VER DATOS DEMOGRÁFICOS
                </Link>
              )}
            </Stack>
          </Paper>
        )}
        {observationInspection?.warnings.map((warning) => (
          <Alert key={warning} severity="warning">
            {warning}
          </Alert>
        ))}
        {territoryErrors.map((message) => (
          <Alert key={message} severity="error">
            {message}
          </Alert>
        ))}
      </Stack>
    </>
  );
}
