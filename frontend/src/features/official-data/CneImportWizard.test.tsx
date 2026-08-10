import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import CneImportWizard from './CneImportWizard';

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
vi.mock('../../app/CampaignProvider', () => ({
  useCampaign: () => ({ active: { id: 'campaign-1', name: 'Campaña' } }),
}));

const server = setupServer();
const nativeFetch = globalThis.fetch;
const source = {
  id: 'source-1',
  code: 'CNE_ECUADOR',
  institution: 'Consejo Nacional Electoral del Ecuador',
  dataset_name: 'Resultados electorales oficiales',
  dataset_type: 'CNE_ELECTORAL_RESULTS',
  is_active: true,
};
const process = {
  id: 'process-1',
  code: 'SEC_2023',
  name: 'Elecciones Seccionales 2023',
  process_type: 'SECTIONAL',
  election_date: '2023-02-05',
  year: 2023,
  status: 'VALIDATED',
  is_final: true,
  source_id: 'source-1',
  is_active: true,
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
  localStorage.clear();
  server.resetHandlers();
  auth.user = {
    ...auth.user,
    is_superuser: true,
    roles: [{ code: 'ADMIN', name: 'Administrador' }],
  };
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function commonHandlers(
  sources: unknown[] = [],
  processes: unknown[] = [],
  contests: unknown[] = [],
) {
  server.use(
    http.get('*/api/v1/data-sources', () => HttpResponse.json(sources)),
    http.get('*/api/v1/electoral-processes', () => HttpResponse.json(processes)),
    http.get('*/api/v1/provinces', () =>
      HttpResponse.json([{ id: 1, code: '01', name: 'Azuay', is_active: true }]),
    ),
    http.get('*/api/v1/cantons', () =>
      HttpResponse.json([
        {
          id: 10,
          province_id: 1,
          code: '03',
          dpa_code: '0103',
          name: 'Gualaceo',
          is_active: true,
        },
      ]),
    ),
    http.get('*/api/v1/cantons/:id', () =>
      HttpResponse.json({
        id: 10,
        province_id: 1,
        code: '03',
        dpa_code: '0103',
        name: 'Gualaceo',
        is_active: true,
      }),
    ),
    http.get('*/api/v1/electoral-processes/:id/contests', () => HttpResponse.json(contests)),
    http.get('*/api/v1/political-organizations', () => HttpResponse.json([])),
    http.get('*/api/v1/electoral-processes/:pid/contests/:cid/candidates', () =>
      HttpResponse.json([]),
    ),
    http.get('*/api/v1/electoral-processes/:pid/geographies', () => HttpResponse.json([])),
    http.get('*/api/v1/electoral-processes/:pid/contests/:cid/turnout', () =>
      HttpResponse.json([]),
    ),
    http.get('*/api/v1/electoral-processes/:pid/contests/:cid/candidate-results', () =>
      HttpResponse.json([]),
    ),
  );
}

function renderWizard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/admin/official-data/cne']}>
        <Routes>
          <Route path="/app/admin/official-data/cne" element={<CneImportWizard />} />
          <Route path="/403" element={<div>Acceso denegado</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('asistente de importación CNE', () => {
  it('muestra fuente inexistente y permite crearla', async () => {
    commonHandlers();
    renderWizard();
    expect(await screen.findByText('No existe una fuente oficial CNE registrada.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Crear fuente CNE' })).toBeVisible();
  });

  it('crea una fuente CNE con valores iniciales editables', async () => {
    const sourceRows: unknown[] = [];
    let payload: any;
    commonHandlers(sourceRows);
    server.use(
      http.post('*/api/v1/data-sources', async ({ request }) => {
        payload = await request.json();
        sourceRows.push(source);
        return HttpResponse.json(source, { status: 201 });
      }),
    );
    renderWizard();
    await userEvent.click(await screen.findByRole('button', { name: 'Crear fuente CNE' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Crear fuente CNE' }));
    expect(await screen.findByText('Fuente CNE creada correctamente.')).toBeVisible();
    expect(payload).toMatchObject({
      code: 'CNE_ECUADOR',
      dataset_type: 'CNE_ELECTORAL_RESULTS',
      is_official: true,
    });
  });

  it('reutiliza una fuente si el código entra en conflicto', async () => {
    const sourceRows: unknown[] = [];
    commonHandlers(sourceRows);
    server.use(
      http.post('*/api/v1/data-sources', () => {
        sourceRows.push(source);
        return HttpResponse.json({ detail: 'Fuente duplicada' }, { status: 409 });
      }),
    );
    renderWizard();
    await userEvent.click(await screen.findByRole('button', { name: 'Crear fuente CNE' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Crear fuente CNE' }),
    );
    expect(await screen.findByText('Fuente CNE existente. Se reutilizará.')).toBeVisible();
  });

  it('muestra errores 422 al crear la fuente', async () => {
    commonHandlers();
    server.use(
      http.post('*/api/v1/data-sources', () =>
        HttpResponse.json(
          { detail: [{ loc: ['body', 'code'], msg: 'Inválido' }] },
          { status: 422 },
        ),
      ),
    );
    renderWizard();
    await userEvent.click(await screen.findByRole('button', { name: 'Crear fuente CNE' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Crear fuente CNE' }),
    );
    expect(await screen.findByText('Revisa los campos indicados.')).toBeVisible();
  });

  it('reutiliza un proceso existente sin pedir UUID', async () => {
    commonHandlers([source], [process]);
    renderWizard();
    await userEvent.click(await screen.findByLabelText('Fuente oficial CNE'));
    await userEvent.click(await screen.findByRole('option', { name: /Consejo Nacional/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Crear o reutilizar proceso' }));
    expect(await screen.findByText('Proceso electoral existente. Se reutilizará.')).toBeVisible();
  });

  it('crea un proceso y deriva el año de la fecha', async () => {
    const processRows: unknown[] = [];
    let payload: any;
    commonHandlers([source], processRows);
    server.use(
      http.post('*/api/v1/electoral-processes', async ({ request }) => {
        payload = await request.json();
        processRows.push(process);
        return HttpResponse.json(process, { status: 201 });
      }),
    );
    renderWizard();
    await userEvent.click(await screen.findByLabelText('Fuente oficial CNE'));
    await userEvent.click(await screen.findByRole('option', { name: /Consejo Nacional/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Crear o reutilizar proceso' }));
    expect(await screen.findByText('Proceso electoral creado correctamente.')).toBeVisible();
    expect(payload).toMatchObject({
      code: 'SEC_2023',
      election_date: '2023-02-05',
      year: 2023,
      source_id: 'source-1',
    });
  });

  it('resuelve canton_id y crea el contest_code generado', async () => {
    const contests: unknown[] = [];
    let payload: any;
    commonHandlers([source], [process], contests);
    server.use(
      http.post('*/api/v1/electoral-processes/:id/contests', async ({ request }) => {
        payload = await request.json();
        const created = {
          id: 'contest-1',
          electoral_process_id: 'process-1',
          ...payload,
          province_id: null,
          parish_id: null,
          is_active: true,
        };
        contests.push(created);
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    renderWizard();
    await userEvent.click(await screen.findByLabelText('Fuente oficial CNE'));
    await userEvent.click(await screen.findByRole('option', { name: /Consejo Nacional/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Crear o reutilizar proceso' }));
    await screen.findByText('Proceso electoral existente. Se reutilizará.');
    await userEvent.click(screen.getByLabelText('Provincia'));
    await userEvent.click(await screen.findByRole('option', { name: 'Azuay' }));
    await userEvent.click(screen.getByLabelText('Cantón'));
    await userEvent.click(await screen.findByRole('option', { name: 'Gualaceo' }));
    expect(screen.getByLabelText('Nombre técnico / contest_code')).toHaveValue('MAYOR_GUALACEO');
    await userEvent.click(screen.getByRole('button', { name: 'Crear o reutilizar contienda' }));
    expect(await screen.findByText('Contienda creada correctamente.')).toBeVisible();
    expect(payload).toMatchObject({ canton_id: 10, name: 'MAYOR_GUALACEO', office_type: 'MAYOR' });
  });

  it('reconstruye proceso y contienda desde base usando el contexto persistido', async () => {
    const contest = {
      id: 'contest-1',
      electoral_process_id: 'process-1',
      office_type: 'MAYOR',
      name: 'MAYOR_GUALACEO',
      vote_method: 'SINGLE_CHOICE',
      province_id: null,
      canton_id: 10,
      parish_id: null,
      seats: 1,
      is_active: true,
    };
    localStorage.setItem(
      'territorio.officialData.cne',
      JSON.stringify({
        sourceId: 'source-1',
        processCode: 'SEC_2023',
        contestCode: 'MAYOR_GUALACEO',
      }),
    );
    commonHandlers([source], [process], [contest]);
    renderWizard();
    expect(await screen.findByDisplayValue('MAYOR_GUALACEO')).toBeVisible();
    expect(screen.getByDisplayValue('Elecciones Seccionales 2023')).toBeVisible();
  });

  it('presenta los cuatro archivos en orden y bloquea dependencias', async () => {
    commonHandlers([source], []);
    renderWizard();
    expect(await screen.findByText('Paso 4 — Organizaciones políticas')).toBeVisible();
    expect(screen.getByText('Paso 5 — Participación electoral')).toBeVisible();
    expect(screen.getByText('Paso 6 — Candidaturas')).toBeVisible();
    expect(screen.getByText('Paso 7 — Resultados electorales')).toBeVisible();
    expect(screen.getAllByText('Bloqueado')).toHaveLength(4);
  });

  it('rechaza el asistente para usuarios no ADMIN', async () => {
    auth.user = {
      ...auth.user,
      is_superuser: false,
      roles: [{ code: 'ANALYST', name: 'Analista' }],
    };
    commonHandlers();
    renderWizard();
    expect(await screen.findByText('Acceso denegado')).toBeVisible();
  });
});
