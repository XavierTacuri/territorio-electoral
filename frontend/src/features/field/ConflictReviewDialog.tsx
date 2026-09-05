import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { useNavigate, useParams } from 'react-router-dom';
import { deleteDraft } from '../../offline/draftsRepository';
import { removeFromQueue } from '../../offline/syncQueueRepository';
import type { OfflineDraft, OwnerScope } from '../../offline/types';

// First-phase conflict resolution: no automatic merge. The coordinator picks
// one of two explicit outcomes (section 10/11 of the PWA audit).
export function ConflictReviewDialog({
  draft,
  scope,
  onClose,
  onResolved,
}: {
  draft: OfflineDraft | null;
  scope: OwnerScope | null;
  onClose: () => void;
  onResolved: () => void;
}) {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  if (!draft) return null;
  const isForbidden = draft.conflict_reason === 'FORBIDDEN';

  async function keepServer() {
    if (!draft || !scope) return;
    // "Conservar servidor": the local attempt is abandoned without ever
    // overwriting the server — never a real conflict-merge, just dropping
    // the device's version.
    await removeFromQueue(draft.id);
    await deleteDraft(draft.id, scope);
    onResolved();
  }

  function reviewDraft() {
    if (!draft) return;
    const path = draft.entity_type === 'ACTIVITY' ? 'activities' : 'needs';
    onClose();
    navigate(`/app/campaigns/${campaignId}/field/${path}/new?draft=${draft.id}`);
  }

  async function deleteDraftOnly() {
    if (!draft || !scope) return;
    await removeFromQueue(draft.id);
    await deleteDraft(draft.id, scope);
    onResolved();
  }

  return (
    <Dialog open={Boolean(draft)} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Este registro requiere revisión</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          {isForbidden ? (
            <Alert severity="warning">Ya no tienes acceso a este territorio.</Alert>
          ) : (
            <Alert severity="info">{draft.last_error || 'El servidor ya tiene un registro similar.'}</Alert>
          )}
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="overline" color="text.secondary">
              Versión del dispositivo
            </Typography>
            <Typography fontWeight={700}>{(draft.payload.title as string | undefined) || 'Sin título'}</Typography>
            <Typography variant="body2" color="text.secondary">
              {(draft.payload.description as string | undefined) || 'Sin descripción'}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Guardado en el dispositivo: {new Date(draft.updated_offline_at).toLocaleString('es-EC')}
            </Typography>
          </Paper>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="overline" color="text.secondary">
              Versión del servidor
            </Typography>
            {isForbidden ? (
              <Typography variant="body2" color="text.secondary">
                No disponible: ya no tienes acceso territorial para consultarla.
              </Typography>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {draft.last_error || 'El servidor reporta un conflicto con este registro.'}
              </Typography>
            )}
          </Paper>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexDirection: { xs: 'column', sm: 'row' }, alignItems: 'stretch', gap: 1, px: 3, pb: 2 }}>
        <Button onClick={onClose} sx={{ width: { xs: '100%', sm: 'auto' } }}>
          Cancelar
        </Button>
        {isForbidden ? (
          <Button color="error" onClick={() => void deleteDraftOnly()} sx={{ width: { xs: '100%', sm: 'auto' } }}>
            Eliminar borrador
          </Button>
        ) : (
          <Button color="warning" onClick={() => void keepServer()} sx={{ width: { xs: '100%', sm: 'auto' } }}>
            Conservar servidor
          </Button>
        )}
        <Button variant="contained" onClick={reviewDraft} sx={{ width: { xs: '100%', sm: 'auto' } }}>
          Revisar borrador
        </Button>
      </DialogActions>
    </Dialog>
  );
}
