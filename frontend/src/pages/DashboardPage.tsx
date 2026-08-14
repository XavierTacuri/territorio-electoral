import { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Grid,
  LinearProgress,
  Paper,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useLocation, useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { apiRequest } from '../api/client';
import { downloadReport } from '../api/downloads';
import { ErrorState } from '../components/feedback/States';
import { PageHeader } from '../components/layout/PageHeader';
import {
  CurrentElectionMap,
  type ElectionMapParish,
} from '../features/historical/CurrentElectionMap';
import { formatDateEsEc, formatIntegerEsEc, formatPercentEsEc } from '../lib/formatEsEc';
import { todayDateOnly } from '../lib/dates';

type Historical = { registered_voters: number; ballots_cast: number; turnout_rate: number | null };
type Parish = ElectionMapParish & {
  male_voters: number | null;
  female_voters: number | null;
  juntas: number | null;
  projection?: ElectionMapParish['projection'] & {
    expected_voters_low: number;
    expected_voters_high: number;
  };
  demographics: Record<string, number>;
};
type Analysis = {
  context: { campaign_name: string; canton_name: string; election_name: string };
  snapshot: {
    id: string;
    snapshot_date: string;
    registered_voters: number;
    male_voters: number;
    female_voters: number;
    juntas: number;
  };
  historical: Record<string, Historical>;
  projection: {
    model_code: string;
    model_version: string;
    parameters: Record<string, string | number>;
    expected_voters_low: number;
    expected_voters_central: number;
    expected_voters_high: number;
  };
  warnings: { code: string; message?: string }[];
  demographics: { year: number; parishes: Parish[] };
  parishes: Parish[];
};
type OperationalSummary = {
  activities?: { upcoming: number; pending_approval: number; completed: number };
  needs?: { open: number; under_review: number; validated: number; critical_unassigned: number };
  commitments: { pending: number; in_progress: number; overdue: number; completed: number };
  coverage?: {
    total_parishes: number;
    with_activities: number;
    with_needs: number;
    with_commitments: number;
  };
  total_activities?: number;
  open_needs?: number;
  activities_by_parish?: { parish_id: number }[];
  needs_by_parish?: { parish_id: number }[];
  parishes_with_commitments?: number;
};
type MapStatus = 'loading' | 'success' | 'empty' | 'error';
type RecentStudies = {
  items: { id: string; name: string; fieldwork_end_date: string; sample_size_total: number }[];
  total: number;
};

const integer = formatIntegerEsEc;
const percent = formatPercentEsEc;
const executivePath = (id: string, suffix: string) => `/app/campaigns/${id}/${suffix}`;

function SectionTitle({ children, eyebrow }: { children: React.ReactNode; eyebrow?: string }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography component="h2" variant="h2">
        {children}
      </Typography>
      {eyebrow && (
        <Typography variant="overline" color="text.secondary">
          {eyebrow}
        </Typography>
      )}
    </Box>
  );
}

function DashboardSkeleton() {
  return (
    <Box role="status" aria-label="Cargando dashboard ejecutivo">
      <Skeleton height={86} sx={{ mb: 2 }} />
      <Grid container spacing={2}>
        {[1, 2, 3].map((item) => (
          <Grid key={item} size={{ xs: 12, md: 4 }}>
            <Skeleton variant="rounded" height={230} />
          </Grid>
        ))}
        <Grid size={{ xs: 12, lg: 5 }}>
          <Skeleton variant="rounded" height={360} />
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Skeleton variant="rounded" height={360} />
        </Grid>
      </Grid>
    </Box>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
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

function DashboardCard({ children, sx }: { children: React.ReactNode; sx?: object }) {
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, ...sx }}>
      {children}
    </Paper>
  );
}

export default function DashboardPage() {
  const { campaignId = '' } = useParams();
  const location = useLocation();
  const message = (location.state as { message?: string } | null)?.message;
  const [selectedParish, setSelectedParish] = useState<Parish | null>(null);
  const [mapStatus, setMapStatus] = useState<MapStatus>('loading');
  const [reportStatus, setReportStatus] = useState<'idle' | 'preparing' | 'generated' | 'error'>(
    'idle',
  );
  const [generatedFormat, setGeneratedFormat] = useState<'PDF' | 'XLSX' | null>(null);

  const analysis = useQuery({
    queryKey: ['current-election-analysis', campaignId],
    queryFn: ({ signal }) =>
      apiRequest<Analysis>(`/campaigns/${campaignId}/current-election/analysis`, { signal }),
    enabled: !!campaignId,
  });
  const operation = useQuery({
    queryKey: ['campaign', campaignId, 'operational-summary', 'campaign-to-date'],
    queryFn: ({ signal }) =>
      apiRequest<OperationalSummary>(`/campaigns/${campaignId}/operations/summary`, { signal }),
    enabled: !!campaignId,
    retry: 1,
  });
  const recentStudies = useQuery({
    queryKey: ['recent-survey-studies', campaignId],
    queryFn: () =>
      apiRequest<RecentStudies>(
        `/campaigns/${campaignId}/survey-studies?status=PUBLISHED&page=1&page_size=3`,
      ),
    enabled: !!campaignId,
  });
  const data = analysis.data;
  const onMapSelect = useCallback(
    (parishId: number) => {
      setSelectedParish(data?.parishes.find((row) => row.parish_id === parishId) ?? null);
    },
    [data?.parishes],
  );

  const computed = useMemo(() => {
    if (!data) return null;
    const projected = data.parishes.filter((row) => row.projection);
    const byCentral = [...projected].sort(
      (a, b) => (b.projection?.central ?? 0) - (a.projection?.central ?? 0),
    );
    const byRegistration = [...data.parishes].sort(
      (a, b) => b.registered_voters_current - a.registered_voters_current,
    );
    const demographicKeys = [
      ['AGE_0_14', '0–14'],
      ['AGE_15_29', '15–29'],
      ['AGE_30_44', '30–44'],
      ['AGE_45_64', '45–64'],
      ['AGE_65_PLUS', '65+'],
    ] as const;
    const demographic = (key: string) =>
      data.parishes.reduce((sum, row) => sum + (row.demographics[key] ?? 0), 0);
    return {
      highestCentral: byCentral[0],
      lowestCentral: byCentral.at(-1),
      highestRegistration: byRegistration[0],
      lowestRegistration: byRegistration.at(-1),
      topFive: byRegistration.slice(0, 5),
      population: demographic('POP_TOTAL'),
      populationMale: demographic('POP_MALE'),
      populationFemale: demographic('POP_FEMALE'),
      ages: demographicKeys.map(([key, name]) => ({ name, value: demographic(key) })),
      modelQuality: data.parishes.some((row) => row.data_quality_status === 'LOW')
        ? 'Baja'
        : data.parishes.some((row) => row.data_quality_status === 'MEDIUM')
          ? 'Media'
          : 'Alta',
    };
  }, [data]);

  const generateReport = async (format: 'PDF' | 'XLSX') => {
    try {
      setReportStatus('preparing');
      setGeneratedFormat(null);
      const run = await apiRequest<{ id: string; artifact?: { original_download_name: string } }>(
        `/campaigns/${campaignId}/reports/generate`,
        {
          method: 'POST',
          body: JSON.stringify({
            template_code: 'CURRENT_ELECTION_EXECUTIVE',
            format,
            title: 'Informe ejecutivo — Elección actual',
            report_date: todayDateOnly(),
            period: 'CAMPAIGN_TO_DATE',
            survey_ids: [],
            electoral_process_ids: [],
            demographic_indicator_codes: [],
            include_comparisons: true,
          }),
        },
      );
      await downloadReport(
        `/campaigns/${campaignId}/reports/${run.id}/download`,
        run.artifact?.original_download_name ?? `informe-eleccion-actual.${format.toLowerCase()}`,
      );
      setGeneratedFormat(format);
      setReportStatus('generated');
    } catch {
      setReportStatus('error');
    }
  };

  if (analysis.isLoading) return <DashboardSkeleton />;
  if (analysis.isError || !data || !computed) {
    return (
      <>
        <PageHeader title="TERRITORIO ELECTORAL" description="Dashboard ejecutivo de campaña" />
        <ErrorState
          message="No fue posible cargar el análisis de la elección actual."
          retry={() => void analysis.refetch()}
        />
        <Box sx={{ mt: 2 }}>
          {operation.isLoading && <Skeleton variant="rounded" height={180} />}
          {operation.isSuccess && (
            <OperationalBlock operation={operation.data} campaignId={campaignId} />
          )}
        </Box>
      </>
    );
  }

  const current = data.snapshot;
  const centralRate = current.registered_voters
    ? data.projection.expected_voters_central / current.registered_voters
    : 0;
  const historicalChart = [
    { year: '2019', rate: (data.historical['2019']?.turnout_rate ?? 0) * 100, type: 'Observado' },
    { year: '2023', rate: (data.historical['2023']?.turnout_rate ?? 0) * 100, type: 'Observado' },
    { year: 'Actual', rate: centralRate * 100, type: 'Proyectado' },
  ];
  const quickLinks = [
    ['VER ELECCIÓN ACTUAL', 'current-election'],
    ['VER MAPA', 'maps'],
    ['ACTIVIDADES', 'activities'],
    ['NECESIDADES', 'needs'],
    ['COMPROMISOS', 'commitments'],
    ['GENERAR INFORME', 'reports'],
  ];

  return (
    <>
      <PageHeader title="TERRITORIO ELECTORAL" description="Dashboard ejecutivo de campaña" />
      {message && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {message}
        </Alert>
      )}
      <DashboardCard
        sx={{ mb: 2, background: 'linear-gradient(135deg, rgba(21,101,192,.08), rgba(0,0,0,0))' }}
      >
        <Grid container spacing={2} alignItems="center">
          <Grid size={{ xs: 12, md: 4 }}>
            <Metric label="CAMPAÑA" value={data.context.campaign_name} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <Metric label="CANTÓN" value={data.context.canton_name} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <Metric label="PROCESO" value={data.context.election_name} />
          </Grid>
          <Grid size={{ xs: 12, md: 2 }}>
            <Metric label="CORTE DEL REGISTRO" value={formatDateEsEc(current.snapshot_date)} />
          </Grid>
        </Grid>
      </DashboardCard>
      <DashboardCard sx={{ mb: 2 }}>
        <SectionTitle eyebrow="DESCRIPTIVO · ESTUDIOS PUBLICADOS">ESTUDIOS RECIENTES</SectionTitle>
        <Grid container spacing={2} alignItems="center">
          <Grid size={{ xs: 12, sm: 3 }}>
            <Metric label="Estudios publicados" value={integer(recentStudies.data?.total ?? 0)} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <Metric
              label="Último estudio"
              value={recentStudies.data?.items[0]?.name ?? 'Sin estudios publicados'}
              detail={
                recentStudies.data?.items[0]
                  ? formatDateEsEc(recentStudies.data.items[0].fieldwork_end_date)
                  : undefined
              }
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 3 }}>
            <Metric
              label="Muestra"
              value={
                recentStudies.data?.items[0]
                  ? integer(recentStudies.data.items[0].sample_size_total)
                  : '—'
              }
            />
          </Grid>
        </Grid>
        <Button component={RouterLink} to={executivePath(campaignId, 'surveys')} sx={{ mt: 1 }}>
          VER ENCUESTAS Y ESTUDIOS
        </Button>
      </DashboardCard>

      {data.warnings.map((warning) => (
        <Alert
          key={warning.code}
          severity="warning"
          icon={<WarningAmberIcon />}
          sx={{ mb: 2 }}
          action={
            <Button component={RouterLink} to={executivePath(campaignId, 'current-election')}>
              VER DETALLE
            </Button>
          }
        >
          <Typography fontWeight={700}>
            {warning.code === 'REGISTRATION_SERIES_BREAK'
              ? 'Variación significativa del registro electoral'
              : warning.code}
          </Typography>
          <Typography variant="body2">
            {warning.code === 'REGISTRATION_SERIES_BREAK'
              ? 'La variación entre procesos no debe interpretarse automáticamente como una tendencia demográfica.'
              : warning.message}
          </Typography>
        </Alert>
      ))}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 12, md: 4 }}>
          <DashboardCard>
            <SectionTitle eyebrow="OBSERVADO · CNE">REGISTRO ELECTORAL</SectionTitle>
            <Metric label="Electores" value={integer(current.registered_voters)} />
            <Grid container spacing={2} sx={{ mt: 1.5 }}>
              <Grid size={6}>
                <Metric
                  label="Hombres"
                  value={integer(current.male_voters)}
                  detail={percent(current.male_voters / current.registered_voters)}
                />
              </Grid>
              <Grid size={6}>
                <Metric
                  label="Mujeres"
                  value={integer(current.female_voters)}
                  detail={percent(current.female_voters / current.registered_voters)}
                />
              </Grid>
              <Grid size={6}>
                <Metric label="Juntas" value={integer(current.juntas)} />
              </Grid>
            </Grid>
          </DashboardCard>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <DashboardCard>
            <SectionTitle eyebrow="PROYECTADO · TERRITORIO ELECTORAL">
              PARTICIPACIÓN PROYECTADA
            </SectionTitle>
            <Metric
              label="Escenario central"
              value={`${integer(data.projection.expected_voters_central)} votantes`}
              detail={percent(centralRate)}
            />
            <Grid container spacing={2} sx={{ mt: 2 }}>
              <Grid size={6}>
                <Metric
                  label="Bajo"
                  value={integer(data.projection.expected_voters_low)}
                  detail={percent(data.projection.expected_voters_low / current.registered_voters)}
                />
              </Grid>
              <Grid size={6}>
                <Metric
                  label="Alto"
                  value={integer(data.projection.expected_voters_high)}
                  detail={percent(data.projection.expected_voters_high / current.registered_voters)}
                />
              </Grid>
            </Grid>
          </DashboardCard>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <DashboardCard>
            <SectionTitle>MODELO DE PARTICIPACIÓN</SectionTitle>
            <Typography fontWeight={700} sx={{ overflowWrap: 'anywhere' }}>
              {data.projection.model_code}
            </Typography>
            <Typography>Versión {data.projection.model_version}</Typography>
            <Typography sx={{ mt: 1 }}>
              Calidad: <strong>{computed.modelQuality}</strong>
            </Typography>
            <Typography>35 % × 2019</Typography>
            <Typography>65 % × 2023</Typography>
            <Button
              component={RouterLink}
              to={executivePath(campaignId, 'current-election')}
              sx={{ mt: 1 }}
            >
              VER METODOLOGÍA
            </Button>
          </DashboardCard>
        </Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 12, lg: 5 }}>
          <DashboardCard>
            <SectionTitle>PARTICIPACIÓN HISTÓRICA</SectionTitle>
            <Box
              role="img"
              aria-label="Participación observada 2019 y 2023 comparada con la proyección actual"
              sx={{ height: 260, width: '100%', minWidth: 0 }}
            >
              <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                <BarChart data={historicalChart} margin={{ left: 8, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="year" />
                  <YAxis domain={[0, 100]} tickFormatter={(value) => `${value} %`} />
                  <Tooltip
                    formatter={(value) =>
                      `${Number(value).toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} %`
                    }
                  />
                  <Bar dataKey="rate" name="Participación">
                    {historicalChart.map((entry) => (
                      <Cell
                        key={entry.year}
                        fill={entry.type === 'Observado' ? '#1565c0' : '#ed6c02'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Box>
            <Stack direction="row" gap={2} justifyContent="center" sx={{ mb: 1 }}>
              <Typography variant="caption">
                <Box
                  component="span"
                  sx={{
                    display: 'inline-block',
                    width: 10,
                    height: 10,
                    bgcolor: '#1565c0',
                    mr: 0.5,
                  }}
                />
                Observado · CNE
              </Typography>
              <Typography variant="caption">
                <Box
                  component="span"
                  sx={{
                    display: 'inline-block',
                    width: 10,
                    height: 10,
                    bgcolor: '#ed6c02',
                    mr: 0.5,
                  }}
                />
                Proyectado · Territorio Electoral
              </Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-around" textAlign="center">
              {historicalChart.map((item) => (
                <Metric
                  key={item.year}
                  label={item.year}
                  value={`${item.rate.toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} %`}
                  detail={item.type}
                />
              ))}
            </Stack>
          </DashboardCard>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <CurrentElectionMap
            campaignId={campaignId}
            parishes={data.parishes}
            onSelect={onMapSelect}
            compact
            title="PANORAMA TERRITORIAL"
            onStatusChange={setMapStatus}
          />
        </Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <DashboardCard>
            <SectionTitle>PANORAMA PARROQUIAL</SectionTitle>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <Metric
                  label="Mayor participación central"
                  value={computed.highestCentral?.name ?? '—'}
                  detail={percent(computed.highestCentral?.projection?.central)}
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <Metric
                  label="Menor participación central"
                  value={computed.lowestCentral?.name ?? '—'}
                  detail={percent(computed.lowestCentral?.projection?.central)}
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <Metric
                  label="Mayor registro electoral"
                  value={computed.highestRegistration?.name ?? '—'}
                  detail={
                    computed.highestRegistration
                      ? integer(computed.highestRegistration.registered_voters_current)
                      : '—'
                  }
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <Metric
                  label="Menor registro electoral"
                  value={computed.lowestRegistration?.name ?? '—'}
                  detail={
                    computed.lowestRegistration
                      ? integer(computed.lowestRegistration.registered_voters_current)
                      : '—'
                  }
                />
              </Grid>
            </Grid>
            <TableContainer sx={{ mt: 2 }}>
              <Table size="small" aria-label="Cinco parroquias con mayor registro electoral">
                <TableHead>
                  <TableRow>
                    <TableCell>Parroquia</TableCell>
                    <TableCell align="right">Electores</TableCell>
                    <TableCell align="right">Central %</TableCell>
                    <TableCell align="right">Votantes esperados</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {computed.topFive.map((row) => (
                    <TableRow key={row.parish_id}>
                      <TableCell>{row.name}</TableCell>
                      <TableCell align="right">{integer(row.registered_voters_current)}</TableCell>
                      <TableCell align="right">{percent(row.projection?.central)}</TableCell>
                      <TableCell align="right">
                        {integer(row.projection?.expected_voters_central ?? 0)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <Button
              component={RouterLink}
              to={executivePath(campaignId, 'current-election')}
              endIcon={<OpenInNewIcon />}
              sx={{ mt: 1 }}
            >
              VER LAS {data.parishes.length} PARROQUIAS
            </Button>
          </DashboardCard>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <DashboardCard>
            <SectionTitle eyebrow={`OFICIAL · INEC CPV ${data.demographics.year}`}>
              CONTEXTO TERRITORIAL
            </SectionTitle>
            <Grid container spacing={1.5}>
              <Grid size={12}>
                <Metric label="Población total" value={integer(computed.population)} />
              </Grid>
              <Grid size={6}>
                <Metric label="Hombres" value={integer(computed.populationMale)} />
              </Grid>
              <Grid size={6}>
                <Metric label="Mujeres" value={integer(computed.populationFemale)} />
              </Grid>
            </Grid>
            <Box
              role="img"
              aria-label="Población por grupos de edad"
              sx={{ height: 180, mt: 1, width: '100%', minWidth: 0 }}
            >
              <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                <BarChart data={computed.ages}>
                  <XAxis dataKey="name" />
                  <YAxis hide />
                  <Tooltip formatter={(value) => integer(Number(value))} />
                  <Bar dataKey="value" name="Personas" fill="#607d8b" />
                </BarChart>
              </ResponsiveContainer>
            </Box>
            <Typography variant="body2" color="text.secondary">
              Contexto territorial. No interviene en la fórmula de participación V1.
            </Typography>
          </DashboardCard>
        </Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid size={{ xs: 12, md: 5 }}>
          <DashboardCard>
            <SectionTitle>ESTADO DE DATOS</SectionTitle>
            <Stack spacing={1}>
              {[
                ['CNE 2019', !!data.historical['2019']],
                ['CNE 2023', !!data.historical['2023']],
                ['Registro actual', current.registered_voters > 0],
                ['INEC CPV 2022', computed.population > 0],
                ['Geometrías', mapStatus === 'success'],
              ].map(([label, available]) => (
                <Stack
                  key={String(label)}
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                >
                  <Typography>{label}</Typography>
                  <Chip
                    size="small"
                    icon={available ? <CheckCircleOutlineIcon /> : undefined}
                    color={available ? 'success' : 'default'}
                    label={
                      available
                        ? 'Disponible'
                        : mapStatus === 'loading' && label === 'Geometrías'
                          ? 'Verificando…'
                          : 'No disponible'
                    }
                  />
                </Stack>
              ))}
            </Stack>
          </DashboardCard>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          {operation.isLoading && (
            <DashboardCard>
              <SectionTitle>OPERACIÓN TERRITORIAL</SectionTitle>
              <Skeleton height={130} />
            </DashboardCard>
          )}
          {operation.isError && (
            <DashboardCard>
              <SectionTitle>OPERACIÓN TERRITORIAL</SectionTitle>
              <ErrorState
                message="No fue posible cargar el resumen operacional."
                retry={() => void operation.refetch()}
              />
            </DashboardCard>
          )}
          {operation.isSuccess && (
            <OperationalBlock operation={operation.data} campaignId={campaignId} />
          )}
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <DashboardCard>
            <SectionTitle>ACCESOS RÁPIDOS</SectionTitle>
            <Stack direction="row" gap={1} flexWrap="wrap">
              {quickLinks.map(([label, suffix]) => (
                <Button
                  key={label}
                  variant="outlined"
                  component={RouterLink}
                  to={executivePath(campaignId, suffix)}
                >
                  {label}
                </Button>
              ))}
            </Stack>
          </DashboardCard>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <DashboardCard>
            <SectionTitle>INFORME EJECUTIVO</SectionTitle>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Plantilla CURRENT_ELECTION_EXECUTIVE · corrida V1 almacenada
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} gap={1}>
              {(['PDF', 'XLSX'] as const).map((format) => (
                <Button
                  key={format}
                  variant="contained"
                  startIcon={<DescriptionOutlinedIcon />}
                  disabled={reportStatus === 'preparing'}
                  aria-label={`Generar informe ${format}`}
                  onClick={() => void generateReport(format)}
                >
                  GENERAR INFORME {format}
                </Button>
              ))}
            </Stack>
            {reportStatus === 'preparing' && (
              <Box role="status" sx={{ mt: 1 }}>
                <Typography>Preparando...</Typography>
                <LinearProgress />
              </Box>
            )}
            {reportStatus === 'generated' && (
              <Alert severity="success" sx={{ mt: 1 }}>
                Generado: informe {generatedFormat}
              </Alert>
            )}
            {reportStatus === 'error' && (
              <Alert severity="error" sx={{ mt: 1 }}>
                Error al generar el informe.
              </Alert>
            )}
          </DashboardCard>
        </Grid>
      </Grid>

      <Dialog
        open={!!selectedParish}
        onClose={() => setSelectedParish(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{selectedParish?.name}</DialogTitle>
        <DialogContent>
          <Stack spacing={1}>
            <Typography>
              Electores: {integer(selectedParish?.registered_voters_current ?? 0)}
            </Typography>
            <Typography>
              Participación central: {percent(selectedParish?.projection?.central)}
            </Typography>
            <Typography>
              Votantes esperados:{' '}
              {integer(selectedParish?.projection?.expected_voters_central ?? 0)}
            </Typography>
            <Button component={RouterLink} to={executivePath(campaignId, 'current-election')}>
              ABRIR ELECCIÓN ACTUAL
            </Button>
          </Stack>
          {selectedParish && (
            <Button
              component={RouterLink}
              to={executivePath(campaignId, `territories/${selectedParish.parish_id}`)}
              sx={{ mt: 2 }}
            >
              VER FICHA TERRITORIAL
            </Button>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function OperationalBlock({
  operation,
  campaignId,
}: {
  operation: OperationalSummary;
  campaignId: string;
}) {
  const pending = operation.commitments.pending + operation.commitments.in_progress;
  const activities = operation.activities ?? {
    upcoming: operation.total_activities ?? 0,
    pending_approval: 0,
    completed: 0,
  };
  const needs = operation.needs ?? {
    open: operation.open_needs ?? 0,
    under_review: 0,
    validated: 0,
    critical_unassigned: 0,
  };
  const coverage = operation.coverage ?? {
    total_parishes: 9,
    with_activities: operation.activities_by_parish?.length ?? 0,
    with_needs: operation.needs_by_parish?.length ?? 0,
    with_commitments: operation.parishes_with_commitments ?? 0,
  };
  return (
    <DashboardCard>
      <SectionTitle>OPERACIÓN TERRITORIAL</SectionTitle>
      <Grid container spacing={1.5}>
        <Grid size={{ xs: 6, sm: 3 }}>
          <Metric label="Actividades próximas" value={integer(activities.upcoming)} />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <Metric label="Pendientes de aprobación" value={integer(activities.pending_approval)} />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <Metric label="Compromisos pendientes" value={integer(pending)} />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <Metric label="Necesidades abiertas" value={integer(needs.open)} />
        </Grid>
      </Grid>
      <Typography component="h3" variant="h3" sx={{ mt: 2, mb: 1 }}>
        Cobertura territorial operativa
      </Typography>
      <Grid container spacing={1}>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Metric
            label="Parroquias con actividad registrada"
            value={`${coverage.with_activities} de ${coverage.total_parishes}`}
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Metric
            label="Parroquias con necesidades abiertas"
            value={`${coverage.with_needs} de ${coverage.total_parishes}`}
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Metric
            label="Parroquias con compromisos"
            value={`${coverage.with_commitments} de ${coverage.total_parishes}`}
          />
        </Grid>
      </Grid>
      <Stack direction="row" gap={1} sx={{ mt: 1 }} flexWrap="wrap">
        <Button component={RouterLink} to={executivePath(campaignId, 'operations')}>
          VER OPERACIÓN TERRITORIAL
        </Button>
        <Button component={RouterLink} to={executivePath(campaignId, 'activities')}>
          ACTIVIDADES
        </Button>
        <Button component={RouterLink} to={executivePath(campaignId, 'needs')}>
          NECESIDADES
        </Button>
        <Button component={RouterLink} to={executivePath(campaignId, 'commitments')}>
          COMPROMISOS
        </Button>
      </Stack>
    </DashboardCard>
  );
}
