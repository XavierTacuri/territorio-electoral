import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  MenuItem,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { useAuth } from '../../auth/AuthProvider';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import { ControlCenterPanel } from './ControlCenterPanel';
import { ElectionDayMap } from './ElectionDayMap';
import { StaffInvitationsSection } from './StaffInvitationsSection';
import {
  INCIDENT_CATEGORY_LABELS,
  INCIDENT_STATUS_LABELS,
  OPERATION_STATUS_LABELS,
  type CoverageSummary,
  type ElectionActCoverageSummary,
  type ElectionDayAdminSupportSession,
  type ElectionDayAssignment,
  type ElectionDayIncident,
  type ElectionDayOperation,
  type ElectionDayPreflightResponse,
  type PollingPlace,
} from './types';

type ElectoralProcessOption = { id: string; name: string; election_date: string };

const canManage = (roles: string[]) =>
  roles.includes('CANDIDATE') || roles.includes('CAMPAIGN_MANAGER');

// Fase 3.1 §3: ciclo visible para Candidato/Jefe de Campaña — nunca el
// vocabulario técnico PREPARATION/ACTIVE/SCRUTINY/CLOSED, que no dice nada a
// quien no conoce el modelo de datos interno.
const CYCLE_STEPS: { status: ElectionDayOperation['status']; label: string }[] = [
  { status: 'PREPARATION', label: 'Preparación' },
  { status: 'ACTIVE', label: 'Jornada activa' },
  { status: 'SCRUTINY', label: 'Escrutinio' },
  { status: 'CLOSED', label: 'Cerrada' },
];

function ElectionDayCycleStepper({ status }: { status: ElectionDayOperation['status'] }) {
  const activeIndex = CYCLE_STEPS.findIndex((s) => s.status === status);
  return (
    <Stepper activeStep={activeIndex} alternativeLabel sx={{ mb: 3 }}>
      {CYCLE_STEPS.map((step) => (
        <Step key={step.status}>
          <StepLabel>{step.label}</StepLabel>
        </Step>
      ))}
    </Stepper>
  );
}

function CreateOperationCard({ campaignId }: { campaignId: string }) {
  const qc = useQueryClient();
  const [processId, setProcessId] = useState('');
  const [electionDate, setElectionDate] = useState('');
  // Only processes that legitimately match this campaign's canton and office
  // (backend-filtered, see ElectoralService.list_processes) are offered — a
  // free picker over every process in the system let users select
  // combinations the backend then rejected.
  const processes = useQuery({
    queryKey: ['electoral-processes-for-election-day', campaignId],
    queryFn: () =>
      apiRequest<ElectoralProcessOption[]>(`/electoral-processes?campaign_id=${campaignId}`),
    enabled: !!campaignId,
  });
  const options = processes.data ?? [];
  const single = options.length === 1 ? options[0] : null;
  const effectiveProcessId = single ? single.id : processId;
  const create = useMutation({
    mutationFn: () =>
      apiRequest<ElectionDayOperation>(`/campaigns/${campaignId}/election-day/operation`, {
        method: 'POST',
        body: JSON.stringify({
          electoral_process_id: effectiveProcessId,
          election_date: electionDate,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['election-day-operation', campaignId] }),
  });
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography component="h2" variant="h2" sx={{ mb: 1 }}>
          Configurar Jornada Electoral
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          Aún no existe una jornada configurada para esta campaña. Confirma el proceso electoral y
          define la fecha de la elección para prepararla.
        </Typography>
        <Stack spacing={2} sx={{ maxWidth: 420 }}>
          {processes.isLoading ? (
            <Typography color="text.secondary">Cargando proceso electoral…</Typography>
          ) : options.length === 0 ? (
            <Alert severity="warning">
              No existe un proceso electoral configurado para el cantón y el cargo de esta campaña.
              Solicita a un administrador que lo registre antes de configurar la jornada.
            </Alert>
          ) : single ? (
            <TextField
              label="Proceso electoral"
              value={single.name}
              disabled
              helperText={`Fecha de elección: ${formatDateOnly(single.election_date)}`}
            />
          ) : (
            <TextField
              select
              label="Proceso electoral"
              value={processId}
              onChange={(e) => setProcessId(e.target.value)}
              helperText={
                options.find((p) => p.id === processId)
                  ? `Fecha de elección: ${formatDateOnly(options.find((p) => p.id === processId)!.election_date)}`
                  : undefined
              }
            >
              {options.map((p) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.name} — {formatDateOnly(p.election_date)}
                </MenuItem>
              ))}
            </TextField>
          )}
          <TextField
            type="date"
            label="Fecha de la elección"
            InputLabelProps={{ shrink: true }}
            value={electionDate}
            onChange={(e) => setElectionDate(e.target.value)}
          />
          <Button
            variant="contained"
            disabled={!effectiveProcessId || !electionDate || create.isPending}
            onClick={() => create.mutate()}
          >
            Crear jornada
          </Button>
          {create.isError && (
            <Alert severity="error">
              No se pudo crear la jornada. Verifica que el proceso corresponda a esta campaña.
            </Alert>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function ElectionDayPage() {
  const { campaignId = '' } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [closeOpen, setCloseOpen] = useState(false);
  const roles = user?.roles.map((r) => r.code) ?? [];
  const manager = canManage(roles);
  const platformAdmin = roles.includes('ADMIN') || Boolean(user?.is_superuser);

  const operation = useQuery({
    queryKey: ['election-day-operation', campaignId],
    queryFn: () =>
      apiRequest<ElectionDayOperation>(`/campaigns/${campaignId}/election-day/operation`),
    retry: false,
  });
  const notConfigured =
    operation.isError && operation.error instanceof ApiError && operation.error.status === 404;
  const supportRequired =
    platformAdmin &&
    !manager &&
    operation.isError &&
    operation.error instanceof ApiError &&
    operation.error.status === 403;
  const active = Boolean(operation.data);

  const campaignRef = useQuery({
    queryKey: ['election-day-campaign-ref', campaignId],
    queryFn: () => apiRequest<{ id: string; name: string }>(`/campaigns/${campaignId}`),
    enabled: platformAdmin && !manager,
  });
  const adminSupport = useQuery({
    queryKey: ['election-day-admin-support-current', campaignId],
    queryFn: () =>
      apiRequest<ElectionDayAdminSupportSession | null>(
        `/campaigns/${campaignId}/election-day/admin-support/current`,
      ),
    enabled: platformAdmin && !manager && active,
    retry: false,
  });
  const endSupportMutation = useMutation({
    mutationFn: () =>
      apiRequest<ElectionDayAdminSupportSession>(
        `/campaigns/${campaignId}/election-day/admin-support/end`,
        { method: 'POST' },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['election-day-admin-support-current', campaignId] });
      qc.invalidateQueries({ queryKey: ['election-day-operation', campaignId] });
    },
  });
  const preflight = useQuery({
    queryKey: ['election-day-preflight', campaignId],
    queryFn: () =>
      apiRequest<ElectionDayPreflightResponse>(
        `/campaigns/${campaignId}/election-day/operation/preflight`,
      ),
    enabled: active && manager && operation.data?.status === 'PREPARATION',
  });

  const coverage = useQuery({
    queryKey: ['election-day-coverage', campaignId],
    queryFn: () => apiRequest<CoverageSummary>(`/campaigns/${campaignId}/election-day/coverage`),
    enabled: active,
    refetchInterval: operation.data?.status === 'ACTIVE' ? 45000 : false,
  });
  // §37: métricas puramente documentales (cuántas actas llegaron y en qué
  // estado) — nunca conteo de votos, ranking ni ganador. Solo tiene sentido
  // una vez empezado el escrutinio.
  const actsCoverage = useQuery({
    queryKey: ['election-acts-coverage', campaignId],
    queryFn: () =>
      apiRequest<ElectionActCoverageSummary>(`/campaigns/${campaignId}/election-day/acts/coverage`),
    enabled:
      active && (operation.data?.status === 'SCRUTINY' || operation.data?.status === 'CLOSED'),
    refetchInterval: operation.data?.status === 'SCRUTINY' ? 30000 : false,
  });
  const places = useQuery({
    queryKey: ['election-day-places', campaignId],
    queryFn: () =>
      apiRequest<{ items: PollingPlace[] }>(`/campaigns/${campaignId}/election-day/polling-places`),
    enabled: active,
  });
  const assignments = useQuery({
    queryKey: ['election-day-assignments', campaignId],
    queryFn: () =>
      apiRequest<{ items: ElectionDayAssignment[] }>(
        `/campaigns/${campaignId}/election-day/assignments`,
      ),
    enabled: active,
    refetchInterval: operation.data?.status === 'ACTIVE' ? 45000 : false,
  });
  const incidents = useQuery({
    queryKey: ['election-day-incidents', campaignId, 'OPEN'],
    queryFn: () =>
      apiRequest<{ items: ElectionDayIncident[] }>(
        `/campaigns/${campaignId}/election-day/incidents`,
      ),
    enabled: active,
    refetchInterval: operation.data?.status === 'ACTIVE' ? 45000 : false,
  });

  const openMutation = useMutation({
    mutationFn: () =>
      apiRequest<ElectionDayOperation>(`/campaigns/${campaignId}/election-day/operation/open`, {
        method: 'POST',
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['election-day-operation', campaignId] }),
  });
  const startScrutinyMutation = useMutation({
    mutationFn: () =>
      apiRequest<ElectionDayOperation>(
        `/campaigns/${campaignId}/election-day/operation/start-scrutiny`,
        { method: 'POST' },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['election-day-operation', campaignId] }),
  });
  const closeMutation = useMutation({
    mutationFn: () =>
      apiRequest<ElectionDayOperation>(`/campaigns/${campaignId}/election-day/operation/close`, {
        method: 'POST',
        body: JSON.stringify({}),
      }),
    onSuccess: () => {
      setCloseOpen(false);
      qc.invalidateQueries({ queryKey: ['election-day-operation', campaignId] });
    },
  });

  if (operation.isLoading) return <LoadingSkeleton />;
  if (supportRequired) {
    return (
      <>
        <PageHeader
          title="Jornada Electoral"
          description="Centro operativo del día de la elección."
        />
        <Alert
          severity="info"
          action={
            <Button
              component={RouterLink}
              to="/app/admin/election-day-support"
              color="inherit"
              size="small"
            >
              IR A SOPORTE JORNADA ELECTORAL
            </Button>
          }
        >
          Necesitas iniciar el modo soporte administrativo para esta campaña antes de consultar el
          Centro de Control.
        </Alert>
      </>
    );
  }
  if (notConfigured) {
    return (
      <>
        <PageHeader
          title="Jornada Electoral"
          description="Centro operativo del día de la elección."
        />
        {manager ? (
          <CreateOperationCard campaignId={campaignId} />
        ) : (
          <EmptyState
            title="No hay una jornada configurada para esta campaña."
            detail="Solicita a un responsable de campaña que la configure."
          />
        )}
      </>
    );
  }
  if (operation.isError || !operation.data) return <ErrorState retry={() => operation.refetch()} />;

  const op = operation.data;
  const cov = coverage.data;
  const openIncidents = incidents.data?.items.filter((i) => i.status !== 'RESOLVED') ?? [];
  const notCheckedIn = (assignments.data?.items ?? []).filter(
    (a) => a.status === 'ASSIGNED' || a.status === 'CONFIRMED',
  );
  const coveredIds = new Set(
    (assignments.data?.items ?? [])
      .filter((a) => a.status !== 'REPLACED' && a.polling_place_id)
      .map((a) => a.polling_place_id as string),
  );
  const checkedInIds = new Set(
    (assignments.data?.items ?? [])
      .filter((a) => a.status === 'CHECKED_IN' && a.polling_place_id)
      .map((a) => a.polling_place_id as string),
  );

  const isAdminSupport = platformAdmin && !manager;

  return (
    <>
      {isAdminSupport && adminSupport.data && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              disabled={endSupportMutation.isPending}
              onClick={() => endSupportMutation.mutate()}
            >
              SALIR DEL MODO SOPORTE
            </Button>
          }
        >
          Modo soporte administrativo · Campaña: {campaignRef.data?.name ?? campaignId}
        </Alert>
      )}
      <PageHeader
        title="Jornada Electoral"
        description="Centro operativo de la jornada electoral: cobertura, presencia y validación de actas."
        action={
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              color={
                op.status === 'ACTIVE'
                  ? 'success'
                  : op.status === 'CLOSED'
                    ? 'default'
                    : op.status === 'SCRUTINY'
                      ? 'info'
                      : 'warning'
              }
              label={OPERATION_STATUS_LABELS[op.status]}
            />
            {manager && op.status === 'PREPARATION' && (
              <Button
                variant="contained"
                disabled={openMutation.isPending || preflight.data?.ready === false}
                onClick={() => openMutation.mutate()}
              >
                Activar jornada
              </Button>
            )}
            {manager && op.status === 'ACTIVE' && (
              <Button
                variant="contained"
                disabled={startScrutinyMutation.isPending}
                onClick={() => startScrutinyMutation.mutate()}
              >
                Iniciar escrutinio
              </Button>
            )}
            {manager && op.status === 'SCRUTINY' && (
              <Button variant="outlined" color="warning" onClick={() => setCloseOpen(true)}>
                Cerrar jornada
              </Button>
            )}
          </Stack>
        }
      />
      {manager && <ElectionDayCycleStepper status={op.status} />}
      {op.status === 'CLOSED' && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <strong>Jornada cerrada.</strong> Esta jornada ya no admite cambios operativos. El Centro
          de Control permanece disponible en modo consulta.
        </Alert>
      )}
      {manager && op.status === 'PREPARATION' && preflight.data && (
        <Stack spacing={1} sx={{ mb: 2 }}>
          {preflight.data.blockers.map((b) => (
            <Alert key={b} severity="error">
              {b}
            </Alert>
          ))}
          {preflight.data.warnings.map((w) => (
            <Alert key={w} severity="warning">
              {w}
            </Alert>
          ))}
        </Stack>
      )}
      {openMutation.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          No se pudo activar la jornada. Verifica los bloqueos indicados arriba.
        </Alert>
      )}
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Fecha: {formatDateOnly(op.election_date)} · Actualización operativa{' '}
        {op.status === 'ACTIVE' ? 'cada 45 s' : 'manual'}
      </Typography>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          ['Recintos', cov ? `${cov.covered_polling_places} / ${cov.total_polling_places}` : '—'],
          ['Juntas', cov ? `${cov.covered_boards} / ${cov.total_boards}` : '—'],
          [
            'Personal presente',
            cov ? `${cov.personnel_checked_in} / ${cov.personnel_confirmed}` : '—',
          ],
          ['Incidencias abiertas', cov ? cov.open_incidents : '—'],
          [
            'Documentos recibidos',
            cov ? `${cov.documents_received} / ${cov.expected_documents}` : '—',
          ],
        ].map(([label, value]) => (
          <Grid key={label} size={{ xs: 6, md: 2.4 }}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="overline" color="text.secondary">
                  {label}
                </Typography>
                <Typography variant="h3">{value}</Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {(op.status === 'SCRUTINY' || op.status === 'CLOSED') && actsCoverage.data && (
        <Card variant="outlined" sx={{ mb: 3 }}>
          <CardContent>
            <Typography component="h2" variant="h2" sx={{ mb: 1 }}>
              Actas
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Cobertura documental del escrutinio — nunca conteo de votos ni resultado.
            </Typography>
            <Grid container spacing={2}>
              {[
                ['JRV esperadas', actsCoverage.data.expected_boards],
                ['Recibidas', actsCoverage.data.received],
                ['Validadas', actsCoverage.data.validated],
                ['En revisión', actsCoverage.data.in_review],
                ['Observadas', actsCoverage.data.observed],
                ['Pendientes', actsCoverage.data.pending],
                ['Cobertura recibida', `${actsCoverage.data.received_coverage_pct}%`],
                ['Cobertura validada', `${actsCoverage.data.validated_coverage_pct}%`],
              ].map(([label, value]) => (
                <Grid key={label} size={{ xs: 6, md: 2 }}>
                  <Typography variant="overline" color="text.secondary">
                    {label}
                  </Typography>
                  <Typography variant="h3">{value}</Typography>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      )}

      {(op.status === 'SCRUTINY' || op.status === 'CLOSED') && (
        <ControlCenterPanel
          campaignId={campaignId}
          operationStatus={op.status}
          isAdminSupport={isAdminSupport}
        />
      )}

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 8 }}>
          {places.data && (
            <ElectionDayMap
              places={places.data.items}
              coveredIds={coveredIds}
              checkedInIds={checkedInIds}
              incidents={incidents.data?.items ?? []}
              onSelect={(place) => {
                window.location.assign(
                  `/app/campaigns/${campaignId}/election-day/polling-places/${place.id}`,
                );
              }}
            />
          )}
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Typography component="h2" variant="h2" sx={{ mb: 1 }}>
                Requiere atención
              </Typography>
              {openIncidents.length === 0 && notCheckedIn.length === 0 ? (
                <Typography color="text.secondary">Sin pendientes por ahora.</Typography>
              ) : (
                <Stack spacing={1}>
                  {openIncidents.slice(0, 3).map((i) => (
                    <Alert key={i.id} severity="warning" variant="outlined">
                      {INCIDENT_CATEGORY_LABELS[i.category]} — {INCIDENT_STATUS_LABELS[i.status]}
                    </Alert>
                  ))}
                  {notCheckedIn.length > 0 && (
                    <Alert severity="info" variant="outlined">
                      {notCheckedIn.length} persona(s) asignada(s) aún sin confirmar presencia.
                    </Alert>
                  )}
                </Stack>
              )}
              <Button
                component={RouterLink}
                to={`/app/campaigns/${campaignId}/alerts`}
                sx={{ mt: 1 }}
              >
                VER TODAS LAS ALERTAS
              </Button>
            </CardContent>
          </Card>
          <Card variant="outlined">
            <CardContent>
              <Typography component="h2" variant="h2" sx={{ mb: 1 }}>
                Incidencias recientes
              </Typography>
              {(incidents.data?.items ?? []).length === 0 ? (
                <Typography color="text.secondary">No hay incidencias abiertas.</Typography>
              ) : (
                <Stack spacing={1}>
                  {(incidents.data?.items ?? []).slice(0, 5).map((i) => (
                    <Box key={i.id} sx={{ py: 0.5, borderBottom: 1, borderColor: 'divider' }}>
                      <Typography variant="body2">
                        {INCIDENT_CATEGORY_LABELS[i.category]} · {INCIDENT_STATUS_LABELS[i.status]}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Typography component="h2" variant="h2" sx={{ mt: 4, mb: 2 }}>
        Recintos electorales
      </Typography>
      {!places.data?.items.length ? (
        <EmptyState
          title="No existen recintos cargados para este proceso."
          detail="Agrega recintos desde la administración de la jornada."
        />
      ) : (
        <Stack spacing={1}>
          {places.data.items.map((place) => (
            <Card variant="outlined" key={place.id}>
              <CardContent
                sx={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: 1,
                }}
              >
                <Box>
                  <Typography fontWeight={700}>{place.name}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {place.official_code} · {place.address || 'Sin dirección registrada'}
                  </Typography>
                </Box>
                <Button
                  component={RouterLink}
                  to={`/app/campaigns/${campaignId}/election-day/polling-places/${place.id}`}
                >
                  VER RECINTO
                </Button>
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}

      {manager && (
        <StaffInvitationsSection
          campaignId={campaignId}
          places={places.data?.items ?? []}
          operationStatus={op.status}
        />
      )}

      <Dialog open={closeOpen} onClose={() => setCloseOpen(false)} fullWidth>
        <DialogTitle>Cerrar jornada</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Typography>
              Recintos cubiertos: {cov?.covered_polling_places ?? 0}/
              {cov?.total_polling_places ?? 0} · Juntas cubiertas: {cov?.covered_boards ?? 0}/
              {cov?.total_boards ?? 0}
            </Typography>
            <Typography>Incidencias abiertas: {cov?.open_incidents ?? 0}</Typography>
            <Typography>
              Documentos recibidos: {cov?.documents_received ?? 0}/{cov?.expected_documents ?? 0}
            </Typography>
            {(cov?.open_incidents ?? 0) > 0 && (
              <Alert severity="warning">
                Existen incidencias sin resolver. Podrán resolverse administrativamente después del
                cierre.
              </Alert>
            )}
            {actsCoverage.data && actsCoverage.data.received - actsCoverage.data.validated > 0 && (
              <Alert severity="warning">
                Existen {actsCoverage.data.received - actsCoverage.data.validated} actas recibidas
                que todavía no han sido validadas.
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCloseOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            color="warning"
            disabled={closeMutation.isPending}
            onClick={() => closeMutation.mutate()}
          >
            Confirmar cierre
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
