export type ReportTypeInfo = {
  code: string;
  name: string;
  description: string;
  requires_parish: boolean;
  requires_theme: boolean;
  allowed_formats: string[];
};

export type ReportCitation = {
  id: string;
  source_type: string;
  title: string;
  source_name: string;
  source_url: string | null;
  deep_link: string | null;
  evidence_class: string;
  record_date: string | null;
};

export type ReportNarrative = {
  titulo_sugerido: string;
  resumen_ejecutivo: string;
  hallazgos_principales: string[];
  limitations: string[];
  provider: string;
};

export type ReportSection = {
  title: string;
  subtitle?: string | null;
  text?: string | null;
  headers: string[];
  rows: unknown[][];
};

export type ReportPreview = {
  report_kind: string;
  title: string;
  subtitle: string | null;
  generated_at: string;
  generated_by: string;
  is_demo: boolean;
  narrative: ReportNarrative;
  sections: ReportSection[];
  citations: ReportCitation[];
  limitations: string[];
};

export type ReportRunFilters = {
  date_from?: string | null;
  date_to?: string | null;
  parish_id?: number | null;
  theme?: string | null;
  include_surveys?: boolean;
  include_public_intelligence?: boolean;
  include_evidence?: boolean;
  include_demo?: boolean;
  include_citations?: boolean;
};

export type ReportRun = {
  id: string;
  campaign_id: string;
  template_code: string;
  requested_format: string;
  status: string;
  report_date: string;
  date_from: string | null;
  date_to: string | null;
  title: string;
  error_code?: string | null;
  error_message?: string | null;
  artifact: {
    id: string;
    format: string;
    original_download_name: string;
    is_available: boolean;
  } | null;
  filters: ReportRunFilters;
};

export const EVIDENCE_CLASS_LABELS: Record<string, string> = {
  OFFICIAL: 'Oficial',
  PUBLIC: 'Fuente pública',
  CAMPAIGN: 'Registro de campaña',
  DEMO: 'Datos simulados',
};

export const SOURCE_TYPE_LABELS: Record<string, string> = {
  CNE: 'Consejo Nacional Electoral',
  TURNOUT_MODEL: 'Modelo de participación',
  INEC: 'Instituto Nacional de Estadística y Censos',
  SURVEY_STUDY: 'Estudio de encuesta',
  TERRITORIAL_ACTIVITY: 'Actividad territorial',
  CITIZEN_NEED: 'Necesidad ciudadana',
  ACTIVITY_EVIDENCE: 'Evidencia de actividad',
  PUBLIC_INTELLIGENCE: 'Información pública',
  OPERATIONS_OVERVIEW: 'Resumen operativo',
};

export const THEME_OPTIONS: { code: string; label: string }[] = [
  { code: 'VIALIDAD', label: 'Vialidad' },
  { code: 'AGUA', label: 'Agua y saneamiento' },
  { code: 'SEGURIDAD', label: 'Seguridad' },
  { code: 'CONECTIVIDAD', label: 'Conectividad' },
  { code: 'EMPLEO', label: 'Empleo' },
  { code: 'SALUD', label: 'Salud' },
  { code: 'EDUCACION', label: 'Educación' },
  { code: 'TRANSPORTE', label: 'Transporte' },
  { code: 'VIVIENDA', label: 'Vivienda' },
  { code: 'AMBIENTE', label: 'Ambiente' },
  { code: 'PRESUPUESTO', label: 'Presupuesto' },
  { code: 'OBRAS_PUBLICAS', label: 'Obras públicas' },
  { code: 'OTROS', label: 'Otros' },
];

export const RUN_STATUS_LABELS: Record<string, string> = {
  PENDING: 'Pendiente',
  GENERATING: 'Generando',
  COMPLETED: 'Completado',
  FAILED: 'Fallido',
  CANCELLED: 'Cancelado',
};
