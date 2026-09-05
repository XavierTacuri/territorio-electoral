export type ElectionDayOperation = {
  id: string;
  organization_id: string;
  campaign_id: string;
  electoral_process_id: string;
  election_date: string;
  status: 'PREPARATION' | 'ACTIVE' | 'CLOSED';
  opened_at: string | null;
  closed_at: string | null;
  opened_by_user_id: string | null;
  closed_by_user_id: string | null;
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

export type ElectionDayAssignmentRole =
  | 'POLLING_PLACE_COORDINATOR'
  | 'BOARD_DELEGATE'
  | 'MOBILE_SUPPORT';
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
  polling_place_id: string;
  board_id: string | null;
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
  POLLING_PLACE_COORDINATOR: 'Coordinador de recinto',
  BOARD_DELEGATE: 'Delegado de junta',
  MOBILE_SUPPORT: 'Apoyo móvil',
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
  CLOSED: 'Jornada cerrada',
};
