export type ElectoralProcess = {
  id: string;
  code: string;
  name: string;
  process_type: string;
  election_date: string;
  year: number;
  status: string;
  is_final: boolean;
  source_id: string;
  is_active: boolean;
};

export type ElectoralContest = {
  id: string;
  electoral_process_id: string;
  office_type: string;
  name: string;
  vote_method: string;
  province_id: number | null;
  canton_id: number | null;
  parish_id: number | null;
  seats: number;
  is_active: boolean;
};

export type Province = { id: number; code: string; name: string; is_active: boolean };
export type Canton = {
  id: number;
  province_id: number;
  code: string;
  dpa_code: string;
  name: string;
  is_active: boolean;
};

export type PoliticalOrganization = { id: string; external_code: string | null; name: string };
export type ElectoralCandidate = { id: string; external_code: string; full_name: string };
export type ElectoralGeography = {
  id: string;
  level: string;
  external_code: string;
  canton_id: number | null;
  parish_id: number | null;
  is_mapped: boolean;
};
export type Turnout = { id: string; electoral_geography_id: string };
export type CandidateResult = {
  candidate: ElectoralCandidate;
  votes: number;
};

export type ImportErrorRow = {
  row_number?: number | null;
  column_name?: string | null;
  error_code: string;
  message: string;
};

export type ImportResult = {
  id: string;
  status: string;
  rows_read: number;
  rows_valid: number;
  rows_inserted: number;
  rows_updated: number;
  rows_failed: number;
  errors: ImportErrorRow[];
  mapping_profile?: string | null;
};

export type CneDataset =
  | 'CNE_POLITICAL_ORGANIZATIONS'
  | 'CNE_TURNOUT'
  | 'CNE_CANDIDATES'
  | 'CNE_ELECTORAL_RESULTS';
export type OfficialDataset =
  | CneDataset
  | 'CNE_ELECTORAL_ROLL_SNAPSHOT'
  | 'CNE_POLLING_PLACES'
  | 'CNE_ELECTORAL_BOARDS';

export type CsvInspection = {
  headers: string[];
  rows: Record<string, string>[];
  delimiter: ',' | ';';
  missingHeaders: string[];
  processCodes: string[];
  contestCodes: string[];
  candidateCodes: string[];
  organizationCodes: string[];
  geographyCodes: string[];
  usesOrganizations: boolean;
};
