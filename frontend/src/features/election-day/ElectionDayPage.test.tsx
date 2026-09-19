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
let actsCoverage: any = {
  expected_boards: 0,
  received: 0,
  validated: 0,
  in_review: 0,
  observed: 0,
  pending: 0,
};
let places: any[] = [];
let assignments: any[] = [];
let incidents: any[] = [];
let processes: any[] = [];
let createdBody: any = null;
let lastAction: string | null = null;
let preflight: any = {
  ready: true,
  blockers: [],
  warnings: [],
  summary: {
    polling_places: 1,
    boards: 1,
    delegates: 1,
    validators: 1,
    uncovered_polling_places: 0,
  },
};

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
  actsCoverage = {
    expected_boards: 0,
    received: 0,
    validated: 0,
    in_review: 0,
    observed: 0,
    pending: 0,
  };
  places = [];
  assignments = [];
  incidents = [];
  processes = [];
  createdBody = null;
  lastAction = null;
  preflight = {
    ready: true,
    blockers: [],
    warnings: [],
    summary: {
      polling_places: 1,
      boards: 1,
      delegates: 1,
      validators: 1,
      uncovered_polling_places: 0,
    },
  };
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
    http.get('*/api/v1/campaigns/campaign-1/election-day/operation/preflight', () =>
      HttpResponse.json(preflight),
    ),
    http.post('*/api/v1/campaigns/campaign-1/election-day/operation/open', () => {
      lastAction = 'open';
      return HttpResponse.json({ ...operation, status: 'ACTIVE' });
    }),
    http.post('*/api/v1/campaigns/campaign-1/election-day/operation/start-scrutiny', () => {
      lastAction = 'start-scrutiny';
      return HttpResponse.json({ ...operation, status: 'SCRUTINY' });
    }),
    http.post('*/api/v1/campaigns/campaign-1/election-day/operation/close', () => {
      lastAction = 'close';
      return HttpResponse.json({ ...operation, status: 'CLOSED' });
    }),
    http.get('*/api/v1/campaigns/campaign-1/election-day/coverage', () =>
      HttpResponse.json(coverage),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/acts/coverage', () =>
      HttpResponse.json(actsCoverage),
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
    http.get('*/api/v1/campaigns/campaign-1/election-day/staff/invitations', () =>
      HttpResponse.json({ items: [], total: 0 }),
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
  it('con un único proceso válido para la campaña, lo muestra bloqueado en vez de un selector libre', async () => {
    processes = [
      { id: 'proc-1', name: 'Elecciones Seccionales 2027', election_date: '2027-02-14' },
    ];
    handlers();
    renderPage();
    expect(await screen.findByText('Configurar Jornada Electoral')).toBeVisible();
    const field = (await screen.findByLabelText('Proceso electoral')) as HTMLInputElement;
    expect(field).toBeDisabled();
    expect(field).toHaveValue('Elecciones Seccionales 2027');
    expect(screen.getByText('Fecha de elección: 14/02/2027')).toBeVisible();
    // No selector to open: the field is a locked TextField, not a dropdown.
    expect(screen.queryByRole('option')).not.toBeInTheDocument();
  });

  it('con varios procesos válidos, ofrece un selector restringido a esos procesos', async () => {
    processes = [
      { id: 'proc-1', name: 'Elecciones Seccionales 2023', election_date: '2023-02-05' },
      { id: 'proc-2', name: 'Elecciones Seccionales 2027', election_date: '2027-02-14' },
    ];
    handlers();
    renderPage();
    await screen.findByText('Configurar Jornada Electoral');
    const field = await screen.findByLabelText('Proceso electoral');
    expect(field).not.toBeDisabled();
    await userEvent.click(field);
    expect(
      await screen.findByRole('option', { name: /Elecciones Seccionales 2023/ }),
    ).toBeVisible();
    expect(screen.getByRole('option', { name: /Elecciones Seccionales 2027/ })).toBeVisible();
  });

  it('sin ningún proceso válido para el cantón/cargo de la campaña, explica por qué no puede configurarse', async () => {
    processes = [];
    handlers();
    renderPage();
    await screen.findByText('Configurar Jornada Electoral');
    expect(await screen.findByText(/No existe un proceso electoral configurado/)).toBeVisible();
    expect(screen.queryByLabelText('Proceso electoral')).not.toBeInTheDocument();
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

  it('crea la jornada al enviar el formulario con el único proceso válido ya seleccionado', async () => {
    processes = [
      { id: 'proc-1', name: 'Elecciones Seccionales 2027', election_date: '2027-02-14' },
    ];
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
    await screen.findByLabelText('Proceso electoral');
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

  it('permite iniciar el escrutinio desde una jornada activa', async () => {
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
    handlers();
    renderPage();
    await screen.findByText('Escuela Central');
    expect(screen.queryByRole('button', { name: 'Cerrar jornada' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Iniciar escrutinio' }));
    await waitFor(() => expect(lastAction).toBe('start-scrutiny'));
  });

  it('no permite activar la jornada si el preflight tiene bloqueos', async () => {
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
    preflight = {
      ready: false,
      blockers: ['No existe ningún validador de actas asignado.'],
      warnings: [],
      summary: {
        polling_places: 1,
        boards: 1,
        delegates: 1,
        validators: 0,
        uncovered_polling_places: 0,
      },
    };
    handlers();
    renderPage();
    await screen.findByText('Escuela Central');
    expect(await screen.findByText('No existe ningún validador de actas asignado.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Activar jornada' })).toBeDisabled();
  });

  it('muestra el diálogo de cierre con el resumen de cobertura y confirma el cierre', async () => {
    operationStatus = 200;
    operation = {
      id: 'op1',
      organization_id: 'org1',
      campaign_id: 'campaign-1',
      electoral_process_id: 'proc-1',
      election_date: '2027-03-14',
      status: 'SCRUTINY',
      opened_at: '2027-03-14T10:00:00Z',
      closed_at: null,
      opened_by_user_id: 'u1',
      closed_by_user_id: null,
      scrutiny_started_at: '2027-03-14T20:00:00Z',
      scrutiny_started_by_user_id: 'u1',
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
    actsCoverage = {
      expected_boards: 3,
      received: 2,
      validated: 1,
      in_review: 1,
      observed: 0,
      pending: 1,
    };
    handlers();
    renderPage();
    await screen.findByText('Escuela Central');
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar jornada' }));
    expect(await screen.findByRole('heading', { name: 'Cerrar jornada' })).toBeVisible();
    expect(screen.getByText(/Existen incidencias sin resolver/)).toBeVisible();
    expect(
      screen.getByText('Existen 1 actas recibidas que todavía no han sido validadas.'),
    ).toBeVisible();
    // La advertencia nunca bloquea el cierre: el botón sigue habilitado.
    expect(screen.getByRole('button', { name: 'Confirmar cierre' })).toBeEnabled();
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
