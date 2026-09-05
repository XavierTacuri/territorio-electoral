export const SOURCE_TYPE_LABELS: Record<string, string> = {
  OFFICIAL_WEBSITE: 'Sitio oficial',
  OFFICIAL_API: 'API oficial',
  OPEN_DATA: 'Datos abiertos',
  RSS: 'RSS',
  NEWS: 'Noticias',
  PUBLIC_DOCUMENT_REPOSITORY: 'Repositorio documental',
  OTHER: 'Otro',
};
export const ITEM_TYPE_LABELS: Record<string, string> = {
  ARTICLE: 'Artículo',
  OFFICIAL_NOTICE: 'Aviso oficial',
  PRESS_RELEASE: 'Comunicado de prensa',
  REPORT: 'Informe',
  DATASET: 'Dataset',
  PUBLIC_DOCUMENT: 'Documento público',
  REGULATION: 'Normativa',
  PROJECT_UPDATE: 'Actualización de proyecto',
  EVENT_NOTICE: 'Aviso de evento',
  OTHER: 'Otro',
};
export const FETCH_STATUS_LABELS: Record<string, string> = {
  QUEUED: 'En cola',
  RUNNING: 'En ejecución',
  SUCCESS: 'Correcta',
  PARTIAL: 'Parcial',
  FAILED: 'Fallida',
};
export const RETRIEVAL_METHOD_LABELS: Record<string, string> = {
  MANUAL: 'Manual',
  RSS: 'RSS',
  API: 'API',
};
export const PUBLIC_TOPIC_LABELS: Record<string, string> = {
  WATER_SANITATION: 'Agua y saneamiento',
  WATER: 'Agua y saneamiento',
  BUDGET: 'Presupuesto',
  EDUCATION: 'Educación',
  HEALTH: 'Salud',
  OTHER: 'Otros',
  PUBLIC_WORKS: 'Obras públicas',
  SECURITY: 'Seguridad',
  ROAD_INFRASTRUCTURE: 'Vialidad',
  ROADS: 'Vialidad',
  TRANSPORT: 'Transporte',
  ENVIRONMENT: 'Ambiente',
  HOUSING: 'Vivienda',
  EMPLOYMENT: 'Empleo',
  CONNECTIVITY: 'Conectividad',
};
export const publicTopicLabel = (code: string, fallback?: string) =>
  PUBLIC_TOPIC_LABELS[code] ?? fallback ?? 'Otros';
