import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { addPendingAttachment } from '../../offline/attachmentsRepository';
import { createDraft } from '../../offline/draftsRepository';
import { enqueue } from '../../offline/syncQueueRepository';
import type { OwnerScope } from '../../offline/types';
import type { CachedElectionActCandidate } from '../../offline/types';

type Props = {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  scope: OwnerScope;
  mode: 'REGISTER' | 'CORRECT';
  pollingPlaceId: string;
  boardId: string;
  boardLabel: string;
  contestId: string;
  contestName: string;
  voteMethod: string;
  candidates: CachedElectionActCandidate[];
  actId: string | null;
};

// §12/§13: captura mínima que puede rellenar un Delegado en el propio
// recinto — nunca texto libre para votos (siempre un número por candidato
// tomado del catálogo oficial), y al menos una fotografía del acta física
// antes de poder guardar (se sube junto con el envío al sincronizar).
export default function ActFormDialog({
  open,
  onClose,
  onSaved,
  scope,
  mode,
  pollingPlaceId,
  boardId,
  boardLabel,
  contestId,
  contestName,
  voteMethod,
  candidates,
  actId,
}: Props) {
  const [blank, setBlank] = useState('0');
  const [nullVotes, setNullVotes] = useState('0');
  const [validBallots, setValidBallots] = useState('');
  const [ballotsCounted, setBallotsCounted] = useState('');
  const [votes, setVotes] = useState<Record<string, string>>({});
  const [reason, setReason] = useState('');
  const [photos, setPhotos] = useState<File[]>([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  function reset() {
    setBlank('0');
    setNullVotes('0');
    setValidBallots('');
    setBallotsCounted('');
    setVotes({});
    setReason('');
    setPhotos([]);
    setError('');
  }

  function addPhoto(file: File) {
    if (file.type !== 'image/jpeg' && file.type !== 'image/png') {
      setError('Solo se aceptan fotografías en formato JPEG o PNG.');
      return;
    }
    setError('');
    setPhotos((prev) => [...prev, file]);
  }

  async function save() {
    setError('');
    if (photos.length === 0) {
      setError('Debes adjuntar al menos una fotografía del acta.');
      return;
    }
    if (mode === 'CORRECT' && !reason.trim()) {
      setError('Indica el motivo de la corrección.');
      return;
    }
    const blankN = Number(blank) || 0;
    const nullN = Number(nullVotes) || 0;
    const validN = validBallots.trim() === '' ? null : Number(validBallots);
    const countedN = ballotsCounted.trim() === '' ? null : Number(ballotsCounted);
    if (
      blankN < 0 ||
      nullN < 0 ||
      (validN !== null && validN < 0) ||
      (countedN !== null && countedN < 0)
    ) {
      setError('Los totales no pueden ser negativos.');
      return;
    }
    setSaving(true);
    try {
      const results = candidates.map((c) => ({
        electoral_candidate_id: c.id,
        votes: Number(votes[c.id]) || 0,
      }));
      const cid = crypto.randomUUID();
      const draft = await createDraft(
        scope,
        'ELECTION_ACT_SUBMIT',
        0,
        {
          is_correction: mode === 'CORRECT',
          act_id: actId,
          polling_place_id: pollingPlaceId,
          electoral_board_id: boardId,
          electoral_contest_id: contestId,
          blank_ballots: blankN,
          null_ballots: nullN,
          valid_ballots: validN,
          ballots_counted: countedN,
          results,
          correction_reason: mode === 'CORRECT' ? reason.trim() : undefined,
        },
        cid,
      );
      for (const photo of photos) {
        await addPendingAttachment(scope, draft.id, photo, 'Fotografía del acta');
      }
      await enqueue(scope, draft.id, 'ELECTION_ACT_SUBMIT');
      reset();
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      fullWidth
      maxWidth="sm"
    >
      <DialogTitle>
        {mode === 'REGISTER' ? 'Registrar acta' : 'Corregir acta'} — {boardLabel}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {contestName} ({voteMethod})
          </Typography>
          {mode === 'CORRECT' && (
            <TextField
              multiline
              minRows={2}
              label="Motivo de la corrección"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
            />
          )}
          <Stack direction="row" spacing={2}>
            <TextField
              label="Votos en blanco"
              type="number"
              value={blank}
              onChange={(e) => setBlank(e.target.value)}
              fullWidth
            />
            <TextField
              label="Votos nulos"
              type="number"
              value={nullVotes}
              onChange={(e) => setNullVotes(e.target.value)}
              fullWidth
            />
          </Stack>
          <Stack direction="row" spacing={2}>
            <TextField
              label="Votos válidos (opcional)"
              type="number"
              value={validBallots}
              onChange={(e) => setValidBallots(e.target.value)}
              fullWidth
            />
            <TextField
              label="Total de actas escrutadas (opcional)"
              type="number"
              value={ballotsCounted}
              onChange={(e) => setBallotsCounted(e.target.value)}
              fullWidth
            />
          </Stack>
          <Typography variant="overline" color="text.secondary">
            Votos por candidato
          </Typography>
          {candidates.map((c) => (
            <TextField
              key={c.id}
              label={c.display_name || c.full_name}
              type="number"
              value={votes[c.id] ?? ''}
              onChange={(e) => setVotes((prev) => ({ ...prev, [c.id]: e.target.value }))}
              fullWidth
            />
          ))}
          <Box>
            <Button component="label" variant="outlined" size="large">
              TOMAR FOTO DEL ACTA
              <input
                type="file"
                hidden
                accept="image/jpeg,image/png"
                capture="environment"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) addPhoto(file);
                  e.target.value = '';
                }}
              />
            </Button>
            <Typography variant="body2" sx={{ mt: 1 }}>
              Fotos agregadas: {photos.length}
            </Typography>
          </Box>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button
          onClick={() => {
            reset();
            onClose();
          }}
        >
          Cancelar
        </Button>
        <Button variant="contained" disabled={saving} onClick={() => void save()}>
          Guardar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
