import { useMemo, useState } from 'react';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  Grid,
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { apiRequest } from '../../api/client';
import { downloadReport } from '../../api/downloads';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { CurrentElectionMap, type ElectionMapParish } from '../historical/CurrentElectionMap';
import { formatDateEsEc, formatIntegerEsEc, formatPercentEsEc } from '../../lib/formatEsEc';
import { todayDateOnly } from '../../lib/dates';

type History = { registered_voters: number; ballots_cast: number; turnout_rate: number | null };
type Availability = {
  cne_2019: boolean;
  cne_2023: boolean;
  current_registration: boolean;
  inec_2022: boolean;
  geometry: boolean;
};
type Parish = ElectionMapParish & {
  male_voters: number | null;
  female_voters: number | null;
  juntas: number | null;
  historical_2019?: History | null;
  historical_2023?: History | null;
  projection?: ElectionMapParish['projection'] & {
    expected_voters_low: number;
    expected_voters_high: number;
  };
  demographics: Record<string, number>;
  demographics_2010: Record<string, number>;
  population_growth_2010_2022: number | null;
  availability: Availability;
};
type Analysis = {
  context: { campaign_name: string; canton_name: string; election_name: string };
  snapshot: { snapshot_date: string };
  projection: { model_code: string; model_version: string };
  warnings: { code: string; message: string }[];
  sources: {
    code: string;
    institution: string;
    dataset_name: string;
    official_url?: string | null;
    reference_year?: number | null;
  }[];
  parishes: Parish[];
};
type Operation = {
  parish_id: number;
  activities: number;
  needs_open: number;
  commitments_pending: number;
  commitments_completed: number;
  latest_activities: { id: string; title: string; date: string; status: string }[];
  latest_needs: { id: string; title: string; status: string }[];
  latest_commitments: { id: string; title: string; status: string; due_date?: string }[];
};

const integer = formatIntegerEsEc;
const percent = formatPercentEsEc;
const quality: Record<string, string> = {
  HIGH: 'Alta',
  MEDIUM: 'Media',
  LOW: 'Baja',
  INSUFFICIENT_DATA: 'Datos insuficientes',
};
const ageKeys = [
  ['0–14', 'AGE_0_14'],
  ['15–29', 'AGE_15_29'],
  ['30–44', 'AGE_30_44'],
  ['45–64', 'AGE_45_64'],
  ['65+', 'AGE_65_PLUS'],
] as const;

function Card({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
}) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: { xs: 2, md: 3 }, height: '100%', minWidth: 0, overflow: 'hidden' }}
    >
      <Typography variant="h2">{title}</Typography>
      {eyebrow && (
        <Typography variant="overline" color="text.secondary">
          {eyebrow}
        </Typography>
      )}
      <Box sx={{ mt: 2, minWidth: 0, maxWidth: '100%' }}>{children}</Box>
    </Paper>
  );
}
function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: React.ReactNode;
  detail?: string;
}) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h2" sx={{ overflowWrap: 'anywhere' }}>
        {value}
      </Typography>
      {detail && (
        <Typography variant="body2" color="text.secondary">
          {detail}
        </Typography>
      )}
    </Box>
  );
}
function available(value: boolean) {
  return (
    <Chip
      size="small"
      color={value ? 'success' : 'default'}
      label={value ? 'Disponible' : 'No disponible'}
    />
  );
}
function delta(from?: number, to?: number) {
  if (from == null || to == null) return { absolute: null, rate: null };
  return { absolute: to - from, rate: from ? (to - from) / from : null };
}

export default function TerritorialIntelligencePage() {
  const { campaignId = '', parishId } = useParams();
  const navigate = useNavigate();
  const [comparison, setComparison] = useState<Parish[]>([]);
  const [reportStatus, setReportStatus] = useState<'idle' | 'preparing' | 'generated' | 'error'>(
    'idle',
  );
  const analysis = useQuery({
    queryKey: ['current-election-analysis', campaignId],
    queryFn: ({ signal }) =>
      apiRequest<Analysis>(`/campaigns/${campaignId}/current-election/analysis`, { signal }),
    enabled: !!campaignId,
  });
  const operation = useQuery({
    queryKey: ['territory-operation-summary', campaignId],
    queryFn: ({ signal }) =>
      apiRequest<{ parishes: Operation[] }>(`/campaigns/${campaignId}/territories/summary`, {
        signal,
      }),
    enabled: !!campaignId,
    retry: 1,
  });
  const selected = analysis.data?.parishes.find((item) => String(item.parish_id) === parishId);
  const operationByParish = useMemo(
    () => new Map((operation.data?.parishes ?? []).map((item) => [item.parish_id, item])),
    [operation.data],
  );
  if (analysis.isLoading) return <LoadingSkeleton />;
  if (analysis.isError || !analysis.data)
    return (
      <ErrorState
        message="No fue posible cargar la inteligencia territorial."
        retry={() => void analysis.refetch()}
      />
    );
  const data = analysis.data;
  const select = (parish: Parish | null) =>
    navigate(
      parish
        ? `/app/campaigns/${campaignId}/territories/${parish.parish_id}`
        : `/app/campaigns/${campaignId}/territories`,
    );
  const generate = async (format: 'PDF' | 'XLSX') => {
    if (!selected) return;
    setReportStatus('preparing');
    try {
      const run = await apiRequest<{ id: string; artifact?: { original_download_name?: string } }>(
        `/campaigns/${campaignId}/reports/generate`,
        {
          method: 'POST',
          body: JSON.stringify({
            template_code: 'PARISH_TERRITORIAL_PROFILE',
            format,
            title: `Ficha territorial · ${selected.name}`,
            report_date: todayDateOnly(),
            parish_id: selected.parish_id,
            survey_ids: [],
            electoral_process_ids: [],
            demographic_indicator_codes: [],
            include_comparisons: true,
          }),
        },
      );
      await downloadReport(
        `/campaigns/${campaignId}/reports/${run.id}/download`,
        run.artifact?.original_download_name ?? `ficha-territorial.${format.toLowerCase()}`,
      );
      setReportStatus('generated');
    } catch {
      setReportStatus('error');
    }
  };
  return (
    <>
      <PageHeader
        title="INTELIGENCIA TERRITORIAL"
        description="Ficha, contexto y operación agregada por parroquia."
      />
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid size={{ xs: 12, md: 3 }}>
            <Metric label="CAMPAÑA" value={data.context.campaign_name} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 2 }}>
            <Metric label="CANTÓN" value={data.context.canton_name} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <Metric label="PROCESO" value={data.context.election_name} />
          </Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            <Autocomplete
              options={data.parishes}
              value={selected ?? null}
              onChange={(_, value) => select(value)}
              getOptionLabel={(item) => `${item.name} · DPA ${item.dpa_code}`}
              isOptionEqualToValue={(a, b) => a.parish_id === b.parish_id}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Seleccionar parroquia"
                  placeholder="Buscar por nombre o DPA"
                />
              )}
            />
          </Grid>
        </Grid>
      </Paper>
      {!selected ? (
        <Alert severity="info">
          Seleccione una parroquia para abrir su ficha territorial completa.
        </Alert>
      ) : (
        <TerritoryProfile
          parish={selected}
          data={data}
          operation={operationByParish.get(selected.parish_id)}
          operationError={operation.isError}
          campaignId={campaignId}
          onSelectId={(id) => select(data.parishes.find((p) => p.parish_id === id) ?? null)}
          reportStatus={reportStatus}
          generate={generate}
        />
      )}
      <Box sx={{ mt: 2 }}>
        <Comparison
          parishes={data.parishes}
          selected={comparison}
          onChange={setComparison}
          operations={operationByParish}
        />
      </Box>
    </>
  );
}

function TerritoryProfile({
  parish,
  data,
  operation,
  operationError,
  campaignId,
  onSelectId,
  reportStatus,
  generate,
}: {
  parish: Parish;
  data: Analysis;
  operation?: Operation;
  operationError: boolean;
  campaignId: string;
  onSelectId: (id: number) => void;
  reportStatus: string;
  generate: (format: 'PDF' | 'XLSX') => Promise<void>;
}) {
  const totalPopulation = parish.demographics.POP_TOTAL ?? 0;
  const history = [
    ['2019', parish.historical_2019],
    ['2023', parish.historical_2023],
  ] as const;
  const registrationChanges = [
    [
      '2019 → 2023',
      delta(parish.historical_2019?.registered_voters, parish.historical_2023?.registered_voters),
    ],
    [
      '2023 → actual',
      delta(parish.historical_2023?.registered_voters, parish.registered_voters_current),
    ],
    [
      '2019 → actual',
      delta(parish.historical_2019?.registered_voters, parish.registered_voters_current),
    ],
  ] as const;
  return (
    <Stack spacing={2}>
      <Paper sx={{ p: { xs: 2, md: 3 }, bgcolor: 'primary.main', color: 'primary.contrastText' }}>
        <Typography variant="h2">
          {parish.name.toUpperCase()} · DPA {parish.dpa_code}
        </Typography>
        <Grid container spacing={2} sx={{ mt: 1 }}>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric label="ELECTORES" value={integer(parish.registered_voters_current)} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric label="CENTRAL" value={percent(parish.projection?.central)} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric
              label="VOTANTES ESPERADOS"
              value={integer(parish.projection?.expected_voters_central ?? 0)}
            />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric
              label="CALIDAD"
              value={quality[parish.data_quality_status] ?? parish.data_quality_status}
            />
          </Grid>
        </Grid>
      </Paper>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card title="REGISTRO ELECTORAL" eyebrow="OBSERVADO · CNE">
            <Grid container spacing={2}>
              <Grid size={12}>
                <Metric
                  label="Electores actuales"
                  value={integer(parish.registered_voters_current)}
                />
              </Grid>
              <Grid size={4}>
                <Metric
                  label="Hombres"
                  value={integer(parish.male_voters ?? 0)}
                  detail={percent((parish.male_voters ?? 0) / parish.registered_voters_current)}
                />
              </Grid>
              <Grid size={4}>
                <Metric
                  label="Mujeres"
                  value={integer(parish.female_voters ?? 0)}
                  detail={percent((parish.female_voters ?? 0) / parish.registered_voters_current)}
                />
              </Grid>
              <Grid size={4}>
                <Metric label="Juntas" value={integer(parish.juntas ?? 0)} />
              </Grid>
            </Grid>
            <Typography sx={{ mt: 2 }}>
              Corte: {formatDateEsEc(data.snapshot.snapshot_date)}
            </Typography>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card title="PARTICIPACIÓN HISTÓRICA" eyebrow="OBSERVADO · CNE">
            <Box sx={{ height: 220, minWidth: 0 }}>
              <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                <BarChart
                  data={history.map(([year, h]) => ({
                    year,
                    electores: h?.registered_voters,
                    sufragantes: h?.ballots_cast,
                    tasa: (h?.turnout_rate ?? 0) * 100,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="year" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="electores" name="Electores" fill="#607d8b" />
                  <Bar dataKey="sufragantes" name="Sufragantes" fill="#1565c0" />
                </BarChart>
              </ResponsiveContainer>
            </Box>
            <Grid container spacing={2}>
              {history.map(([year, h]) => (
                <Grid key={year} size={6}>
                  <Metric
                    label={year}
                    value={percent(h?.turnout_rate)}
                    detail={`${integer(h?.registered_voters ?? 0)} electores · ${integer(h?.ballots_cast ?? 0)} sufragantes`}
                  />
                </Grid>
              ))}
            </Grid>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card title="PROYECCIÓN DE PARTICIPACIÓN" eyebrow="PROYECTADO · TERRITORIO ELECTORAL">
            <Grid container spacing={2}>
              {[
                ['LOW', parish.projection?.low, parish.projection?.expected_voters_low],
                ['CENTRAL', parish.projection?.central, parish.projection?.expected_voters_central],
                ['HIGH', parish.projection?.high, parish.projection?.expected_voters_high],
              ].map(([label, rate, voters]) => (
                <Grid key={String(label)} size={4}>
                  <Metric
                    label={String(label)}
                    value={percent(Number(rate))}
                    detail={`${integer(Number(voters))} votantes`}
                  />
                </Grid>
              ))}
            </Grid>
            <Box sx={{ mt: 3 }}>
              <Typography variant="h3">¿CÓMO SE CALCULÓ?</Typography>
              <Typography>
                35 % × {percent(parish.historical_2019?.turnout_rate)} + 65 % ×{' '}
                {percent(parish.historical_2023?.turnout_rate)} ={' '}
                <strong>{percent(parish.projection?.central)}</strong>
              </Typography>
              <Typography>
                {integer(parish.registered_voters_current)} electores ×{' '}
                {percent(parish.projection?.central)} ={' '}
                <strong>
                  {integer(parish.projection?.expected_voters_central ?? 0)} votantes esperados
                </strong>
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {data.projection.model_code} · Versión {data.projection.model_version}
              </Typography>
            </Box>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <CurrentElectionMap
            campaignId={campaignId}
            parishes={data.parishes}
            onSelect={onSelectId}
            selectedParishId={parish.parish_id}
            compact
            title={`MAPA · ${parish.name.toUpperCase()}`}
          />
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card title="CONTEXTO TERRITORIAL" eyebrow="OFICIAL · INEC CPV 2022">
            {parish.availability.inec_2022 ? (
              <>
                <Grid container spacing={2}>
                  <Grid size={4}>
                    <Metric label="Población" value={integer(totalPopulation)} />
                  </Grid>
                  <Grid size={4}>
                    <Metric
                      label="Hombres"
                      value={integer(parish.demographics.POP_MALE ?? 0)}
                      detail={percent((parish.demographics.POP_MALE ?? 0) / totalPopulation)}
                    />
                  </Grid>
                  <Grid size={4}>
                    <Metric
                      label="Mujeres"
                      value={integer(parish.demographics.POP_FEMALE ?? 0)}
                      detail={percent((parish.demographics.POP_FEMALE ?? 0) / totalPopulation)}
                    />
                  </Grid>
                  {ageKeys.map(([label, key]) => (
                    <Grid key={key} size={{ xs: 6, sm: 4 }}>
                      <Metric
                        label={label}
                        value={integer(parish.demographics[key] ?? 0)}
                        detail={percent((parish.demographics[key] ?? 0) / totalPopulation)}
                      />
                    </Grid>
                  ))}
                  <Grid size={6}>
                    <Metric
                      label="Densidad"
                      value={
                        parish.demographics.POPULATION_DENSITY ?? parish.demographics.DENSITY ?? '—'
                      }
                    />
                  </Grid>
                  <Grid size={6}>
                    <Metric
                      label="Crecimiento 2010–2022"
                      value={percent(parish.population_growth_2010_2022)}
                    />
                  </Grid>
                </Grid>
                <Typography sx={{ mt: 2 }}>
                  Población 2010: {integer(parish.demographics_2010.POP_TOTAL ?? 0)} · Población
                  2022: {integer(totalPopulation)}
                </Typography>
              </>
            ) : (
              <Alert severity="info">No existe contexto INEC disponible para esta parroquia.</Alert>
            )}
            <Alert severity="info" sx={{ mt: 2 }}>
              Contexto territorial. No interviene en la fórmula de participación V1.
            </Alert>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card title="CALIDAD DEL ANÁLISIS">
            <Metric
              label="Calidad"
              value={quality[parish.data_quality_status] ?? parish.data_quality_status}
            />
            <Stack spacing={1} sx={{ mt: 2 }}>
              {(
                [
                  ['CNE 2019', parish.availability.cne_2019],
                  ['CNE 2023', parish.availability.cne_2023],
                  ['Registro actual', parish.availability.current_registration],
                  ['INEC', parish.availability.inec_2022],
                  ['Geometría', parish.availability.geometry],
                ] as const
              ).map(([label, value]) => (
                <Stack key={label} direction="row" justifyContent="space-between">
                  <Typography>{label}</Typography>
                  {available(value)}
                </Stack>
              ))}
            </Stack>
            <Typography variant="h3" sx={{ mt: 3 }}>
              CAMBIO DEL REGISTRO
            </Typography>
            {registrationChanges.map(([label, change]) => (
              <Typography key={label}>
                {label}:{' '}
                {change.absolute == null
                  ? '—'
                  : `${change.absolute >= 0 ? '+' : ''}${integer(change.absolute)} · ${percent(change.rate)}`}
              </Typography>
            ))}
            {data.warnings.length > 0 && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                La variación del registro no debe interpretarse automáticamente como tendencia
                demográfica.
              </Alert>
            )}
          </Card>
        </Grid>
        <Grid size={12}>
          <Card title="OPERACIÓN TERRITORIAL">
            {operationError ? (
              <Alert severity="warning">
                No fue posible cargar la operación territorial. La ficha analítica permanece
                disponible.
              </Alert>
            ) : (
              <>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Metric
                      label="Actividades registradas"
                      value={integer(operation?.activities ?? 0)}
                    />
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Metric
                      label="Necesidades abiertas"
                      value={integer(operation?.needs_open ?? 0)}
                    />
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Metric
                      label="Compromisos pendientes"
                      value={integer(operation?.commitments_pending ?? 0)}
                    />
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Metric
                      label="Compromisos completados"
                      value={integer(operation?.commitments_completed ?? 0)}
                    />
                  </Grid>
                </Grid>
                <Grid container spacing={2} sx={{ mt: 2 }}>
                  {[
                    ['Últimas actividades', operation?.latest_activities],
                    ['Últimas necesidades', operation?.latest_needs],
                    ['Últimos compromisos', operation?.latest_commitments],
                  ].map(([title, items]) => (
                    <Grid key={String(title)} size={{ xs: 12, md: 4 }}>
                      <Typography variant="h3">{String(title)}</Typography>
                      {(items as { id: string; title: string; status: string }[] | undefined)
                        ?.length ? (
                        (items as { id: string; title: string; status: string }[]).map((item) => (
                          <Typography key={item.id}>
                            {item.title} · {item.status}
                          </Typography>
                        ))
                      ) : (
                        <Typography color="text.secondary">Sin registros</Typography>
                      )}
                    </Grid>
                  ))}
                </Grid>
              </>
            )}
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card title="FUENTES">
            <Stack spacing={1}>
              {data.sources.map((source) => (
                <Box key={source.code}>
                  <Typography fontWeight={700}>
                    {source.institution} · {source.dataset_name}
                  </Typography>
                  {source.official_url ? (
                    <Button
                      component="a"
                      href={source.official_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      VER FUENTE OFICIAL
                    </Button>
                  ) : (
                    <Typography variant="body2">URL oficial no registrada</Typography>
                  )}
                </Box>
              ))}
            </Stack>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card title="DESCARGAR FICHA TERRITORIAL">
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <Button
                variant="contained"
                onClick={() => void generate('PDF')}
                disabled={reportStatus === 'preparing'}
              >
                GENERAR FICHA PDF
              </Button>
              <Button
                variant="outlined"
                onClick={() => void generate('XLSX')}
                disabled={reportStatus === 'preparing'}
              >
                GENERAR FICHA XLSX
              </Button>
            </Stack>
            {reportStatus === 'preparing' && (
              <>
                <LinearProgress sx={{ mt: 2 }} />
                <Typography>Preparando…</Typography>
              </>
            )}
            {reportStatus === 'generated' && (
              <Alert severity="success" sx={{ mt: 2 }}>
                Ficha generada
              </Alert>
            )}
            {reportStatus === 'error' && (
              <Alert severity="error" sx={{ mt: 2 }}>
                No fue posible generar la ficha.
              </Alert>
            )}
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
}

function Comparison({
  parishes,
  selected,
  onChange,
  operations,
}: {
  parishes: Parish[];
  selected: Parish[];
  onChange: (value: Parish[]) => void;
  operations: Map<number, Operation>;
}) {
  const metrics = (p: Parish): Record<string, number | undefined> => ({
    electores: p.registered_voters_current,
    '2019': p.historical_2019?.turnout_rate ?? undefined,
    '2023': p.historical_2023?.turnout_rate ?? undefined,
    low: p.projection?.low,
    central: p.projection?.central,
    high: p.projection?.high,
    votantes: p.projection?.expected_voters_central,
    poblacion: p.demographics.POP_TOTAL,
    crecimiento: p.population_growth_2010_2022 ?? undefined,
    densidad: p.demographics.POPULATION_DENSITY ?? p.demographics.DENSITY,
    ...Object.fromEntries(
      ageKeys.map(([label, key]) => [
        label,
        (p.demographics[key] ?? 0) / (p.demographics.POP_TOTAL ?? 1),
      ]),
    ),
    actividades: operations.get(p.parish_id)?.activities ?? 0,
    necesidades: operations.get(p.parish_id)?.needs_open ?? 0,
    compromisos:
      (operations.get(p.parish_id)?.commitments_pending ?? 0) +
      (operations.get(p.parish_id)?.commitments_completed ?? 0),
  });
  const rows: [string, string, 'integer' | 'percent' | 'plain'][] = [
    ['Electores actuales', 'electores', 'integer'],
    ['Participación 2019', '2019', 'percent'],
    ['Participación 2023', '2023', 'percent'],
    ['LOW', 'low', 'percent'],
    ['CENTRAL', 'central', 'percent'],
    ['HIGH', 'high', 'percent'],
    ['Votantes centrales', 'votantes', 'integer'],
    ['Población', 'poblacion', 'integer'],
    ['Crecimiento', 'crecimiento', 'percent'],
    ['Densidad', 'densidad', 'plain'],
    ...ageKeys.map(([label]) => [`${label} %`, label, 'percent'] as [string, string, 'percent']),
    ['Actividades', 'actividades', 'integer'],
    ['Necesidades', 'necesidades', 'integer'],
    ['Compromisos', 'compromisos', 'integer'],
  ];
  return (
    <Card title="COMPARAR TERRITORIOS">
      <Autocomplete
        multiple
        options={parishes}
        value={selected}
        limitTags={3}
        getOptionLabel={(p) => `${p.name} · ${p.dpa_code}`}
        isOptionEqualToValue={(a, b) => a.parish_id === b.parish_id}
        getOptionDisabled={(option) =>
          selected.length >= 3 && !selected.some((p) => p.parish_id === option.parish_id)
        }
        onChange={(_, value) => onChange(value.slice(0, 3))}
        renderInput={(params) => (
          <TextField {...params} label="Seleccione entre 2 y 3 parroquias" />
        )}
      />
      {selected.length < 2 ? (
        <Alert severity="info" sx={{ mt: 2 }}>
          Seleccione al menos dos parroquias.
        </Alert>
      ) : (
        <>
          <TableContainer sx={{ mt: 2, maxWidth: '100%', overflowX: 'auto' }}>
            <Table size="small" sx={{ minWidth: 650 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Indicador</TableCell>
                  {selected.map((p) => (
                    <TableCell key={p.parish_id}>{p.name}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map(([label, key, kind]) => (
                  <TableRow key={label}>
                    <TableCell>{label}</TableCell>
                    {selected.map((p) => {
                      const value = metrics(p)[key] as number | undefined;
                      return (
                        <TableCell key={p.parish_id}>
                          {value == null
                            ? '—'
                            : kind === 'percent'
                              ? percent(value)
                              : kind === 'integer'
                                ? integer(value)
                                : String(value)}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <Box sx={{ height: 240, minWidth: 0, mt: 2 }}>
            <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
              <BarChart
                data={selected.map((p) => ({
                  name: p.name,
                  Electores: p.registered_voters_current,
                  Población: p.demographics.POP_TOTAL ?? 0,
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="Electores" fill="#1565c0" />
                <Bar dataKey="Población" fill="#607d8b" />
              </BarChart>
            </ResponsiveContainer>
          </Box>
        </>
      )}
    </Card>
  );
}
