import { Alert, Button, Card, CardContent, Chip, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import { ITEM_TYPE_LABELS } from './labels';
import type { PublicItem } from './types';
export default function PublicItemDetailPage() {
  const { campaignId = '', itemId = '' } = useParams();
  const q = useQuery({
    queryKey: ['public-item', campaignId, itemId],
    queryFn: () =>
      apiRequest<PublicItem>(`/campaigns/${campaignId}/public-intelligence/items/${itemId}`),
  });
  if (q.isLoading) return <LoadingSkeleton />;
  if (q.isError || !q.data) return <ErrorState retry={() => q.refetch()} />;
  const x = q.data;
  return (
    <>
      <PageHeader
        title="INTELIGENCIA PÚBLICA — DETALLE"
        description="Referencia documental trazable y fechada."
      />
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1}>
              <Chip label={ITEM_TYPE_LABELS[x.item_type] ?? x.item_type} />
              {x.official && <Chip color="primary" label="FUENTE OFICIAL" />}
            </Stack>
            <Typography variant="h1">{x.title}</Typography>
            <Typography>{x.summary || 'Sin resumen disponible.'}</Typography>
            {x.content_excerpt && (
              <>
                <Typography variant="h2">Extracto permitido</Typography>
                <Typography>{x.content_excerpt}</Typography>
              </>
            )}
            <Typography variant="h2">Citación</Typography>
            <Typography>Fuente: {x.source_name}</Typography>
            <Typography>Publisher: {x.publisher}</Typography>
            <Typography>
              Publicado:{' '}
              {x.published_at
                ? formatDateOnly(x.published_at.slice(0, 10))
                : 'Sin fecha registrada'}
            </Typography>
            <Typography>
              Consultado:{' '}
              {new Intl.DateTimeFormat('es-EC', { dateStyle: 'short', timeStyle: 'short' }).format(
                new Date(x.fetched_at),
              )}
            </Typography>
            <Button href={x.url} target="_blank" rel="noopener noreferrer">
              Abrir fuente
            </Button>
            <Typography variant="h2">Temas</Typography>
            <Stack direction="row" spacing={1}>
              {x.topics.map((t) => (
                <Chip key={t.code} label={t.name} />
              ))}
            </Stack>
            <Typography variant="h2">Territorios asociados</Typography>
            {x.territories.map((t) => (
              <Typography key={t.parish_id}>
                {t.name} · {t.association_method}
              </Typography>
            ))}
            <Typography variant="h2">Revisiones</Typography>
            {x.revisions.length > 1 ? (
              <Alert severity="info">
                Esta publicación registra {x.revisions.length} versiones.
              </Alert>
            ) : (
              <Typography>Sin cambios posteriores detectados.</Typography>
            )}
          </Stack>
        </CardContent>
      </Card>
    </>
  );
}
