import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { cacheCampaignInfo, getCachedCampaignInfo } from '../../offline/campaignInfoRepository';
import { addPendingAttachment } from '../../offline/attachmentsRepository';
import { createDraft } from '../../offline/draftsRepository';
import {
  cacheElectionActContext,
  getCachedElectionActContext,
} from '../../offline/electionActRepository';
import {
  cacheMyElectionDayAssignments,
  getCachedMyElectionDayAssignments,
} from '../../offline/electionDayRepository';
import { countPending, enqueue } from '../../offline/syncQueueRepository';
import type {
  CachedElectionActContext,
  CachedElectionDayAssignmentEntry,
  OwnerScope,
} from '../../offline/types';
import { useOnlineStatus } from '../../offline/useOnlineStatus';
import { SyncNowButton } from '../field/SyncNowButton';
import ActFormDialog from './ActFormDialog';
import {
  ACT_STATUS_LABELS,
  ASSIGNMENT_STATUS_LABELS,
  INCIDENT_CATEGORY_LABELS,
  type ElectionActContestOption,
  type ElectionActListResponse,
  type ElectionActStatus,
  type ElectoralBoard,
  type ElectionDayAssignment,
  type ElectionDayMyContext,
  type PollingPlace,
} from './types';

function getPosition(): Promise<{ latitude: number; longitude: number } | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    const timeout = setTimeout(() => resolve(null), 5000);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        clearTimeout(timeout);
        resolve({ latitude: position.coords.latitude, longitude: position.coords.longitude });
      },
      () => {
        clearTimeout(timeout);
        resolve(null);
      },
      { timeout: 4500 },
    );
  });
}

function RecintoCard({
  entry,
  actContext,
  showActs,
  onCheckIn,
  onReportIncident,
  onAttachDocument,
  onOpenActForm,
}: {
  entry: CachedElectionDayAssignmentEntry;
  actContext: CachedElectionActContext | undefined;
  showActs: boolean;
  onCheckIn: (entry: CachedElectionDayAssignmentEntry) => Promise<void>;
  onReportIncident: (
    entry: CachedElectionDayAssignmentEntry,
    category: string,
    description: string,
  ) => Promise<void>;
  onAttachDocument: (entry: CachedElectionDayAssignmentEntry, file: File) => Promise<void>;
  onOpenActForm: (
    entry: CachedElectionDayAssignmentEntry,
    mode: 'REGISTER' | 'CORRECT',
    boardId: string,
    boardLabel: string,
    actId: string | null,
  ) => void;
}) {
  const [incidentOpen, setIncidentOpen] = useState(false);
  const [incidentCategory, setIncidentCategory] = useState('OTHER');
  const [incidentDescription, setIncidentDescription] = useState('');

  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="overline" color="text.secondary">
          Recinto
        </Typography>
        <Typography variant="h3">{entry.polling_place_name}</Typography>
        <Typography sx={{ mt: 1 }}>
          Estado:{' '}
          {ASSIGNMENT_STATUS_LABELS[
            entry.assignment_status as keyof typeof ASSIGNMENT_STATUS_LABELS
          ] ?? entry.assignment_status}
        </Typography>
        <Stack spacing={1.5} sx={{ mt: 2 }}>
          <Button variant="contained" size="large" onClick={() => void onCheckIn(entry)}>
            CONFIRMAR PRESENCIA
          </Button>
          <Button size="large" variant="outlined" onClick={() => setIncidentOpen((v) => !v)}>
            REPORTAR INCIDENCIA
          </Button>
          {incidentOpen && (
            <Stack spacing={1.5} sx={{ p: 2, bgcolor: 'action.hover', borderRadius: 2 }}>
              <TextField
                select
                label="Categoría"
                value={incidentCategory}
                onChange={(e) => setIncidentCategory(e.target.value)}
              >
                {Object.entries(INCIDENT_CATEGORY_LABELS).map(([code, label]) => (
                  <MenuItem key={code} value={code}>
                    {label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                multiline
                minRows={3}
                label="Descripción"
                value={incidentDescription}
                onChange={(e) => setIncidentDescription(e.target.value)}
              />
              <Button
                variant="contained"
                disabled={!incidentDescription.trim()}
                onClick={async () => {
                  await onReportIncident(entry, incidentCategory, incidentDescription.trim());
                  setIncidentOpen(false);
                  setIncidentDescription('');
                }}
              >
                Guardar incidencia
              </Button>
            </Stack>
          )}
          <Button component="label" size="large" variant="outlined">
            ADJUNTAR DOCUMENTO
            <input
              type="file"
              hidden
              accept="application/pdf,image/jpeg,image/png"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void onAttachDocument(entry, file);
              }}
            />
          </Button>
        </Stack>

        {showActs && (
          <Box sx={{ mt: 3 }}>
            <Typography variant="overline" color="text.secondary">
              Actas por junta
            </Typography>
            {!actContext ? (
              <Typography color="text.secondary" sx={{ mt: 1 }}>
                Sin datos de actas guardados en este dispositivo todavía. Conéctate una vez antes de
                empezar el escrutinio.
              </Typography>
            ) : (
              <Stack spacing={1.5} sx={{ mt: 1 }}>
                {actContext.boards.map((board) => {
                  const status = board.act_status as ElectionActStatus | null;
                  const canRegister = !status;
                  const canCorrect = status === 'OBSERVED';
                  return (
                    <Box
                      key={board.board_id}
                      data-testid={`board-row-${board.board_code}`}
                      sx={{
                        p: 1.5,
                        border: 1,
                        borderColor: 'divider',
                        borderRadius: 2,
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: 1,
                      }}
                    >
                      <Box>
                        <Typography variant="body1">Junta {board.board_number}</Typography>
                        <Chip
                          size="small"
                          label={status ? ACT_STATUS_LABELS[status] : 'Sin registrar'}
                          color={
                            status === 'VALIDATED'
                              ? 'success'
                              : status === 'OBSERVED'
                                ? 'warning'
                                : 'default'
                          }
                        />
                      </Box>
                      {canRegister && (
                        <Button
                          variant="contained"
                          size="small"
                          onClick={() =>
                            onOpenActForm(
                              entry,
                              'REGISTER',
                              board.board_id,
                              `Junta ${board.board_number}`,
                              null,
                            )
                          }
                        >
                          REGISTRAR ACTA
                        </Button>
                      )}
                      {canCorrect && (
                        <Button
                          variant="outlined"
                          color="warning"
                          size="small"
                          onClick={() =>
                            onOpenActForm(
                              entry,
                              'CORRECT',
                              board.board_id,
                              `Junta ${board.board_number}`,
                              board.act_id,
                            )
                          }
                        >
                          CORREGIR ACTA
                        </Button>
                      )}
                    </Box>
                  );
                })}
              </Stack>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

// §12: cachea, por recinto, la contienda elegible de la campaña (siempre
// una sola — está delimitada por el office_type de la propia campaña) junto
// con el estado de cada junta, para que el Delegado sepa sin conexión qué
// juntas ya tienen acta y cuáles todavía no.
async function loadActContexts(
  campaignId: string,
  scope: OwnerScope,
  places: PollingPlace[],
): Promise<Record<string, CachedElectionActContext>> {
  const contests = await apiRequest<ElectionActContestOption[]>(
    `/campaigns/${campaignId}/election-day/acts/contests`,
  );
  const contest = contests[0];
  if (!contest) return {};
  const result: Record<string, CachedElectionActContext> = {};
  for (const place of places) {
    const [boards, acts] = await Promise.all([
      apiRequest<ElectoralBoard[]>(
        `/campaigns/${campaignId}/election-day/polling-places/${place.id}/boards`,
      ),
      apiRequest<ElectionActListResponse>(
        `/campaigns/${campaignId}/election-day/acts?polling_place_id=${place.id}`,
      ),
    ]);
    const boardStatuses = boards.map((b) => {
      const act = acts.items.find(
        (a) => a.electoral_board_id === b.id && a.electoral_contest_id === contest.id,
      );
      return {
        board_id: b.id,
        board_code: b.official_code,
        board_number: b.board_number,
        act_id: act?.id ?? null,
        act_status: act?.status ?? null,
        latest_revision_number: act?.latest_revision_number ?? null,
      };
    });
    result[place.id] = await cacheElectionActContext(scope, place.id, {
      contest_id: contest.id,
      contest_name: contest.name,
      vote_method: contest.vote_method,
      candidates: contest.candidates,
      boards: boardStatuses,
    });
  }
  return result;
}

export default function MyElectionDayPage() {
  const { campaignId = '' } = useParams();
  const { user } = useAuth();
  const online = useOnlineStatus();
  const [scope, setScope] = useState<OwnerScope | null>(null);
  const [assignments, setAssignments] = useState<CachedElectionDayAssignmentEntry[]>([]);
  const [actContexts, setActContexts] = useState<Record<string, CachedElectionActContext>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(0);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [actDialog, setActDialog] = useState<{
    entry: CachedElectionDayAssignmentEntry;
    mode: 'REGISTER' | 'CORRECT';
    boardId: string;
    boardLabel: string;
    actId: string | null;
  } | null>(null);
  const clientGeneratedId = useRef(crypto.randomUUID());

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!user) return;
      setLoading(true);
      setError(null);
      if (online) {
        try {
          // §19: nunca GET /campaigns/{id} — personal operativo sin
          // CampaignUser no tiene acceso a ese endpoint general.
          const context = await apiRequest<ElectionDayMyContext>(
            `/campaigns/${campaignId}/election-day/my-context`,
          );
          const mine = await apiRequest<ElectionDayAssignment[]>(
            `/campaigns/${campaignId}/election-day/my-assignments`,
          );
          const delegateAssignments = mine.filter(
            (a) => a.assignment_role === 'POLLING_PLACE_DELEGATE' && a.polling_place_id,
          );
          if (delegateAssignments.length === 0) {
            if (!cancelled) {
              setAssignments([]);
              setError('No tienes una asignación de delegado de recinto en esta campaña.');
            }
            return;
          }
          const places = await Promise.all(
            delegateAssignments.map((a) =>
              apiRequest<PollingPlace>(
                `/campaigns/${campaignId}/election-day/polling-places/${a.polling_place_id}`,
              ),
            ),
          );
          const resolved: CachedElectionDayAssignmentEntry[] = delegateAssignments.map((a, i) => ({
            assignment_id: a.id,
            assignment_status: a.status,
            polling_place_id: a.polling_place_id as string,
            polling_place_name: places[i].name,
          }));
          const scopeValue: OwnerScope = {
            user_id: user.id,
            organization_id: context.organization_id,
            campaign_id: campaignId,
          };
          await cacheCampaignInfo(campaignId, context.organization_id, context.campaign_name);
          await cacheMyElectionDayAssignments(scopeValue, resolved);
          const actCtxMap =
            context.operation_status === 'SCRUTINY'
              ? await loadActContexts(campaignId, scopeValue, places)
              : {};
          if (!cancelled) {
            setScope(scopeValue);
            setAssignments(resolved);
            setActContexts(actCtxMap);
            setPending(await countPending(scopeValue));
          }
          return;
        } catch {
          // Cae al caché offline abajo.
        }
      }
      const campaignInfo = await getCachedCampaignInfo(campaignId);
      if (!campaignInfo) {
        if (!cancelled) setError('Sin datos guardados en este dispositivo todavía.');
        return;
      }
      const scopeValue: OwnerScope = {
        user_id: user.id,
        organization_id: campaignInfo.organization_id,
        campaign_id: campaignId,
      };
      const cached = await getCachedMyElectionDayAssignments(scopeValue);
      const actCtxMap: Record<string, CachedElectionActContext> = {};
      for (const entry of cached?.assignments ?? []) {
        const ctx = await getCachedElectionActContext(scopeValue, entry.polling_place_id);
        if (ctx) actCtxMap[entry.polling_place_id] = ctx;
      }
      if (!cancelled) {
        setScope(scopeValue);
        setAssignments(cached?.assignments ?? []);
        setActContexts(actCtxMap);
        setError(cached ? null : 'Sin datos guardados en este dispositivo todavía.');
        setPending(await countPending(scopeValue));
      }
    }
    void load().finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId, user?.id, online]);

  async function refreshPending() {
    if (scope) setPending(await countPending(scope));
  }

  async function confirmPresence(entry: CachedElectionDayAssignmentEntry) {
    if (!scope) return;
    const position = await getPosition();
    const draft = await createDraft(
      scope,
      'ELECTION_DAY_CHECK_IN',
      0,
      {
        assignment_id: entry.assignment_id,
        latitude: position?.latitude ?? null,
        longitude: position?.longitude ?? null,
      },
      clientGeneratedId.current,
    );
    await enqueue(scope, draft.id, 'ELECTION_DAY_CHECK_IN');
    clientGeneratedId.current = crypto.randomUUID();
    setSavedMessage('Guardado en el dispositivo. Se sincronizará con el servidor.');
    await refreshPending();
  }

  async function reportIncident(
    entry: CachedElectionDayAssignmentEntry,
    category: string,
    description: string,
  ) {
    if (!scope || !description) return;
    const draft = await createDraft(
      scope,
      'ELECTION_DAY_INCIDENT',
      0,
      {
        polling_place_id: entry.polling_place_id,
        board_id: null,
        category,
        description,
      },
      clientGeneratedId.current,
    );
    await enqueue(scope, draft.id, 'ELECTION_DAY_INCIDENT');
    clientGeneratedId.current = crypto.randomUUID();
    setSavedMessage('Incidencia guardada en el dispositivo. Se sincronizará con el servidor.');
    await refreshPending();
  }

  async function attachDocument(entry: CachedElectionDayAssignmentEntry, file: File) {
    if (!scope) return;
    const cid = crypto.randomUUID();
    const draft = await createDraft(
      scope,
      'ELECTION_DAY_DOCUMENT',
      0,
      {
        polling_place_id: entry.polling_place_id,
        board_id: null,
        document_type: 'ACTA_COPY',
      },
      cid,
    );
    await addPendingAttachment(scope, draft.id, file, 'Copia de acta');
    await enqueue(scope, draft.id, 'ELECTION_DAY_DOCUMENT');
    setSavedMessage('Documento guardado en el dispositivo. Se sincronizará con el servidor.');
    await refreshPending();
  }

  // Actualización optimista local: mientras no vuelva a sincronizar con el
  // servidor, oculta REGISTRAR ACTA para la junta recién guardada (evita que
  // el mismo delegado intente registrarla dos veces offline).
  async function handleActSaved(pollingPlaceId: string, boardId: string) {
    if (!scope) return;
    const ctx = actContexts[pollingPlaceId];
    if (ctx) {
      const boards = ctx.boards.map((b) =>
        b.board_id === boardId ? { ...b, act_status: 'RECEIVED' as const } : b,
      );
      const updated = await cacheElectionActContext(scope, pollingPlaceId, {
        contest_id: ctx.contest_id,
        contest_name: ctx.contest_name,
        vote_method: ctx.vote_method,
        candidates: ctx.candidates,
        boards,
      });
      setActContexts((prev) => ({ ...prev, [pollingPlaceId]: updated }));
    }
    setSavedMessage('Acta guardada en el dispositivo. Se sincronizará con el servidor.');
    await refreshPending();
  }

  if (loading) return <LoadingSkeleton />;

  return (
    <>
      <PageHeader
        title="Mi Jornada"
        description="Confirma tu presencia, reporta incidencias y adjunta documentos por cada recinto — funciona sin conexión."
      />
      {!online && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Sin conexión: los registros se guardan en el dispositivo y se sincronizan al reconectar.
        </Alert>
      )}
      {error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {assignments.map((entry) => (
        <RecintoCard
          key={entry.assignment_id}
          entry={entry}
          actContext={actContexts[entry.polling_place_id]}
          showActs={Boolean(actContexts[entry.polling_place_id])}
          onCheckIn={confirmPresence}
          onReportIncident={reportIncident}
          onAttachDocument={attachDocument}
          onOpenActForm={(e, mode, boardId, boardLabel, actId) =>
            setActDialog({ entry: e, mode, boardId, boardLabel, actId })
          }
        />
      ))}
      {savedMessage && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSavedMessage(null)}>
          {savedMessage}
        </Alert>
      )}
      <Box sx={{ mt: 2 }}>
        <Typography sx={{ mb: 1 }}>Pendientes de sincronización: {pending}</Typography>
        <SyncNowButton scope={scope} onDone={() => void refreshPending()} pendingCount={pending} />
      </Box>

      {actDialog && scope && (
        <ActFormDialog
          open
          onClose={() => setActDialog(null)}
          scope={scope}
          mode={actDialog.mode}
          pollingPlaceId={actDialog.entry.polling_place_id}
          boardId={actDialog.boardId}
          boardLabel={actDialog.boardLabel}
          contestId={actContexts[actDialog.entry.polling_place_id]?.contest_id ?? ''}
          contestName={actContexts[actDialog.entry.polling_place_id]?.contest_name ?? ''}
          voteMethod={actContexts[actDialog.entry.polling_place_id]?.vote_method ?? ''}
          candidates={actContexts[actDialog.entry.polling_place_id]?.candidates ?? []}
          actId={actDialog.actId}
          onSaved={() => void handleActSaved(actDialog.entry.polling_place_id, actDialog.boardId)}
        />
      )}
    </>
  );
}
