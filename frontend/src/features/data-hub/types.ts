import type { DataSource } from '../admin/SourcesPage';

export const DATASET_LABELS: Record<string, string> = {
  CNE_ELECTORAL_ROLL_SNAPSHOT: 'CNE · Registro electoral preelectoral',
  CNE_ELECTORAL_RESULTS: 'CNE · Resultados electorales',
  CNE_CANDIDATES: 'CNE · Candidaturas',
  CNE_POLITICAL_ORGANIZATIONS: 'CNE · Organizaciones políticas',
  CNE_TURNOUT: 'CNE · Participación electoral',
  CNE_POLLING_PLACES: 'CNE · Recintos electorales',
  CNE_ELECTORAL_BOARDS: 'CNE · Juntas receptoras del voto',
  INEC_DEMOGRAPHIC_INDICATORS: 'INEC · Indicadores demográficos',
  INEC_POPULATION_PROJECTIONS: 'INEC · Proyecciones poblacionales',
  INEC_GEOGRAPHIC_CLASSIFIER: 'INEC · Clasificador geográfico',
  OTHER_AGGREGATED_OFFICIAL: 'Otra fuente oficial agregada',
};

export const NEW_IMPORT_ROUTE: Record<string, string> = {
  CNE_ELECTORAL_ROLL_SNAPSHOT: '/app/admin/official-data/cne/roll',
  CNE_ELECTORAL_RESULTS: '/app/admin/official-data/cne',
  CNE_CANDIDATES: '/app/admin/official-data/cne',
  CNE_POLITICAL_ORGANIZATIONS: '/app/admin/official-data/cne',
  CNE_TURNOUT: '/app/admin/official-data/cne',
  CNE_POLLING_PLACES: '/app/admin/official-data/election-day/polling-places',
  CNE_ELECTORAL_BOARDS: '/app/admin/official-data/election-day/boards',
  INEC_DEMOGRAPHIC_INDICATORS: '/app/admin/official-data/inec',
  INEC_POPULATION_PROJECTIONS: '/app/admin/official-data/inec',
  INEC_GEOGRAPHIC_CLASSIFIER: '/app/admin/official-data/geography',
};

export const VERSION_STATUS_LABELS: Record<string, string> = {
  DRAFT: 'Borrador',
  VALIDATED: 'Validada',
  ACTIVE: 'Activa',
  SUPERSEDED: 'Reemplazada',
  REJECTED: 'Rechazada',
  ARCHIVED: 'Archivada',
};

export const JOB_STATUS_LABELS: Record<string, string> = {
  RECEIVED: 'Recibida',
  VALIDATING: 'Validando',
  VALIDATED: 'Validada',
  IMPORTING: 'Importando',
  COMPLETED: 'Completada',
  FAILED: 'Fallida',
  REJECTED: 'Rechazada',
};

export function newImportRoute(datasetType: string) {
  return NEW_IMPORT_ROUTE[datasetType] ?? '/app/admin/data-imports';
}

export type DatasetVersion = {
  id: string;
  data_source_id: string;
  dataset_type: string;
  reference_date: string | null;
  version_label: string;
  checksum: string;
  import_job_id: string;
  status: string;
  activated_at: string | null;
  activated_by_user_id: string | null;
  superseded_by_id: string | null;
};

export type ImportJob = {
  id: string;
  source_id: string;
  dataset_type: string;
  original_filename: string;
  file_sha256: string;
  file_size_bytes: number;
  status: string;
  validation_only: boolean;
  rows_read: number;
  rows_valid: number;
  rows_inserted: number;
  rows_updated: number;
  rows_skipped: number;
  rows_failed: number;
  encoding_used: string | null;
  delimiter_used: string | null;
  mapping_profile: string | null;
  error_summary: string | null;
};

export type VersionKind = 'SNAPSHOT_VERSIONED' | 'UPSERT_GOVERNED' | string;

export type DataHubCatalogEntry = {
  dataset_type: string;
  dataset_label: string;
  version_kind: VersionKind;
  version_kind_label: string;
  sources: DataSource[];
  active_version: DatasetVersion | null;
  last_job: ImportJob | null;
  versions_count: number;
};

export type DataHubCatalog = {
  summary: {
    active_sources: number;
    datasets: number;
    recent_imports: number;
    imports_with_errors: number;
    datasets_without_active_version: number;
  };
  entries: DataHubCatalogEntry[];
};

export type DatasetDetail = {
  dataset_type: string;
  dataset_label: string;
  version_kind: VersionKind;
  version_kind_label: string;
  sources: DataSource[];
  active_version: DatasetVersion | null;
  versions: DatasetVersion[];
  jobs: ImportJob[];
};

export type VersionDiff = {
  version_id: string;
  compared_to_id: string | null;
  comparable: boolean;
  metric: string | null;
  previous_value: number | null;
  new_value: number | null;
  delta: number | null;
  items: { parish_id: number; previous: number; new: number; delta: number }[];
  warnings: (string | { code: string; message: string })[];
};
