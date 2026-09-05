export type ClaimEvidenceItem = {
  id: string;
  title: string;
  source_name: string;
  evidence_class: string;
  source_label: string;
  record_date: string | null;
  external_url: string | null;
};

export type ClaimCheckResponse = {
  claim_text: string;
  verdict: 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'UNSUPPORTED';
  verdict_label: string;
  evidence: ClaimEvidenceItem[];
  warnings: string[];
};
