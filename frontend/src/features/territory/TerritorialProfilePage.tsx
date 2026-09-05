import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  Grid,
  LinearProgress,
  Link as MuiLink,
  Paper,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
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
import { ApiError } from '../../api/errors';
import { downloadReport } from '../../api/downloads';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { ErrorPage } from '../../pages/ErrorPages';
import { CurrentElectionMap } from '../historical/CurrentElectionMap';
import { formatDateEsEc } from '../../lib/formatEsEc';
import { needStatusLabel } from '../../lib/labels';
import { todayDateOnly } from '../../lib/dates';
import { operationStatusLabel } from '../operations/statusLabels';
import type { Activity, Catalog, Need, Page, Parish as ParishRef } from '../operations/types';
import {
  ageKeys,
  available,
  delta,
  integer,
  percent,
  quality,
  Card,
  KpiMetric,
  Metric,
  type Analysis,
  type Operation,
  type PublishedStudies,
} from './territoryShared';

type CantonRef = { id: number; province_id: number; name: string };
type ProvinceRef = { id: number; name: string };
type PublicItem = {
  id: string;
  title: string;
  source_name: string;
  published_at?: string | null;
  topics: { name: string }[];
};
type TimelineKind = 'activity' | 'need' | 'study' | 'public';
type TimelineItem = {
  date: string;
  kind: TimelineKind;
  label: string;
  title: string;
  href?: string;
};
const TIMELINE_FILTERS: { value: 'all' | TimelineKind; label: string }[] = [
  { value: 'all', label: 'Todos' },
  { value: 'activity', label: 'Actividades' },
  { value: 'need', label: 'Necesidades' },
  { value: 'study', label: 'Estudios' },
  { value: 'public', label: 'Información pública' },
];
const suggestedQuestions = (name: string) => [
  `Resume el expediente territorial de ${name}.`,
  `¿Qué necesidades se han registrado en ${name}?`,
  `¿Qué actividades se han realizado en ${name}?`,
  `¿Qué información demográfica está disponible?`,
  `¿Qué estudios contienen información sobre esta parroquia?`,
  `Resume la evidencia disponible sobre vialidad en esta parroquia.`,
];
const isDemoStudy = (name: string) => name.startsWith('[DEMO]');

function OperationalKpi({
  label,
  isLoading,
  value,
}: {
  label: string;
  isLoading: boolean;
  value: number | undefined;
}) {
  return (
    <Metric
      label={label}
      value={isLoading ? '…' : value == null ? 'Sin datos disponibles' : integer(value)}
    />
  );
}

export default function TerritorialProfilePage() {
  const { campaignId = '', parishId = '' } = useParams();
  const navigate = useNavigate();
  const [reportStatus, setReportStatus] = useState<'idle' | 'preparing' | 'generated' | 'error'>(
    'idle',
  );
  const [timelineFilter, setTimelineFilter] = useState<'all' | TimelineKind>('all');

  const parishAccess = useQuery({
    queryKey: ['parish-access', parishId],
    queryFn: () => apiRequest<ParishRef & { canton_id: number }>(`/parishes/${parishId}`),
    enabled: !!parishId,
    retry: false,
  });
  const canton = useQuery({
    queryKey: ['canton', parishAccess.data?.canton_id],
    queryFn: () => apiRequest<CantonRef>(`/cantons/${parishAccess.data!.canton_id}`),
    enabled: !!parishAccess.data?.canton_id,
    staleTime: Infinity,
  });
  const provinces = useQuery({
    queryKey: ['provinces'],
    queryFn: () => apiRequest<ProvinceRef[]>('/provinces'),
    staleTime: Infinity,
  });
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
  const activities = useQuery({
    queryKey: ['territory-activities', campaignId, parishId],
    queryFn: () =>
      apiRequest<Page<Activity>>(
        `/campaigns/${campaignId}/activities?parish_id=${parishId}&page=1&page_size=5`,
      ),
    enabled: !!campaignId && !!parishId,
    retry: 1,
  });
  const needs = useQuery({
    queryKey: ['territory-needs', campaignId, parishId],
    queryFn: () =>
      apiRequest<Page<Need>>(
        `/campaigns/${campaignId}/needs?parish_id=${parishId}&page=1&page_size=5`,
      ),
    enabled: !!campaignId && !!parishId,
    retry: 1,
  });
  const needCategories = useQuery({
    queryKey: ['need-categories'],
    queryFn: () => apiRequest<Catalog[]>('/need-categories'),
    staleTime: Infinity,
  });
  const studies = useQuery({
    queryKey: ['territory-survey-studies', campaignId, parishId],
    queryFn: () =>
      apiRequest<PublishedStudies>(
        `/campaigns/${campaignId}/survey-studies?status=PUBLISHED&page=1&page_size=100&parish_id=${parishId}`,
      ),
    enabled: !!campaignId && !!parishId,
    retry: 1,
  });
  const publicItems = useQuery({
    queryKey: ['territory-public-items', campaignId, parishId],
    queryFn: () =>
      apiRequest<{ items: PublicItem[] }>(
        `/campaigns/${campaignId}/public-intelligence/items?parish_id=${parishId}&page=1&page_size=5`,
      ),
    enabled: !!campaignId && !!parishId,
    retry: 1,
  });

  const categoryName = useMemo(
    () => new Map((needCategories.data ?? []).map((c) => [c.id, c.name])),
    [needCategories.data],
  );

  if (parishAccess.isLoading) return <LoadingSkeleton />;
  if (parishAccess.isError || !parishAccess.data) {
    const status = parishAccess.error instanceof ApiError ? parishAccess.error.status : undefined;
    if (status === 403)
      return <ErrorPage code="403" message="No tienes acceso territorial a esta parroquia." />;
    if (status === 404) return <ErrorPage code="404" message="La parroquia no existe." />;
    return (
      <ErrorState
        message="No fue posible cargar la parroquia."
        retry={() => void parishAccess.refetch()}
      />
    );
  }
  if (analysis.isLoading) return <LoadingSkeleton />;
  if (analysis.isError || !analysis.data)
    return (
      <ErrorState
        message="No fue posible cargar el expediente territorial."
        retry={() => void analysis.refetch()}
      />
    );
  const data = analysis.data;
  const selected = data.parishes.find((item) => String(item.parish_id) === parishId);
  if (!selected)
    return <ErrorPage code="404" message="La parroquia no pertenece a esta campaña." />;

  const parishInfo = parishAccess.data;
  const provinceName = provinces.data?.find((p) => p.id === canton.data?.province_id)?.name;
  const operationByParish = new Map(
    (operation.data?.parishes ?? []).map((item) => [item.parish_id, item]),
  );
  const parishOperation = operationByParish.get(selected.parish_id);
  const totalPopulation = selected.demographics.POP_TOTAL ?? 0;
  const hasHistory = Boolean(selected.historical_2019 || selected.historical_2023);
  const history = [
    ['2019', selected.historical_2019],
    ['2023', selected.historical_2023],
  ] as const;
  const registrationChanges = [
    [
      '2019 → 2023',
      delta(
        selected.historical_2019?.registered_voters,
        selected.historical_2023?.registered_voters,
      ),
    ],
    [
      '2023 → actual',
      delta(selected.historical_2023?.registered_voters, selected.registered_voters_current),
    ],
    [
      '2019 → actual',
      delta(selected.historical_2019?.registered_voters, selected.registered_voters_current),
    ],
  ] as const;

  const askIa = (question: string) =>
    `/app/campaigns/${campaignId}/territory-ai?parish_id=${selected.parish_id}&question=${encodeURIComponent(question)}`;

  const generate = async (format: 'PDF' | 'XLSX') => {
    setReportStatus('preparing');
    try {
      const run = await apiRequest<{ id: string; artifact?: { original_download_name?: string } }>(
        `/campaigns/${campaignId}/reports/generate`,
        {
          method: 'POST',
          body: JSON.stringify({
            template_code: 'PARISH_TERRITORIAL_PROFILE',
            format,
            title: `Expediente territorial · ${selected.name}`,
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
        run.artifact?.original_download_name ?? `expediente-territorial.${format.toLowerCase()}`,
      );
      setReportStatus('generated');
    } catch {
      setReportStatus('error');
    }
  };

  const timeline: TimelineItem[] = [];
  for (const item of activities.data?.items ?? [])
    timeline.push({
      date: item.activity_date,
      kind: 'activity',
      label: 'Actividad',
      title: `${item.title} · ${operationStatusLabel(item.status)}`,
      href: `/app/campaigns/${campaignId}/activities/${item.id}`,
    });
  for (const item of needs.data?.items ?? [])
    timeline.push({
      date: item.reported_date,
      kind: 'need',
      label: 'Necesidad registrada',
      title: item.title,
      href: `/app/campaigns/${campaignId}/needs/${item.id}`,
    });
  for (const item of studies.data?.items ?? [])
    if (item.fieldwork_end_date)
      timeline.push({
        date: item.fieldwork_end_date,
        kind: 'study',
        label: 'Estudio publicado',
        title: item.name,
        href: `/app/campaigns/${campaignId}/survey-studies/${item.id}`,
      });
  for (const item of publicItems.data?.items ?? [])
    if (item.published_at)
      timeline.push({
        date: item.published_at.slice(0, 10),
        kind: 'public',
        label: 'Información pública',
        title: item.title,
      });
  timeline.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  const filteredTimeline =
    timelineFilter === 'all' ? timeline : timeline.filter((item) => item.kind === timelineFilter);

  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <MuiLink
          component={RouterLink}
          to={`/app/campaigns/${campaignId}/dashboard`}
          underline="hover"
          color="inherit"
        >
          Centro de Comando
        </MuiLink>
        <MuiLink
          component={RouterLink}
          to={`/app/campaigns/${campaignId}/territories`}
          underline="hover"
          color="inherit"
        >
          Inteligencia territorial
        </MuiLink>
        <Typography color="text.primary">{selected.name}</Typography>
      </Breadcrumbs>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: 2,
          flexWrap: 'wrap',
          alignItems: 'flex-start',
          mb: 3,
        }}
      >
        <Box>
          <Typography component="h1" variant="h1">
            EXPEDIENTE TERRITORIAL
          </Typography>
          <Typography variant="h3" sx={{ mt: 1 }}>
            {selected.name}
          </Typography>
          <Typography color="text.secondary">
            {data.context.canton_name}
            {provinceName ? ` · ${provinceName}` : ''}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
            <Chip
              size="small"
              label={parishInfo.parish_type === 'RURAL' ? 'Parroquia rural' : 'Parroquia urbana'}
            />
            <Chip size="small" variant="outlined" label={`DPA ${selected.dpa_code}`} />
          </Stack>
        </Box>
        <Stack direction="row" spacing={1} flexWrap="wrap">
          <Button
            variant="contained"
            component={RouterLink}
            to={askIa(`Resume el expediente territorial de ${selected.name}.`)}
          >
            PREGUNTAR A TERRITORIO IA
          </Button>
          <Button variant="outlined" href="#mapa-territorial">
            VER EN MAPA
          </Button>
        </Stack>
      </Box>
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 6, md: 2 }}>
            <KpiMetric label="Padrón electoral" value={selected.registered_voters_current} />
          </Grid>
          <Grid size={{ xs: 6, md: 2 }}>
            <KpiMetric label="Población" value={selected.demographics.POP_TOTAL ?? null} />
          </Grid>
          <Grid size={{ xs: 6, md: 2 }}>
            <KpiMetric
              label="Participación 2019"
              value={selected.historical_2019?.turnout_rate ?? null}
              formatter={percent}
            />
          </Grid>
          <Grid size={{ xs: 6, md: 2 }}>
            <KpiMetric
              label="Participación 2023"
              value={selected.historical_2023?.turnout_rate ?? null}
              formatter={percent}
            />
          </Grid>
          <Grid size={{ xs: 6, md: 2 }}>
            <OperationalKpi
              label="Actividades registradas"
              isLoading={activities.isLoading}
              value={activities.data?.total}
            />
          </Grid>
          <Grid size={{ xs: 6, md: 2 }}>
            <OperationalKpi
              label="Necesidades registradas"
              isLoading={needs.isLoading}
              value={needs.data?.total}
            />
          </Grid>
        </Grid>
      </Paper>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card title="PADRÓN ELECTORAL" eyebrow="OBSERVADO · CNE">
            <Grid container spacing={2}>
              <Grid size={12}>
                <Metric
                  label="Electores actuales"
                  value={integer(selected.registered_voters_current)}
                />
              </Grid>
              <Grid size={4}>
                <Metric
                  label="Hombres"
                  value={
                    selected.male_voters == null
                      ? 'Sin datos disponibles'
                      : integer(selected.male_voters)
                  }
                />
              </Grid>
              <Grid size={4}>
                <Metric
                  label="Mujeres"
                  value={
                    selected.female_voters == null
                      ? 'Sin datos disponibles'
                      : integer(selected.female_voters)
                  }
                />
              </Grid>
              <Grid size={4}>
                <Metric
                  label="Juntas"
                  value={
                    selected.juntas == null ? 'Sin datos disponibles' : integer(selected.juntas)
                  }
                />
              </Grid>
            </Grid>
            <Typography sx={{ mt: 2 }}>
              Corte: {formatDateEsEc(data.snapshot.snapshot_date)} · Fuente: CNE (oficial)
            </Typography>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card title="PARTICIPACIÓN ELECTORAL" eyebrow="PROYECTADO · ESCENARIOS V1">
            <Grid container spacing={2}>
              {[
                ['BAJO', selected.projection?.low, selected.projection?.expected_voters_low],
                [
                  'CENTRAL',
                  selected.projection?.central,
                  selected.projection?.expected_voters_central,
                ],
                ['ALTO', selected.projection?.high, selected.projection?.expected_voters_high],
              ].map(([label, rate, voters]) => (
                <Grid key={String(label)} size={4}>
                  <Metric
                    label={String(label)}
                    value={rate == null ? 'Sin datos disponibles' : percent(Number(rate))}
                    detail={voters == null ? undefined : `${integer(Number(voters))} votantes`}
                  />
                </Grid>
              ))}
            </Grid>
            <Alert severity="info" sx={{ mt: 2 }}>
              Los escenarios de participación son descriptivos y no constituyen una predicción del
              resultado electoral.
            </Alert>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {data.projection.model_code} · Versión {data.projection.model_version}
            </Typography>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card title="ANTECEDENTES ELECTORALES" eyebrow="OBSERVADO · CNE">
            {!hasHistory ? (
              <Alert severity="info">
                No existen resultados históricos desagregados disponibles para esta parroquia.
              </Alert>
            ) : (
              <>
                <Box sx={{ height: 220, minWidth: 0 }}>
                  <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                    <BarChart
                      data={history.map(([year, h]) => ({
                        year,
                        electores: h?.registered_voters,
                        sufragantes: h?.ballots_cast,
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
                        value={h ? percent(h.turnout_rate) : 'Sin datos disponibles'}
                        detail={
                          h
                            ? `${integer(h.registered_voters)} electores · ${integer(h.ballots_cast)} sufragantes`
                            : undefined
                        }
                      />
                    </Grid>
                  ))}
                </Grid>
                {data.warnings.length > 0 && (
                  <Alert severity="warning" sx={{ mt: 2 }}>
                    La variación del registro no debe interpretarse automáticamente como tendencia
                    demográfica.
                  </Alert>
                )}
                <Typography variant="h3" sx={{ mt: 2 }}>
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
              </>
            )}
          </Card>
        </Grid>
        <Grid size={12} id="mapa-territorial">
          <CurrentElectionMap
            campaignId={campaignId}
            parishes={data.parishes}
            onSelect={(id) => navigate(`/app/campaigns/${campaignId}/territories/${id}`)}
            selectedParishId={selected.parish_id}
            compact
            title={`MAPA · ${selected.name.toUpperCase()}`}
          />
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card title="DEMOGRAFÍA" eyebrow="OFICIAL · INEC CPV 2022">
            {selected.availability.inec_2022 && totalPopulation > 0 ? (
              <>
                <Grid container spacing={2}>
                  <Grid size={4}>
                    <Metric label="Población" value={integer(totalPopulation)} />
                  </Grid>
                  <Grid size={4}>
                    <Metric
                      label="Hombres"
                      value={integer(selected.demographics.POP_MALE ?? 0)}
                      detail={percent((selected.demographics.POP_MALE ?? 0) / totalPopulation)}
                    />
                  </Grid>
                  <Grid size={4}>
                    <Metric
                      label="Mujeres"
                      value={integer(selected.demographics.POP_FEMALE ?? 0)}
                      detail={percent((selected.demographics.POP_FEMALE ?? 0) / totalPopulation)}
                    />
                  </Grid>
                  {ageKeys.map(([label, key]) => (
                    <Grid key={key} size={{ xs: 6, sm: 4 }}>
                      <Metric
                        label={label}
                        value={integer(selected.demographics[key] ?? 0)}
                        detail={percent((selected.demographics[key] ?? 0) / totalPopulation)}
                      />
                    </Grid>
                  ))}
                  <Grid size={6}>
                    <Metric
                      label="Densidad"
                      value={
                        selected.demographics.POPULATION_DENSITY ??
                        selected.demographics.DENSITY ??
                        '—'
                      }
                    />
                  </Grid>
                  <Grid size={6}>
                    <Metric
                      label="Crecimiento 2010–2022"
                      value={percent(selected.population_growth_2010_2022)}
                    />
                  </Grid>
                </Grid>
                <Typography sx={{ mt: 2 }}>Fuente: INEC (oficial)</Typography>
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
          <Card title="DISPONIBILIDAD DE INFORMACIÓN">
            <Stack spacing={1}>
              {(
                [
                  ['Padrón', selected.availability.current_registration],
                  ['CNE 2019', selected.availability.cne_2019],
                  ['CNE 2023', selected.availability.cne_2023],
                  ['Demografía (INEC)', selected.availability.inec_2022],
                  ['Geometría', selected.availability.geometry],
                ] as const
              ).map(([label, value]) => (
                <Stack key={label} direction="row" justifyContent="space-between">
                  <Typography>{label}</Typography>
                  {available(value)}
                </Stack>
              ))}
              <Stack direction="row" justifyContent="space-between">
                <Typography>Encuestas</Typography>
                {studies.isLoading ? (
                  <Chip size="small" label="Cargando…" />
                ) : (
                  <Chip
                    size="small"
                    color={studies.data?.items.length ? 'success' : 'default'}
                    label={studies.data?.items.length ? 'Disponible' : 'Sin cobertura parroquial'}
                  />
                )}
              </Stack>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              Calidad general del análisis:{' '}
              {quality[selected.data_quality_status] ?? selected.data_quality_status}
            </Typography>
          </Card>
        </Grid>
        <Grid size={12}>
          <Card title="OPERACIÓN TERRITORIAL">
            {activities.isLoading ? (
              <LinearProgress />
            ) : activities.isError ? (
              <Alert severity="warning">
                No fue posible cargar la operación territorial. El resto del expediente permanece
                disponible.
              </Alert>
            ) : (
              <>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Metric
                      label="Actividades registradas"
                      value={integer(activities.data?.total ?? parishOperation?.activities ?? 0)}
                    />
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Metric
                      label="Necesidades abiertas"
                      value={integer(parishOperation?.needs_open ?? 0)}
                    />
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Metric
                      label="En revisión"
                      value={integer(parishOperation?.needs_under_review ?? 0)}
                    />
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Metric
                      label="Pendientes de aprobación"
                      value={integer(
                        (activities.data?.items ?? []).filter(
                          (a) => a.approval_status === 'PENDING_APPROVAL',
                        ).length,
                      )}
                    />
                  </Grid>
                </Grid>
                {!activities.data?.items.length ? (
                  <Alert severity="info" sx={{ mt: 2 }}>
                    Aún no se han registrado actividades en esta parroquia.
                  </Alert>
                ) : (
                  <Stack spacing={1} sx={{ mt: 2 }}>
                    {activities.data.items.map((item) => (
                      <Stack
                        key={item.id}
                        direction={{ xs: 'column', md: 'row' }}
                        justifyContent="space-between"
                      >
                        <Typography
                          component={RouterLink}
                          to={`/app/campaigns/${campaignId}/activities/${item.id}`}
                          sx={{ fontWeight: 700, textDecoration: 'none', color: 'inherit' }}
                        >
                          {item.title}
                        </Typography>
                        <Typography color="text.secondary">
                          {formatDateEsEc(item.activity_date)} · {operationStatusLabel(item.status)}
                        </Typography>
                      </Stack>
                    ))}
                  </Stack>
                )}
                <Button
                  component={RouterLink}
                  to={`/app/campaigns/${campaignId}/activities?parish_id=${selected.parish_id}`}
                  sx={{ mt: 2 }}
                >
                  VER TODAS LAS ACTIVIDADES
                </Button>
              </>
            )}
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 6 }}>
          <Card title="NECESIDADES TERRITORIALES">
            <Typography variant="body2" color="text.secondary">
              Registro territorial de situaciones o necesidades identificadas durante la operación
              de campaña.
            </Typography>
            {needs.isLoading ? (
              <LinearProgress sx={{ mt: 2 }} />
            ) : needs.isError ? (
              <Alert severity="warning" sx={{ mt: 2 }}>
                No fue posible cargar las necesidades territoriales.
              </Alert>
            ) : !needs.data?.items.length ? (
              <Alert severity="info" sx={{ mt: 2 }}>
                No existen necesidades territoriales registradas.
              </Alert>
            ) : (
              <Stack spacing={1} sx={{ mt: 2 }}>
                {needs.data.items.map((item) => (
                  <Box key={item.id}>
                    <Typography
                      component={RouterLink}
                      to={`/app/campaigns/${campaignId}/needs/${item.id}`}
                      sx={{ fontWeight: 700, textDecoration: 'none', color: 'inherit' }}
                    >
                      {item.title}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {categoryName.get(item.need_category_id) ?? 'Sin categoría'} ·{' '}
                      {formatDateEsEc(item.reported_date)} · {needStatusLabel(item.status)}
                      {item.activity_id ? ' · Origen: actividad registrada' : ''}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            )}
            <Button
              component={RouterLink}
              to={`/app/campaigns/${campaignId}/needs?parish_id=${selected.parish_id}`}
              sx={{ mt: 2 }}
            >
              VER NECESIDADES DE ESTA PARROQUIA
            </Button>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 6 }}>
          <Card title="ENCUESTAS Y ESTUDIOS" eyebrow="COBERTURA PARROQUIAL · SOLO PUBLICADAS">
            {studies.isError ? (
              <Alert severity="warning">No fue posible cargar las encuestas y estudios.</Alert>
            ) : !studies.data?.items.length ? (
              <Alert severity="info">
                No existen resultados de encuestas con cobertura parroquial.
              </Alert>
            ) : (
              <Stack spacing={2}>
                {studies.data.items.slice(0, 3).map((study) => (
                  <Box key={study.id}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography fontWeight={700}>{study.name}</Typography>
                      {isDemoStudy(study.name) && (
                        <Chip size="small" color="warning" label="DEMO" />
                      )}
                    </Stack>
                    <Typography variant="body2">
                      Trabajo de campo: {formatDateEsEc(study.fieldwork_end_date)} · Muestra:{' '}
                      {integer(study.sample_size_total)} ·{' '}
                      {study.pollster_name || 'Responsable no declarado'}
                    </Typography>
                    {isDemoStudy(study.name) && (
                      <Typography variant="caption" color="warning.main">
                        Datos simulados para demostración.
                      </Typography>
                    )}
                    <Button
                      component={RouterLink}
                      to={`/app/campaigns/${campaignId}/survey-studies/${study.id}`}
                    >
                      VER ESTUDIO
                    </Button>
                  </Box>
                ))}
              </Stack>
            )}
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              Para encuestas con cobertura cantonal, visite{' '}
              <MuiLink component={RouterLink} to={`/app/campaigns/${campaignId}/survey-studies`}>
                Encuestas y Estudios
              </MuiLink>
              .
            </Typography>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 6 }}>
          <Card title="INFORMACIÓN PÚBLICA" eyebrow="EVIDENCIA EXTERNA">
            {publicItems.isError ? (
              <Alert severity="warning">
                No fue posible cargar la información pública; el resto del expediente permanece
                disponible.
              </Alert>
            ) : !publicItems.data?.items.length ? (
              <Typography color="text.secondary">
                No hay publicaciones públicas asociadas a esta parroquia.
              </Typography>
            ) : (
              publicItems.data.items.map((item) => (
                <Stack
                  key={item.id}
                  direction={{ xs: 'column', md: 'row' }}
                  spacing={1}
                  sx={{ py: 1 }}
                >
                  <Typography fontWeight={700}>{item.title}</Typography>
                  <Typography color="text.secondary">
                    {item.source_name} ·{' '}
                    {item.published_at
                      ? formatDateEsEc(item.published_at.slice(0, 10))
                      : 'Sin fecha'}{' '}
                    · {item.topics[0]?.name ?? 'Sin tema'}
                  </Typography>
                </Stack>
              ))
            )}
            <Button
              component={RouterLink}
              to={`/app/campaigns/${campaignId}/public-intelligence?parish_id=${selected.parish_id}`}
            >
              VER MÁS
            </Button>
          </Card>
        </Grid>
        <Grid size={12}>
          <Card title="CRONOLOGÍA TERRITORIAL">
            <ToggleButtonGroup
              exclusive
              size="small"
              value={timelineFilter}
              onChange={(_, value: 'all' | TimelineKind | null) =>
                value && setTimelineFilter(value)
              }
              sx={{ flexWrap: 'wrap' }}
            >
              {TIMELINE_FILTERS.map((f) => (
                <ToggleButton key={f.value} value={f.value}>
                  {f.label}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
            {filteredTimeline.length === 0 ? (
              <Alert severity="info" sx={{ mt: 2 }}>
                No hay eventos registrados para este filtro.
              </Alert>
            ) : (
              <Stack spacing={1.5} sx={{ mt: 2 }}>
                {filteredTimeline.map((item, index) => (
                  <Stack
                    key={`${item.kind}-${index}`}
                    direction={{ xs: 'column', md: 'row' }}
                    spacing={{ xs: 0, md: 2 }}
                  >
                    <Typography color="text.secondary" sx={{ minWidth: 110 }}>
                      {formatDateEsEc(item.date)}
                    </Typography>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="body2" color="text.secondary">
                        {item.label}
                      </Typography>
                      {item.href ? (
                        <Typography
                          component={RouterLink}
                          to={item.href}
                          sx={{ fontWeight: 700, textDecoration: 'none', color: 'inherit' }}
                        >
                          {item.title}
                        </Typography>
                      ) : (
                        <Typography fontWeight={700}>{item.title}</Typography>
                      )}
                    </Box>
                  </Stack>
                ))}
              </Stack>
            )}
          </Card>
        </Grid>
        <Grid size={12}>
          <Card title="TERRITORIO IA" eyebrow={`PREGUNTAR SOBRE ${selected.name.toUpperCase()}`}>
            <Button
              variant="contained"
              component={RouterLink}
              to={askIa(`Resume el expediente territorial de ${selected.name}.`)}
            >
              PREGUNTAR A TERRITORIO IA
            </Button>
            <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 2 }}>
              {suggestedQuestions(selected.name).map((question) => (
                <Chip
                  key={question}
                  label={question}
                  component={RouterLink}
                  to={askIa(question)}
                  clickable
                />
              ))}
            </Stack>
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
          <Card title="DESCARGAR EXPEDIENTE">
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <Button
                variant="contained"
                onClick={() => void generate('PDF')}
                disabled={reportStatus === 'preparing'}
              >
                GENERAR PDF
              </Button>
              <Button
                variant="outlined"
                onClick={() => void generate('XLSX')}
                disabled={reportStatus === 'preparing'}
              >
                GENERAR XLSX
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
            <Button
              component={RouterLink}
              to={`/app/campaigns/${campaignId}/reports?type=PARISH_TERRITORIAL_PROFILE&parish_id=${selected.parish_id}`}
              sx={{ mt: 2 }}
            >
              GENERAR INFORME EN EL CENTRO DE INFORMES
            </Button>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
