import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  MenuItem,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { downloadReport } from '../../api/downloads';
import { useAuth } from '../../auth/AuthProvider';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import {
  ASSIGNMENT_ROLE_LABELS,
  ASSIGNMENT_STATUS_LABELS,
  DOCUMENT_STATUS_LABELS,
  DOCUMENT_TYPE_LABELS,
  INCIDENT_CATEGORY_LABELS,
  INCIDENT_STATUS_LABELS,
  type ElectionDayAssignment,
  type ElectionDayDocument,
  type ElectionDayIncident,
  type ElectoralBoard,
  type PollingPlace,
} from './types';

type EligibleUser = { id: string; username: string; first_name: string; last_name: string };
type Toast = { severity: 'success' | 'error'; message: string };

function canManage(roles: string[]) {
  return roles.includes('CANDIDATE') || roles.includes('CAMPAIGN_MANAGER');
}

export default function PollingPlaceDetailPage() {
  const { campaignId = '', polling_place_id: placeId = '' } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const roles = user?.roles.map((r) => r.code) ?? [];
  const manager = canManage(roles) || Boolean(user?.is_superuser);

  const [replaceTarget, setReplaceTarget] = useState<ElectionDayAssignment | null>(null);
  const [replaceUserId, setReplaceUserId] = useState('');
  const [replaceReason, setReplaceReason] = useState('');
  const [replaceError, setReplaceError] = useState('');
  const [toast, setToast] = useState<Toast | null>(null);

  const place = useQuery({
    queryKey: ['election-day-place', campaignId, placeId],
    queryFn: () =>
      apiRequest<PollingPlace>(`/campaigns/${campaignId}/election-day/polling-places/${placeId}`),
  });
  const boards = useQuery({
    queryKey: ['election-day-boards', campaignId, placeId],
    queryFn: () =>
      apiRequest<ElectoralBoard[]>(
        `/campaigns/${campaignId}/election-day/polling-places/${placeId}/boards`,
      ),
  });
  const assignments = useQuery({
    queryKey: ['election-day-assignments', campaignId, placeId],
    queryFn: () =>
      apiRequest<{ items: ElectionDayAssignment[] }>(
        `/campaigns/${campaignId}/election-day/assignments?polling_place_id=${placeId}`,
      ),
  });
  const incidents = useQuery({
    queryKey: ['election-day-incidents', campaignId, placeId],
    queryFn: () =>
      apiRequest<{ items: ElectionDayIncident[] }>(
        `/campaigns/${campaignId}/election-day/incidents`,
      ),
    select: (data) => ({ items: data.items.filter((i) => i.polling_place_id === placeId) }),
  });
  const documents = useQuery({
    queryKey: ['election-day-documents', campaignId, placeId],
    queryFn: () =>
      apiRequest<{ items: ElectionDayDocument[] }>(
        `/campaigns/${campaignId}/election-day/documents?polling_place_id=${placeId}`,
      ),
  });
  const eligibleUsers = useQuery({
    queryKey: ['election-day-eligible-users', campaignId],
    queryFn: () =>
      apiRequest<EligibleUser[]>(`/campaigns/${campaignId}/election-day/eligible-users`),
    enabled: manager,
  });
  const userLabel = (id: string) => {
    const found = eligibleUsers.data?.find((u) => u.id === id);
    return found
      ? `${found.first_name} ${found.last_name} (${found.username})`
      : 'Persona asignada';
  };

  const resolveIncident = useMutation({
    mutationFn: (incidentId: string) =>
      apiRequest<ElectionDayIncident>(
        `/campaigns/${campaignId}/election-day/incidents/${incidentId}/resolve`,
        { method: 'POST', body: JSON.stringify({ status: 'RESOLVED' }) },
      ),
    onError: () =>
      setToast({ severity: 'error', message: 'No fue posible resolver la incidencia.' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['election-day-incidents', campaignId, placeId] });
      setToast({ severity: 'success', message: 'Incidencia resuelta.' });
    },
  });
  const replaceAssignment = useMutation({
    mutationFn: () =>
      apiRequest<ElectionDayAssignment>(
        `/campaigns/${campaignId}/election-day/assignments/${replaceTarget?.id}/replace`,
        {
          method: 'POST',
          body: JSON.stringify({ user_id: replaceUserId, reason: replaceReason || undefined }),
        },
      ),
    onError: () => setReplaceError('No fue posible reemplazar al personal asignado.'),
    onSuccess: () => {
      setReplaceTarget(null);
      setReplaceUserId('');
      setReplaceReason('');
      setReplaceError('');
      qc.invalidateQueries({ queryKey: ['election-day-assignments', campaignId, placeId] });
      setToast({ severity: 'success', message: 'Personal reemplazado.' });
    },
  });

  if (place.isLoading) return <LoadingSkeleton />;
  if (place.isError || !place.data) return <ErrorState retry={() => place.refetch()} />;

  return (
    <>
      <PageHeader
        title={place.data.name}
        description={`${place.data.official_code} · ${place.data.address || 'Sin dirección registrada'}`}
      />
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined" sx={{ mb: 3 }}>
            <CardContent>
              <Typography component="h2" variant="h2" sx={{ mb: 0.5 }}>
                Juntas
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Datos electorales cargados por administración.
              </Typography>
              {!boards.data?.length ? (
                <Typography color="text.secondary">No hay juntas registradas.</Typography>
              ) : (
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Código</TableCell>
                      <TableCell>Número</TableCell>
                      <TableCell>Electores</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {boards.data.map((b) => (
                      <TableRow key={b.id}>
                        <TableCell>{b.official_code}</TableCell>
                        <TableCell>{b.board_number}</TableCell>
                        <TableCell>{b.registered_voters ?? 'No disponible'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card variant="outlined">
            <CardContent>
              <Typography component="h2" variant="h2" sx={{ mb: 1 }}>
                Personal asignado
              </Typography>
              {!assignments.data?.items.length ? (
                <Typography color="text.secondary">No hay personal asignado.</Typography>
              ) : (
                <Stack spacing={1}>
                  {assignments.data.items.map((a) => (
                    <Box
                      key={a.id}
                      sx={{
                        py: 0.5,
                        borderBottom: 1,
                        borderColor: 'divider',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: 1,
                      }}
                    >
                      <Typography variant="body2">
                        {ASSIGNMENT_ROLE_LABELS[a.assignment_role]} ·{' '}
                        {ASSIGNMENT_STATUS_LABELS[a.status]}
                      </Typography>
                      {manager && a.status !== 'REPLACED' && a.status !== 'COMPLETED' && (
                        <Button
                          size="small"
                          onClick={() => {
                            setReplaceTarget(a);
                            setReplaceUserId('');
                            setReplaceReason('');
                            setReplaceError('');
                          }}
                        >
                          REEMPLAZAR
                        </Button>
                      )}
                    </Box>
                  ))}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined" sx={{ mb: 3 }}>
            <CardContent>
              <Typography component="h2" variant="h2" sx={{ mb: 1 }}>
                Incidencias
              </Typography>
              {!incidents.data?.items.length ? (
                <Typography color="text.secondary">No hay incidencias abiertas.</Typography>
              ) : (
                <Stack spacing={1}>
                  {incidents.data.items.map((i) => (
                    <Alert
                      key={i.id}
                      severity={i.status === 'RESOLVED' ? 'success' : 'warning'}
                      variant="outlined"
                      action={
                        manager && i.status !== 'RESOLVED' ? (
                          <Button
                            size="small"
                            color="inherit"
                            disabled={resolveIncident.isPending}
                            onClick={() => resolveIncident.mutate(i.id)}
                          >
                            Resolver
                          </Button>
                        ) : undefined
                      }
                    >
                      {INCIDENT_CATEGORY_LABELS[i.category]} — {INCIDENT_STATUS_LABELS[i.status]}:{' '}
                      {i.description}
                    </Alert>
                  ))}
                </Stack>
              )}
            </CardContent>
          </Card>

          <Card variant="outlined">
            <CardContent>
              <Typography component="h2" variant="h2" sx={{ mb: 1 }}>
                Documentación
              </Typography>
              {!documents.data?.items.length ? (
                <Typography color="text.secondary">Aún no se han recibido documentos.</Typography>
              ) : (
                <Stack spacing={1}>
                  {documents.data.items.map((d) => (
                    <Stack
                      key={d.id}
                      direction="row"
                      justifyContent="space-between"
                      sx={{ py: 0.5, borderBottom: 1, borderColor: 'divider' }}
                    >
                      <Typography variant="body2">
                        {DOCUMENT_TYPE_LABELS[d.document_type]} · {DOCUMENT_STATUS_LABELS[d.status]}
                      </Typography>
                      <Button
                        size="small"
                        onClick={() =>
                          downloadReport(
                            `/campaigns/${campaignId}/election-day/documents/${d.id}/download`,
                            d.original_filename || 'documento',
                          )
                        }
                      >
                        Descargar
                      </Button>
                    </Stack>
                  ))}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Dialog open={Boolean(replaceTarget)} onClose={() => setReplaceTarget(null)} fullWidth>
        <DialogTitle>Reemplazar personal asignado</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Typography variant="overline" color="text.secondary">
              Asignación actual
            </Typography>
            <Typography>Persona: {replaceTarget && userLabel(replaceTarget.user_id)}</Typography>
            <Typography>
              Rol: {replaceTarget && ASSIGNMENT_ROLE_LABELS[replaceTarget.assignment_role]}
            </Typography>
            <Typography>Recinto: {place.data.name}</Typography>
            <TextField
              select
              label="Nuevo usuario"
              value={replaceUserId}
              onChange={(e) => setReplaceUserId(e.target.value)}
            >
              {(eligibleUsers.data ?? [])
                .filter((u) => u.id !== replaceTarget?.user_id)
                .map((u) => (
                  <MenuItem key={u.id} value={u.id}>
                    {u.first_name} {u.last_name} ({u.username})
                  </MenuItem>
                ))}
            </TextField>
            <TextField
              multiline
              minRows={2}
              label="Motivo (opcional)"
              value={replaceReason}
              onChange={(e) => setReplaceReason(e.target.value)}
            />
            {replaceError && <Alert severity="error">{replaceError}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setReplaceTarget(null);
              setReplaceError('');
            }}
          >
            Cancelar
          </Button>
          <Button
            variant="contained"
            disabled={!replaceUserId || replaceAssignment.isPending}
            onClick={() => replaceAssignment.mutate()}
          >
            Confirmar reemplazo
          </Button>
        </DialogActions>
      </Dialog>

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
