import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ElectoralBoardImportPage from './ElectoralBoardImportPage';

vi.mock('../../api/downloads', () => ({ downloadReport: vi.fn() }));

const auth = vi.hoisted(() => ({
  user: { is_superuser: true, roles: [{ code: 'ADMIN' }] } as any,
}));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ user: auth.user }) }));

const server = setupServer();
const source = {
  id: 'source-board-1',
  institution: 'CNE',
  dataset_name: 'Juntas',
  dataset_type: 'CNE_ELECTORAL_BOARDS',
  is_active: true,
};

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/admin/official-data/election-day/boards']}>
        <Routes>
          <Route
            path="/app/admin/official-data/election-day/boards"
            element={<ElectoralBoardImportPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Importación de juntas receptoras del voto', () => {
  it('advierte que el recinto debe existir primero y solo lista fuentes de juntas', async () => {
    server.use(http.get('*/api/v1/data-sources', () => HttpResponse.json([source])));
    renderPage();
    expect(await screen.findByText(/Los recintos deben importarse primero/)).toBeVisible();
    await userEvent.click(screen.getByLabelText('Fuente'));
    expect(await screen.findByRole('option', { name: /CNE · Juntas/ })).toBeVisible();
  });

  it('muestra las columnas del perfil de juntas y ejecuta la validación', async () => {
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
    );
    renderPage();
    expect(
      await screen.findByText(
        'Columnas: process_code, polling_place_code, board_code, board_number, sex_category, registered_voters',
      ),
    ).toBeVisible();
    await userEvent.click(screen.getByLabelText('Fuente'));
    await userEvent.click(await screen.findByRole('option', { name: /CNE · Juntas/ }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const csv = new File(
      [
        'process_code,polling_place_code,board_code,board_number,sex_category,registered_voters\nSEC_2027,R01,J01,1,MIXED,300\n',
      ],
      'juntas.csv',
      { type: 'text/csv' },
    );
    await userEvent.upload(input, csv);
    await userEvent.click(screen.getByRole('button', { name: 'VALIDAR' }));
    expect(await screen.findByText('VALIDATED')).toBeVisible();
  });
});
