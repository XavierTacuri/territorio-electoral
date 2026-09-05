import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
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
  cacheMyElectionDayAssignment,
  getCachedMyElectionDayAssignment,
} from '../../offline/electionDayRepository';
import { countPending, enqueue } from '../../offline/syncQueueRepository';
import type { OwnerScope } from '../../offline/types';
import { useOnlineStatus } from '../../offline/useOnlineStatus';
import { SyncNowButton } from '../field/SyncNowButton';
import {
  ASSIGNMENT_STATUS_LABELS,
  INCIDENT_CATEGORY_LABELS,
  type ElectionDayAssignment,
  type PollingPlace,
} from './types';

type CampaignRef = { id: string; name: string; organization_id: string };

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

export default function MyElectionDayPage() {
  const { campaignId = '' } = useParams();
  const { user } = useAuth();
  const online = useOnlineStatus();
  const [scope, setScope] = useState<OwnerScope | null>(null);
  const [assignment, setAssignment] = useState<{
    assignment_id: string;
    assignment_status: string;
    polling_place_id: string;
    polling_place_name: string;
    board_id: string | null;
    board_code: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(0);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [incidentOpen, setIncidentOpen] = useState(false);
  const [incidentCategory, setIncidentCategory] = useState('OTHER');
  const [incidentDescription, setIncidentDescription] = useState('');
  const clientGeneratedId = useRef(crypto.randomUUID());

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!user) return;
      setLoading(true);
      setError(null);
      if (online) {
        try {
          const campaign = await apiRequest<CampaignRef>(`/campaigns/${campaignId}`);
          const my = await apiRequest<ElectionDayAssignment | null>(
            `/campaigns/${campaignId}/election-day/my-assignment`,
          );
          if (!my) {
            if (!cancelled) {
              setAssignment(null);
              setError('No tienes una asignación de jornada en esta campaña.');
            }
            return;
          }
          const place = await apiRequest<PollingPlace>(
            `/campaigns/${campaignId}/election-day/polling-places/${my.polling_place_id}`,
          );
          const scopeValue: OwnerScope = {
            user_id: user.id,
            organization_id: campaign.organization_id,
            campaign_id: campaignId,
          };
          const resolved = {
            assignment_id: my.id,
            assignment_status: my.status,
            polling_place_id: my.polling_place_id,
            polling_place_name: place.name,
            board_id: my.board_id,
            board_code: null,
          };
          await cacheCampaignInfo(campaignId, campaign.organization_id, campaign.name);
          await cacheMyElectionDayAssignment(scopeValue, resolved);
          if (!cancelled) {
            setScope(scopeValue);
            setAssignment(resolved);
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
      const cached = await getCachedMyElectionDayAssignment(scopeValue);
      if (!cancelled) {
        setScope(scopeValue);
        setAssignment(cached ?? null);
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

  async function confirmPresence() {
    if (!scope || !assignment) return;
    const position = await getPosition();
    const draft = await createDraft(
      scope,
      'ELECTION_DAY_CHECK_IN',
      0,
      {
        assignment_id: assignment.assignment_id,
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

  async function reportIncident() {
    if (!scope || !assignment || !incidentDescription.trim()) return;
    const draft = await createDraft(
      scope,
      'ELECTION_DAY_INCIDENT',
      0,
      {
        polling_place_id: assignment.polling_place_id,
        board_id: assignment.board_id,
        category: incidentCategory,
        description: incidentDescription.trim(),
      },
      clientGeneratedId.current,
    );
    await enqueue(scope, draft.id, 'ELECTION_DAY_INCIDENT');
    clientGeneratedId.current = crypto.randomUUID();
    setIncidentOpen(false);
    setIncidentDescription('');
    setSavedMessage('Incidencia guardada en el dispositivo. Se sincronizará con el servidor.');
    await refreshPending();
  }

  async function attachDocument(file: File) {
    if (!scope || !assignment) return;
    const cid = crypto.randomUUID();
    const draft = await createDraft(
      scope,
      'ELECTION_DAY_DOCUMENT',
      0,
      {
        polling_place_id: assignment.polling_place_id,
        board_id: assignment.board_id,
        document_type: 'ACTA_COPY',
      },
      cid,
    );
    await addPendingAttachment(scope, draft.id, file, 'Copia de acta');
    await enqueue(scope, draft.id, 'ELECTION_DAY_DOCUMENT');
    setSavedMessage('Documento guardado en el dispositivo. Se sincronizará con el servidor.');
    await refreshPending();
  }

  if (loading) return <LoadingSkeleton />;

  return (
    <>
      <PageHeader
        title="Mi Jornada"
        description="Confirma tu presencia, reporta incidencias y adjunta documentos — funciona sin conexión."
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
      {assignment && (
        <Card variant="outlined" sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="overline" color="text.secondary">
              Recinto
            </Typography>
            <Typography variant="h3">{assignment.polling_place_name}</Typography>
            {assignment.board_code && (
              <Typography color="text.secondary">Junta: {assignment.board_code}</Typography>
            )}
            <Typography sx={{ mt: 1 }}>
              Estado:{' '}
              {ASSIGNMENT_STATUS_LABELS[
                assignment.assignment_status as keyof typeof ASSIGNMENT_STATUS_LABELS
              ] ?? assignment.assignment_status}
            </Typography>
            <Stack spacing={1.5} sx={{ mt: 2 }}>
              <Button variant="contained" size="large" onClick={() => void confirmPresence()}>
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
                    onClick={() => void reportIncident()}
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
                    if (file) void attachDocument(file);
                  }}
                />
              </Button>
            </Stack>
          </CardContent>
        </Card>
      )}
      {savedMessage && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSavedMessage(null)}>
          {savedMessage}
        </Alert>
      )}
      <Box sx={{ mt: 2 }}>
        <Typography sx={{ mb: 1 }}>Pendientes de sincronización: {pending}</Typography>
        <SyncNowButton scope={scope} onDone={() => void refreshPending()} pendingCount={pending} />
      </Box>
    </>
  );
}
