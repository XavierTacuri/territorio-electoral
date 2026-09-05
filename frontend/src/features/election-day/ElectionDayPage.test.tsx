import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import ElectionDayPage from './ElectionDayPage';

vi.mock('maplibre-gl', () => ({
  NavigationControl: class {},
  Marker: class {
    setLngLat() {
      return this;
    }
    addTo() {
      return this;
    }
    remove() {}
  },
  Map: class {
    addControl() {}
    fitBounds() {}
    remove() {}
  },
}));

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
let operationStatus: number | 200 = 404;
let operation: any = null;
let coverage: any = null;
let places: any[] = [];
let assignments: any[] = [];
let incidents: any[] = [];
let processes: any[] = [];
let createdBody: any = null;
let lastAction: string | null = null;

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  operationStatus = 404;
  operation = null;
  coverage = null;
  places = [];
  assignments = [];
  incidents = [];
  processes = [];
  createdBody = null;
  lastAction = null;
  auth.user = { ...auth.user, roles: [{ code: 'CANDIDATE', name: 'Candidato' }] };
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers() {
  server.use(
    http.get('*/api/v1/campaigns/campaign-1/election-day/operation', () => {
      if (operationStatus !== 200)
        return HttpResponse.json({ detail: 'not found' }, { status: 404 });
      return HttpResponse.json(operation);
    }),
    http.get('*/api/v1/electoral-processes', () => HttpResponse.json(processes)),
    http.post('*/api/v1/campaigns/campaign-1/election-day/operation', async ({ request }) => {
      createdBody = await request.json();
      return HttpResponse.json({ ...operation, id: 'op1' });
    }),
    http.post('*/api/v1/campaigns/campaign-1/election-day/operation/open', () => {
      lastAction = 'open';
      return HttpResponse.json({ ...operation, status: 'ACTIVE' });
    }),
    http.post('*/api/v1/campaigns/campaign-1/election-day/operation/close', () => {
      lastAction = 'close';
      return HttpResponse.json({ ...operation, status: 'CLOSED' });
    }),
    http.get('*/api/v1/campaigns/campaign-1/election-day/coverage', () =>
      HttpResponse.json(coverage),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/polling-places', () =>
      HttpResponse.json({ items: places }),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/assignments', () =>
      HttpResponse.json({ items: assignments }),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/incidents', () =>
      HttpResponse.json({ items: incidents }),
    ),
  );
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/campaigns/campaign-1/election-day']}>
        <Routes>
          <Route path="/app/campaigns/:campaignId/election-day" element={<ElectionDayPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const cov = {
  total_polling_places: 3,
  covered_polling_places: 2,
  total_boards: 6,
  covered_boards: 4,
  personnel_confirmed: 5,
  personnel_checked_in: 3,
  open_incidents: 1,
  documents_received: 1,
  expected_documents: 3,
};

const place = {
  id: 'place-1',
  electoral_process_id: 'proc-1',
  province_id: 1,
  canton_id: 1,
  parish_id: 1,
  official_code: 'R-001',
  name: 'Escuela Central',
  address: 'Av. Principal',
  latitude: -2.9,
  longitude: -78.8,
  is_active: true,
};

describe('Jornada Electoral — Command Center', () => {
  it('muestra la tarjeta de configuración cuando no existe jornada y el usuario puede gestionar', async () => {
    processes = [{ id: 'proc-1', name: 'Elecciones Seccionales', year: 2027 }];
    handlers();
    renderPage();
    expect(await screen.findByText('Configurar Jornada Electoral')).toBeVisible();
    await userEvent.click(screen.getByLabelText('Proceso electoral'));
    expect(await screen.findByRole('option', { name: /Elecciones Seccionales/ })).toBeVisible();
  });

  it('un usuario sin rol de gestión ve un estado vacío en vez del formulario de creación', async () => {
    auth.user = { ...auth.user, roles: [] };
    handlers();
    renderPage();
    expect(
      await screen.findByText('No hay una jornada configurada para esta campaña.'),
    ).toBeVisible();
    expect(screen.queryByText('Configurar Jornada Electoral')).not.toBeInTheDocument();
  });

  it('crea la jornada al enviar el formulario', async () => {
    processes = [{ id: 'proc-1', name: 'Elecciones Seccionales', year: 2027 }];
    operation = {
      id: 'op1',
      organization_id: 'org1',
      campaign_id: 'campaign-1',
      electoral_process_id: 'proc-1',
      election_date: '2027-03-14',
      status: 'PREPARATION',
      opened_at: null,
      closed_at: null,
      opened_by_user_id: null,
      closed_by_user_id: null,
      notes: null,
    };
    handlers();
    renderPage();
    await screen.findByText('Configurar Jornada Electoral');
    await userEvent.click(screen.getByLabelText('Proceso electoral'));
    await userEvent.click(await screen.findByRole('option', { name: /Elecciones Seccionales/ }));
    const dateInput = screen.getByLabelText('Fecha de la elección');
    await userEvent.type(dateInput, '2027-03-14');
    await userEvent.click(screen.getByRole('button', { name: 'Crear jornada' }));
    await waitFor(() => expect(createdBody).toMatchObject({ electoral_process_id: 'proc-1' }));
  });

  it('muestra KPIs de cobertura, mapa y permite activar la jornada en preparación', async () => {
    operationStatus = 200;
    operation = {
      id: 'op1',
      organization_id: 'org1',
      campaign_id: 'campaign-1',
      electoral_process_id: 'proc-1',
      election_date: '2027-03-14',
      status: 'PREPARATION',
      opened_at: null,
      closed_at: null,
      opened_by_user_id: null,
      closed_by_user_id: null,
      notes: null,
    };
    coverage = cov;
    places = [place];
    assignments = [];
    incidents = [];
    handlers();
    renderPage();
    expect(await screen.findByText('Escuela Central')).toBeVisible();
    expect(screen.getByText('2 / 3')).toBeVisible();
    expect(screen.getByText('4 / 6')).toBeVisible();
    expect(screen.getByText('Preparación')).toBeVisible();
    const activate = screen.getByRole('button', { name: 'Activar jornada' });
    await userEvent.click(activate);
    await waitFor(() => expect(lastAction).toBe('open'));
  });

  it('muestra el diálogo de cierre con el resumen de cobertura y confirma el cierre', async () => {
    operationStatus = 200;
    operation = {
      id: 'op1',
      organization_id: 'org1',
      campaign_id: 'campaign-1',
      electoral_process_id: 'proc-1',
      election_date: '2027-03-14',
      status: 'ACTIVE',
      opened_at: '2027-03-14T10:00:00Z',
      closed_at: null,
      opened_by_user_id: 'u1',
      closed_by_user_id: null,
      notes: null,
    };
    coverage = cov;
    places = [place];
    assignments = [];
    incidents = [
      {
        id: 'inc-1',
        operation_id: 'op1',
        polling_place_id: 'place-1',
        board_id: null,
        reported_by_user_id: 'u1',
        category: 'LOGISTICS',
        description: 'Falta material',
        status: 'OPEN',
        reported_at: '2027-03-14T11:00:00Z',
        resolved_at: null,
        resolution_notes: null,
      },
    ];
    handlers();
    renderPage();
    await screen.findByText('Escuela Central');
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar jornada' }));
    expect(await screen.findByRole('heading', { name: 'Cerrar jornada' })).toBeVisible();
    expect(screen.getByText(/Existen incidencias sin resolver/)).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar cierre' }));
    await waitFor(() => expect(lastAction).toBe('close'));
  });

  it('no ofrece activar ni cerrar la jornada a un usuario sin rol de gestión', async () => {
    auth.user = { ...auth.user, roles: [{ code: 'TERRITORIAL_COORDINATOR', name: 'Coordinador' }] };
    operationStatus = 200;
    operation = {
      id: 'op1',
      organization_id: 'org1',
      campaign_id: 'campaign-1',
      electoral_process_id: 'proc-1',
      election_date: '2027-03-14',
      status: 'PREPARATION',
      opened_at: null,
      closed_at: null,
      opened_by_user_id: null,
      closed_by_user_id: null,
      notes: null,
    };
    coverage = cov;
    places = [place];
    handlers();
    renderPage();
    await screen.findByText('Escuela Central');
    expect(screen.queryByRole('button', { name: 'Activar jornada' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cerrar jornada' })).not.toBeInTheDocument();
  });

  it('muestra estado vacío de recintos cuando no hay ninguno cargado', async () => {
    operationStatus = 200;
    operation = {
      id: 'op1',
      organization_id: 'org1',
      campaign_id: 'campaign-1',
      electoral_process_id: 'proc-1',
      election_date: '2027-03-14',
      status: 'PREPARATION',
      opened_at: null,
      closed_at: null,
      opened_by_user_id: null,
      closed_by_user_id: null,
      notes: null,
    };
    coverage = { ...cov, total_polling_places: 0, covered_polling_places: 0 };
    places = [];
    handlers();
    renderPage();
    expect(
      await screen.findByText('No existen recintos cargados para este proceso.'),
    ).toBeVisible();
  });
});
