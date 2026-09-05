import { Alert, Grid, Stack } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Navigate, Link as RouterLink } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { canViewDataHub } from '../../auth/permissions';
import { MetricCard, StatusBadge } from '../../components/data-display/Common';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { DATASET_LABELS, type DataHubCatalog } from './types';

export default function DataHubPage() {
  const { user } = useAuth();
  const catalog = useQuery({
    queryKey: ['data-hub-catalog'],
    queryFn: () => apiRequest<DataHubCatalog>('/data-hub/catalog'),
  });
  if (!canViewDataHub(user)) return <Navigate to="/403" replace />;
  return (
    <>
      <PageHeader
        title="Centro de datos de Ecuador"
        description="Fuentes oficiales, versiones vigentes y calidad de los conjuntos de datos que sostienen la plataforma."
      />
      {catalog.isLoading ? (
        <LoadingSkeleton />
      ) : catalog.isError ? (
        <ErrorState retry={() => catalog.refetch()} />
      ) : (
        <Stack spacing={3}>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
              <MetricCard label="Fuentes activas" value={catalog.data!.summary.active_sources} />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
              <MetricCard label="Datasets" value={catalog.data!.summary.datasets} />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
              <MetricCard
                label="Importaciones recientes"
                value={catalog.data!.summary.recent_imports}
                detail="Últimos 30 días"
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
              <MetricCard
                label="Importaciones con errores"
                value={catalog.data!.summary.imports_with_errors}
                detail="Últimos 30 días"
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
              <MetricCard
                label="Sin versión vigente"
                value={catalog.data!.summary.datasets_without_active_version}
              />
            </Grid>
          </Grid>
          {!catalog.data!.entries.length ? (
            <EmptyState
              title="No hay datasets administrados todavía."
              detail="Registra una fuente de datos y ejecuta una importación para verla aquí."
            />
          ) : (
            <DataTable
              label="datasets administrados"
              rows={catalog.data!.entries.map((entry) => ({ id: entry.dataset_type, ...entry }))}
              columns={[
                {
                  key: 'dataset',
                  label: 'Dataset',
                  render: (x) => (
                    <RouterLink to={`/app/admin/data-hub/${x.dataset_type}`}>
                      {DATASET_LABELS[x.dataset_type] ?? x.dataset_label}
                    </RouterLink>
                  ),
                },
                {
                  key: 'sources',
                  label: 'Fuentes',
                  render: (x) =>
                    x.sources.length ? x.sources.map((s) => s.institution).join(', ') : '—',
                },
                {
                  key: 'version',
                  label: 'Versión vigente',
                  render: (x) =>
                    x.active_version ? (
                      x.active_version.version_label
                    ) : (
                      <Alert severity="warning" sx={{ py: 0 }}>
                        Sin versión vigente
                      </Alert>
                    ),
                },
                {
                  key: 'last_import',
                  label: 'Última importación',
                  render: (x) =>
                    x.last_job ? (
                      <>
                        <StatusBadge value={x.last_job.status} /> {x.last_job.original_filename}
                      </>
                    ) : (
                      '—'
                    ),
                },
                {
                  key: 'versions',
                  label: 'Versiones',
                  render: (x) => x.versions_count,
                },
              ]}
            />
          )}
        </Stack>
      )}
    </>
  );
}
