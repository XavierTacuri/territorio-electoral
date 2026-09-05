import { useState } from 'react';
import { Alert, Button, Stack, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigate, Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { downloadReport } from '../../api/downloads';
import { useAuth } from '../../auth/AuthProvider';
import { canRunImports, canViewDataHub } from '../../auth/permissions';
import { RoleBadge, StatusBadge } from '../../components/data-display/Common';
import { ConfirmDialog } from '../../components/forms/ConfirmDialog';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { formatDateOnly } from '../../lib/dates';
import {
  DATASET_LABELS,
  JOB_STATUS_LABELS,
  VERSION_STATUS_LABELS,
  newImportRoute,
  type DatasetDetail,
  type DatasetVersion,
  type VersionDiff,
} from './types';

function messageFor(error: unknown) {
  if (!(error instanceof ApiError)) return 'No se pudo completar la operación.';
  if (error.status === 403) return 'No tienes permisos para administrar el Centro de datos.';
  if (error.status === 409) return 'La versión ya está activa o en conflicto con otra operación.';
  if (error.status === 404) return 'La versión no existe.';
  return 'No se pudo completar la operación.';
}

export default function DatasetDetailPage() {
  const { datasetType = '' } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [confirmVersion, setConfirmVersion] = useState<DatasetVersion | null>(null);
  const [confirmAction, setConfirmAction] = useState<'activate' | 'archive' | null>(null);
  const [diffFor, setDiffFor] = useState<string | null>(null);
  const [error, setError] = useState('');
  const detail = useQuery({
    queryKey: ['data-hub-dataset', datasetType],
    queryFn: () => apiRequest<DatasetDetail>(`/data-hub/datasets/${datasetType}`),
  });
  const diff = useQuery({
    queryKey: ['data-hub-diff', diffFor],
    queryFn: () => apiRequest<VersionDiff>(`/data-hub/versions/${diffFor}/diff`),
    enabled: !!diffFor,
  });
  const act = useMutation({
    mutationFn: (payload: { id: string; action: 'activate' | 'archive' }) =>
      apiRequest<DatasetVersion>(`/data-hub/versions/${payload.id}/${payload.action}`, {
        method: 'POST',
      }),
    onSuccess: async () => {
      setConfirmVersion(null);
      setConfirmAction(null);
      setError('');
      await queryClient.invalidateQueries({ queryKey: ['data-hub-dataset', datasetType] });
      await queryClient.invalidateQueries({ queryKey: ['data-hub-catalog'] });
    },
    onError: (reason) => setError(messageFor(reason)),
  });
  if (!canViewDataHub(user)) return <Navigate to="/403" replace />;
  const label = DATASET_LABELS[datasetType] ?? datasetType;
  const isSnapshot = detail.data?.version_kind === 'SNAPSHOT_VERSIONED';
  const activateLabel = isSnapshot ? 'Activar' : 'Marcar como versión de referencia';
  return (
    <>
      <PageHeader
        title={label}
        description="Fuente, versión vigente, historial de importaciones y calidad de este conjunto de datos."
        action={
          canRunImports(user) ? (
            <Button variant="contained" component={RouterLink} to={newImportRoute(datasetType)}>
              Nueva importación
            </Button>
          ) : undefined
        }
      />
      {detail.isLoading ? (
        <LoadingSkeleton />
      ) : detail.isError ? (
        <ErrorState retry={() => detail.refetch()} />
      ) : (
        <Stack spacing={3}>
          {error && <Alert severity="error">{error}</Alert>}
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography color="text.secondary">Tipo de versionado:</Typography>
            <RoleBadge value={detail.data!.version_kind_label} />
          </Stack>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <Alert severity={detail.data!.active_version ? 'success' : 'warning'} sx={{ flex: 1 }}>
              {detail.data!.active_version
                ? `Versión vigente: ${detail.data!.active_version.version_label}`
                : 'Este dataset no tiene una versión vigente activada.'}
            </Alert>
            {canRunImports(user) && (
              <Button
                variant="outlined"
                onClick={() =>
                  downloadReport(
                    `/data-import-profiles/${datasetType}/template`,
                    `plantilla_${datasetType.toLowerCase()}.csv`,
                  )
                }
              >
                Descargar plantilla CSV
              </Button>
            )}
          </Stack>
          {canRunImports(user) && (
            <Alert severity="info">
              Los códigos DPA contienen ceros iniciales. Trate estas columnas como texto al abrir la
              plantilla en Excel.
            </Alert>
          )}
          <div>
            <Typography variant="h2" gutterBottom>
              Fuentes
            </Typography>
            {!detail.data!.sources.length ? (
              <EmptyState
                title="No hay fuentes registradas para este dataset."
                detail="Registra una fuente oficial en Fuentes de datos."
              />
            ) : (
              <DataTable
                label="fuentes"
                rows={detail.data!.sources}
                columns={[
                  { key: 'code', label: 'Código', render: (x) => x.code },
                  { key: 'institution', label: 'Institución', render: (x) => x.institution },
                  {
                    key: 'reference',
                    label: 'Referencia',
                    render: (x) =>
                      x.reference_date
                        ? formatDateOnly(x.reference_date)
                        : (x.reference_year ?? '—'),
                  },
                  {
                    key: 'status',
                    label: 'Estado',
                    render: (x) => (x.is_active ? 'Activa' : 'Inactiva'),
                  },
                ]}
              />
            )}
          </div>
          <div>
            <Typography variant="h2" gutterBottom>
              Versiones
            </Typography>
            {!detail.data!.versions.length ? (
              <EmptyState
                title="Todavía no hay versiones para este dataset."
                detail={
                  datasetType === 'OTHER_AGGREGATED_OFFICIAL'
                    ? 'Las geometrías y otros conjuntos agregados se administran desde Límites territoriales / Importaciones y todavía no cuentan con versionado administrado en el Centro de datos.'
                    : 'Ejecuta una importación para generar la primera versión.'
                }
              />
            ) : (
              <DataTable
                label="versiones"
                rows={detail.data!.versions}
                columns={[
                  { key: 'label', label: 'Versión', render: (x) => x.version_label },
                  {
                    key: 'reference',
                    label: 'Corte / referencia',
                    render: (x) => (x.reference_date ? formatDateOnly(x.reference_date) : '—'),
                  },
                  {
                    key: 'status',
                    label: 'Estado',
                    render: (x) => (
                      <StatusBadge value={VERSION_STATUS_LABELS[x.status] ?? x.status} />
                    ),
                  },
                  {
                    key: 'activated',
                    label: 'Activada',
                    render: (x) => (x.activated_at ? formatDateOnly(x.activated_at) : '—'),
                  },
                  {
                    key: 'actions',
                    label: 'Acciones',
                    render: (x) => (
                      <Stack direction="row" spacing={1} flexWrap="wrap">
                        <Button size="small" onClick={() => setDiffFor(x.id)}>
                          Ver diferencia
                        </Button>
                        {canRunImports(user) &&
                          x.status !== 'ACTIVE' &&
                          x.status !== 'ARCHIVED' && (
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => {
                                setConfirmVersion(x);
                                setConfirmAction('activate');
                              }}
                            >
                              {activateLabel}
                            </Button>
                          )}
                        {canRunImports(user) &&
                          (x.status === 'ACTIVE' || x.status === 'SUPERSEDED') && (
                            <Button
                              size="small"
                              color="warning"
                              onClick={() => {
                                setConfirmVersion(x);
                                setConfirmAction('archive');
                              }}
                            >
                              Archivar
                            </Button>
                          )}
                      </Stack>
                    ),
                  },
                ]}
              />
            )}
          </div>
          {diffFor && (
            <div>
              <Typography variant="h2" gutterBottom>
                Diferencia entre versiones
              </Typography>
              {diff.isLoading ? (
                <LoadingSkeleton />
              ) : !diff.data?.comparable ? (
                <Stack spacing={1}>
                  {diff.data?.warnings?.length ? (
                    diff.data.warnings.map((warning, index) => (
                      <Alert severity="info" key={index}>
                        {typeof warning === 'string' ? warning : warning.message}
                      </Alert>
                    ))
                  ) : (
                    <Alert severity="info">
                      No hay una comparación disponible para esta versión.
                    </Alert>
                  )}
                </Stack>
              ) : (
                <Stack spacing={1}>
                  <Typography>
                    {diff.data.previous_value} → {diff.data.new_value} (
                    {diff.data.delta! >= 0 ? '+' : ''}
                    {diff.data.delta})
                  </Typography>
                  {diff.data.warnings.map((warning, index) => (
                    <Alert severity="warning" key={index}>
                      {typeof warning === 'string' ? warning : warning.message}
                    </Alert>
                  ))}
                </Stack>
              )}
            </div>
          )}
          <div>
            <Typography variant="h2" gutterBottom>
              Historial de importaciones
            </Typography>
            {!detail.data!.jobs.length ? (
              <EmptyState title="No hay importaciones registradas." />
            ) : (
              <DataTable
                label="importaciones"
                rows={detail.data!.jobs}
                columns={[
                  { key: 'file', label: 'Archivo', render: (x) => x.original_filename },
                  {
                    key: 'status',
                    label: 'Estado',
                    render: (x) => <StatusBadge value={JOB_STATUS_LABELS[x.status] ?? x.status} />,
                  },
                  { key: 'valid', label: 'Filas válidas', render: (x) => x.rows_valid },
                  { key: 'failed', label: 'Filas rechazadas', render: (x) => x.rows_failed },
                ]}
              />
            )}
          </div>
        </Stack>
      )}
      <ConfirmDialog
        open={!!confirmVersion}
        title={confirmAction === 'archive' ? 'Archivar versión' : activateLabel}
        busy={act.isPending}
        onCancel={() => {
          setConfirmVersion(null);
          setConfirmAction(null);
        }}
        onConfirm={() =>
          confirmVersion &&
          confirmAction &&
          act.mutate({ id: confirmVersion.id, action: confirmAction })
        }
      >
        {confirmAction === 'archive' ? (
          <Typography>
            La versión "{confirmVersion?.version_label}" dejará de estar disponible como referencia
            operativa. Los datos ya importados no se eliminan.
          </Typography>
        ) : isSnapshot ? (
          <Typography>
            Se activará "{confirmVersion?.version_label}" como versión vigente. Si otra versión está
            activa, pasará a estado "Reemplazada". Los cortes históricos no se eliminan y siguen
            disponibles para consulta y comparación.
          </Typography>
        ) : (
          <Typography>
            Se marcará "{confirmVersion?.version_label}" como versión de referencia administrativa.
            Si otra versión está marcada, pasará a estado "Reemplazada". Esta acción cambia la
            referencia administrativa. No restaura automáticamente los valores reemplazados durante
            importaciones anteriores.
          </Typography>
        )}
      </ConfirmDialog>
    </>
  );
}
