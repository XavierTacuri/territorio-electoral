import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import AlertsPage from './AlertsPage';

const auth = vi.hoisted(() => ({
  user: {
    id: 'u1',
    username: 'candidate',
    email: 'candidate@example.test',
    first_name: 'Candidata',
    last_name: 'Test',
    is_active: true,
    is_superuser: false,
    roles: [{ code: 'CANDIDATE', name: 'Candidato' }],
  } as any,
}));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ user: auth.user }) }));

const server = setupServer();
const nativeFetch = globalThis.fetch;
let items: any[] = [];
let total = 0;
let lastAction: { url: string; body: any } | null = null;
let lastPageRequested: string | null = null;

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  items = [];
  total = 0;
  lastAction = null;
  lastPageRequested = null;
  auth.user = { ...auth.user, roles: [{ code: 'CANDIDATE', name: 'Candidato' }] };
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers() {
  server.use(
    http.get('*/api/v1/campaigns/campaign-1/alerts', ({ request }) => {
      lastPageRequested = new URL(request.url).searchParams.get('page');
      return HttpResponse.json({
        items,
        page: Number(lastPageRequested) || 1,
        page_size: 50,
        total: total || items.length,
      });
    }),
    http.post('*/api/v1/campaigns/campaign-1/alerts/:id/:action', async ({ request, params }) => {
      lastAction = { url: `${params.action}`, body: await request.json() };
      return HttpResponse.json({ ...items[0], status: 'ACKNOWLEDGED' });
    }),
  );
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/campaigns/campaign-1/alerts']}>
        <Routes>
          <Route path="/app/campaigns/:campaignId/alerts" element={<AlertsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const alert = {
  id: 'al1',
  title: 'Actividad pendiente de aprobación',
  severity: 'WARNING',
  status: 'OPEN',
  module: 'OPERATIONS',
  detected_date: '2026-08-30',
  message: 'Asamblea Jadán requiere revisión',
};

describe('Centro de alertas', () => {
  it('muestra estado vacío cuando no hay alertas', async () => {
    handlers();
    renderPage();
    expect(await screen.findByText('No hay alertas que requieran atención.')).toBeVisible();
  });

  it('muestra severidad y estado en español, no los códigos crudos', async () => {
    items = [alert];
    handlers();
    renderPage();
    expect(await screen.findByText('Actividad pendiente de aprobación')).toBeVisible();
    expect(screen.getByText('Requiere atención')).toBeVisible();
    expect(screen.getByText('Pendiente')).toBeVisible();
    expect(screen.getByText('Operación')).toBeVisible();
    expect(screen.queryByText('WARNING')).not.toBeInTheDocument();
    expect(screen.queryByText('OPEN')).not.toBeInTheDocument();
  });

  it('permite a un rol ejecutivo reconocer una alerta', async () => {
    items = [alert];
    handlers();
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Gestionar' }));
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    await waitFor(() => expect(lastAction?.url).toBe('acknowledge'));
  });

  it('muestra la comparación de encuestas y el enlace a Ver comparación', async () => {
    items = [
      {
        id: 'al2',
        title: 'Nueva medición comparable disponible',
        severity: 'INFO',
        status: 'OPEN',
        module: 'SURVEYS',
        detected_date: '2026-08-30',
        message: 'Existe una nueva medición comparable disponible para esta pregunta.',
        rule_code: 'SURVEY_COMPARISON_CHANGE',
        evidence: {
          previous_study_id: 'study-1',
          new_study_id: 'study-2',
          comparable_result: true,
          option_label: 'Candidato A',
          previous_percentage: 0.284,
          new_percentage: 0.311,
          difference_points: 2.7,
        },
      },
    ];
    handlers();
    renderPage();
    expect(await screen.findByText('Nueva medición comparable disponible')).toBeVisible();
    expect(screen.getByText(/28,4 % → 31,1 %/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Ver comparación' })).toHaveAttribute(
      'href',
      '/app/campaigns/campaign-1/survey-studies/compare?ids=study-1,study-2',
    );
  });

  it('muestra paginación cuando hay más de una página y solicita la página siguiente', async () => {
    items = [alert];
    total = 120; // > page_size (50): debe existir más de una página.
    handlers();
    renderPage();
    await screen.findByText('Actividad pendiente de aprobación');
    expect(screen.getByLabelText('Paginación de alertas')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Go to page 2' }));
    await waitFor(() => expect(lastPageRequested).toBe('2'));
  });

  it('no muestra el control de paginación cuando cabe todo en una página', async () => {
    items = [alert];
    total = 1;
    handlers();
    renderPage();
    await screen.findByText('Actividad pendiente de aprobación');
    expect(screen.queryByLabelText('Paginación de alertas')).not.toBeInTheDocument();
  });

  it('un usuario sin rol de gestión ve la alerta en solo lectura', async () => {
    auth.user = { ...auth.user, roles: [] };
    items = [alert];
    handlers();
    renderPage();
    await screen.findByText('Actividad pendiente de aprobación');
    expect(screen.getByText('Solo lectura')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Gestionar' })).not.toBeInTheDocument();
  });
});
