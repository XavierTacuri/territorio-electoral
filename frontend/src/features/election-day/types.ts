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

export type ElectionDayStaffType = 'POLLING_PLACE_DELEGATE' | 'ACT_VALIDATOR';
export type ElectionDayInvitationStatus = 'PENDING' | 'ACCEPTED' | 'REVOKED' | 'EXPIRED';

export const STAFF_TYPE_LABELS: Record<ElectionDayStaffType, string> = {
  POLLING_PLACE_DELEGATE: 'Delegado de recinto',
  ACT_VALIDATOR: 'Validador de actas',
};

export const INVITATION_STATUS_LABELS: Record<ElectionDayInvitationStatus, string> = {
  PENDING: 'Pendiente',
  ACCEPTED: 'Aceptada',
  REVOKED: 'Revocada',
  EXPIRED: 'Expirada',
};

export type ElectionDayStaffInvitation = {
  id: string;
  campaign_id: string;
  operation_id: string;
  email: string;
  first_name: string;
  last_name: string;
  staff_type: ElectionDayStaffType;
  status: ElectionDayInvitationStatus;
  invited_by_user_id: string;
  accepted_user_id: string | null;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
  polling_place_ids: string[];
};

export type ElectionDayStaffInvitationCreatedResponse = {
  invitation: ElectionDayStaffInvitation;
  invite_token: string;
  invite_url: string;
};

export type ElectionDayInvitationPollingPlaceSummary = { id: string; name: string };

export type ElectionDayInvitationPreview = {
  campaign_name: string;
  election_date: string;
  staff_type: ElectionDayStaffType;
  email: string;
  first_name: string;
  last_name: string;
  polling_places: ElectionDayInvitationPollingPlaceSummary[];
  expires_at: string;
  requires_login: boolean;
  status: ElectionDayInvitationStatus;
};

export type ElectionDayMyContext = {
  campaign_id: string;
  campaign_name: string;
  organization_id: string;
  operation_id: string;
  election_date: string;
  operation_status: ElectionDayOperation['status'];
  staff_types: ElectionDayStaffType[];
  polling_places: ElectionDayInvitationPollingPlaceSummary[];
};

export type ElectionDayMyContextSummary = {
  campaign_id: string;
  campaign_name: string;
  operation_id: string;
  election_date: string;
  operation_status: ElectionDayOperation['status'];
  staff_types: ElectionDayStaffType[];
};

// ---------- Actas electorales (Fase 2) ----------

export type ElectionActStatus = 'RECEIVED' | 'IN_REVIEW' | 'OBSERVED' | 'VALIDATED';

export const ACT_STATUS_LABELS: Record<ElectionActStatus, string> = {
  RECEIVED: 'Recibida',
  IN_REVIEW: 'En revisión',
  OBSERVED: 'Observada',
  VALIDATED: 'Validada',
};

export type ElectionActResultInput = { electoral_candidate_id: string; votes: number };

export type ElectionActRead = {
  id: string;
  campaign_id: string;
  operation_id: string;
  polling_place_id: string;
  electoral_board_id: string;
  electoral_contest_id: string;
  status: ElectionActStatus;
  latest_revision_number: number;
  validated_revision_id: string | null;
  review_claimed_by_user_id: string | null;
  review_claimed_at: string | null;
  review_claim_expires_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ElectionActEvidenceRead = {
  id: string;
  revision_id: string;
  mime_type: string;
  size_bytes: number;
  original_filename: string | null;
  uploaded_by_user_id: string;
  created_at: string;
};

export type ElectionActRevisionRead = {
  id: string;
  act_id: string;
  revision_number: number;
  revision_type: 'INITIAL' | 'CORRECTION';
  status: 'DRAFT' | 'SUBMITTED';
  submitted_by_user_id: string;
  blank_ballots: number;
  null_ballots: number;
  valid_ballots: number | null;
  ballots_counted: number | null;
  correction_reason: string | null;
  notes: string | null;
  created_at: string;
  submitted_at: string | null;
  results: { electoral_candidate_id: string; votes: number }[];
  evidence: ElectionActEvidenceRead[];
};

export type ElectionActReviewRead = {
  id: string;
  act_id: string;
  revision_id: string;
  reviewer_user_id: string;
  review_source: 'CAMPAIGN_VALIDATOR' | 'ADMIN_SUPPORT';
  action: 'VALIDATED' | 'OBSERVED';
  reason: string | null;
  created_at: string;
};

export type ElectionActDetail = {
  act: ElectionActRead;
  polling_place_name: string;
  electoral_board_code: string;
  electoral_contest_name: string;
  revisions: ElectionActRevisionRead[];
  reviews: ElectionActReviewRead[];
};

export type ElectionActListResponse = { items: ElectionActRead[]; total: number };

export type ElectionActCandidateOption = {
  id: string;
  full_name: string;
  display_name: string | null;
  list_number: string | null;
  ballot_order: number | null;
};

export type ElectionActContestOption = {
  id: string;
  name: string;
  office_type: string;
  vote_method: 'SINGLE_CHOICE' | 'MULTI_VOTE' | 'LIST_VOTE' | 'OTHER';
  candidates: ElectionActCandidateOption[];
};

export type ElectionActCoverageSummary = {
  expected_boards: number;
  received: number;
  validated: number;
  in_review: number;
  observed: number;
  pending: number;
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
