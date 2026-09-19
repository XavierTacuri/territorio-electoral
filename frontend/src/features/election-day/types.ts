export type ElectionDayOperation = {
  id: string;
  organization_id: string;
  campaign_id: string;
  electoral_process_id: string;
  election_date: string;
  status: 'PREPARATION' | 'ACTIVE' | 'SCRUTINY' | 'CLOSED';
  opened_at: string | null;
  closed_at: string | null;
  opened_by_user_id: string | null;
  closed_by_user_id: string | null;
  scrutiny_started_at: string | null;
  scrutiny_started_by_user_id: string | null;
  notes: string | null;
};

export type CoverageSummary = {
  total_polling_places: number;
  covered_polling_places: number;
  total_boards: number;
  covered_boards: number;
  personnel_confirmed: number;
  personnel_checked_in: number;
  open_incidents: number;
  documents_received: number;
  expected_documents: number;
};

export type PollingPlace = {
  id: string;
  electoral_process_id: string;
  province_id: number;
  canton_id: number;
  parish_id: number;
  official_code: string;
  name: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  is_active: boolean;
};

export type ElectoralBoard = {
  id: string;
  polling_place_id: string;
  official_code: string;
  board_number: number;
  sex_category: string | null;
  registered_voters: number | null;
  is_active: boolean;
};

export type ElectionDayAssignmentRole = 'POLLING_PLACE_DELEGATE' | 'ACT_VALIDATOR';
export type ElectionDayAssignmentStatus =
  | 'ASSIGNED'
  | 'CONFIRMED'
  | 'CHECKED_IN'
  | 'ABSENT'
  | 'REPLACED'
  | 'COMPLETED';

export type ElectionDayAssignment = {
  id: string;
  operation_id: string;
  user_id: string;
  polling_place_id: string | null;
  assignment_role: ElectionDayAssignmentRole;
  status: ElectionDayAssignmentStatus;
  checked_in_at: string | null;
  checkin_latitude: number | null;
  checkin_longitude: number | null;
  replaced_by_assignment_id: string | null;
};

export type IncidentCategory =
  | 'PERSONNEL'
  | 'ACCESS'
  | 'LOGISTICS'
  | 'DOCUMENTATION'
  | 'CONNECTIVITY'
  | 'OTHER';
export type IncidentStatus = 'OPEN' | 'IN_REVIEW' | 'RESOLVED';

export type ElectionDayIncident = {
  id: string;
  operation_id: string;
  polling_place_id: string;
  board_id: string | null;
  reported_by_user_id: string;
  category: IncidentCategory;
  description: string;
  status: IncidentStatus;
  reported_at: string;
  resolved_at: string | null;
  resolution_notes: string | null;
};

export type DocumentType = 'ACTA_COPY' | 'INCIDENT_DOCUMENT' | 'OTHER';
export type DocumentStatus = 'RECEIVED' | 'REQUIRES_REVIEW' | 'VALIDATED';

export type ElectionDayDocument = {
  id: string;
  operation_id: string;
  polling_place_id: string;
  board_id: string | null;
  document_type: DocumentType;
  mime_type: string | null;
  size_bytes: number | null;
  original_filename: string | null;
  uploaded_by_user_id: string;
  status: DocumentStatus;
};

export const ASSIGNMENT_ROLE_LABELS: Record<ElectionDayAssignmentRole, string> = {
  POLLING_PLACE_DELEGATE: 'Delegado de recinto',
  ACT_VALIDATOR: 'Validador de actas',
};

export const ASSIGNMENT_STATUS_LABELS: Record<ElectionDayAssignmentStatus, string> = {
  ASSIGNED: 'Asignado',
  CONFIRMED: 'Confirmado',
  CHECKED_IN: 'Presente',
  ABSENT: 'Ausente',
  REPLACED: 'Reemplazado',
  COMPLETED: 'Finalizado',
};

export const INCIDENT_CATEGORY_LABELS: Record<IncidentCategory, string> = {
  PERSONNEL: 'Personal',
  ACCESS: 'Acceso',
  LOGISTICS: 'Logística',
  DOCUMENTATION: 'Documentación',
  CONNECTIVITY: 'Conectividad',
  OTHER: 'Otra',
};

export const INCIDENT_STATUS_LABELS: Record<IncidentStatus, string> = {
  OPEN: 'Abierta',
  IN_REVIEW: 'En revisión',
  RESOLVED: 'Resuelta',
};

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  ACTA_COPY: 'Copia de acta',
  INCIDENT_DOCUMENT: 'Documento de incidencia',
  OTHER: 'Otro',
};

export const DOCUMENT_STATUS_LABELS: Record<DocumentStatus, string> = {
  RECEIVED: 'Recibido',
  REQUIRES_REVIEW: 'Requiere revisión',
  VALIDATED: 'Revisado',
};

export const OPERATION_STATUS_LABELS: Record<ElectionDayOperation['status'], string> = {
  PREPARATION: 'Preparación',
  ACTIVE: 'Jornada activa',
  SCRUTINY: 'Escrutinio',
  CLOSED: 'Jornada cerrada',
};

export type ElectionDayPreflightSummary = {
  polling_places: number;
  boards: number;
  delegates: number;
  validators: number;
  uncovered_polling_places: number;
};

export type ElectionDayPreflightResponse = {
  ready: boolean;
  blockers: string[];
  warnings: string[];
  summary: ElectionDayPreflightSummary;
};

export type ElectionDayControlCenterResponse = {
  operation: ElectionDayOperation;
  coverage: CoverageSummary;
};

export type ElectionDayValidationStatus = {
  operation_status: ElectionDayOperation['status'];
  pending_reviews: number;
};

export type ElectionDayAdminSupportSession = {
  id: string;
  admin_user_id: string;
  organization_id: string;
  campaign_id: string;
  operation_id: string;
  reason: string | null;
  started_at: string;
  ended_at: string | null;
};
