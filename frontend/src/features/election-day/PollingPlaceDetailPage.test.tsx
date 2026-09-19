import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import PollingPlaceDetailPage from './PollingPlaceDetailPage';

vi.mock('../../api/downloads', () => ({ downloadReport: vi.fn() }));

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
let place: any = null;
let boards: any[] = [];
let assignments: any[] = [];
let incidents: any[] = [];
let documents: any[] = [];
let resolvedIncidentId: string | null = null;
let eligibleUsers: any[] = [];
let replacedAssignmentId: string | null = null;
let replacedBody: any = null;
let resolveStatus = 200;
let replaceStatus = 200;

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  place = null;
  boards = [];
  assignments = [];
  incidents = [];
  documents = [];
  resolvedIncidentId = null;
  eligibleUsers = [];
  replacedAssignmentId = null;
  replacedBody = null;
  resolveStatus = 200;
  replaceStatus = 200;
  auth.user = { ...auth.user, roles: [{ code: 'CANDIDATE', name: 'Candidato' }] };
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers() {
  server.use(
    http.get('*/api/v1/campaigns/campaign-1/election-day/polling-places/place-1', () =>
      HttpResponse.json(place),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/polling-places/place-1/boards', () =>
      HttpResponse.json(boards),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/assignments', () =>
      HttpResponse.json({ items: assignments }),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/incidents', () =>
      HttpResponse.json({ items: incidents }),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/documents', () =>
      HttpResponse.json({ items: documents }),
    ),
    http.post('*/api/v1/campaigns/campaign-1/election-day/incidents/:id/resolve', ({ params }) => {
      if (resolveStatus !== 200)
        return HttpResponse.json({ detail: 'error' }, { status: resolveStatus });
      resolvedIncidentId = String(params.id);
      return HttpResponse.json({ ...incidents[0], status: 'RESOLVED' });
    }),
    http.get('*/api/v1/campaigns/campaign-1/election-day/eligible-users', () =>
      HttpResponse.json(eligibleUsers),
    ),
    http.post(
      '*/api/v1/campaigns/campaign-1/election-day/assignments/:id/replace',
      async ({ request, params }) => {
        if (replaceStatus !== 200)
          return HttpResponse.json({ detail: 'error' }, { status: replaceStatus });
        replacedAssignmentId = String(params.id);
        replacedBody = await request.json();
        return HttpResponse.json({ id: 'a-new', status: 'ASSIGNED', ...replacedBody });
      },
    ),
  );
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={['/app/campaigns/campaign-1/election-day/polling-places/place-1']}
      >
        <Routes>
          <Route
            path="/app/campaigns/:campaignId/election-day/polling-places/:polling_place_id"
            element={<PollingPlaceDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const basePlace = {
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

describe('Detalle de recinto electoral', () => {
  it('muestra la matriz de juntas (solo lectura) y el personal asignado', async () => {
    place = basePlace;
    boards = [
      {
        id: 'board-1',
        polling_place_id: 'place-1',
        official_code: 'J-01',
        board_number: 1,
        sex_category: null,
        registered_voters: 300,
        is_active: true,
      },
    ];
    assignments = [
      {
        id: 'a1',
        operation_id: 'op1',
        user_id: 'u2',
        polling_place_id: 'place-1',
        assignment_role: 'POLLING_PLACE_DELEGATE',
        status: 'CHECKED_IN',
        checked_in_at: '2027-03-14T09:00:00Z',
        checkin_latitude: null,
        checkin_longitude: null,
        replaced_by_assignment_id: null,
      },
    ];
    handlers();
    renderPage();
    expect(await screen.findByText('Escuela Central')).toBeVisible();
    expect(screen.getByText('J-01')).toBeVisible();
    expect(screen.getByText('300')).toBeVisible();
    expect(screen.getByText('Datos electorales cargados por administración.')).toBeVisible();
    expect(screen.getByText(/Delegado de recinto/)).toBeVisible();
    expect(screen.getByText(/Presente/)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'AGREGAR JUNTA' })).not.toBeInTheDocument();
  });

  it('muestra estados vacíos cuando no hay juntas, incidencias ni documentos', async () => {
    place = basePlace;
    handlers();
    renderPage();
    await screen.findByText('Escuela Central');
    expect(screen.getByText('No hay juntas registradas.')).toBeVisible();
    expect(screen.getByText('No hay incidencias abiertas.')).toBeVisible();
    expect(screen.getByText('Aún no se han recibido documentos.')).toBeVisible();
  });

  it('nunca ofrece agregar junta, reportar incidencia ni adjuntar documento desde esta pantalla', async () => {
    place = basePlace;
    handlers();
    renderPage();
    await screen.findByText('Escuela Central');
    expect(screen.queryByRole('button', { name: 'AGREGAR JUNTA' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'REPORTAR INCIDENCIA' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'ADJUNTAR DOCUMENTO' })).not.toBeInTheDocument();
  });

  it('permite a un gestor resolver una incidencia abierta', async () => {
    place = basePlace;
    incidents = [
      {
        id: 'inc-1',
        operation_id: 'op1',
        polling_place_id: 'place-1',
        board_id: null,
        reported_by_user_id: 'u2',
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
    await userEvent.click(screen.getByRole('button', { name: 'Resolver' }));
    await waitFor(() => expect(resolvedIncidentId).toBe('inc-1'));
  });

  it('muestra los documentos recibidos con botón de descarga', async () => {
    place = basePlace;
    documents = [
      {
        id: 'doc-1',
        operation_id: 'op1',
        polling_place_id: 'place-1',
        board_id: null,
        document_type: 'ACTA_COPY',
        mime_type: 'application/pdf',
        size_bytes: 1024,
        original_filename: 'acta.pdf',
        uploaded_by_user_id: 'u1',
        status: 'RECEIVED',
      },
    ];
    handlers();
    renderPage();
    expect(await screen.findByText(/Copia de acta/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Descargar' })).toBeVisible();
  });

  it('un usuario sin rol de gestión no ve el botón de reemplazar', async () => {
    auth.user = { ...auth.user, roles: [] };
    place = basePlace;
    assignments = [
      {
        id: 'a1',
        operation_id: 'op1',
        user_id: 'u2',
        polling_place_id: 'place-1',
        assignment_role: 'POLLING_PLACE_DELEGATE',
        status: 'ASSIGNED',
        checked_in_at: null,
        checkin_latitude: null,
        checkin_longitude: null,
        replaced_by_assignment_id: null,
      },
    ];
    handlers();
    renderPage();
    await screen.findByText('Escuela Central');
    expect(screen.queryByRole('button', { name: 'REEMPLAZAR' })).not.toBeInTheDocument();
  });

  it('un gestor reemplaza el personal asignado y ve el historial preservado', async () => {
    place = basePlace;
    assignments = [
      {
        id: 'a1',
        operation_id: 'op1',
        user_id: 'u2',
        polling_place_id: 'place-1',
        assignment_role: 'POLLING_PLACE_DELEGATE',
        status: 'ASSIGNED',
        checked_in_at: null,
        checkin_latitude: null,
        checkin_longitude: null,
        replaced_by_assignment_id: null,
      },
    ];
    eligibleUsers = [
      { id: 'u2', username: 'delegado_a', first_name: 'Delegado', last_name: 'A' },
      { id: 'u3', username: 'delegado_b', first_name: 'Delegado', last_name: 'B' },
    ];
    handlers();
    renderPage();
    await screen.findByText('Escuela Central');
    await userEvent.click(await screen.findByRole('button', { name: 'REEMPLAZAR' }));
    expect(await screen.findByText('Persona: Delegado A (delegado_a)')).toBeVisible();
    // La propia persona actual nunca aparece como opción de reemplazo.
    await userEvent.click(screen.getByLabelText('Nuevo usuario'));
    expect(screen.queryByRole('option', { name: /delegado_a/ })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole('option', { name: /delegado_b/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar reemplazo' }));
    await waitFor(() => expect(replacedAssignmentId).toBe('a1'));
    expect(replacedBody).toMatchObject({ user_id: 'u3' });
    expect(await screen.findByText('Personal reemplazado.')).toBeVisible();
  });

  it('mantiene el diálogo de reemplazo abierto y muestra el error si el backend falla', async () => {
    replaceStatus = 409;
    place = basePlace;
    assignments = [
      {
        id: 'a1',
        operation_id: 'op1',
        user_id: 'u2',
        polling_place_id: 'place-1',
        assignment_role: 'POLLING_PLACE_DELEGATE',
        status: 'ASSIGNED',
        checked_in_at: null,
        checkin_latitude: null,
        checkin_longitude: null,
        replaced_by_assignment_id: null,
      },
    ];
    eligibleUsers = [{ id: 'u3', username: 'delegado_b', first_name: 'Delegado', last_name: 'B' }];
    handlers();
    renderPage();
    await screen.findByText('Escuela Central');
    await userEvent.click(await screen.findByRole('button', { name: 'REEMPLAZAR' }));
    await userEvent.click(screen.getByLabelText('Nuevo usuario'));
    await userEvent.click(await screen.findByRole('option', { name: /delegado_b/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar reemplazo' }));
    expect(
      await screen.findByText('No fue posible reemplazar al personal asignado.'),
    ).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Reemplazar personal asignado' })).toBeVisible();
  });

  it('muestra un aviso visible si falla resolver una incidencia, sin romper la página', async () => {
    resolveStatus = 409;
    place = basePlace;
    incidents = [
      {
        id: 'inc-1',
        operation_id: 'op1',
        polling_place_id: 'place-1',
        board_id: null,
        reported_by_user_id: 'u2',
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
    await userEvent.click(await screen.findByRole('button', { name: 'Resolver' }));
    expect(await screen.findByText('No fue posible resolver la incidencia.')).toBeVisible();
    expect(screen.getByText(/Falta material/)).toBeVisible();
  });
});
