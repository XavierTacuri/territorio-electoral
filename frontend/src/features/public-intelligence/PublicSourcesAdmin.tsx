import { useState } from 'react';
import {
  Alert,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { useAuth } from '../../auth/AuthProvider';
import { canManageCampaign } from '../../auth/permissions';
import type { FetchRun, PublicSource } from './types';
const status: Record<string, string> = {
  QUEUED: 'En cola',
  RUNNING: 'En ejecución',
  SUCCESS: 'Correcta',
  PARTIAL: 'Parcial',
  FAILED: 'Fallida',
};
const dt = (v?: string | null) =>
  v
    ? new Intl.DateTimeFormat('es-EC', { dateStyle: 'short', timeStyle: 'short' }).format(
        new Date(v),
      )
    : 'Nunca';
const safeError = (v?: string | null) =>
  (v ?? 'Sin detalle disponible')
    .replace(/([?&](token|api[_-]?key|password|authorization|cookie)=)[^&\s]+/gi, '$1[OCULTO]')
    .slice(0, 300);
export function PublicSourcesAdmin({
  campaignId,
  sources,
}: {
  campaignId: string;
  sources: PublicSource[];
}) {
  const { user } = useAuth();
  const canManage = canManageCampaign(user);
  const [editing, setEditing] = useState<PublicSource>(),
    [confirm, setConfirm] = useState<PublicSource>(),
    [history, setHistory] = useState<PublicSource>(),
    [result, setResult] = useState<FetchRun>();
  const runs = useQuery({
    queryKey: ['public-runs', history?.id],
    queryFn: () => apiRequest<FetchRun[]>(`/public-sources/${history!.id}/fetch-runs`),
    enabled: !!history,
  });
  const mutate = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<PublicSource> }) =>
      apiRequest(`/public-sources/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: async () => {
      setEditing(undefined);
      setConfirm(undefined);
      await queryClient.invalidateQueries({ queryKey: ['public-sources', campaignId] });
    },
  });
  const fetchNow = useMutation({
    mutationFn: (id: string) =>
      apiRequest<FetchRun>(`/public-sources/${id}/fetch`, { method: 'POST' }),
    onSuccess: async (r) => {
      setResult(r);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['public-summary', campaignId] }),
        queryClient.invalidateQueries({ queryKey: ['public-items', campaignId] }),
        queryClient.invalidateQueries({ queryKey: ['public-sources', campaignId] }),
        queryClient.invalidateQueries({ queryKey: ['public-runs'] }),
      ]);
    },
  });
  const freshness = (s: PublicSource) => {
    if (!s.active) return 'Inactiva';
    if (!s.last_success_at) return 'Nunca actualizada';
    if (!s.refresh_interval_minutes) return 'Actualizada';
    const limit = new Date(s.last_success_at).getTime() + s.refresh_interval_minutes * 60000 * 1.25;
    return Date.now() > limit ? 'Desactualizada' : 'Actualizada';
  };
  return (
    <>
      {!sources.length && (
        <Alert severity="info">
          No hay fuentes públicas configuradas. Use NUEVA FUENTE para comenzar.
        </Alert>
      )}
      {result && (
        <Alert severity={result.status === 'FAILED' ? 'error' : 'success'}>
          {result.items_created} nuevas · {result.items_updated} actualizadas ·{' '}
          {result.items_unchanged} sin cambios · {result.items_failed} errores
        </Alert>
      )}
      <Grid container spacing={2}>
        {sources.map((s) => (
          <Grid key={s.id} size={{ xs: 12, md: 6 }}>
            <Card variant="outlined">
              <CardContent>
                <Stack direction="row" gap={1} flexWrap="wrap">
                  <Typography variant="h2">{s.name}</Typography>
                  <Chip
                    label={s.active ? 'Activa' : 'Inactiva'}
                    color={s.active ? 'success' : 'default'}
                  />
                  {s.official && <Chip label="Fuente oficial" color="primary" />}
                </Stack>
                <Typography>{s.publisher}</Typography>
                <Typography>Última actualización correcta: {dt(s.last_success_at)}</Typography>
                <Typography>Estado: {freshness(s)}</Typography>
                {s.last_success_at && s.refresh_interval_minutes && (
                  <Typography>
                    Próxima actualización estimada:{' '}
                    {dt(
                      new Date(
                        new Date(s.last_success_at).getTime() + s.refresh_interval_minutes * 60000,
                      ).toISOString(),
                    )}
                  </Typography>
                )}
              </CardContent>
              <CardActions sx={{ flexWrap: 'wrap' }}>
                <Button href={s.base_url} target="_blank" rel="noopener noreferrer">
                  Ver
                </Button>
                {canManage && <Button onClick={() => setEditing({ ...s })}>Editar</Button>}
                {canManage && (
                  <Button
                    disabled={!s.active || fetchNow.isPending || s.retrieval_method === 'MANUAL'}
                    onClick={() => fetchNow.mutate(s.id)}
                  >
                    Actualizar ahora
                  </Button>
                )}
                <Button onClick={() => setHistory(s)}>Ver historial</Button>
                {canManage && (
                  <Button
                    color={s.active ? 'warning' : 'success'}
                    onClick={() =>
                      s.active ? setConfirm(s) : mutate.mutate({ id: s.id, body: { active: true } })
                    }
                  >
                    {s.active ? 'Desactivar' : 'Reactivar'}
                  </Button>
                )}
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>
      <Dialog open={!!editing} onClose={() => setEditing(undefined)} fullWidth maxWidth="sm">
        <DialogTitle>Editar fuente</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {(
              [
                'name',
                'publisher',
                'base_url',
                'feed_url',
                'api_url',
                'jurisdiction',
                'refresh_interval_minutes',
                'terms_notes',
                'license_notes',
              ] as const
            ).map((k) => (
              <TextField
                key={k}
                label={
                  (
                    {
                      name: 'Nombre',
                      publisher: 'Publisher',
                      base_url: 'URL base',
                      feed_url: 'RSS URL',
                      api_url: 'API URL',
                      jurisdiction: 'Jurisdicción',
                      refresh_interval_minutes: 'Intervalo actualización (min)',
                      terms_notes: 'Notas de términos',
                      license_notes: 'Notas de licencia',
                    } as any
                  )[k]
                }
                value={(editing as any)?.[k] ?? ''}
                type={k === 'refresh_interval_minutes' ? 'number' : 'text'}
                onChange={(e) =>
                  setEditing((x) =>
                    x
                      ? {
                          ...x,
                          [k]:
                            k === 'refresh_interval_minutes'
                              ? Number(e.target.value)
                              : e.target.value,
                        }
                      : x,
                  )
                }
              />
            ))}
            <TextField
              select
              label="Método"
              value={editing?.retrieval_method ?? 'MANUAL'}
              onChange={(e) =>
                setEditing((x) => (x ? { ...x, retrieval_method: e.target.value } : x))
              }
            >
              {['MANUAL', 'RSS', 'API', 'WEB_PAGE', 'FILE_DOWNLOAD'].map((x) => (
                <MenuItem key={x} value={x}>
                  {x}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(undefined)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={() =>
              editing &&
              mutate.mutate({
                id: editing.id,
                body: {
                  name: editing.name,
                  publisher: editing.publisher,
                  base_url: editing.base_url,
                  feed_url: editing.feed_url,
                  api_url: editing.api_url,
                  jurisdiction: editing.jurisdiction,
                  refresh_interval_minutes: editing.refresh_interval_minutes,
                  terms_notes: editing.terms_notes,
                  license_notes: editing.license_notes,
                  retrieval_method: editing.retrieval_method,
                },
              })
            }
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={!!confirm} onClose={() => setConfirm(undefined)}>
        <DialogTitle>Desactivar fuente</DialogTitle>
        <DialogContent>
          <Typography>
            Esta fuente dejará de actualizarse automáticamente. Las publicaciones y el historial
            existente se conservarán.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(undefined)}>Cancelar</Button>
          <Button
            color="warning"
            onClick={() => confirm && mutate.mutate({ id: confirm.id, body: { active: false } })}
          >
            Desactivar
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={!!history} onClose={() => setHistory(undefined)} fullWidth maxWidth="md">
        <DialogTitle>HISTORIAL DE ACTUALIZACIONES</DialogTitle>
        <DialogContent>
          {runs.data?.map((r) => (
            <Card key={r.id} variant="outlined" sx={{ my: 1 }}>
              <CardContent>
                <Typography fontWeight={700}>{status[r.status] ?? r.status}</Typography>
                <Typography>
                  Inicio: {dt(r.started_at)} · Fin: {dt(r.finished_at)} · Trigger: {r.trigger_type}
                </Typography>
                <Typography>
                  Descubiertos {r.items_discovered} · Nuevos {r.items_created} · Actualizados{' '}
                  {r.items_updated} · Sin cambios {r.items_unchanged} · Errores {r.items_failed}
                </Typography>
                {['FAILED', 'PARTIAL'].includes(r.status) && (
                  <Alert severity="warning">{safeError(r.error_summary)}</Alert>
                )}
              </CardContent>
            </Card>
          ))}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHistory(undefined)}>Cerrar</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
