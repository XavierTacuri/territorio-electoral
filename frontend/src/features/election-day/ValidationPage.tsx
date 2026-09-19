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
  Divider,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiBlob, apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import {
  ACT_STATUS_LABELS,
  type ElectionActDetail,
  type ElectionActListResponse,
  type ElectionActRead,
} from './types';

type Toast = { severity: 'success' | 'error'; message: string };

// Las actas requieren Bearer token (no basta la cookie de sesión), así que
// no puede ser un <a href> directo — se descarga el blob autenticado y se
// abre en una pestaña nueva, igual que el patrón de descarga de reportes.
async function viewEvidence(campaignId: string, actId: string, evidenceId: string) {
  const { blob } = await apiBlob(
    `/campaigns/${campaignId}/election-day/acts/${actId}/evidence/${evidenceId}/download`,
  );
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank', 'noopener,noreferrer');
  window.setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function ActReviewCard({
  campaignId,
  act,
  onDone,
}: {
  campaignId: string;
  act: ElectionActRead;
  onDone: (message: string) => void;
}) {
  const qc = useQueryClient();
  const [observing, setObserving] = useState(false);
  const [reason, setReason] = useState('');
  const [actionError, setActionError] = useState('');

  const detail = useQuery({
    queryKey: ['election-act-detail', campaignId, act.id],
    queryFn: () =>
      apiRequest<ElectionActDetail>(`/campaigns/${campaignId}/election-day/acts/${act.id}`),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['election-act-queue', campaignId] });
    qc.invalidateQueries({ queryKey: ['election-act-detail', campaignId, act.id] });
  };

  const claim = useMutation({
    mutationFn: () =>
      apiRequest<ElectionActRead>(`/campaigns/${campaignId}/election-day/acts/${act.id}/claim`, {
        method: 'POST',
      }),
    onError: (error) =>
      setActionError(
        error instanceof ApiError && error.status === 409
          ? 'Esta acta está siendo revisada por otro validador.'
          : 'No fue posible reclamar esta acta.',
      ),
    onSuccess: () => {
      setActionError('');
      invalidate();
    },
  });

  const release = useMutation({
    mutationFn: () =>
      apiRequest<ElectionActRead>(`/campaigns/${campaignId}/election-day/acts/${act.id}/release`, {
        method: 'POST',
      }),
    onSuccess: () => invalidate(),
  });

  const revisionId = detail.data?.revisions
    .filter((r) => r.status === 'SUBMITTED')
    .slice(-1)[0]?.id;

  const validate = useMutation({
    mutationFn: () =>
      apiRequest<ElectionActRead>(`/campaigns/${campaignId}/election-day/acts/${act.id}/validate`, {
        method: 'POST',
        body: JSON.stringify({ revision_id: revisionId }),
      }),
    onError: (error) =>
      setActionError(
        error instanceof ApiError && error.status === 409
          ? 'El acta cambió desde que la revisaste. Actualiza antes de continuar.'
          : 'No fue posible validar el acta.',
      ),
    onSuccess: () => {
      setActionError('');
      onDone('Acta validada.');
      invalidate();
    },
  });

  const observe = useMutation({
    mutationFn: () =>
      apiRequest<ElectionActRead>(`/campaigns/${campaignId}/election-day/acts/${act.id}/observe`, {
        method: 'POST',
        body: JSON.stringify({ revision_id: revisionId, reason }),
      }),
    onError: (error) =>
      setActionError(
        error instanceof ApiError && error.status === 409
          ? 'El acta cambió desde que la revisaste. Actualiza antes de continuar.'
          : 'No fue posible observar el acta.',
      ),
    onSuccess: () => {
      setActionError('');
      setObserving(false);
      setReason('');
      onDone('Acta observada.');
      invalidate();
    },
  });

  const claimedByMe = Boolean(act.review_claimed_by_user_id) && !claim.isPending;

  return (
    <Card
      variant="outlined"
      sx={{ mb: 2 }}
      data-testid={
        detail.data ? `act-card-${detail.data.electoral_board_code}` : `act-card-${act.id}`
      }
    >
      <CardContent>
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="center"
          flexWrap="wrap"
          gap={1}
        >
          <Box>
            <Typography variant="h3">
              {detail.data?.polling_place_name ?? 'Cargando…'} —{' '}
              {detail.data?.electoral_board_code ?? ''}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {detail.data?.electoral_contest_name} · Revisión #{act.latest_revision_number}
            </Typography>
          </Box>
          <Chip
            size="small"
            label={ACT_STATUS_LABELS[act.status]}
            color={act.status === 'OBSERVED' ? 'warning' : 'default'}
          />
        </Stack>

        {detail.isLoading && <LoadingSkeleton />}
        {detail.data && (
          <>
            <Divider sx={{ my: 1.5 }} />
            {detail.data.revisions
              .filter((r) => r.status === 'SUBMITTED')
              .slice(-1)
              .map((rev) => (
                <Stack key={rev.id} spacing={0.5}>
                  <Typography variant="body2">
                    Blancos: {rev.blank_ballots} · Nulos: {rev.null_ballots} · Válidos:{' '}
                    {rev.valid_ballots ?? '—'} · Total escrutado: {rev.ballots_counted ?? '—'}
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    {rev.results.map((r) => (
                      <Chip
                        key={r.electoral_candidate_id}
                        size="small"
                        label={`${r.votes} votos`}
                      />
                    ))}
                  </Stack>
                  <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                    {rev.evidence.map((ev) => (
                      <Button
                        key={ev.id}
                        size="small"
                        onClick={() => void viewEvidence(campaignId, act.id, ev.id)}
                      >
                        Ver foto
                      </Button>
                    ))}
                  </Stack>
                </Stack>
              ))}

            {actionError && (
              <Alert severity="error" sx={{ mt: 1.5 }}>
                {actionError}
              </Alert>
            )}

            <Stack direction="row" spacing={1.5} sx={{ mt: 2 }} flexWrap="wrap">
              {!act.review_claimed_by_user_id && (
                <Button
                  variant="contained"
                  disabled={claim.isPending}
                  onClick={() => claim.mutate()}
                >
                  RECLAMAR PARA REVISAR
                </Button>
              )}
              {claimedByMe && (
                <>
                  <Button
                    variant="contained"
                    color="success"
                    disabled={validate.isPending || !revisionId}
                    onClick={() => validate.mutate()}
                  >
                    VALIDAR
                  </Button>
                  <Button
                    variant="outlined"
                    color="warning"
                    onClick={() => setObserving(true)}
                    disabled={observe.isPending}
                  >
                    OBSERVAR
                  </Button>
                  <Button
                    variant="text"
                    disabled={release.isPending}
                    onClick={() => release.mutate()}
                  >
                    LIBERAR
                  </Button>
                </>
              )}
            </Stack>
          </>
        )}
      </CardContent>

      <Dialog open={observing} onClose={() => setObserving(false)} fullWidth>
        <DialogTitle>Observar acta</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            multiline
            minRows={3}
            fullWidth
            label="Motivo de la observación"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setObserving(false)}>Cancelar</Button>
          <Button
            variant="contained"
            color="warning"
            disabled={!reason.trim() || observe.isPending}
            onClick={() => observe.mutate()}
          >
            Confirmar observación
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}

export default function ValidationPage() {
  const { campaignId = '' } = useParams();
  const [toast, setToast] = useState<Toast | null>(null);

  const queue = useQuery({
    queryKey: ['election-act-queue', campaignId],
    queryFn: () =>
      apiRequest<ElectionActListResponse>(
        `/campaigns/${campaignId}/election-day/acts/validation/queue?page_size=50`,
      ),
    retry: false,
    refetchInterval: 20000,
  });

  if (queue.isLoading) return <LoadingSkeleton />;

  if (queue.isError) {
    const forbidden = queue.error instanceof ApiError && queue.error.status === 403;
    return (
      <>
        <PageHeader title="Validación de actas" />
        {forbidden ? (
          <Alert severity="warning">
            No tienes una asignación de validador de actas en esta jornada.
          </Alert>
        ) : (
          <ErrorState retry={() => queue.refetch()} />
        )}
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Validación de actas"
        description="Cola de revisión de actas de la jornada electoral."
      />
      {!queue.data?.items.length ? (
        <EmptyState
          title="No existen actas pendientes de revisión."
          detail="Las actas enviadas por los delegados aparecerán aquí en cuanto lleguen."
        />
      ) : (
        queue.data.items.map((act) => (
          <ActReviewCard
            key={act.id}
            campaignId={campaignId}
            act={act}
            onDone={(message) => setToast({ severity: 'success', message })}
          />
        ))
      )}
      <Snackbar
        open={Boolean(toast)}
        autoHideDuration={4000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {toast ? (
          <Alert severity={toast.severity} onClose={() => setToast(null)} sx={{ width: '100%' }}>
            {toast.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </>
  );
}
