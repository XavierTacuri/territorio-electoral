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
  FormControlLabel,
  Grid,
  MenuItem,
  Pagination,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { useAuth } from '../../auth/AuthProvider';
import { canManageCampaign } from '../../auth/permissions';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import { ITEM_TYPE_LABELS, SOURCE_TYPE_LABELS } from './labels';
import type { ItemPage, PublicItem, PublicSource, PublicSummary } from './types';
import { PublicIntelligenceMap } from './PublicIntelligenceMap';
import { PublicSourcesAdmin } from './PublicSourcesAdmin';

const dateTime = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat('es-EC', { dateStyle: 'short', timeStyle: 'short' }).format(
        new Date(value),
      )
    : 'Sin consultas';

function ItemCard({ item, campaignId }: { item: PublicItem; campaignId: string }) {
  return (
    <Card variant="outlined" sx={{ my: 2 }}>
      <CardContent>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
          <Chip label={ITEM_TYPE_LABELS[item.item_type] ?? item.item_type} />
          {item.official && <Chip label="FUENTE OFICIAL" color="primary" />}
          <Typography color="text.secondary">{item.publisher}</Typography>
        </Stack>
        <Typography variant="h2" sx={{ mt: 1 }}>
          {item.title}
        </Typography>
        <Typography>{item.summary || item.content_excerpt || 'Sin resumen disponible.'}</Typography>
        <Typography variant="caption">
          Publicado:{' '}
          {item.published_at ? formatDateOnly(item.published_at.slice(0, 10)) : 'Sin fecha'} ·
          Fuente: {item.source_name}
        </Typography>
      </CardContent>
      <CardActions>
        <Button
          component={RouterLink}
          to={`/app/campaigns/${campaignId}/public-intelligence/${item.id}`}
        >
          Ver detalle
        </Button>
        <Button href={item.url} target="_blank" rel="noopener noreferrer">
          Abrir fuente
        </Button>
      </CardActions>
    </Card>
  );
}

export default function PublicIntelligencePage() {
  const { user } = useAuth();
  const { campaignId = '' } = useParams();
  const [tab, setTab] = useState(0),
    [page, setPage] = useState(1),
    [search, setSearch] = useState(''),
    [official, setOfficial] = useState(''),
    [parishId, setParishId] = useState<number>(),
    [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    code: '',
    name: '',
    publisher: '',
    source_type: 'RSS',
    base_url: '',
    feed_url: '',
    retrieval_method: 'RSS',
    refresh_interval_minutes: 60,
    official: true,
  });
  const summary = useQuery({
    queryKey: ['public-summary', campaignId],
    queryFn: () =>
      apiRequest<PublicSummary>(`/campaigns/${campaignId}/public-intelligence/summary`),
  });
  const items = useQuery({
    queryKey: ['public-items', campaignId, page, search, official, parishId],
    queryFn: () =>
      apiRequest<ItemPage>(
        `/campaigns/${campaignId}/public-intelligence/items?page=${page}&page_size=12&search=${encodeURIComponent(search)}${official ? `&official=${official}` : ''}${parishId ? `&parish_id=${parishId}` : ''}`,
      ),
  });
  const sources = useQuery({
    queryKey: ['public-sources', campaignId],
    queryFn: () => apiRequest<PublicSource[]>(`/campaigns/${campaignId}/public-sources`),
  });
  const create = useMutation({
    mutationFn: () =>
      apiRequest(`/campaigns/${campaignId}/public-sources`, {
        method: 'POST',
        body: JSON.stringify({ ...form, feed_url: form.feed_url || null, api_url: null }),
      }),
    onSuccess: async () => {
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: ['public-sources', campaignId] });
    },
  });
  const fetchNow = useMutation({
    mutationFn: (id: string) => apiRequest(`/public-sources/${id}/fetch`, { method: 'POST' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['public-summary', campaignId] });
      await queryClient.invalidateQueries({ queryKey: ['public-items', campaignId] });
      await queryClient.invalidateQueries({ queryKey: ['public-sources', campaignId] });
    },
  });
  if (summary.isLoading || items.isLoading || sources.isLoading) return <LoadingSkeleton />;
  if (summary.isError || items.isError || sources.isError)
    return (
      <ErrorState
        retry={() => {
          void summary.refetch();
          void items.refetch();
          void sources.refetch();
        }}
      />
    );
  const s = summary.data!;
  return (
    <>
      <PageHeader
        title="INTELIGENCIA PÚBLICA"
        description="Información pública trazable proveniente de fuentes oficiales y abiertas."
        action={
          canManageCampaign(user) ? (
            <Button variant="contained" onClick={() => setOpen(true)}>
              Nueva fuente
            </Button>
          ) : undefined
        }
      />
      <Tabs value={tab} onChange={(_, value) => setTab(value)} sx={{ mb: 3 }}>
        <Tab label="Resumen" />
        <Tab label="Feed" />
        <Tab label="Fuentes públicas" />
        <Tab label="Mapa" />
      </Tabs>
      {tab === 0 && (
        <>
          <Grid container spacing={2}>
            {[
              ['Fuentes activas', s.active_sources],
              ['Últimas 24 h', s.items_last_24h],
              ['Últimos 7 días', s.items_last_7_days],
              ['Fuentes oficiales', s.official_sources],
              ['Documentos nuevos', s.new_documents],
              ['Fuentes con error', s.sources_with_error],
            ].map(([label, value]) => (
              <Grid key={String(label)} size={{ xs: 12, sm: 6, md: 4 }}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography color="text.secondary">{label}</Typography>
                    <Typography variant="h2">{value}</Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
          <Typography variant="h2" sx={{ mt: 4 }}>
            Últimas publicaciones
          </Typography>
          {!s.latest_items.length && (
            <Alert severity="info">No hay publicaciones públicas registradas.</Alert>
          )}
          {s.latest_items.map((item) => (
            <ItemCard key={item.id} item={item} campaignId={campaignId} />
          ))}
        </>
      )}
      {tab === 1 && (
        <>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
            <TextField
              label="Buscar"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
            />
            <TextField
              select
              label="Oficial"
              value={official}
              onChange={(event) => setOfficial(event.target.value)}
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="">Todas</MenuItem>
              <MenuItem value="true">Oficiales</MenuItem>
              <MenuItem value="false">No oficiales</MenuItem>
            </TextField>
          </Stack>
          {!items.data!.items.length && (
            <Alert severity="info">
              No hay información pública para los filtros seleccionados.
            </Alert>
          )}
          {items.data!.items.map((item) => (
            <ItemCard key={item.id} item={item} campaignId={campaignId} />
          ))}
          <Pagination
            page={page}
            count={items.data!.total_pages}
            onChange={(_, value) => setPage(value)}
          />
        </>
      )}
      {tab === 2 && (
        <>
          <PublicSourcesAdmin campaignId={campaignId} sources={sources.data!} />
          {/* Legacy summary retained temporarily while source cards are delegated. */}
          {/* eslint-disable-next-line no-constant-binary-expression */}
          {false && (
            <>
              {!sources.data!.length && (
                <Alert severity="info">No hay fuentes públicas configuradas.</Alert>
              )}
              <Grid container spacing={2}>
                {sources.data!.map((source) => (
                  <Grid key={source.id} size={{ xs: 12, md: 6 }}>
                    <Card variant="outlined">
                      <CardContent>
                        <Stack direction="row" spacing={1}>
                          <Typography variant="h2">{source.name}</Typography>
                          {source.official && <Chip label="FUENTE OFICIAL" color="primary" />}
                        </Stack>
                        <Typography>{source.publisher}</Typography>
                        <Typography>
                          {SOURCE_TYPE_LABELS[source.source_type] ?? source.source_type} ·{' '}
                          {source.retrieval_method}
                        </Typography>
                        <Typography>Última consulta: {dateTime(source.last_fetch_at)}</Typography>
                        {source.consecutive_failures > 0 && (
                          <Alert severity="error">Error de actualización</Alert>
                        )}
                      </CardContent>
                      <CardActions>
                        <Button href={source.base_url} target="_blank" rel="noopener noreferrer">
                          Ver fuente
                        </Button>
                        <Button
                          disabled={fetchNow.isPending || source.retrieval_method === 'MANUAL'}
                          onClick={() => fetchNow.mutate(source.id)}
                        >
                          Actualizar ahora
                        </Button>
                      </CardActions>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </>
          )}
        </>
      )}
      {tab === 3 && (
        <>
          <PublicIntelligenceMap
            campaignId={campaignId}
            onView={(id) => {
              setParishId(id);
              setPage(1);
              setTab(1);
            }}
          />
          {/* Legacy territorial cards retained temporarily while MapLibre is delegated. */}
          {/* eslint-disable-next-line no-constant-binary-expression */}
          {false && (
            <>
              <Typography variant="h2">Publicaciones públicas registradas</Typography>
              <Alert severity="info">
                El mapa utiliza únicamente asociaciones parroquiales existentes y métricas
                descriptivas.
              </Alert>
              <Grid container spacing={2} sx={{ mt: 1 }}>
                {Array.from(
                  new Map(
                    items.data!.items.flatMap((item) =>
                      item.territories.map(
                        (territory) => [territory.parish_id, territory] as const,
                      ),
                    ),
                  ).values(),
                ).map((territory) => (
                  <Grid key={territory.parish_id} size={{ xs: 12, sm: 6, md: 4 }}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography fontWeight={700}>{territory.name}</Typography>
                        <Typography>
                          {
                            items.data!.items.filter((item) =>
                              item.territories.some(
                                (value) => value.parish_id === territory.parish_id,
                              ),
                            ).length
                          }{' '}
                          publicaciones
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </>
          )}
        </>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Crear fuente pública</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {(
              [
                ['code', 'Código'],
                ['name', 'Nombre'],
                ['publisher', 'Publisher'],
                ['base_url', 'URL base'],
                ['feed_url', 'RSS URL (opcional)'],
              ] as const
            ).map(([key, label]) => (
              <TextField
                key={key}
                required={key !== 'feed_url'}
                label={label}
                value={form[key]}
                onChange={(event) => setForm({ ...form, [key]: event.target.value })}
              />
            ))}
            <TextField
              required
              type="number"
              label="Intervalo actualización (min)"
              value={form.refresh_interval_minutes}
              onChange={(event) =>
                setForm({ ...form, refresh_interval_minutes: Number(event.target.value) })
              }
            />
            <TextField
              select
              label="Tipo"
              value={form.source_type}
              onChange={(event) => setForm({ ...form, source_type: event.target.value })}
            >
              {Object.entries(SOURCE_TYPE_LABELS).map(([value, label]) => (
                <MenuItem key={value} value={value}>
                  {label}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={
                <Switch
                  checked={form.official}
                  onChange={(event) => setForm({ ...form, official: event.target.checked })}
                />
              }
              label="Fuente oficial"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button variant="contained" disabled={create.isPending} onClick={() => create.mutate()}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
