import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Grid,
  MenuItem,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { useCampaign } from '../../app/CampaignProvider';
import { useAuth } from '../../auth/AuthProvider';
import { canRunImports } from '../../auth/permissions';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly, parseDateOnly } from '../../lib/dates';
import type { DataSource } from '../admin/SourcesPage';
import { CneFileStep } from './CneFileStep';
import { normalizedTechnicalCode, resultDependencyErrors } from './csv';
import type {
  CandidateResult,
  Canton,
  CsvInspection,
  ElectoralCandidate,
  ElectoralContest,
  ElectoralGeography,
  ElectoralProcess,
  PoliticalOrganization,
  Province,
  Turnout,
} from './types';

const sourceSchema = z.object({
  code: z.string().trim().min(1, 'El código es obligatorio.'),
  institution: z.string().trim().min(1, 'La institución es obligatoria.'),
  dataset_name: z.string().trim().min(1, 'El nombre del conjunto es obligatorio.'),
  description: z.string().trim().min(1, 'La descripción es obligatoria.'),
});
type SourceValues = z.infer<typeof sourceSchema>;

const processSchema = z.object({
  code: z.string().trim().min(1, 'El código es obligatorio.'),
  name: z.string().trim().min(1, 'El nombre es obligatorio.'),
  process_type: z.enum(['SECTIONAL', 'GENERAL', 'REFERENDUM', 'CONSULTATION', 'OTHER']),
  election_date: z
    .string()
    .refine((value) => !!parseDateOnly(value), 'Usa una fecha válida DD/MM/AAAA.'),
  status: z.enum(['DRAFT', 'IMPORTED', 'VALIDATED', 'PUBLISHED', 'ARCHIVED']),
  is_final: z.boolean(),
});
type ProcessValues = z.infer<typeof processSchema>;

const contestSchema = z.object({
  office_type: z.enum([
    'MAYOR',
    'URBAN_COUNCILOR',
    'RURAL_COUNCILOR',
    'PARISH_BOARD',
    'PREFECTURE',
    'OTHER',
  ]),
  name: z.string().trim().min(1, 'El nombre técnico es obligatorio.'),
  vote_method: z.enum(['SINGLE_CHOICE', 'MULTI_VOTE', 'LIST_VOTE', 'OTHER']),
  province_id: z.string().min(1, 'Selecciona una provincia.'),
  canton_id: z.string().min(1, 'Selecciona un cantón.'),
  seats: z.coerce.number().int().min(1, 'Debe existir al menos un escaño.'),
});
type ContestValues = z.infer<typeof contestSchema>;

const sourceDefaults: SourceValues = {
  code: 'CNE_ECUADOR',
  institution: 'Consejo Nacional Electoral del Ecuador',
  dataset_name: 'Resultados electorales oficiales',
  description: 'Resultados electorales oficiales del Consejo Nacional Electoral del Ecuador.',
};
const processDefaults: ProcessValues = {
  code: 'SEC_2023',
  name: 'Elecciones Seccionales 2023',
  process_type: 'SECTIONAL',
  election_date: '05/02/2023',
  status: 'VALIDATED',
  is_final: true,
};
const contestDefaults: ContestValues = {
  office_type: 'MAYOR',
  name: '',
  vote_method: 'SINGLE_CHOICE',
  province_id: '',
  canton_id: '',
  seats: 1,
};

const officeLabels: Record<ContestValues['office_type'], string> = {
  MAYOR: 'Alcaldía',
  URBAN_COUNCILOR: 'Concejalía urbana',
  RURAL_COUNCILOR: 'Concejalía rural',
  PARISH_BOARD: 'Junta parroquial',
  PREFECTURE: 'Prefectura',
  OTHER: 'Otra dignidad',
};

function apiMessage(error: unknown, fallback: string) {
  if (!(error instanceof ApiError)) return fallback;
  const detail = (error.detail as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' ? detail : error.message;
}

function storedContext() {
  try {
    return JSON.parse(localStorage.getItem('territorio.officialData.cne') ?? '{}') as {
      sourceId?: string;
      processCode?: string;
      contestCode?: string;
    };
  } catch {
    return {};
  }
}

export default function CneImportWizard() {
  const { user } = useAuth();
  const { active: activeCampaign } = useCampaign();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const remembered = useMemo(storedContext, []);
  const [sourceId, setSourceId] = useState(
    searchParams.get('sourceId') ?? remembered.sourceId ?? '',
  );
  const [processId, setProcessId] = useState('');
  const [contestId, setContestId] = useState('');
  const [sourceDialog, setSourceDialog] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [organizationInspection, setOrganizationInspection] = useState<CsvInspection | null>(null);
  const [turnoutInspection, setTurnoutInspection] = useState<CsvInspection | null>(null);
  const [candidateInspection, setCandidateInspection] = useState<CsvInspection | null>(null);
  const [resultInspection, setResultInspection] = useState<CsvInspection | null>(null);

  const sourceForm = useForm<SourceValues>({
    resolver: zodResolver(sourceSchema),
    defaultValues: sourceDefaults,
  });
  const processForm = useForm<ProcessValues>({
    resolver: zodResolver(processSchema),
    defaultValues: processDefaults,
  });
  const contestForm = useForm<ContestValues>({
    resolver: zodResolver(contestSchema),
    defaultValues: contestDefaults,
  });

  const sources = useQuery({
    queryKey: ['data-sources'],
    queryFn: () => apiRequest<DataSource[]>('/data-sources'),
  });
  const processes = useQuery({
    queryKey: ['electoral-processes'],
    queryFn: () => apiRequest<ElectoralProcess[]>('/electoral-processes'),
  });
  const provinces = useQuery({
    queryKey: ['provinces'],
    queryFn: () => apiRequest<Province[]>('/provinces'),
  });
  const cantons = useQuery({
    queryKey: ['cantons', contestForm.watch('province_id')],
    queryFn: () =>
      apiRequest<Canton[]>(`/cantons?province_id=${contestForm.getValues('province_id')}`),
    enabled: !!contestForm.watch('province_id'),
  });
  const contests = useQuery({
    queryKey: ['electoral-contests', processId],
    queryFn: () => apiRequest<ElectoralContest[]>(`/electoral-processes/${processId}/contests`),
    enabled: !!processId,
  });
  const organizations = useQuery({
    queryKey: ['political-organizations', sourceId],
    queryFn: () =>
      apiRequest<PoliticalOrganization[]>(`/political-organizations?source_id=${sourceId}`),
    enabled: !!sourceId,
  });
  const candidates = useQuery({
    queryKey: ['electoral-candidates', processId, contestId],
    queryFn: () =>
      apiRequest<ElectoralCandidate[]>(
        `/electoral-processes/${processId}/contests/${contestId}/candidates`,
      ),
    enabled: !!processId && !!contestId,
  });
  const geographies = useQuery({
    queryKey: ['electoral-geographies', processId, contestForm.watch('canton_id')],
    queryFn: () =>
      apiRequest<ElectoralGeography[]>(
        `/electoral-processes/${processId}/geographies?aggregation_level=PARISH&canton_id=${contestForm.getValues('canton_id')}&is_mapped=true`,
      ),
    enabled: !!processId && !!contestId && !!contestForm.watch('canton_id'),
  });
  const turnout = useQuery({
    queryKey: ['turnout', processId, contestId],
    queryFn: () =>
      apiRequest<Turnout[]>(
        `/electoral-processes/${processId}/contests/${contestId}/turnout?aggregation_level=PARISH`,
      ),
    enabled: !!processId && !!contestId,
  });
  const results = useQuery({
    queryKey: ['candidate-results', processId, contestId],
    queryFn: () =>
      apiRequest<CandidateResult[]>(
        `/electoral-processes/${processId}/contests/${contestId}/candidate-results?aggregation_level=PARISH`,
      ),
    enabled: !!processId && !!contestId,
  });
  const cneSources = useMemo(
    () =>
      (sources.data ?? []).filter(
        (source) => source.is_active && source.dataset_type.startsWith('CNE_'),
      ),
    [sources.data],
  );
  const selectedSource = cneSources.find((source) => source.id === sourceId);
  const selectedProcess = processes.data?.find((process) => process.id === processId);
  const selectedContest = contests.data?.find((contest) => contest.id === contestId);
  const contestCanton = useQuery({
    queryKey: ['canton', selectedContest?.canton_id],
    queryFn: () => apiRequest<Canton>(`/cantons/${selectedContest!.canton_id}`),
    enabled: !!selectedContest?.canton_id,
  });

  const remember = (next: { sourceId?: string; processCode?: string; contestCode?: string }) => {
    const params = new URLSearchParams(searchParams);
    Object.entries(next).forEach(([key, value]) => {
      if (value) params.set(key, value);
      else params.delete(key);
    });
    const saved = { ...storedContext(), ...next };
    localStorage.setItem('territorio.officialData.cne', JSON.stringify(saved));
    setSearchParams(params, { replace: true });
  };

  useEffect(() => {
    const code = searchParams.get('processCode') ?? remembered.processCode;
    if (!code || processId || !processes.data) return;
    const existing = processes.data.find(
      (process) => process.code.toUpperCase() === code.toUpperCase(),
    );
    if (!existing) return;
    setProcessId(existing.id);
    processForm.reset({
      code: existing.code,
      name: existing.name,
      process_type: existing.process_type as ProcessValues['process_type'],
      election_date: formatDateOnly(existing.election_date),
      status: existing.status as ProcessValues['status'],
      is_final: existing.is_final,
    });
  }, [processForm, processId, processes.data, remembered.processCode, searchParams]);

  useEffect(() => {
    const code = searchParams.get('contestCode') ?? remembered.contestCode;
    if (!code || contestId || !contests.data) return;
    const existing = contests.data.find((contest) => contest.name === code);
    if (existing) setContestId(existing.id);
  }, [contestId, contests.data, remembered.contestCode, searchParams]);

  useEffect(() => {
    if (!selectedContest || !contestCanton.data) return;
    contestForm.reset({
      office_type: selectedContest.office_type as ContestValues['office_type'],
      name: selectedContest.name,
      vote_method: selectedContest.vote_method as ContestValues['vote_method'],
      province_id: String(contestCanton.data.province_id),
      canton_id: String(selectedContest.canton_id),
      seats: selectedContest.seats,
    });
  }, [contestCanton.data, contestForm, selectedContest]);

  const createSource = useMutation({
    mutationFn: (values: SourceValues) =>
      apiRequest<DataSource>('/data-sources', {
        method: 'POST',
        body: JSON.stringify({
          ...values,
          dataset_type: 'CNE_ELECTORAL_RESULTS',
          is_official: true,
        }),
      }),
    onSuccess: async (source) => {
      await queryClient.invalidateQueries({ queryKey: ['data-sources'] });
      setSourceId(source.id);
      remember({ sourceId: source.id });
      setSourceDialog(false);
      setNotice('Fuente CNE creada correctamente.');
    },
    onError: async (reason) => {
      if (reason instanceof ApiError && reason.status === 409) {
        const refreshed = await queryClient.fetchQuery({
          queryKey: ['data-sources'],
          queryFn: () => apiRequest<DataSource[]>('/data-sources'),
        });
        const existing = refreshed.find(
          (source) => source.code.toUpperCase() === sourceForm.getValues('code').toUpperCase(),
        );
        if (existing) {
          setSourceId(existing.id);
          remember({ sourceId: existing.id });
          setSourceDialog(false);
          setNotice('Fuente CNE existente. Se reutilizará.');
          return;
        }
      }
      setError(apiMessage(reason, 'No se pudo crear la fuente CNE.'));
    },
  });

  const continueProcess = processForm.handleSubmit(async (values) => {
    if (!selectedSource) return;
    setError('');
    const existing = processes.data?.find(
      (process) => process.code.toUpperCase() === values.code.toUpperCase(),
    );
    if (existing) {
      setProcessId(existing.id);
      remember({ processCode: existing.code, contestCode: '' });
      setContestId('');
      setNotice('Proceso electoral existente. Se reutilizará.');
      return;
    }
    try {
      const electionDate = parseDateOnly(values.election_date)!;
      const created = await apiRequest<ElectoralProcess>('/electoral-processes', {
        method: 'POST',
        body: JSON.stringify({
          code: values.code,
          name: values.name,
          process_type: values.process_type,
          election_date: electionDate,
          year: Number(electionDate.slice(0, 4)),
          status: values.status,
          is_final: values.is_final,
          source_id: sourceId,
        }),
      });
      await queryClient.invalidateQueries({ queryKey: ['electoral-processes'] });
      setProcessId(created.id);
      remember({ processCode: created.code, contestCode: '' });
      setContestId('');
      setNotice('Proceso electoral creado correctamente.');
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        const refreshed = await processes.refetch();
        const existingAfterConflict = refreshed.data?.find(
          (process) => process.code.toUpperCase() === values.code.toUpperCase(),
        );
        if (existingAfterConflict) {
          setProcessId(existingAfterConflict.id);
          remember({ processCode: existingAfterConflict.code, contestCode: '' });
          setContestId('');
          setNotice('Proceso electoral existente. Se reutilizará.');
          return;
        }
      }
      setError(apiMessage(reason, 'No se pudo crear el proceso electoral.'));
    }
  });

  const continueContest = contestForm.handleSubmit(async (values) => {
    if (!processId) return;
    setError('');
    const cantonId = Number(values.canton_id);
    const existing = contests.data?.find(
      (contest) =>
        contest.name === values.name &&
        contest.office_type === values.office_type &&
        contest.canton_id === cantonId,
    );
    if (existing) {
      setContestId(existing.id);
      remember({ contestCode: existing.name });
      setNotice('Contienda existente. Se reutilizará.');
      return;
    }
    try {
      const created = await apiRequest<ElectoralContest>(
        `/electoral-processes/${processId}/contests`,
        {
          method: 'POST',
          body: JSON.stringify({
            office_type: values.office_type,
            name: values.name,
            vote_method: values.vote_method,
            canton_id: cantonId,
            seats: values.seats,
          }),
        },
      );
      await queryClient.invalidateQueries({ queryKey: ['electoral-contests', processId] });
      setContestId(created.id);
      remember({ contestCode: created.name });
      setNotice('Contienda creada correctamente.');
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        const refreshed = await contests.refetch();
        const existingAfterConflict = refreshed.data?.find(
          (contest) =>
            contest.name === values.name &&
            contest.office_type === values.office_type &&
            contest.canton_id === cantonId,
        );
        if (existingAfterConflict) {
          setContestId(existingAfterConflict.id);
          remember({ contestCode: existingAfterConflict.name });
          setNotice('Contienda existente. Se reutilizará.');
          return;
        }
      }
      setError(apiMessage(reason, 'No se pudo crear la contienda.'));
    }
  });

  const refreshImportedData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['data-imports'] }),
      queryClient.invalidateQueries({ queryKey: ['political-organizations', sourceId] }),
      queryClient.invalidateQueries({ queryKey: ['electoral-candidates', processId, contestId] }),
      queryClient.invalidateQueries({ queryKey: ['electoral-geographies', processId] }),
      queryClient.invalidateQueries({ queryKey: ['turnout', processId, contestId] }),
      queryClient.invalidateQueries({ queryKey: ['candidate-results', processId, contestId] }),
    ]);
  };

  const processReady = !!selectedProcess;
  const contestReady = !!selectedContest;
  const candidatesWithoutOrganizations =
    !!candidateInspection && !candidateInspection.usesOrganizations;
  const organizationsReady =
    (organizations.data?.length ?? 0) > 0 || candidatesWithoutOrganizations;
  const turnoutReady = (turnout.data?.length ?? 0) > 0;
  const candidatesReady = (candidates.data?.length ?? 0) > 0;
  const resultsReady = (results.data?.length ?? 0) > 0;
  const candidateOrganizationErrors = (candidateInspection?.organizationCodes ?? [])
    .filter(
      (code) =>
        !(organizations.data ?? []).some((organization) => organization.external_code === code),
    )
    .map((code) => `La organización ${code} no está registrada en la fuente seleccionada.`);
  const resultErrors = resultInspection
    ? resultDependencyErrors(
        resultInspection,
        new Set((candidates.data ?? []).map((candidate) => candidate.external_code)),
        new Set((geographies.data ?? []).map((geography) => geography.external_code)),
      )
    : [];
  const currentStep = !selectedSource
    ? 0
    : !processReady
      ? 1
      : !contestReady
        ? 2
        : !organizationsReady
          ? 3
          : !turnoutReady
            ? 4
            : !candidatesReady
              ? 5
              : !resultsReady
                ? 6
                : 7;

  if (!canRunImports(user)) return <Navigate to="/403" replace />;
  if (sources.isLoading || processes.isLoading || provinces.isLoading) return <LoadingSkeleton />;
  if (sources.isError || processes.isError || provinces.isError)
    return <ErrorState message="No se pudo reconstruir el estado del asistente." />;

  return (
    <>
      <PageHeader
        title="Importar datos oficiales CNE"
        description="Asistente guiado para preparar dependencias, validar y ejecutar archivos canónicos oficiales."
      />
      <Stepper activeStep={currentStep} alternativeLabel sx={{ mb: 3, overflowX: 'auto' }}>
        {[
          'Fuente',
          'Proceso electoral',
          'Contienda',
          'Organizaciones',
          'Participación',
          'Candidaturas',
          'Resultados',
          'Verificación final',
        ].map((label) => (
          <Step
            key={label}
            completed={
              currentStep > 0 &&
              currentStep >
                [
                  'Fuente',
                  'Proceso electoral',
                  'Contienda',
                  'Organizaciones',
                  'Participación',
                  'Candidaturas',
                  'Resultados',
                  'Verificación final',
                ].indexOf(label)
            }
          >
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>
      <Stack spacing={3}>
        {notice && <Alert severity="success">{notice}</Alert>}
        {error && <Alert severity="error">{error}</Alert>}

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h2">Paso 1 — Fuente</Typography>
            {!cneSources.length && (
              <Alert severity="warning">No existe una fuente oficial CNE registrada.</Alert>
            )}
            <TextField
              select
              label="Fuente oficial CNE"
              value={sourceId}
              onChange={(event) => {
                setSourceId(event.target.value);
                setProcessId('');
                setContestId('');
                remember({ sourceId: event.target.value, processCode: '', contestCode: '' });
              }}
            >
              <MenuItem value="">Seleccione</MenuItem>
              {cneSources.map((source) => (
                <MenuItem key={source.id} value={source.id}>
                  {source.institution} · {source.dataset_name}
                </MenuItem>
              ))}
            </TextField>
            {!cneSources.length && (
              <Button variant="contained" onClick={() => setSourceDialog(true)}>
                Crear fuente CNE
              </Button>
            )}
          </Stack>
        </Paper>

        <Paper component="form" variant="outlined" sx={{ p: 3 }} onSubmit={continueProcess}>
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="h2">Paso 2 — Proceso electoral</Typography>
              {processReady && <Chip color="success" label="Se reutilizará" />}
            </Stack>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 4 }}>
                <TextField
                  fullWidth
                  label="Código"
                  {...processForm.register('code')}
                  error={!!processForm.formState.errors.code}
                  helperText={processForm.formState.errors.code?.message}
                />
              </Grid>
              <Grid size={{ xs: 12, md: 8 }}>
                <TextField
                  fullWidth
                  label="Nombre"
                  {...processForm.register('name')}
                  error={!!processForm.formState.errors.name}
                  helperText={processForm.formState.errors.name?.message}
                />
              </Grid>
              <Grid size={{ xs: 12, md: 3 }}>
                <TextField
                  select
                  fullWidth
                  label="Tipo"
                  value={processForm.watch('process_type')}
                  onChange={(event) =>
                    processForm.setValue(
                      'process_type',
                      event.target.value as ProcessValues['process_type'],
                    )
                  }
                >
                  {['SECTIONAL', 'GENERAL', 'REFERENDUM', 'CONSULTATION', 'OTHER'].map((value) => (
                    <MenuItem key={value} value={value}>
                      {value}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, md: 3 }}>
                <TextField
                  fullWidth
                  label="Fecha"
                  placeholder="DD/MM/AAAA"
                  {...processForm.register('election_date')}
                  error={!!processForm.formState.errors.election_date}
                  helperText={processForm.formState.errors.election_date?.message}
                />
              </Grid>
              <Grid size={{ xs: 12, md: 3 }}>
                <TextField
                  fullWidth
                  label="Año"
                  value={parseDateOnly(processForm.watch('election_date'))?.slice(0, 4) ?? ''}
                  disabled
                />
              </Grid>
              <Grid size={{ xs: 12, md: 3 }}>
                <TextField
                  select
                  fullWidth
                  label="Estado"
                  value={processForm.watch('status')}
                  onChange={(event) =>
                    processForm.setValue('status', event.target.value as ProcessValues['status'])
                  }
                >
                  {['DRAFT', 'IMPORTED', 'VALIDATED', 'PUBLISHED', 'ARCHIVED'].map((value) => (
                    <MenuItem key={value} value={value}>
                      {value}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
            </Grid>
            <FormControlLabel
              control={
                <Checkbox
                  checked={processForm.watch('is_final')}
                  onChange={(event) => processForm.setValue('is_final', event.target.checked)}
                />
              }
              label="Resultado final"
            />
            <Button type="submit" variant="contained" disabled={!selectedSource}>
              Crear o reutilizar proceso
            </Button>
          </Stack>
        </Paper>

        <Paper component="form" variant="outlined" sx={{ p: 3 }} onSubmit={continueContest}>
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="h2">Paso 3 — Contienda</Typography>
              {contestReady && <Chip color="success" label="Se reutilizará" />}
            </Stack>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 4 }}>
                <TextField
                  select
                  fullWidth
                  label="Dignidad"
                  value={contestForm.watch('office_type')}
                  onChange={(event) => {
                    const office = event.target.value as ContestValues['office_type'];
                    contestForm.setValue('office_type', office);
                    const canton = cantons.data?.find(
                      (item) => String(item.id) === contestForm.getValues('canton_id'),
                    );
                    if (canton)
                      contestForm.setValue('name', normalizedTechnicalCode(office, canton.name));
                  }}
                >
                  {Object.entries(officeLabels).map(([value, label]) => (
                    <MenuItem key={value} value={value}>
                      {label}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, md: 4 }}>
                <TextField
                  select
                  fullWidth
                  label="Provincia"
                  value={contestForm.watch('province_id')}
                  onChange={(event) => {
                    contestForm.setValue('province_id', event.target.value, {
                      shouldValidate: true,
                    });
                    contestForm.setValue('canton_id', '');
                    contestForm.setValue('name', '');
                  }}
                  error={!!contestForm.formState.errors.province_id}
                  helperText={contestForm.formState.errors.province_id?.message}
                >
                  {(provinces.data ?? [])
                    .filter((province) => province.is_active)
                    .map((province) => (
                      <MenuItem key={province.id} value={String(province.id)}>
                        {province.name}
                      </MenuItem>
                    ))}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, md: 4 }}>
                <TextField
                  select
                  fullWidth
                  label="Cantón"
                  disabled={!contestForm.watch('province_id')}
                  value={contestForm.watch('canton_id')}
                  onChange={(event) => {
                    const canton = cantons.data?.find(
                      (item) => String(item.id) === event.target.value,
                    );
                    contestForm.setValue('canton_id', event.target.value, {
                      shouldValidate: true,
                    });
                    if (canton)
                      contestForm.setValue(
                        'name',
                        normalizedTechnicalCode(contestForm.getValues('office_type'), canton.name),
                        { shouldValidate: true },
                      );
                  }}
                  error={!!contestForm.formState.errors.canton_id}
                  helperText={contestForm.formState.errors.canton_id?.message}
                >
                  {selectedContest &&
                    contestCanton.data &&
                    !(cantons.data ?? []).some(
                      (canton) => String(canton.id) === contestForm.watch('canton_id'),
                    ) && (
                      <MenuItem value={String(contestCanton.data.id)}>
                        {contestCanton.data.name}
                      </MenuItem>
                    )}
                  {(cantons.data ?? [])
                    .filter((canton) => canton.is_active)
                    .map((canton) => (
                      <MenuItem key={canton.id} value={String(canton.id)}>
                        {canton.name}
                      </MenuItem>
                    ))}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, md: 5 }}>
                <TextField
                  fullWidth
                  label="Nombre técnico / contest_code"
                  {...contestForm.register('name')}
                  error={!!contestForm.formState.errors.name}
                  helperText={contestForm.formState.errors.name?.message}
                />
              </Grid>
              <Grid size={{ xs: 12, md: 4 }}>
                <TextField
                  select
                  fullWidth
                  label="Método"
                  value={contestForm.watch('vote_method')}
                  onChange={(event) =>
                    contestForm.setValue(
                      'vote_method',
                      event.target.value as ContestValues['vote_method'],
                    )
                  }
                >
                  {['SINGLE_CHOICE', 'MULTI_VOTE', 'LIST_VOTE', 'OTHER'].map((value) => (
                    <MenuItem key={value} value={value}>
                      {value}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, md: 3 }}>
                <TextField
                  fullWidth
                  type="number"
                  label="Escaños"
                  {...contestForm.register('seats')}
                  error={!!contestForm.formState.errors.seats}
                  helperText={contestForm.formState.errors.seats?.message}
                />
              </Grid>
            </Grid>
            <Button type="submit" variant="contained" disabled={!processReady}>
              Crear o reutilizar contienda
            </Button>
          </Stack>
        </Paper>

        <CneFileStep
          step={4}
          dataset="CNE_POLITICAL_ORGANIZATIONS"
          sourceId={sourceId}
          processCode={selectedProcess?.code ?? processForm.getValues('code')}
          contestCode={selectedContest?.name ?? contestForm.getValues('name')}
          locked={!contestReady}
          complete={organizationsReady}
          onInspection={setOrganizationInspection}
          onExecuted={refreshImportedData}
        />
        <CneFileStep
          step={5}
          dataset="CNE_TURNOUT"
          sourceId={sourceId}
          processCode={selectedProcess?.code ?? processForm.getValues('code')}
          contestCode={selectedContest?.name ?? contestForm.getValues('name')}
          locked={!contestReady}
          complete={turnoutReady}
          onInspection={setTurnoutInspection}
          onExecuted={refreshImportedData}
        />
        <CneFileStep
          step={6}
          dataset="CNE_CANDIDATES"
          sourceId={sourceId}
          processCode={selectedProcess?.code ?? processForm.getValues('code')}
          contestCode={selectedContest?.name ?? contestForm.getValues('name')}
          locked={!contestReady || !organizationsReady}
          complete={candidatesReady}
          additionalErrors={candidateOrganizationErrors}
          onInspection={setCandidateInspection}
          onExecuted={refreshImportedData}
        />
        <CneFileStep
          step={7}
          dataset="CNE_ELECTORAL_RESULTS"
          sourceId={sourceId}
          processCode={selectedProcess?.code ?? processForm.getValues('code')}
          contestCode={selectedContest?.name ?? contestForm.getValues('name')}
          locked={!turnoutReady || !candidatesReady}
          complete={resultsReady}
          additionalErrors={resultErrors}
          onInspection={setResultInspection}
          onExecuted={refreshImportedData}
        />

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h2" gutterBottom>
            Paso 8 — Verificación final
          </Typography>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography>Proceso: {selectedProcess?.name ?? 'Pendiente'}</Typography>
              <Typography>Código: {selectedProcess?.code ?? 'Pendiente'}</Typography>
              <Typography>Contienda: {selectedContest?.name ?? 'Pendiente'}</Typography>
              <Typography>
                Dignidad:{' '}
                {selectedContest
                  ? officeLabels[selectedContest.office_type as ContestValues['office_type']]
                  : 'Pendiente'}
              </Typography>
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography>
                Organizaciones:{' '}
                {organizations.data?.length ?? organizationInspection?.rows.length ?? 0}
              </Typography>
              <Typography>
                Candidaturas:{' '}
                {candidates.data?.length ?? candidateInspection?.candidateCodes.length ?? 0}
              </Typography>
              <Typography>
                Parroquias:{' '}
                {geographies.data?.length ?? turnoutInspection?.geographyCodes.length ?? 0}
              </Typography>
              <Typography>
                Participación: {turnout.data?.length ?? turnoutInspection?.rows.length ?? 0}{' '}
                territorios
              </Typography>
              <Typography>
                Filas de resultados: {results.data?.length ?? resultInspection?.rows.length ?? 0}
              </Typography>
            </Grid>
          </Grid>
          {resultsReady ? (
            <Alert severity="success" sx={{ mt: 2 }}>
              IMPORTACIÓN CNE COMPLETADA
            </Alert>
          ) : (
            <Alert severity="info" sx={{ mt: 2 }}>
              La verificación final se completará cuando existan resultados asociados a la
              contienda.
            </Alert>
          )}
          <Button
            component={Link}
            to={activeCampaign ? `/app/campaigns/${activeCampaign.id}/electoral` : '/app/campaigns'}
            sx={{ mt: 2 }}
            variant="outlined"
          >
            Ver datos electorales
          </Button>
        </Paper>
      </Stack>

      <Dialog open={sourceDialog} onClose={() => setSourceDialog(false)} fullWidth maxWidth="sm">
        <DialogTitle>Crear fuente CNE</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Código"
              {...sourceForm.register('code')}
              error={!!sourceForm.formState.errors.code}
              helperText={sourceForm.formState.errors.code?.message}
            />
            <TextField
              label="Institución"
              {...sourceForm.register('institution')}
              error={!!sourceForm.formState.errors.institution}
              helperText={sourceForm.formState.errors.institution?.message}
            />
            <TextField
              label="Nombre del conjunto"
              {...sourceForm.register('dataset_name')}
              error={!!sourceForm.formState.errors.dataset_name}
              helperText={sourceForm.formState.errors.dataset_name?.message}
            />
            <TextField
              label="Descripción"
              multiline
              minRows={3}
              {...sourceForm.register('description')}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSourceDialog(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={createSource.isPending}
            onClick={sourceForm.handleSubmit((values) => createSource.mutate(values))}
          >
            Crear fuente CNE
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
