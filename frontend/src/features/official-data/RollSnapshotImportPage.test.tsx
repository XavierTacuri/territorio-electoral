import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import RollSnapshotImportPage from './RollSnapshotImportPage';

const auth = vi.hoisted(() => ({
  user: { is_superuser: true, roles: [{ code: 'ADMIN' }] } as any,
}));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ user: auth.user }) }));
const server = setupServer();
const source = {
  id: 'source-1',
  institution: 'CNE',
  dataset_name: 'Registro',
  dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT',
  is_active: true,
};
const csv = new File(
  [
    'snapshot_date,process_code,geography_level,province_dpa,canton_dpa,parish_dpa,registered_voters,male_voters,female_voters,electoral_zones,juntas\n2027-06-01,SEC_2027,PARISH,01,0103,010350,100,40,60,1,2\n',
  ],
  'fixture.csv',
  { type: 'text/csv' },
);
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/admin/official-data/cne/roll']}>
        <Routes>
          <Route path="/app/admin/official-data/cne/roll" element={<RollSnapshotImportPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
describe('flujo real de snapshot electoral', () => {
  it('detecta proceso inexistente, permite crearlo y habilita revalidación', async () => {
    let processes: any[] = [];
    server.use(
      http.get('*/api/v1/data-sources', () => HttpResponse.json([source])),
      http.get('*/api/v1/electoral-processes', () => HttpResponse.json(processes)),
      http.post('*/api/v1/electoral-processes', async ({ request }) => {
        const body = (await request.json()) as any;
        const created = {
          id: 'process-2027',
          ...body,
          election_date: body.election_date,
          year: body.year,
          is_active: true,
        };
        processes = [created];
        return HttpResponse.json(created, { status: 201 });
      }),
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
    await userEvent.click(await screen.findByLabelText('Fuente CNE'));
    await userEvent.click(await screen.findByRole('option', { name: /CNE · Registro/ }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, csv);
    expect(await screen.findByText(/Proceso detectado/)).toBeVisible();
    expect(screen.getByText('SEC_2027')).toBeVisible();
    expect(
      screen.getByText('Este archivo requiere un proceso electoral que todavía no existe.'),
    ).toBeVisible();
    expect(
      screen.getAllByRole('button', { name: 'CREAR PROCESO ELECTORAL' }).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'VALIDAR SNAPSHOT' })).toBeDisabled();
  });
});
