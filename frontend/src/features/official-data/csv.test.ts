import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  CNE_HEADERS,
  inspectInecCsv,
  INEC_OBSERVATION_HEADERS,
  inspectCsvText,
  normalizedTechnicalCode,
  resultDependencyErrors,
  wizardConsistencyErrors,
} from './csv';
import { runOfficialImport } from './importApi';

describe('contratos CSV del asistente oficial', () => {
  it('inspecciona cabeceras y metadatos sin modificar el archivo', () => {
    const csv = `${CNE_HEADERS.CNE_CANDIDATES.join(',')}\nSEC_2023,MAYOR,MAYOR_GUALACEO,C1,Persona,ORG1,10,1\n`;
    const result = inspectCsvText(csv, 'CNE_CANDIDATES');
    expect(result.missingHeaders).toEqual([]);
    expect(result.processCodes).toEqual(['SEC_2023']);
    expect(result.contestCodes).toEqual(['MAYOR_GUALACEO']);
    expect(result.candidateCodes).toEqual(['C1']);
    expect(result.usesOrganizations).toBe(true);
  });

  it('detecta cabeceras faltantes y CSV con punto y coma', () => {
    const result = inspectCsvText('candidate_code;full_name\nC1;Persona', 'CNE_CANDIDATES');
    expect(result.delimiter).toBe(';');
    expect(result.missingHeaders).toContain('process_code');
  });

  it('comprueba proceso, contienda, candidatos y geografías', () => {
    const inspection = inspectCsvText(
      `${CNE_HEADERS.CNE_ELECTORAL_RESULTS.join(',')}\nOTRO,OTRA,PARISH,010350,C2,20,1`,
      'CNE_ELECTORAL_RESULTS',
    );
    expect(wizardConsistencyErrors(inspection, 'SEC_2023', 'MAYOR_GUALACEO')).toHaveLength(2);
    expect(resultDependencyErrors(inspection, new Set(['C1']), new Set())).toEqual([
      'El candidato C2 no está registrado.',
      'El código territorial 010350 no tiene una geografía electoral mapeada.',
    ]);
  });

  it('genera contest_code normalizado y editable', () => {
    expect(normalizedTechnicalCode('MAYOR', 'Gualaceo')).toBe('MAYOR_GUALACEO');
    expect(normalizedTechnicalCode('PARISH_BOARD', 'Simón Bolívar')).toBe(
      'PARISH_BOARD_SIMON_BOLIVAR',
    );
  });

  it('el perfil automático nunca envía DEFAULT ni mapping_profile', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'job-1',
          status: 'VALIDATED',
          rows_read: 1,
          rows_valid: 1,
          rows_inserted: 0,
          rows_updated: 0,
          rows_failed: 0,
          errors: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);
    await runOfficialImport(
      'validate',
      'source-1',
      'CNE_ELECTORAL_RESULTS',
      new File(['x'], 'resultados.csv', { type: 'text/csv' }),
    );
    const body = fetchMock.mock.calls[0][1]?.body as FormData;
    expect(body.get('dataset_type')).toBe('CNE_ELECTORAL_RESULTS');
    expect(body.has('mapping_profile')).toBe(false);
    expect([...body.values()]).not.toContain('DEFAULT');
  });

  it('valida observaciones, conserva DPA, detecta años y duplicados', () => {
    const csv = `${INEC_OBSERVATION_HEADERS.join(',')}\nPOP_TOTAL,2010,PARISH,01,0103,010350,100,,\nPOP_TOTAL,2022,PARISH,01,0103,010350,22019,,\nPOP_TOTAL,2022,PARISH,01,0103,010350,22019,,\n`;
    const result = inspectInecCsv(csv, 'observation');
    expect(result.missingHeaders).toEqual([]);
    expect(result.territoryCodes).toEqual(['010350']);
    expect(result.years).toEqual([2010, 2022]);
    expect(result.duplicateKeys).toHaveLength(1);
    expect(result.rows[0].province_dpa).toBe('01');
    expect(result.rows[0].parish_dpa).toBe('010350');
  });

  it('envía exactamente CANONICAL_DEMOGRAPHIC_OBSERVATION', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ status: 'VALIDATED', errors: [] }), { status: 200 }),
      );
    vi.stubGlobal('fetch', fetchMock);
    await runOfficialImport(
      'validate',
      'source-1',
      'INEC_DEMOGRAPHIC_INDICATORS',
      new File(['x'], 'obs.csv'),
      false,
      'CANONICAL_DEMOGRAPHIC_OBSERVATION',
    );
    const body = fetchMock.mock.calls[0][1]?.body as FormData;
    expect(body.get('mapping_profile')).toBe('CANONICAL_DEMOGRAPHIC_OBSERVATION');
    expect([...body.values()]).not.toContain('DEFAULT');
  });

  afterEach(() => vi.unstubAllGlobals());
});
