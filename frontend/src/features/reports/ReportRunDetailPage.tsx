import { Alert, Button, Stack } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { downloadReport } from '../../api/downloads';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { ReportPreviewView } from './ReportPreviewView';
import type { ReportPreview, ReportRun } from './types';

type StalenessAlert = {
  id: string;
  resource_type: string | null;
  resource_id: string | null;
  evidence: { reasons?: string[] };
};

export default function ReportRunDetailPage() {
  const { campaignId = '', runId = '' } = useParams();
  const run = useQuery({
    queryKey: ['report-run', campaignId, runId],
    queryFn: () => apiRequest<ReportRun>(`/campaigns/${campaignId}/reports/${runId}`),
  });
  const preview = useQuery({
    queryKey: ['report-run-preview', campaignId, runId],
    queryFn: () => apiRequest<ReportPreview>(`/campaigns/${campaignId}/reports/${runId}/preview`),
    enabled: run.data?.status === 'COMPLETED',
  });
  const staleness = useQuery({
    queryKey: ['report-run-staleness', campaignId, runId],
    queryFn: () =>
      apiRequest<{ items: StalenessAlert[] }>(
        `/campaigns/${campaignId}/alerts?status=OPEN&module=REPORTS&page=1&page_size=50`,
      ),
    enabled: run.data?.status === 'COMPLETED',
  });
  const staleAlert = staleness.data?.items.find(
    (item) => item.resource_type === 'REPORT_RUN' && item.resource_id === runId,
  );

  function regenerateLink(current: ReportRun) {
    const filters = current.filters || {};
    const params = new URLSearchParams();
    if (filters.parish_id != null) params.set('parish_id', String(filters.parish_id));
    if (filters.theme) params.set('theme', filters.theme);
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);
    if (filters.include_surveys === false) params.set('include_surveys', 'false');
    if (filters.include_public_intelligence === false)
      params.set('include_public_intelligence', 'false');
    if (filters.include_evidence === false) params.set('include_evidence', 'false');
    if (filters.include_demo === false) params.set('include_demo', 'false');
    if (current.template_code === 'DEBATE_BRIEF_REPORT') {
      return `/app/campaigns/${campaignId}/debate?${params.toString()}`;
    }
    params.set('type', current.template_code);
    return `/app/campaigns/${campaignId}/reports?${params.toString()}`;
  }

  if (run.isLoading) return <LoadingSkeleton />;
  if (run.isError || !run.data) return <ErrorState retry={() => run.refetch()} />;

  return (
    <>
      <PageHeader
        title="Detalle de informe"
        description={run.data.title}
        action={
          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              disabled={!run.data.artifact?.is_available}
              onClick={() =>
                downloadReport(
                  `/campaigns/${campaignId}/reports/${runId}/download`,
                  run.data!.artifact?.original_download_name ||
                    `informe.${run.data!.requested_format.toLowerCase()}`,
                )
              }
            >
              Descargar {run.data.requested_format}
            </Button>
            <Button component={RouterLink} to={`/app/campaigns/${campaignId}/reports`}>
              Volver al Centro de Informes
            </Button>
          </Stack>
        }
      />
      {run.data.status === 'FAILED' && (
        <Alert severity="error">
          No fue posible generar este informe. Puedes intentar generarlo nuevamente desde el Centro
          de Informes.
        </Alert>
      )}
      {staleAlert && (
        <Alert
          severity="info"
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              component={RouterLink}
              to={regenerateLink(run.data)}
            >
              GENERAR VERSIÓN ACTUALIZADA
            </Button>
          }
        >
          Existe información oficial más reciente que la utilizada para este informe
          {staleAlert.evidence.reasons?.length
            ? `: ${staleAlert.evidence.reasons.join('; ')}.`
            : '.'}{' '}
          El informe original no se modifica automáticamente.
        </Alert>
      )}
      {preview.isLoading && run.data.status === 'COMPLETED' && <LoadingSkeleton />}
      {preview.isError && (
        <Alert severity="warning">
          No fue posible reconstruir la previsualización de este informe.
        </Alert>
      )}
      {preview.data && <ReportPreviewView preview={preview.data} />}
    </>
  );
}
