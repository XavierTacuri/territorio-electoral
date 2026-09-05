import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import ElectoralMilestonesPage from './ElectoralMilestonesPage';

const auth = vi.hoisted(() => ({
  user: {
    id: 'admin',
    username: 'admin',
    email: 'admin@example.test',
    first_name: 'Admin',
    last_name: 'Test',
    is_active: true,
    is_superuser: true,
    roles: [{ code: 'ADMIN', name: 'Administrador' }],
  } as any,
}));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ user: auth.user }) }));

const server = setupServer();
const nativeFetch = globalThis.fetch;
let milestones: any[] = [];
let lastCreate: any = null;

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'), init)) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  milestones = [];
  lastCreate = null;
  auth.user = { ...auth.user, is_superuser: true, roles: [{ code: 'ADMIN', name: 'Administrador' }] };
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers() {
  server.use(
    http.get('*/api/v1/electoral-milestones', () => HttpResponse.json(milestones)),
    http.get('*/api/v1/electoral-processes', () =>
      HttpResponse.json([{ id: 'p1', code: 'SEC_2027', name: 'Seccionales 2027' }]),
    ),
    http.get('*/api/v1/data-sources', () =>
      HttpResponse.json([
        { id: 's1', code: 'CNE', institution: 'Consejo Nacional Electoral', dataset_name: 'Calendario', dataset_type: 'OTHER_AGGREGATED_OFFICIAL', is_active: true },
      ]),
    ),
    http.post('*/api/v1/electoral-milestones', async ({ request }) => {
      lastCreate = await request.json();
      return HttpResponse.json({ id: 'm1', ...lastCreate, status: 'ACTIVE' }, { status: 201 });
    }),
  );
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/admin/electoral-milestones']}>
        <Routes>
          <Route path="/app/admin/electoral-milestones" element={<ElectoralMilestonesPage />} />
          <Route path="/403" element={<div>Acceso denegado</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Calendario electoral oficial (admin)', () => {
  it('muestra estado vacío y crea un hito sintético', async () => {
    handlers();
    renderPage();
    expect(await screen.findByText('No hay hitos electorales registrados.')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Nuevo hito' }));
    await userEvent.click(screen.getByLabelText('Proceso electoral'));
    await userEvent.click(await screen.findByRole('option', { name: /Seccionales 2027/ }));
    await userEvent.type(screen.getByLabelText('Título'), 'Convocatoria sintética');
    const dateField = screen.getByLabelText('Fecha y hora');
    await userEvent.type(dateField, '2027-01-05T09:00');
    await userEvent.click(screen.getByLabelText('Fuente oficial'));
    await userEvent.click(await screen.findByRole('option', { name: /Consejo Nacional Electoral/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Crear hito' }));
    await waitFor(() =>
      expect(lastCreate).toMatchObject({ title: 'Convocatoria sintética', electoral_process_id: 'p1', source_id: 's1' }),
    );
  });

  it('rechaza el acceso a roles sin administración global', async () => {
    auth.user = { ...auth.user, is_superuser: false, roles: [{ code: 'ANALYST', name: 'Analista' }] };
    handlers();
    renderPage();
    expect(await screen.findByText('Acceso denegado')).toBeVisible();
  });
});
