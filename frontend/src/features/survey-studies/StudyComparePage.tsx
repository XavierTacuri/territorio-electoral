import { Alert, Grid, Paper, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useLocation, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { PageHeader } from '../../components/layout/PageHeader';
import { LoadingSkeleton } from '../../components/feedback/States';
import { formatDateEsEc, formatIntegerEsEc, formatPercentEsEc } from '../../lib/formatEsEc';
import type { Study } from './types';
type Comparison = { comparable: boolean; message?: string; studies: Study[] };
export default function StudyComparePage() {
  const { campaignId = '' } = useParams();
  const ids =
    new URLSearchParams(useLocation().search).get('ids')?.split(',').filter(Boolean) ?? [];
  const q = useQuery({
    queryKey: ['survey-compare', campaignId, ids],
    queryFn: () =>
      apiRequest<Comparison>(
        `/campaigns/${campaignId}/survey-analysis?${ids.map((x) => 'study_ids=' + x).join('&')}`,
      ),
    enabled: ids.length >= 2,
  });
  if (q.isLoading) return <LoadingSkeleton />;
  return (
    <>
      <PageHeader
        title="COMPARADOR DE ESTUDIOS"
        description="Comparación descriptiva de hasta tres estudios."
      />
      {q.data?.message && (
        <Alert severity={q.data.comparable ? 'info' : 'warning'} sx={{ mb: 2 }}>
          {q.data.message}
        </Alert>
      )}
      <Grid container spacing={2}>
        {q.data?.studies.map((s) => (
          <Grid key={s.id} size={{ xs: 12, md: 4 }}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="h2">{s.name}</Typography>
              <Typography>Fecha: {formatDateEsEc(s.fieldwork_end_date)}</Typography>
              <Typography>Tipo: {s.study_type === 'CNE_EXIT_POLL' ? 'Exit poll / Boca de urna' : 'Encuesta general'}</Typography>
              <Typography>Muestra: {formatIntegerEsEc(s.sample_size_total)}</Typography>
              <Typography>Método: {s.sampling_method}</Typography>
              <Typography>
                Margen:{' '}
                {s.margin_of_error != null
                  ? '±' + formatPercentEsEc(s.margin_of_error)
                  : 'No declarado'}
              </Typography>
              <Typography>Cobertura: {s.geography_level === 'PARISH' ? 'Parroquial' : 'Cantonal'}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>
    </>
  );
}
