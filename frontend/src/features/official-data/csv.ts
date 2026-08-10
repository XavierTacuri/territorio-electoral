import type { CneDataset, CsvInspection } from './types';

export const INEC_INDICATOR_HEADERS = [
  'indicator_code',
  'name',
  'description',
  'category',
  'unit',
  'value_type',
] as const;
export const INEC_OBSERVATION_HEADERS = [
  'indicator_code',
  'reference_year',
  'geography_level',
  'province_dpa',
  'canton_dpa',
  'parish_dpa',
  'value',
  'numerator',
  'denominator',
] as const;
export type InecRow = Record<string, string>;
export type InecInspection = {
  headers: string[];
  rows: InecRow[];
  missingHeaders: string[];
  duplicateKeys: string[];
  indicatorCodes: string[];
  territoryCodes: string[];
  years: number[];
  errors: string[];
  warnings: string[];
};

function parseCsvForInec(text: string): { headers: string[]; rows: InecRow[] } {
  const normalized = text.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
  const lines = normalized.split('\n').filter((line) => line.trim());
  const delimiter =
    (lines[0]?.match(/;/g)?.length ?? 0) > (lines[0]?.match(/,/g)?.length ?? 0) ? ';' : ',';
  const parse = (line: string) => {
    const values: string[] = [];
    let value = '';
    let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      if (ch === '"') {
        if (quoted && line[i + 1] === '"') {
          value += '"';
          i += 1;
        } else quoted = !quoted;
      } else if (ch === delimiter && !quoted) {
        values.push(value.trim());
        value = '';
      } else value += ch;
    }
    values.push(value.trim());
    return values;
  };
  const headers = parse(lines[0] ?? '').map((header) => header.trim().toLowerCase());
  const rows = lines.slice(1).map((line) => {
    const values = parse(line);
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? '']));
  });
  return { headers, rows };
}

export function inspectInecCsv(
  text: string,
  kind: 'indicator' | 'observation',
  indicatorUnits: Record<string, string> = {},
): InecInspection {
  const { headers, rows } = parseCsvForInec(text);
  const required = kind === 'indicator' ? INEC_INDICATOR_HEADERS : INEC_OBSERVATION_HEADERS;
  const missingHeaders = required.filter((header) => !headers.includes(header));
  const errors: string[] = [];
  const warnings: string[] = [];
  const duplicateKeys: string[] = [];
  const seen = new Set<string>();
  const indicatorCodes = [...new Set(rows.map((row) => row.indicator_code).filter(Boolean))];
  rows.forEach((row, index) => {
    const rowNumber = index + 2;
    if (kind === 'observation') {
      const level = row.geography_level?.toUpperCase();
      const year = Number(row.reference_year);
      if (!row.indicator_code) errors.push(`Fila ${rowNumber}: indicator_code vacío.`);
      if (!Number.isInteger(year) || year < 1900 || year > 2200)
        errors.push(`Fila ${rowNumber}: año inválido.`);
      if (!['PROVINCE', 'CANTON', 'PARISH'].includes(level))
        errors.push(`Fila ${rowNumber}: geography_level inválido.`);
      if (!row.value || !Number.isFinite(Number(row.value)))
        errors.push(`Fila ${rowNumber}: valor inválido.`);
      if (
        row.denominator &&
        (!(Number(row.denominator) > 0) || !Number.isFinite(Number(row.denominator)))
      )
        errors.push(`Fila ${rowNumber}: denominador inválido.`);
      const unit = indicatorUnits[row.indicator_code?.toUpperCase()]?.toUpperCase();
      const code = row.indicator_code?.toUpperCase();
      if (
        Number.isFinite(Number(row.value)) &&
        Number(row.value) < 0 &&
        unit &&
        (unit !== 'RATE' || code === 'POP_DENSITY_KM2')
      )
        errors.push(`Fila ${rowNumber}: valor negativo no permitido.`);
      if (level === 'PARISH' && (!row.province_dpa || !row.canton_dpa || !row.parish_dpa))
        errors.push(`Fila ${rowNumber}: DPA incompleto.`);
      if (
        level === 'PARISH' &&
        (!/^\d{2}$/.test(row.province_dpa) ||
          !/^\d{4}$/.test(row.canton_dpa) ||
          !/^\d{6}$/.test(row.parish_dpa))
      )
        errors.push(`Fila ${rowNumber}: DPA debe conservar ceros iniciales.`);
      const key = [
        row.indicator_code,
        year,
        level,
        row.province_dpa,
        row.canton_dpa,
        row.parish_dpa,
      ].join('|');
      if (seen.has(key)) duplicateKeys.push(key);
      else seen.add(key);
    }
  });
  if (kind === 'observation') {
    const grouped = new Map<string, Record<string, number>>();
    rows.forEach((row) => {
      const key = [
        row.geography_level,
        row.province_dpa,
        row.canton_dpa,
        row.parish_dpa,
        row.reference_year,
      ].join('|');
      const values = grouped.get(key) ?? {};
      values[row.indicator_code] = Number(row.value);
      grouped.set(key, values);
    });
    grouped.forEach((values, key) => {
      if (
        values.POP_TOTAL !== undefined &&
        values.POP_MALE !== undefined &&
        values.POP_FEMALE !== undefined &&
        values.POP_TOTAL !== values.POP_MALE + values.POP_FEMALE
      )
        warnings.push(`Consistencia CPV: POP_TOTAL difiere de POP_MALE + POP_FEMALE en ${key}.`);
      const ages = Object.entries(values)
        .filter(([code]) => code.startsWith('POP_AGE_'))
        .reduce((sum, [, value]) => sum + value, 0);
      if (
        values.POP_TOTAL !== undefined &&
        Object.keys(values).some((code) => code.startsWith('POP_AGE_')) &&
        values.POP_TOTAL !== ages
      )
        warnings.push(`Consistencia CPV: POP_TOTAL difiere de la suma de edades en ${key}.`);
    });
  }
  return {
    headers,
    rows,
    missingHeaders,
    duplicateKeys,
    indicatorCodes,
    territoryCodes: [
      ...new Set(
        rows.map((row) => row.parish_dpa || row.canton_dpa || row.province_dpa).filter(Boolean),
      ),
    ],
    years: [
      ...new Set(
        rows.map((row) => Number(row.reference_year)).filter((year) => Number.isInteger(year)),
      ),
    ].sort(),
    errors,
    warnings,
  };
}

export const CNE_HEADERS: Record<CneDataset, readonly string[]> = {
  CNE_POLITICAL_ORGANIZATIONS: [
    'organization_code',
    'name',
    'short_name',
    'organization_type',
    'list_number',
    'scope',
  ],
  CNE_TURNOUT: [
    'process_code',
    'contest_code',
    'geography_level',
    'geography_code',
    'province_dpa',
    'canton_dpa',
    'parish_dpa',
    'zone_code',
    'precinct_code',
    'jrv_code',
    'registered_voters',
    'ballots_cast',
    'valid_votes',
    'blank_votes',
    'null_votes',
    'other_votes',
    'is_final',
  ],
  CNE_CANDIDATES: [
    'process_code',
    'office_type',
    'contest_code',
    'candidate_code',
    'full_name',
    'organization_code',
    'list_number',
    'ballot_order',
  ],
  CNE_ELECTORAL_RESULTS: [
    'process_code',
    'contest_code',
    'geography_level',
    'geography_code',
    'candidate_code',
    'votes',
    'is_final',
  ],
};

function parseLine(line: string, delimiter: ',' | ';'): string[] {
  const values: string[] = [];
  let value = '';
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"') {
      if (quoted && line[index + 1] === '"') {
        value += '"';
        index += 1;
      } else quoted = !quoted;
    } else if (character === delimiter && !quoted) {
      values.push(value.trim());
      value = '';
    } else value += character;
  }
  values.push(value.trim());
  return values;
}

const unique = (rows: Record<string, string>[], field: string) => [
  ...new Set(rows.map((row) => row[field]).filter(Boolean)),
];

export function inspectCsvText(text: string, dataset: CneDataset): CsvInspection {
  const normalized = text.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
  const lines = normalized.split('\n').filter((line) => line.trim());
  const sample = lines[0] ?? '';
  const delimiter: ',' | ';' =
    (sample.match(/;/g)?.length ?? 0) > (sample.match(/,/g)?.length ?? 0) ? ';' : ',';
  const headers = parseLine(sample, delimiter).map((header) => header.trim());
  const rows = lines.slice(1).map((line) => {
    const values = parseLine(line, delimiter);
    return Object.fromEntries(
      headers.map((header, index) => [header, values[index]?.trim() ?? '']),
    );
  });
  const missingHeaders = CNE_HEADERS[dataset].filter((header) => !headers.includes(header));
  return {
    headers,
    rows,
    delimiter,
    missingHeaders,
    processCodes: unique(rows, 'process_code'),
    contestCodes: unique(rows, 'contest_code'),
    candidateCodes: unique(rows, 'candidate_code'),
    organizationCodes: unique(rows, 'organization_code'),
    geographyCodes: unique(rows, 'geography_code'),
    usesOrganizations: rows.some((row) => !!row.organization_code),
  };
}

export function wizardConsistencyErrors(
  inspection: CsvInspection,
  processCode: string,
  contestCode: string,
): string[] {
  const errors: string[] = [];
  if (inspection.processCodes.some((code) => code.toUpperCase() !== processCode.toUpperCase()))
    errors.push(`El archivo contiene un process_code distinto de ${processCode}.`);
  if (inspection.contestCodes.some((code) => code !== contestCode))
    errors.push(`El archivo contiene un contest_code distinto de ${contestCode}.`);
  return errors;
}

export function resultDependencyErrors(
  inspection: CsvInspection,
  candidateCodes: Set<string>,
  geographyCodes: Set<string>,
): string[] {
  const errors: string[] = [];
  inspection.candidateCodes.forEach((code) => {
    if (!candidateCodes.has(code)) errors.push(`El candidato ${code} no está registrado.`);
  });
  inspection.geographyCodes.forEach((code) => {
    if (!geographyCodes.has(code))
      errors.push(`El código territorial ${code} no tiene una geografía electoral mapeada.`);
  });
  return errors;
}

export function normalizedTechnicalCode(...parts: string[]) {
  return parts
    .join('_')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}
