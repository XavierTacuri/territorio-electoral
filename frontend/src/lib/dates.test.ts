import { describe, expect, it } from 'vitest';
import {
  formatDateOnly,
  formatDateRange,
  isValidDateOnly,
  parseDateOnly,
  todayDateOnly,
} from './dates';
describe('fechas funcionales', () => {
  it('formatea sin crear Date desde el string', () =>
    expect(formatDateOnly('2027-02-14')).toBe('14/02/2027'));
  it('rechaza fechas inexistentes', () => expect(isValidDateOnly('2027-02-30')).toBe(false));
  it('parsea formato visible', () => expect(parseDateOnly('14/02/2027')).toBe('2027-02-14'));
  it('formatea rangos', () =>
    expect(formatDateRange('2027-02-01', '2027-02-14')).toBe('01/02/2027 – 14/02/2027'));
  it('usa Guayaquil para hoy', () =>
    expect(todayDateOnly(new Date('2026-08-04T03:30:00Z'))).toBe('2026-08-03'));
});
describe('casos límite date-only', () => {
  it('acepta año bisiesto', () => expect(isValidDateOnly('2024-02-29')).toBe(true));
  it('rechaza febrero imposible', () => expect(isValidDateOnly('2023-02-29')).toBe(false));
  it('rechaza mes cero', () => expect(isValidDateOnly('2026-00-10')).toBe(false));
  it('rechaza día cero', () => expect(isValidDateOnly('2026-08-00')).toBe(false));
  it('no interpreta timestamps', () => expect(isValidDateOnly('2026-08-03T00:00:00Z')).toBe(false));
  it('parsea formato visible sin Date UTC', () =>
    expect(parseDateOnly('14/02/2027')).toBe('2027-02-14'));
});
