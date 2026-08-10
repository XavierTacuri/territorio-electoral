import { lazy, Suspense } from 'react';
import { Alert, Grid, MenuItem, TextField } from '@mui/material';
import { useQueries } from '@tanstack/react-query';
import { useLocation, useParams } from 'react-router-dom';
import { apiRequest } from '../api/client';
import { MetricCard } from '../components/data-display/Common';
import { EmptyState, ErrorState, LoadingSkeleton } from '../components/feedback/States';
import { PageHeader } from '../components/layout/PageHeader';
const Charts = lazy(() => import('../features/dashboard/DashboardCharts'));
export default function DashboardPage() {
  const { campaignId = '' } = useParams();
  const location = useLocation();
  const message = (location.state as { message?: string } | null)?.message;
  const period = 'LAST_30_DAYS';
  const base = '/campaigns/' + campaignId + '/dashboard';
  const results = useQueries({
    queries: [
      ['overview', '/overview?period=' + period],
      ['trends', '/activity-trends?period=' + period + '&group_by=DAY'],
      ['needs', '/needs?period=' + period],
      ['quality', '/data-quality?period=' + period],
      ['alerts', '/../alerts/summary'],
    ].map(([key, path]) => ({
      queryKey: ['campaign', campaignId, 'dashboard', key],
      queryFn: () =>
        apiRequest<any>(
          path.includes('..') ? '/campaigns/' + campaignId + '/alerts/summary' : base + path,
        ),
      enabled: !!campaignId,
    })),
  });
  if (results.some((x) => x.isLoading)) return <LoadingSkeleton />;
  if (results.some((x) => x.isError))
    return (
      <>
        <PageHeader title="Dashboard" />
        <ErrorState retry={() => results.forEach((x) => x.refetch())} />
      </>
    );
  const [overview, trends, needs, quality, alerts] = results.map((x) => x.data);
  const metrics = overview?.metrics ?? [];
  const needRows = needs?.categories ?? overview?.top_needs ?? [];
  const alertRows = (alerts?.by_severity ?? []).map((x: any) => ({
    name: x.severity ?? x.name ?? 'Sin dato',
    count: x.count ?? 0,
  }));
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Resumen agregado de la campaña, sin rankings, perfiles ni predicciones."
        action={
          <TextField select label="Período" value={period} sx={{ minWidth: 220 }}>
            <MenuItem value="THIS_WEEK">Esta semana</MenuItem>
            <MenuItem value="LAST_7_DAYS">Últimos siete días</MenuItem>
            <MenuItem value="LAST_30_DAYS">Últimos treinta días</MenuItem>
            <MenuItem value="CAMPAIGN_TO_DATE">Campaña hasta la fecha</MenuItem>
          </TextField>
        }
      />
      {message && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {message}
        </Alert>
      )}
      {metrics.length ? (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          {metrics.map((metric: any) => (
            <Grid key={metric.code ?? metric.label} size={{ xs: 12, sm: 6, lg: 3 }}>
              <MetricCard
                label={metric.label ?? metric.code}
                value={metric.value ?? 0}
                detail={metric.comparison?.label ?? metric.unit}
              />
            </Grid>
          ))}
        </Grid>
      ) : (
        <EmptyState title="No hay métricas para este período" />
      )}
      <Suspense fallback={<LoadingSkeleton />}>
        <Charts
          trends={trends?.points ?? []}
          needs={needRows}
          quality={quality?.issues ?? []}
          alerts={alertRows}
        />
      </Suspense>
    </>
  );
}
