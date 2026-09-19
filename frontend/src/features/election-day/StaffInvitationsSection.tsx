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
  DialogContentText,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { formatDateOnly } from '../../lib/dates';
import type { PollingPlace } from './types';
import {
  INVITATION_STATUS_LABELS,
  STAFF_TYPE_LABELS,
  type ElectionDayStaffInvitation,
  type ElectionDayStaffInvitationCreatedResponse,
  type ElectionDayStaffType,
} from './types';

type Props = { campaignId: string; places: PollingPlace[] };

type FormState = {
  first_name: string;
  last_name: string;
  email: string;
  staff_type: ElectionDayStaffType;
  polling_place_ids: string[];
};

const emptyForm: FormState = {
  first_name: '',
  last_name: '',
  email: '',
  staff_type: 'POLLING_PLACE_DELEGATE',
  polling_place_ids: [],
};

function InvitationRow({
  invitation,
  onRevoke,
  onReissue,
  revoking,
  reissuing,
}: {
  invitation: ElectionDayStaffInvitation;
  onRevoke: (id: string) => void;
  onReissue: (id: string) => void;
  revoking: boolean;
  reissuing: boolean;
}) {
  const statusColor =
    invitation.status === 'ACCEPTED'
      ? 'success'
      : invitation.status === 'PENDING'
        ? 'warning'
        : 'default';
  return (
    <Card variant="outlined">
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
          <Typography fontWeight={700}>
            {invitation.first_name} {invitation.last_name}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {invitation.email} · {STAFF_TYPE_LABELS[invitation.staff_type]}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Expira: {formatDateOnly(invitation.expires_at)}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip
            size="small"
            color={statusColor as 'success' | 'warning' | 'default'}
            label={INVITATION_STATUS_LABELS[invitation.status]}
          />
          {invitation.status === 'PENDING' && (
            <>
              <Button size="small" disabled={reissuing} onClick={() => onReissue(invitation.id)}>
                REEMITIR
              </Button>
              <Button
                size="small"
                color="warning"
                disabled={revoking}
                onClick={() => onRevoke(invitation.id)}
              >
                REVOCAR
              </Button>
            </>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

export function StaffInvitationsSection({ campaignId, places }: Props) {
  const qc = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [linkResult, setLinkResult] = useState<ElectionDayStaffInvitationCreatedResponse | null>(
    null,
  );
  const [copied, setCopied] = useState(false);

  const listKey = ['election-day-staff-invitations', campaignId];
  const list = useQuery({
    queryKey: listKey,
    queryFn: () =>
      apiRequest<{ items: ElectionDayStaffInvitation[]; total: number }>(
        `/campaigns/${campaignId}/election-day/staff/invitations`,
      ),
  });

  const create = useMutation({
    mutationFn: () =>
      apiRequest<ElectionDayStaffInvitationCreatedResponse>(
        `/campaigns/${campaignId}/election-day/staff/invitations`,
        {
          method: 'POST',
          body: JSON.stringify({
            first_name: form.first_name.trim(),
            last_name: form.last_name.trim(),
            email: form.email.trim(),
            staff_type: form.staff_type,
            polling_place_ids:
              form.staff_type === 'POLLING_PLACE_DELEGATE' ? form.polling_place_ids : [],
          }),
        },
      ),
    onSuccess: (response) => {
      setFormOpen(false);
      setForm(emptyForm);
      setLinkResult(response);
      void qc.invalidateQueries({ queryKey: listKey });
    },
  });

  const revoke = useMutation({
    mutationFn: (invitationId: string) =>
      apiRequest<ElectionDayStaffInvitation>(
        `/campaigns/${campaignId}/election-day/staff/invitations/${invitationId}/revoke`,
        { method: 'POST' },
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: listKey }),
  });

  const reissue = useMutation({
    mutationFn: (invitationId: string) =>
      apiRequest<ElectionDayStaffInvitationCreatedResponse>(
        `/campaigns/${campaignId}/election-day/staff/invitations/${invitationId}/reissue`,
        { method: 'POST' },
      ),
    onSuccess: (response) => {
      setLinkResult(response);
      void qc.invalidateQueries({ queryKey: listKey });
    },
  });

  const items = list.data?.items ?? [];
  const delegates = items.filter(
    (i) => i.status === 'ACCEPTED' && i.staff_type === 'POLLING_PLACE_DELEGATE',
  );
  const validators = items.filter(
    (i) => i.status === 'ACCEPTED' && i.staff_type === 'ACT_VALIDATOR',
  );
  const pending = items.filter((i) => i.status !== 'ACCEPTED');

  const canSubmit =
    form.first_name.trim() &&
    form.last_name.trim() &&
    form.email.trim() &&
    (form.staff_type === 'ACT_VALIDATOR' || form.polling_place_ids.length > 0);

  return (
    <Box sx={{ mt: 4 }}>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}
      >
        <Typography component="h2" variant="h2">
          Personal de Jornada
        </Typography>
        <Button
          variant="contained"
          onClick={() => {
            setForm(emptyForm);
            setFormOpen(true);
          }}
        >
          AGREGAR PERSONAL
        </Button>
      </Stack>

      <Typography variant="overline" color="text.secondary">
        Delegados de recinto
      </Typography>
      <Stack spacing={1} sx={{ mb: 2 }}>
        {delegates.length === 0 ? (
          <Typography color="text.secondary" sx={{ mb: 1 }}>
            Aún no hay delegados con acceso activo.
          </Typography>
        ) : (
          delegates.map((i) => (
            <InvitationRow
              key={i.id}
              invitation={i}
              onRevoke={revoke.mutate}
              onReissue={reissue.mutate}
              revoking={revoke.isPending}
              reissuing={reissue.isPending}
            />
          ))
        )}
      </Stack>

      <Typography variant="overline" color="text.secondary">
        Validadores de actas
      </Typography>
      <Stack spacing={1} sx={{ mb: 2 }}>
        {validators.length === 0 ? (
          <Typography color="text.secondary" sx={{ mb: 1 }}>
            Aún no hay validadores con acceso activo.
          </Typography>
        ) : (
          validators.map((i) => (
            <InvitationRow
              key={i.id}
              invitation={i}
              onRevoke={revoke.mutate}
              onReissue={reissue.mutate}
              revoking={revoke.isPending}
              reissuing={reissue.isPending}
            />
          ))
        )}
      </Stack>

      <Typography variant="overline" color="text.secondary">
        Invitaciones pendientes
      </Typography>
      <Stack spacing={1}>
        {pending.length === 0 ? (
          <Typography color="text.secondary">No hay invitaciones pendientes.</Typography>
        ) : (
          pending.map((i) => (
            <InvitationRow
              key={i.id}
              invitation={i}
              onRevoke={revoke.mutate}
              onReissue={reissue.mutate}
              revoking={revoke.isPending}
              reissuing={reissue.isPending}
            />
          ))
        )}
      </Stack>

      <Dialog open={formOpen} onClose={() => setFormOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Agregar personal de Jornada</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Nombre"
              value={form.first_name}
              onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))}
            />
            <TextField
              label="Apellido"
              value={form.last_name}
              onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))}
            />
            <TextField
              label="Correo"
              type="email"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
            <TextField
              select
              label="Perfil"
              value={form.staff_type}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  staff_type: e.target.value as ElectionDayStaffType,
                  polling_place_ids: [],
                }))
              }
            >
              <MenuItem value="POLLING_PLACE_DELEGATE">Delegado de recinto</MenuItem>
              <MenuItem value="ACT_VALIDATOR">Validador de actas</MenuItem>
            </TextField>
            {form.staff_type === 'POLLING_PLACE_DELEGATE' && (
              <TextField
                select
                label="Recintos"
                value={form.polling_place_ids}
                SelectProps={{
                  multiple: true,
                  renderValue: (selected) =>
                    places
                      .filter((p) => (selected as string[]).includes(p.id))
                      .map((p) => p.name)
                      .join(', '),
                }}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    polling_place_ids:
                      typeof e.target.value === 'string'
                        ? e.target.value.split(',')
                        : (e.target.value as string[]),
                  }))
                }
                helperText="El delegado requiere al menos un recinto."
              >
                {places.map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {p.name}
                  </MenuItem>
                ))}
              </TextField>
            )}
            {create.isError && (
              <Alert severity="error">No se pudo crear la invitación. Verifica los datos.</Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFormOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={!canSubmit || create.isPending}
            onClick={() => create.mutate()}
          >
            Crear invitación
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={!!linkResult}
        onClose={() => {
          setLinkResult(null);
          setCopied(false);
        }}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Invitación creada correctamente</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            Este enlace se muestra ahora para que puedas compartirlo de forma segura. No volverá a
            mostrarse después de cerrar esta ventana.
          </DialogContentText>
          <TextField
            fullWidth
            value={linkResult?.invite_url ?? ''}
            InputProps={{ readOnly: true }}
          />
          {copied && (
            <Alert severity="success" sx={{ mt: 1 }}>
              Enlace copiado.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            variant="contained"
            onClick={async () => {
              if (linkResult) {
                await navigator.clipboard.writeText(linkResult.invite_url);
                setCopied(true);
              }
            }}
          >
            COPIAR ENLACE
          </Button>
          <Button
            onClick={() => {
              setLinkResult(null);
              setCopied(false);
            }}
          >
            Cerrar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
