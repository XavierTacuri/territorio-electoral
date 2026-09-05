import { Box, Chip, Paper, Typography } from '@mui/material';
import { formatIntegerEsEc, formatPercentEsEc } from '../../lib/formatEsEc';
import type { ElectionMapParish } from '../historical/CurrentElectionMap';

export type History = { registered_voters: number; ballots_cast: number; turnout_rate: number | null };
export type Availability = {
  cne_2019: boolean;
  cne_2023: boolean;
  current_registration: boolean;
  inec_2022: boolean;
  geometry: boolean;
};
// Intersecting with the real ElectionMapParish (rather than redeclaring its
// fields) keeps this type assignable to CurrentElectionMap's prop even though
// the fields below are narrower/nullable versions of the base type's fields.
export type Parish = ElectionMapParish & {
  male_voters: number | null;
  female_voters: number | null;
  juntas: number | null;
  data_quality_status: string;
  historical_2019?: History | null;
  historical_2023?: History | null;
  projection?: {
    low: number;
    central: number;
    high: number;
    expected_voters_low: number;
    expected_voters_central: number;
    expected_voters_high: number;
  } | null;
  demographics: Record<string, number>;
  demographics_2010: Record<string, number>;
  population_growth_2010_2022: number | null;
  availability: Availability;
};
export type Analysis = {
  context: { campaign_name: string; canton_name: string; election_name: string };
  snapshot: { snapshot_date: string };
  projection: { model_code: string; model_version: string };
  warnings: { code: string; message: string }[];
  sources: {
    code: string;
    institution: string;
    dataset_name: string;
    official_url?: string | null;
    reference_year?: number | null;
  }[];
  parishes: Parish[];
};
export type Operation = {
  parish_id: number;
  activities: number;
  needs_open: number;
  needs_under_review: number;
  needs_validated: number;
  commitments_related: number;
  needs_by_category: { category: string; count: number }[];
  commitments_pending: number;
  commitments_completed: number;
  latest_activities: { id: string; title: string; date: string; status: string }[];
  latest_needs: { id: string; title: string; status: string; date: string; category: string }[];
  latest_commitments: { id: string; title: string; status: string; due_date?: string }[];
};
export type PublishedStudies = {
  items: {
    id: string;
    name: string;
    fieldwork_end_date: string;
    sample_size_total: number;
    pollster_name?: string;
    territories?: { parish_id?: number }[];
  }[];
};

export const integer = formatIntegerEsEc;
export const percent = formatPercentEsEc;
export const quality: Record<string, string> = {
  HIGH: 'Alta',
  MEDIUM: 'Media',
  LOW: 'Baja',
  INSUFFICIENT_DATA: 'Datos insuficientes',
};
export const ageKeys = [
  ['0–14', 'AGE_0_14'],
  ['15–29', 'AGE_15_29'],
  ['30–44', 'AGE_30_44'],
  ['45–64', 'AGE_45_64'],
  ['65+', 'AGE_65_PLUS'],
] as const;

export function Card({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
}) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: { xs: 2, md: 3 }, height: '100%', minWidth: 0, overflow: 'hidden' }}
    >
      <Typography variant="h2">{title}</Typography>
      {eyebrow && (
        <Typography variant="overline" color="text.secondary">
          {eyebrow}
        </Typography>
      )}
      <Box sx={{ mt: 2, minWidth: 0, maxWidth: '100%' }}>{children}</Box>
    </Paper>
  );
}
export function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: React.ReactNode;
  detail?: string;
}) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h2" sx={{ overflowWrap: 'anywhere' }}>
        {value}
      </Typography>
      {detail && (
        <Typography variant="body2" color="text.secondary">
          {detail}
        </Typography>
      )}
    </Box>
  );
}
const SIN_DATOS = 'Sin datos disponibles';
export function KpiMetric({ label, value, formatter = integer }: {
  label: string;
  value: number | null | undefined;
  formatter?: (value: number) => string;
}) {
  return <Metric label={label} value={value == null ? SIN_DATOS : formatter(value)} />;
}
export function available(value: boolean) {
  return (
    <Chip
      size="small"
      color={value ? 'success' : 'default'}
      label={value ? 'Disponible' : 'No disponible'}
    />
  );
}
export function delta(from?: number, to?: number) {
  if (from == null || to == null) return { absolute: null, rate: null };
  return { absolute: to - from, rate: from ? (to - from) / from : null };
}
