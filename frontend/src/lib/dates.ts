const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
export function isValidDateOnly(value: string): boolean {
  const match = DATE_ONLY.exec(value);
  if (!match) return false;
  const [, year, month, day] = match;
  const utc = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  return (
    utc.getUTCFullYear() === Number(year) &&
    utc.getUTCMonth() + 1 === Number(month) &&
    utc.getUTCDate() === Number(day)
  );
}
export function formatDateOnly(value?: string | null): string {
  if (!value || !isValidDateOnly(value)) return '—';
  const [year, month, day] = value.split('-');
  return day + '/' + month + '/' + year;
}
export function parseDateOnly(value: string): string | null {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value);
  if (!match) return null;
  const normalized = match[3] + '-' + match[2] + '-' + match[1];
  return isValidDateOnly(normalized) ? normalized : null;
}
export function formatDateRange(from?: string | null, to?: string | null): string {
  if (!from && !to) return 'Sin período';
  return formatDateOnly(from) + ' – ' + formatDateOnly(to);
}
export function todayDateOnly(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Guayaquil',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? '';
  return get('year') + '-' + get('month') + '-' + get('day');
}
