import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CneFileStep } from './CneFileStep';
import { CNE_HEADERS } from './csv';

const runMock = vi.hoisted(() => vi.fn());
vi.mock('./importApi', () => ({ runOfficialImport: runMock }));

const validated = {
  id: 'job-1',
  status: 'VALIDATED',
  rows_read: 1,
  rows_valid: 1,
  rows_inserted: 0,
  rows_updated: 0,
  rows_failed: 0,
  errors: [],
};

function csvFile(dataset: keyof typeof CNE_HEADERS, row: string) {
  const text = `${CNE_HEADERS[dataset].join(',')}\n${row}\n`;
  const file = new File([text], 'official.csv', { type: 'text/csv' });
  Object.defineProperty(file, 'text', { value: () => Promise.resolve(text) });
  return file;
}

function renderStep(
  dataset: keyof typeof CNE_HEADERS = 'CNE_ELECTORAL_RESULTS',
  additionalErrors: string[] = [],
) {
  return render(
    <CneFileStep
      step={7}
      dataset={dataset}
      sourceId="source-1"
      processCode="SEC_2023"
      contestCode="MAYOR_GUALACEO"
      locked={false}
      complete={false}
      additionalErrors={additionalErrors}
      onInspection={() => undefined}
      onExecuted={() => undefined}
    />,
  );
}

beforeEach(() => {
  runMock.mockReset();
  runMock.mockResolvedValue(validated);
});

describe('paso de archivo CNE', () => {
  it('valida y ejecuta solamente después de una validación correcta', async () => {
    renderStep();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(
      input,
      csvFile('CNE_ELECTORAL_RESULTS', 'SEC_2023,MAYOR_GUALACEO,PARISH,010350,C1,20,1'),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Validar' }));
    await waitFor(() =>
      expect(runMock).toHaveBeenCalledWith(
        'validate',
        'source-1',
        'CNE_ELECTORAL_RESULTS',
        expect.any(File),
        false,
      ),
    );
    runMock.mockResolvedValue({ ...validated, status: 'COMPLETED', rows_inserted: 1 });
    await userEvent.click(screen.getByRole('button', { name: 'Ejecutar' }));
    await waitFor(() =>
      expect(runMock).toHaveBeenLastCalledWith(
        'execute',
        'source-1',
        'CNE_ELECTORAL_RESULTS',
        expect.any(File),
        false,
      ),
    );
  });

  it('muestra errores del backend sin ejecutar', async () => {
    runMock.mockRejectedValue(new Error('El candidato C2 no está registrado.'));
    renderStep();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(
      input,
      csvFile('CNE_ELECTORAL_RESULTS', 'SEC_2023,MAYOR_GUALACEO,PARISH,010350,C2,20,1'),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Validar' }));
    expect(await screen.findByText('El candidato C2 no está registrado.')).toBeVisible();
    expect(runMock).toHaveBeenCalledTimes(1);
  });

  it('solicita confirmación antes de forzar un checksum ya importado', async () => {
    renderStep();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(
      input,
      csvFile('CNE_ELECTORAL_RESULTS', 'SEC_2023,MAYOR_GUALACEO,PARISH,010350,C1,20,1'),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Validar' }));
    await screen.findByText(/Estado: VALIDATED/);
    await userEvent.click(screen.getByLabelText('Forzar actualización'));
    await userEvent.click(screen.getByRole('button', { name: 'Ejecutar' }));
    expect(screen.getByRole('dialog', { name: 'Forzar actualización' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    await waitFor(() =>
      expect(runMock).toHaveBeenLastCalledWith(
        'execute',
        'source-1',
        'CNE_ELECTORAL_RESULTS',
        expect.any(File),
        true,
      ),
    );
  });

  it('bloquea turnout si faltan electores registrados', async () => {
    renderStep('CNE_TURNOUT');
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(
      input,
      csvFile(
        'CNE_TURNOUT',
        'SEC_2023,MAYOR_GUALACEO,PARISH,010350,01,0103,010350,,,,,80,70,5,5,0,1',
      ),
    );
    expect(await screen.findByText(/El archivo no contiene electores registrados/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Validar' })).toBeDisabled();
  });

  it('bloquea resultados con dependencias faltantes', async () => {
    renderStep('CNE_ELECTORAL_RESULTS', ['El candidato C2 no está registrado.']);
    expect(screen.getByText('El candidato C2 no está registrado.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Validar' })).toBeDisabled();
  });
});
