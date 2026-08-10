import { lazy, Suspense } from 'react';
import { Button, Card, CardContent, Grid, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { Link as RouterLink } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { MetricCard, PrivacySuppressedNotice } from '../../components/data-display/Common';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import type { SurveyResults } from './types';
const Charts = lazy(() => import('./ResultCharts'));
export default function SurveyResultsPage() {
  const { campaignId = '', surveyId = '' } = useParams();
  const results = useQuery({
    queryKey: ['campaign', campaignId, 'survey', surveyId, 'results'],
    queryFn: () =>
      apiRequest<SurveyResults>('/campaigns/' + campaignId + '/surveys/' + surveyId + '/results'),
  });
  const participation = useQuery({
    queryKey: ['campaign', campaignId, 'survey', surveyId, 'participation'],
    queryFn: () =>
      apiRequest<Record<string, any>>(
        '/campaigns/' + campaignId + '/surveys/' + surveyId + '/participation-summary',
      ),
  });
  if (results.isLoading) return <LoadingSkeleton />;
  if (results.isError || !results.data) return <ErrorState retry={() => results.refetch()} />;
  const item = results.data;
  const suppressed = (participation.data?.territories_below_threshold ?? []).length > 0;
  return (
    <>
      <PageHeader
        title={'Resultados: ' + item.title}
        description="Solo resultados agregados; nunca respuestas individuales ni textos abiertos."
        action={
          <Button component={RouterLink} to={`/app/campaigns/${campaignId}/surveys/${surveyId}`}>
            Volver al constructor
          </Button>
        }
      />
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 6, md: 3 }}>
          <MetricCard label="Totales" value={item.total_responses} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <MetricCard label="Válidas" value={item.valid_responses} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <MetricCard label="Inválidas" value={item.invalid_responses} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <MetricCard label="Completas" value={item.complete_responses} />
        </Grid>
      </Grid>
      {suppressed && <PrivacySuppressedNotice />}
      <Paper variant="outlined" sx={{ p: 2, my: 2 }}>
        <Suspense fallback={<LoadingSkeleton />}>
          <Charts questions={item.question_results} />
        </Suspense>
      </Paper>
      <Grid container spacing={2}>
        {item.question_results.map((q) => (
          <Grid key={q.code} size={{ xs: 12, md: 6 }}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h2">{q.question_text}</Typography>
                <Typography>{q.answered_count} respuestas agregadas</Typography>
                <Stack>
                  {q.options.map((o) => (
                    <Typography key={o.code}>
                      {o.label}: {o.count} ({o.percentage ?? 0}%)
                    </Typography>
                  ))}
                </Stack>
                {q.numeric && (
                  <Typography>
                    Promedio: {q.numeric.average ?? '—'} · Mediana: {q.numeric.median ?? '—'}
                  </Typography>
                )}
                {q.text && (
                  <Typography>
                    Textos contabilizados: {q.text.non_empty_count}; su contenido no se expone.
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </>
  );
}
