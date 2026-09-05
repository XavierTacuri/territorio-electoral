import { useState } from 'react';
import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import SyncIcon from '@mui/icons-material/Sync';
import { useNavigate, useParams } from 'react-router-dom';
import { LoadingSkeleton } from '../../components/feedback/States';
import { deleteDraft } from '../../offline/draftsRepository';
import { enqueue } from '../../offline/syncQueueRepository';
import type { OfflineDraft, PendingAttachment } from '../../offline/types';
import { ConflictReviewDialog } from './ConflictReviewDialog';
import { useFieldContext } from './useFieldContext';
import { useFieldData } from './useFieldData';
import { SyncNowButton } from './SyncNowButton';

const STATUS_LABELS: Record<OfflineDraft['sync_status'], string> = {
  DRAFT: 'Borrador',
  PENDING: 'Pendiente',
  SYNCING: 'Sincronizando',
  SYNCED: 'Sincronizado',
  REQUIRES_REVIEW: 'Requiere revisión',
  ERROR: 'Error',
};

const ENTITY_LABELS: Record<OfflineDraft['entity_type'], string> = {
  ACTIVITY: 'Actividad',
  NEED: 'Necesidad',
  ELECTION_DAY_CHECK_IN: 'Confirmación de presencia',
  ELECTION_DAY_INCIDENT: 'Incidencia de jornada',
  ELECTION_DAY_DOCUMENT: 'Documento de jornada',
};

function attachmentSummary(attachments: PendingAttachment[]): string {
  if (attachments.length === 0) return '';
  const synced = attachments.filter((a) => a.sync_status === 'SYNCED').length;
  const review = attachments.filter((a) => a.sync_status === 'REQUIRES_REVIEW').length;
  const parts = [`${attachments.length} evidencia(s)`];
  if (synced > 0) parts.push(`${synced} sincronizada(s)`);
  if (review > 0) parts.push(`${review} requiere(n) revisión`);
  return ` · ${parts.join(', ')}`;
}

export default function FieldDraftsPage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const field = useFieldContext();
  const { drafts, attachments, pendingCount, refresh } = useFieldData(field.scope);
  const [toDelete, setToDelete] = useState<OfflineDraft | null>(null);
  const [toReview, setToReview] = useState<OfflineDraft | null>(null);

  if (field.loading) return <LoadingSkeleton />;

  async function confirmDelete() {
    if (!toDelete || !field.scope) return;
    await deleteDraft(toDelete.id, field.scope);
    setToDelete(null);
    refresh();
  }

  async function queueForSync(draft: OfflineDraft) {
    if (!field.scope) return;
    await enqueue(field.scope, draft.id, draft.entity_type);
    refresh();
  }

  return (
    <Stack spacing={2}>
      <Stack spacing={1}>
        <Typography variant="h2" sx={{ fontSize: '1.2rem' }}>
          Mis borradores
        </Typography>
        <SyncNowButton
          scope={field.scope}
          onDone={refresh}
          icon={<SyncIcon />}
          pendingCount={pendingCount}
        />
      </Stack>
      {drafts.length === 0 ? (
        <Alert severity="info">No tienes borradores guardados en este dispositivo.</Alert>
      ) : (
        <List disablePadding>
          {drafts.map((draft) => (
            // A row of up to four buttons doesn't fit MUI's secondaryAction
            // slot at 375px without overlapping the text next to it — each
            // draft is its own stacked block instead: text on top, actions
            // in their own wrapping row below.
            <ListItem key={draft.id} divider disableGutters sx={{ display: 'block', py: 1.5 }}>
              <ListItemText
                primary={
                  <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                    <span>
                      {(draft.payload.title as string | undefined) ||
                        ENTITY_LABELS[draft.entity_type]}
                    </span>
                    <Chip size="small" label={ENTITY_LABELS[draft.entity_type]} />
                  </Stack>
                }
                secondary={
                  <>
                    Última edición: {new Date(draft.updated_offline_at).toLocaleString('es-EC')} ·{' '}
                    {STATUS_LABELS[draft.sync_status]}
                    {draft.last_error ? ` · ${draft.last_error}` : ''}
                    {attachmentSummary(attachments.filter((a) => a.draft_id === draft.id))}
                  </>
                }
              />
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
                {(draft.sync_status === 'DRAFT' || draft.sync_status === 'ERROR') && (
                  <Button size="small" onClick={() => void queueForSync(draft)}>
                    Sincronizar
                  </Button>
                )}
                {draft.sync_status === 'REQUIRES_REVIEW' && (
                  <Button size="small" color="warning" onClick={() => setToReview(draft)}>
                    Revisar
                  </Button>
                )}
                <Button
                  size="small"
                  onClick={() =>
                    navigate(
                      `/app/campaigns/${campaignId}/field/${draft.entity_type === 'ACTIVITY' ? 'activities' : 'needs'}/new?draft=${draft.id}`,
                    )
                  }
                >
                  Continuar
                </Button>
                <Button size="small" color="error" onClick={() => setToDelete(draft)}>
                  Eliminar
                </Button>
              </Stack>
            </ListItem>
          ))}
        </List>
      )}
      <Dialog open={Boolean(toDelete)} onClose={() => setToDelete(null)}>
        <DialogTitle>Eliminar borrador</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Esta acción elimina el borrador solo de este dispositivo. Esto no afecta ningún registro
            ya sincronizado con el servidor.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setToDelete(null)}>Cancelar</Button>
          <Button color="error" onClick={() => void confirmDelete()}>
            Eliminar
          </Button>
        </DialogActions>
      </Dialog>
      <ConflictReviewDialog
        draft={toReview}
        scope={field.scope}
        onClose={() => setToReview(null)}
        onResolved={() => {
          setToReview(null);
          refresh();
        }}
      />
    </Stack>
  );
}
