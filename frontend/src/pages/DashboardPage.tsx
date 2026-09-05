import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Grid,
  LinearProgress,
  Paper,
  Skeleton,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useLocation, useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../api/client';
import { eventStatusLabel } from '../features/calendar/types';
import { CommandCenterMap, type TerritoryOperation } from '../features/dashboard/CommandCenterMap';
import type { ElectionMapParish } from '../features/historical/CurrentElectionMap';
import type { Activity, Commitment } from '../features/operations/types';
import type { CampaignRead } from '../features/campaigns/types';
import type { StudyPage } from '../features/survey-studies/types';
import { formatDateEsEc, formatIntegerEsEc, formatPercentEsEc } from '../lib/formatEsEc';

type Parish = ElectionMapParish & { demographics: Record<string, number> };
type Analysis = {
  context: { campaign_name: string; canton_name: string; election_name: string };
  snapshot: { snapshot_date: string; registered_voters: number };
  historical: Record<string, { turnout_rate: number | null }>;
  projection: { model_code: string; expected_voters_central: number };
  parishes: Parish[];
};
type Operations = {
  activities: {
    total: number;
    demo?: number;
    upcoming: number;
    pending_approval: number;
    completed: number;
  };
  needs: { total: number; demo?: number; open: number; under_review: number; validated: number };
  commitments: { pending: number; in_progress: number; overdue: number; completed: number };
  coverage: {
    total_parishes: number;
    with_activities: number;
    with_needs: number;
    with_commitments: number;
  };
  can_approve?: boolean;
};
type Agenda = { activities: Activity[]; pending_approval: Activity[]; commitments: Commitment[] };
type TerritorySummary = {
  parishes: (TerritoryOperation & {
    latest_activities: { id: string; title: string; date: string; status: string }[];
    latest_needs: { id: string; title: string; date: string; status: string }[];
    latest_commitments: { id: string; title: string; due_date?: string | null; status: string }[];
  })[];
};
type AlertRow = {
  id: string;
  title: string;
  message: string;
  severity: string;
  status: string;
  detected_date: string;
};
type CalendarEventRow = {
  id: string;
  event_type: string;
  title: string;
  starts_at: string;
  is_official: boolean;
  deep_link: string | null;
  status?: string | null;
};
const SEVERITY_LABELS_SHORT: Record<string, string> = {
  INFO: 'Información',
  WARNING: 'Requiere atención',
  CRITICAL: 'Crítica',
};

const route = (id: string, suffix: string) => `/app/campaigns/${id}/${suffix}`;
const integer = (value?: number) => formatIntegerEsEc(value ?? 0);
function Card({ children, sx }: { children: React.ReactNode; sx?: object }) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: { xs: 2, md: 2.5 }, minWidth: 0, overflow: 'hidden', borderRadius: 3, ...sx }}
    >
      {children}
    </Paper>
  );
}
function Heading({ children, eyebrow }: { children: React.ReactNode; eyebrow?: string }) {
  return (
    <Box sx={{ mb: 2 }}>
      {eyebrow && (
        <Typography variant="overline" color="text.secondary">
          {eyebrow}
        </Typography>
      )}
      <Typography component="h2" variant="h2">
        {children}
      </Typography>
    </Box>
  );
}
function Kpi({ value, label, source }: { value: string; label: string; source: string }) {
  return (
    <Card sx={{ height: '100%', p: { xs: 1.75, md: 2 } }}>
      <Typography
        sx={{
          fontSize: { xs: '1.65rem', md: '2rem' },
          fontWeight: 750,
          lineHeight: 1.1,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </Typography>
      <Typography fontWeight={650} sx={{ mt: 0.75 }}>
        {label}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {source}
      </Typography>
    </Card>
  );
}
const SectionError = () => <Alert severity="warning">No fue posible cargar esta sección.</Alert>;
function DashboardSkeleton() {
  return (
    <Box role="status" aria-label="Cargando Centro de Comando Territorial">
      <Skeleton height={100} />
      <Grid container spacing={1.5}>
        {Array.from({ length: 6 }, (_, i) => (
          <Grid key={i} size={{ xs: 6, md: 2 }}>
            <Skeleton variant="rounded" height={118} />
          </Grid>
        ))}
      </Grid>
      <Skeleton variant="rounded" height={460} sx={{ mt: 2 }} />
    </Box>
  );
}

export default function DashboardPage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [question, setQuestion] = useState('');
  const analysis = useQuery({
    queryKey: ['current-election-analysis', campaignId],
    queryFn: ({ signal }) =>
      apiRequest<Analysis>(`/campaigns/${campaignId}/current-election/analysis`, { signal }),
    enabled: !!campaignId,
    retry: 1,
  });
  const operations = useQuery({
    queryKey: ['campaign', campaignId, 'operations-overview'],
    queryFn: ({ signal }) =>
      apiRequest<Operations>(`/campaigns/${campaignId}/operations/summary`, { signal }),
    enabled: !!campaignId,
    retry: 1,
  });
  const agenda = useQuery({
    queryKey: ['campaign', campaignId, 'operations-agenda'],
    queryFn: ({ signal }) =>
      apiRequest<Agenda>(`/campaigns/${campaignId}/operations/agenda`, { signal }),
    enabled: !!campaignId,
    retry: 1,
  });
  const territories = useQuery({
    queryKey: ['campaign', campaignId, 'territories-summary'],
    queryFn: ({ signal }) =>
      apiRequest<TerritorySummary>(`/campaigns/${campaignId}/territories/summary`, { signal }),
    enabled: !!campaignId,
    retry: 1,
  });
  const studies = useQuery({
    queryKey: ['recent-survey-studies', campaignId],
    queryFn: ({ signal }) =>
      apiRequest<StudyPage>(
        `/campaigns/${campaignId}/survey-studies?status=PUBLISHED&page=1&page_size=3`,
        { signal },
      ),
    enabled: !!campaignId,
    retry: 1,
  });
  const campaign = useQuery({
    queryKey: ['campaign', campaignId],
    queryFn: ({ signal }) => apiRequest<CampaignRead>(`/campaigns/${campaignId}`, { signal }),
    enabled: !!campaignId,
    retry: 1,
  });
  const openAlerts = useQuery({
    queryKey: ['campaign', campaignId, 'alerts-open'],
    queryFn: ({ signal }) =>
      apiRequest<{ items: AlertRow[] }>(
        `/campaigns/${campaignId}/alerts?status=OPEN&page=1&page_size=5`,
        { signal },
      ),
    enabled: !!campaignId,
    retry: 1,
  });
  const upcomingEvents = useQuery({
    queryKey: ['campaign', campaignId, 'calendar-upcoming'],
    queryFn: ({ signal }) => {
      const from = new Date(),
        to = new Date();
      to.setDate(to.getDate() + 30);
      const fmt = (d: Date) => d.toISOString().slice(0, 10);
      return apiRequest<{ events: CalendarEventRow[] }>(
        `/campaigns/${campaignId}/calendar?date_from=${fmt(from)}&date_to=${fmt(to)}`,
        { signal },
      );
    },
    enabled: !!campaignId,
    retry: 1,
  });
  const data = analysis.data,
    ops = operations.data,
    today = new Date().toISOString().slice(0, 10);
  const updated = new Intl.DateTimeFormat('es-EC', { hour: '2-digit', minute: '2-digit' }).format(
    new Date(),
  );
  const recent = useMemo(
    () =>
      (territories.data?.parishes ?? [])
        .flatMap((p) => [
          ...p.latest_activities.map((x) => ({
            ...x,
            type: x.status === 'COMPLETED' ? 'Actividad completada' : 'Actividad actualizada',
            module: 'activities',
          })),
          ...p.latest_needs.map((x) => ({
            ...x,
            type: 'Nueva necesidad registrada',
            module: 'needs',
          })),
        ])
        .filter((x) => x.date)
        .sort((a, b) => b.date.localeCompare(a.date))
        .slice(0, 6),
    [territories.data],
  );
  const centralRate = data?.snapshot.registered_voters
    ? data.projection.expected_voters_central / data.snapshot.registered_voters
    : undefined;
  const missingCoverage = Math.max(
    0,
    (ops?.coverage.total_parishes ?? 0) - (ops?.coverage.with_activities ?? 0),
  );
  const ask = (value = question) => {
    if (value.trim())
      navigate(`${route(campaignId, 'territory-ai')}?question=${encodeURIComponent(value.trim())}`);
  };
  if (analysis.isLoading && operations.isLoading) return <DashboardSkeleton />;
  return (
    <Box
      sx={{
        width: '100%',
        maxWidth: 1600,
        minWidth: 0,
        boxSizing: 'border-box',
        mx: 'auto',
        pb: 4,
        overflow: 'hidden',
      }}
    >
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        justifyContent="space-between"
        alignItems={{ md: 'flex-end' }}
        gap={2}
        sx={{ mb: 3 }}
      >
        <Box>
          <Typography variant="overline" color="primary.main">
            CENTRO DE COMANDO
          </Typography>
          <Typography component="h1" variant="h1">
            Centro de Comando Territorial
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.75 }}>
            {data?.context.campaign_name ?? campaign.data?.name ?? 'Campaña'}
            <br />
            {data?.context.canton_name ?? campaign.data?.canton_name ?? 'Cantón'}
            {campaign.data?.province_name ? ` · ${campaign.data.province_name}` : ''}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Última actualización: {updated}
          </Typography>
        </Box>
        <Stack direction={{ xs: 'column', sm: 'row' }} gap={1}>
          <Button
            variant="contained"
            startIcon={<AutoAwesomeOutlinedIcon />}
            component={RouterLink}
            to={route(campaignId, 'territory-ai')}
          >
            CONSULTAR TERRITORIO IA
          </Button>
          <Button component={RouterLink} to={route(campaignId, 'panorama')}>
            VER PANORAMA COMPLETO
          </Button>
          <Button
            component={RouterLink}
            to={`${route(campaignId, 'reports')}?type=CAMPAIGN_EXECUTIVE_REPORT`}
          >
            GENERAR INFORME EJECUTIVO
          </Button>
        </Stack>
      </Stack>
      {(location.state as { message?: string } | null)?.message && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {(location.state as { message: string }).message}
        </Alert>
      )}
      <Grid container spacing={1.5} sx={{ mb: 2.5 }}>
        <Grid size={{ xs: 6, md: 2 }}>
          <Kpi
            value={data ? integer(data.snapshot.registered_voters) : '—'}
            label="Padrón electoral"
            source="CNE · Oficial"
          />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Kpi
            value={centralRate == null ? '—' : formatPercentEsEc(centralRate)}
            label="Participación central"
            source="Modelo de participación V1"
          />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Kpi
            value={data ? integer(data.projection.expected_voters_central) : '—'}
            label="Votantes esperados"
            source="Modelo de participación V1"
          />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Kpi
            value={ops ? integer(ops.activities.total) : '—'}
            label="Actividades"
            source="Registro de campaña"
          />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Kpi
            value={ops ? integer(ops.needs.total) : '—'}
            label="Necesidades"
            source="Registro de campaña"
          />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Kpi
            value={ops ? `${ops.coverage.with_activities} / ${ops.coverage.total_parishes}` : '—'}
            label="Cobertura territorial"
            source="Registro de campaña"
          />
        </Grid>
      </Grid>
      {ops?.can_approve && ops.activities.pending_approval > 0 && (
        <Alert
          icon={<WarningAmberOutlinedIcon />}
          severity="info"
          sx={{ mb: 2 }}
          action={
            <Button component={RouterLink} to={route(campaignId, 'approvals')}>
              REVISAR
            </Button>
          }
        >
          <b>REQUIERE TU ATENCIÓN</b>
          <br />
          {ops.activities.pending_approval} actividades pendientes de aprobación
        </Alert>
      )}
      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <CommandCenterMap
            campaignId={campaignId}
            parishes={data?.parishes ?? []}
            operations={territories.data?.parishes ?? []}
          />
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Card sx={{ height: '100%' }}>
            <Heading eyebrow="ESTADO OPERATIVO">Hoy en territorio</Heading>
            {agenda.isError ? (
              <SectionError />
            ) : agenda.isLoading ? (
              <Skeleton height={220} />
            ) : (
              <Stack spacing={0.5}>
                <OperationalRow
                  label="Actividades programadas hoy"
                  value={
                    (agenda.data?.activities ?? []).filter((x) => x.activity_date === today).length
                  }
                  to={route(campaignId, 'operations/agenda')}
                />
                <OperationalRow
                  label="Actividades pendientes de aprobación"
                  value={agenda.data?.pending_approval.length ?? 0}
                  to={route(campaignId, 'approvals')}
                />
                <OperationalRow
                  label="Necesidades registradas"
                  value={ops?.needs.total ?? 0}
                  to={route(campaignId, 'needs')}
                />
                <OperationalRow
                  label="Actividades realizadas"
                  value={ops?.activities.completed ?? 0}
                  to={route(campaignId, 'activities')}
                />
              </Stack>
            )}
          </Card>
        </Grid>
      </Grid>
      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card sx={{ height: '100%' }}>
            <Heading eyebrow="SÍNTESIS · FUENTES OFICIALES">Panorama electoral</Heading>
            {analysis.isError || !data ? (
              <>
                <Typography color="text.secondary">
                  La campaña no cuenta con datos electorales actuales disponibles.
                </Typography>
                <Button onClick={() => void analysis.refetch()}>REINTENTAR</Button>
              </>
            ) : (
              <Stack spacing={1}>
                <DataLine label="Padrón actual" value={integer(data.snapshot.registered_voters)} />
                <DataLine
                  label="Participación 2019"
                  value={formatPercentEsEc(data.historical['2019']?.turnout_rate)}
                />
                <DataLine
                  label="Participación 2023"
                  value={formatPercentEsEc(data.historical['2023']?.turnout_rate)}
                />
                <DataLine label="Participación central V1" value={formatPercentEsEc(centralRate)} />
                <DataLine
                  label="Votantes esperados"
                  value={integer(data.projection.expected_voters_central)}
                />
                <Chip size="small" label="Oficial" sx={{ alignSelf: 'flex-start' }} />
                <Button
                  component={RouterLink}
                  to={route(campaignId, 'panorama')}
                  sx={{ alignSelf: 'flex-start' }}
                >
                  VER PANORAMA ELECTORAL
                </Button>
              </Stack>
            )}
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <StudiesBlock studies={studies} campaignId={campaignId} />
        </Grid>
      </Grid>
      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card sx={{ height: '100%' }}>
            <Heading>Necesidades territoriales</Heading>
            {operations.isError ? (
              <SectionError />
            ) : (
              <Stack spacing={1}>
                <DataLine label="Total registradas" value={integer(ops?.needs.total)} />
                <DataLine label="En revisión" value={integer(ops?.needs.under_review)} />
                <DataLine
                  label="Parroquias con registros"
                  value={`${ops?.coverage.with_needs ?? 0} de ${ops?.coverage.total_parishes ?? 0}`}
                />
                {(ops?.needs.demo ?? 0) > 0 && (
                  <Chip size="small" label="Datos simulados" sx={{ alignSelf: 'flex-start' }} />
                )}
                <Button
                  component={RouterLink}
                  to={route(campaignId, 'needs')}
                  sx={{ alignSelf: 'flex-start' }}
                >
                  VER NECESIDADES
                </Button>
              </Stack>
            )}
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card sx={{ height: '100%' }}>
            <Heading>Actividades</Heading>
            {operations.isError ? (
              <SectionError />
            ) : (
              <Stack spacing={1}>
                <DataLine label="Próximas" value={integer(ops?.activities.upcoming)} />
                <DataLine
                  label="Pendientes de aprobación"
                  value={integer(ops?.activities.pending_approval)}
                />
                <DataLine label="Realizadas" value={integer(ops?.activities.completed)} />
                <Button
                  component={RouterLink}
                  to={route(campaignId, 'activities')}
                  sx={{ alignSelf: 'flex-start' }}
                >
                  VER ACTIVIDADES
                </Button>
              </Stack>
            )}
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Coverage ops={ops} error={operations.isError} missing={missingCoverage} />
        </Grid>
      </Grid>
      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <RecentActivity items={recent} error={territories.isError} campaignId={campaignId} />
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card
            sx={{
              height: '100%',
              bgcolor: 'primary.main',
              color: 'primary.contrastText',
              border: 0,
            }}
          >
            <Stack direction="row" gap={1}>
              <AutoAwesomeOutlinedIcon />
              <Typography variant="overline">ASISTENTE CON EVIDENCIA</Typography>
            </Stack>
            <Typography component="h2" variant="h2" sx={{ my: 1 }}>
              Territorio IA
            </Typography>
            <Typography sx={{ opacity: 0.9 }}>
              Consulta la información electoral, territorial y operativa de tu campaña con
              respuestas respaldadas por evidencia.
            </Typography>
            <TextField
              fullWidth
              size="small"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && ask()}
              placeholder="Pregunta sobre tu campaña..."
              sx={{ mt: 2, bgcolor: 'background.paper', borderRadius: 1 }}
            />
            <Button
              variant="contained"
              color="inherit"
              onClick={() => ask()}
              sx={{ mt: 1, color: 'primary.main' }}
            >
              CONSULTAR
            </Button>
            <Stack sx={{ mt: 2 }}>
              {[
                '¿Cuál es el panorama electoral actual?',
                '¿Qué actividades requieren atención?',
                '¿Qué necesidades se han registrado?',
                '¿Qué muestran las encuestas publicadas?',
                '¿Cómo ha cambiado la participación electoral?',
              ].map((p) => (
                <Button
                  key={p}
                  onClick={() => ask(p)}
                  sx={{ color: 'inherit', justifyContent: 'flex-start', textAlign: 'left' }}
                >
                  {p}
                </Button>
              ))}
            </Stack>
          </Card>
        </Grid>
      </Grid>
      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid size={{ xs: 12, md: 6 }}>
          <UpcomingEventsBlock query={upcomingEvents} campaignId={campaignId} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <AlertsBlock query={openAlerts} campaignId={campaignId} />
        </Grid>
      </Grid>
    </Box>
  );
}

function StudiesBlock({
  studies,
  campaignId,
}: {
  studies: ReturnType<typeof useQuery<StudyPage>>;
  campaignId: string;
}) {
  const items = studies.data?.items ?? [],
    latest = items[0],
    demo = items.some((x) => x.name.startsWith('[DEMO]'));
  return (
    <Card sx={{ height: '100%' }}>
      <Heading eyebrow="SOLO PUBLICADOS">Encuestas y estudios</Heading>
      {studies.isError ? (
        <SectionError />
      ) : studies.isLoading ? (
        <Skeleton height={180} />
      ) : latest ? (
        <Stack spacing={1}>
          <Typography variant="h3">{studies.data?.total} estudios publicados</Typography>
          <DataLine label="Último estudio" value={latest.name.replace(/^\[DEMO\]\s*/, '')} />
          <DataLine label="Muestra" value={integer(latest.sample_size_total)} />
          <DataLine
            label="Trabajo de campo"
            value={`${formatDateEsEc(latest.fieldwork_start_date)} – ${formatDateEsEc(latest.fieldwork_end_date)}`}
          />
          {demo && (
            <Alert severity="info" icon={false}>
              Datos simulados para demostración.
            </Alert>
          )}
          <Button
            component={RouterLink}
            to={route(campaignId, 'surveys')}
            sx={{ alignSelf: 'flex-start' }}
          >
            VER ENCUESTAS
          </Button>
        </Stack>
      ) : (
        <Typography color="text.secondary">
          Aún no existen encuestas publicadas para esta campaña.
        </Typography>
      )}
    </Card>
  );
}
function Coverage({ ops, error, missing }: { ops?: Operations; error: boolean; missing: number }) {
  return (
    <Card sx={{ height: '100%' }}>
      <Heading>Cobertura territorial</Heading>
      {error ? (
        <SectionError />
      ) : (
        <>
          <Typography variant="h3">
            {ops?.coverage.with_activities ?? 0} de {ops?.coverage.total_parishes ?? 0} parroquias
          </Typography>
          <Typography color="text.secondary">con actividad registrada</Typography>
          <LinearProgress
            variant="determinate"
            value={
              ops?.coverage.total_parishes
                ? (100 * ops.coverage.with_activities) / ops.coverage.total_parishes
                : 0
            }
            sx={{ my: 2, height: 8, borderRadius: 4 }}
          />
          <Typography>
            {missing
              ? `${missing} parroquias sin cobertura operativa.`
              : 'Todas las parroquias cuentan con operación registrada.'}
          </Typography>
        </>
      )}
    </Card>
  );
}
function RecentActivity({
  items,
  error,
  campaignId,
}: {
  items: { id: string; title: string; date: string; type: string; module: string }[];
  error: boolean;
  campaignId: string;
}) {
  return (
    <Card sx={{ height: '100%' }}>
      <Heading eyebrow="ÚLTIMOS MOVIMIENTOS">Actividad reciente</Heading>
      {error ? (
        <SectionError />
      ) : items.length ? (
        <Stack>
          {items.map((item, i) => (
            <Box
              key={`${item.module}-${item.id}-${i}`}
              component={RouterLink}
              to={route(campaignId, item.module)}
              sx={{
                display: 'grid',
                gridTemplateColumns: '80px minmax(0, 1fr)',
                gap: 1.5,
                py: 1.25,
                color: 'inherit',
                textDecoration: 'none',
                borderBottom: i < items.length - 1 ? 1 : 0,
                borderColor: 'divider',
              }}
            >
              <Typography variant="caption" color="text.secondary">
                {formatDateEsEc(item.date)}
              </Typography>
              <Box sx={{ minWidth: 0 }}>
                <Typography fontWeight={700}>{item.type}</Typography>
                <Typography color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
                  {item.title.replace(/^\[DEMO\]\s*/, '')}
                </Typography>
              </Box>
            </Box>
          ))}
        </Stack>
      ) : (
        <Typography color="text.secondary">Aún no hay actividad reciente registrada.</Typography>
      )}
    </Card>
  );
}
function DataLine({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" justifyContent="space-between" gap={2} sx={{ minWidth: 0 }}>
      <Typography color="text.secondary">{label}</Typography>
      <Typography fontWeight={700} textAlign="right" sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>
        {value}
      </Typography>
    </Stack>
  );
}
function OperationalRow({ label, value, to }: { label: string; value: number; to: string }) {
  return (
    <Button
      component={RouterLink}
      to={to}
      sx={{
        justifyContent: 'space-between',
        color: 'text.primary',
        py: 1.25,
        borderBottom: 1,
        borderColor: 'divider',
        borderRadius: 0,
      }}
    >
      <span>{label}</span>
      <Chip size="small" label={value} />
    </Button>
  );
}
function AlertsBlock({
  query,
  campaignId,
}: {
  query: ReturnType<typeof useQuery<{ items: AlertRow[] }>>;
  campaignId: string;
}) {
  const items = query.data?.items ?? [];
  return (
    <Card sx={{ height: '100%' }}>
      <Heading eyebrow="DETERMINÍSTICAS">Alertas</Heading>
      {query.isError ? (
        <SectionError />
      ) : query.isLoading ? (
        <Skeleton height={160} />
      ) : !items.length ? (
        <Typography color="text.secondary">No hay alertas que requieran atención.</Typography>
      ) : (
        <Stack spacing={1}>
          {items.map((a) => (
            <Box
              key={a.id}
              sx={{ display: 'flex', gap: 1.5, p: 1.5, bgcolor: 'action.hover', borderRadius: 2 }}
            >
              <WarningAmberOutlinedIcon color={a.severity === 'CRITICAL' ? 'error' : 'inherit'} />
              <Box sx={{ minWidth: 0 }}>
                <Typography fontWeight={700}>{a.title}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {SEVERITY_LABELS_SHORT[a.severity] ?? a.severity} · {a.message}
                </Typography>
              </Box>
            </Box>
          ))}
        </Stack>
      )}
      <Button component={RouterLink} to={route(campaignId, 'alerts')} sx={{ mt: 1.5 }}>
        VER TODAS
      </Button>
    </Card>
  );
}
function UpcomingEventsBlock({
  query,
  campaignId,
}: {
  query: ReturnType<typeof useQuery<{ events: CalendarEventRow[] }>>;
  campaignId: string;
}) {
  const items = (query.data?.events ?? [])
    .slice()
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
    .slice(0, 5);
  return (
    <Card sx={{ height: '100%' }}>
      <Heading eyebrow="CALENDARIO DE CAMPAÑA">Próximas actividades</Heading>
      {query.isError ? (
        <SectionError />
      ) : query.isLoading ? (
        <Skeleton height={160} />
      ) : !items.length ? (
        <Typography color="text.secondary">
          No hay actividades de campaña programadas en los próximos 30 días.
        </Typography>
      ) : (
        <Stack spacing={0.5}>
          {items.map((e) => (
            <Box
              key={e.id}
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 1,
                py: 1,
                borderBottom: 1,
                borderColor: 'divider',
              }}
            >
              <Typography sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                {formatDateEsEc(e.starts_at.slice(0, 10))} · {e.title}
              </Typography>
              <Chip
                size="small"
                color={e.status === 'COMPLETED' ? 'success' : 'info'}
                label={eventStatusLabel({ status: e.status ?? null })}
              />
            </Box>
          ))}
        </Stack>
      )}
      <Button component={RouterLink} to={route(campaignId, 'calendar')} sx={{ mt: 1.5 }}>
        VER CALENDARIO
      </Button>
    </Card>
  );
}
