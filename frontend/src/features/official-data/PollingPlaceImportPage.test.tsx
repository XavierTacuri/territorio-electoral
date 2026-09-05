import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import PollingPlaceImportPage from './PollingPlaceImportPage';

vi.mock('../../api/downloads', () => ({ downloadReport: vi.fn() }));

const auth = vi.hoisted(() => ({
  user: { is_superuser: true, roles: [{ code: 'ADMIN' }] } as any,
}));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ user: auth.user }) }));

const server = setupServer();
const source = {
  id: 'source-pp-1',
  institution: 'CNE',
  dataset_name: 'Recintos',
  dataset_type: 'CNE_POLLING_PLACES',
  is_active: true,
};
const csv = new File(
  [
    'process_code,province_dpa,canton_dpa,parish_dpa,polling_place_code,polling_place_name,polling_place_address,polling_place_latitude,polling_place_longitude\nSEC_2027,01,0103,010350,R01,Escuela Central,Av. Principal,-2.9,-78.8\n',
  ],
  'recintos.csv',
  { type: 'text/csv' },
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/admin/official-data/election-day/polling-places']}>
        <Routes>
          <Route
            path="/app/admin/official-data/election-day/polling-places"
            element={<PollingPlaceImportPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Importación de recintos electorales', () => {
  it('advierte cuando no existe una fuente activa del tipo correcto', async () => {
    server.use(http.get('*/api/v1/data-sources', () => HttpResponse.json([])));
    renderPage();
    expect(
      await screen.findByText(/No existe una fuente activa de este tipo/),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'VALIDAR' })).toBeDisabled();
  });

  it('valida, ejecuta y muestra el resultado', async () => {
    server.use(
      http.get('*/api/v1/data-sources', () => HttpResponse.json([source])),
      http.post('*/api/v1/data-imports/validate', () =>
        HttpResponse.json({
          status: 'VALIDATED',
          rows_read: 1,
          rows_valid: 1,
          rows_failed: 0,
          errors: [],
        }),
      ),
      http.post('*/api/v1/data-imports/execute', () =>
        HttpResponse.json({
          status: 'COMPLETED',
          rows_read: 1,
          rows_valid: 1,
          rows_failed: 0,
          errors: [],
        }),
      ),
    );
    renderPage();
    await userEvent.click(await screen.findByLabelText('Fuente'));
    await userEvent.click(await screen.findByRole('option', { name: /CNE · Recintos/ }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, csv);
    await userEvent.click(screen.getByRole('button', { name: 'VALIDAR' }));
    expect(await screen.findByText('VALIDATED')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'EJECUTAR' }));
    expect(await screen.findByText('Recintos importados correctamente.')).toBeVisible();
  });

  it('muestra errores de validación agrupados sin exponer detalles técnicos', async () => {
    server.use(
      http.get('*/api/v1/data-sources', () => HttpResponse.json([source])),
      http.post('*/api/v1/data-imports/validate', () =>
        HttpResponse.json({
          status: 'REJECTED',
          rows_read: 2,
          rows_valid: 0,
          rows_failed: 2,
          errors: [
            { row_number: 2, error_code: 'INVALID_ROW', message: 'La parroquia no pertenece al cantón indicado' },
            { row_number: 3, error_code: 'INVALID_ROW', message: 'La parroquia no pertenece al cantón indicado' },
          ],
        }),
      ),
    );
    renderPage();
    await userEvent.click(await screen.findByLabelText('Fuente'));
    await userEvent.click(await screen.findByRole('option', { name: /CNE · Recintos/ }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, csv);
    await userEvent.click(screen.getByRole('button', { name: 'VALIDAR' }));
    expect(
      await screen.findByText(/La parroquia no pertenece al cantón indicado.*2 filas afectadas/),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'EJECUTAR' })).toBeDisabled();
  });

  it('descarga la plantilla CSV del perfil', async () => {
    const { downloadReport } = await import('../../api/downloads');
    server.use(http.get('*/api/v1/data-sources', () => HttpResponse.json([source])));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'DESCARGAR PLANTILLA' }));
    await waitFor(() =>
      expect(downloadReport).toHaveBeenCalledWith(
        '/data-import-profiles/CNE_POLLING_PLACES/template',
        'plantilla_cne_polling_places.csv',
      ),
    );
  });
});
