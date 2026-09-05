export type OfficeType = 'MAYOR' | 'URBAN_COUNCILOR' | 'RURAL_COUNCILOR' | 'PARISH_BOARD';
export type CampaignStatus = 'DRAFT' | 'ACTIVE' | 'COMPLETED' | 'ARCHIVED';

export type Province = {
  id: number;
  code: string;
  dpa_code: string;
  name: string;
  is_active: boolean;
};
export type Canton = {
  id: number;
  province_id: number;
  code: string;
  dpa_code: string;
  name: string;
  is_active: boolean;
};
export type Candidate = {
  id: string;
  display_name: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
};
export type CampaignSummary = {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  canton_id: number;
  canton_name?: string | null;
  province_id?: number | null;
  province_name?: string | null;
  office_type: OfficeType;
  election_name: string;
  election_date: string;
  status: CampaignStatus;
  is_active: boolean;
};
export type CampaignRead = CampaignSummary & {
  start_date: string | null;
  end_date: string | null;
  description: string | null;
  candidate: Candidate | null;
};
export type CampaignListResponse = {
  items: CampaignSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export const officeLabels: Record<OfficeType, string> = {
  MAYOR: 'Alcaldía / Alcalde',
  URBAN_COUNCILOR: 'Concejalía urbana',
  RURAL_COUNCILOR: 'Concejalía rural',
  PARISH_BOARD: 'Junta parroquial',
};
export const statusLabels: Record<CampaignStatus, string> = {
  DRAFT: 'Borrador',
  ACTIVE: 'Activa',
  COMPLETED: 'Completada',
  ARCHIVED: 'Archivada',
};
