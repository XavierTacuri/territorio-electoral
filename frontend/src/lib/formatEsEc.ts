import { formatDateOnly } from './dates';
export const formatIntegerEsEc = (value: number) =>
  new Intl.NumberFormat('es-EC', { maximumFractionDigits: 0 }).format(value);
export const formatDecimalEsEc = (value: number, digits = 2) =>
  value.toLocaleString('es-EC', { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const formatPercentEsEc = (value?: number | null) =>
  value == null ? '—' : `${formatDecimalEsEc(value * 100)} %`;
export const formatDateEsEc = (value?: string | null) => formatDateOnly(value);
