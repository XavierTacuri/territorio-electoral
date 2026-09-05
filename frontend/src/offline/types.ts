export type OwnerScope = {
  user_id: string;
  organization_id: string;
  campaign_id: string;
};

export function ownerKey(scope: OwnerScope): string {
  return `${scope.user_id}::${scope.organization_id}::${scope.campaign_id}`;
}

export type DraftEntityType =
  | 'ACTIVITY'
  | 'NEED'
  | 'ELECTION_DAY_CHECK_IN'
  | 'ELECTION_DAY_INCIDENT'
  | 'ELECTION_DAY_DOCUMENT';

export type DraftSyncStatus =
  | 'DRAFT'
  | 'PENDING'
  | 'SYNCING'
  | 'SYNCED'
  | 'REQUIRES_REVIEW'
  | 'ERROR';

// Distinguishes why a draft needs review, so the conflict UI can pick the
// right actions without parsing error text: FORBIDDEN means the coordinator
// lost access to the territory (never offer to overwrite the server, see
// section 11); CONFLICT means the server already has a similar record and
// the two versions genuinely need comparing.
export type ConflictReason = 'FORBIDDEN' | 'CONFLICT' | null;

export type OfflineDraft = {
  id: string; // `${entity_type}:${client_generated_id}`
  owner_key: string; // ownerKey({user_id, organization_id, campaign_id}) — isolation boundary
  client_generated_id: string;
  entity_type: DraftEntityType;
  organization_id: string;
  campaign_id: string;
  parish_id: number;
  user_id: string;
  payload: Record<string, unknown>;
  created_offline_at: string;
  updated_offline_at: string;
  sync_status: DraftSyncStatus;
  last_error: string | null;
  conflict_reason: ConflictReason;
  server_id: string | null;
};

export type SyncQueueStatus = 'PENDING' | 'SYNCING' | 'SYNCED' | 'FAILED' | 'CONFLICT';

export type SyncQueueItem = {
  id: string; // matches the draft id it syncs
  owner_key: string;
  draft_id: string;
  entity_type: DraftEntityType;
  organization_id: string;
  campaign_id: string;
  user_id: string;
  status: SyncQueueStatus;
  attempts: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

export type CachedAssignment = {
  owner_key: string;
  organization_id: string;
  campaign_id: string;
  user_id: string;
  parishes: { parish_id: number; parish_name: string }[];
  fetched_at: string;
};

export type FieldAgendaItem = {
  id: string;
  title: string;
  activity_date: string;
  start_time: string | null;
  status: string;
  approval_status: string;
  parish_id: number;
  parish_name: string | null;
};

export type CachedAgenda = {
  owner_key: string;
  organization_id: string;
  campaign_id: string;
  user_id: string;
  items: FieldAgendaItem[];
  fetched_at: string;
};

export type AttachmentSyncStatus = 'PENDING' | 'SYNCING' | 'SYNCED' | 'FAILED' | 'REQUIRES_REVIEW';

export type PendingAttachment = {
  id: string;
  client_generated_id: string; // sent to the server for idempotent retry
  draft_id: string;
  owner_key: string;
  evidence_type: 'PHOTO' | 'DOCUMENT';
  title: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  blob: Blob;
  created_at: string;
  sync_status: AttachmentSyncStatus;
  last_error: string | null;
  server_id: string | null;
};

export type CachedCatalog = {
  name: string;
  items: { code: string; name: string }[];
  fetched_at: string;
};

export type CachedCampaignInfo = {
  campaign_id: string;
  organization_id: string;
  name: string;
  fetched_at: string;
};

export type CachedElectionDayAssignment = {
  owner_key: string;
  assignment_id: string;
  assignment_status: string;
  polling_place_id: string;
  polling_place_name: string;
  board_id: string | null;
  board_code: string | null;
  fetched_at: string;
};

export type SessionSnapshot = {
  id: 'current';
  user: {
    id: string;
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    is_active: boolean;
    is_superuser: boolean;
    roles: { code: string; name: string }[];
  };
  updated_at: string;
};
