import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import ImportPage from '../imports/ImportPage';
import SourcesPage, { DataSource } from './SourcesPage';

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
const source: DataSource = {
  id: 'source-1',
  code: 'CNE_ECUADOR',
  institution: 'Consejo Nacional Electoral del Ecuador',
  dataset_name: 'Resultados electorales oficiales',
  dataset_type: 'CNE_ELECTORAL_RESULTS',
  official_url: null,
  publication_date: null,
  reference_date: null,
  reference_year: null,
  license_or_terms: null,
  description: 'Resultados oficiales.',
  is_official: true,
  is_active: true,
};
let sources: DataSource[] = [];
let createStatus = 201;
let updateStatus = 200;
let lastRequest: { method: string; body: any } | null = null;
let jobsUrl = '';

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  sources = [];
  createStatus = 201;
  updateStatus = 200;
  lastRequest = null;
  jobsUrl = '';
  auth.user = {
    ...auth.user,
    is_superuser: true,
    roles: [{ code: 'ADMIN', name: 'Administrador' }],
  };
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers() {
  server.use(
    http.get('*/api/v1/data-sources', () => HttpResponse.json(sources)),
    http.post('*/api/v1/data-sources', async ({ request }) => {
      lastRequest = { method: request.method, body: await request.json() };
      if (createStatus !== 201)
        return HttpResponse.json(
          { detail: createStatus === 409 ? 'Código duplicado' : [] },
          { status: createStatus },
        );
      sources = [source];
      return HttpResponse.json(source, { status: 201 });
    }),
    http.patch('*/api/v1/data-sources/:id', async ({ request }) => {
      lastRequest = { method: request.method, body: await request.json() };
      if (updateStatus !== 200)
        return HttpResponse.json({ detail: 'Error' }, { status: updateStatus });
      const body = lastRequest.body as Partial<DataSource>;
      sources = [{ ...source, ...body }];
      return HttpResponse.json(sources[0]);
    }),
    http.get('*/api/v1/data-imports', ({ request }) => {
      jobsUrl = request.url;
      return HttpResponse.json([]);
    }),
  );
}

function renderPage(path: string, element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/app/admin/data-sources" element={element} />
          <Route path="/app/admin/data-imports" element={element} />
          <Route path="/403" element={<div>Acceso denegado</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
async function openCreate() {
  await userEvent.click(await screen.findByRole('button', { name: 'Crear primera fuente' }));
}
async function fillCreate() {
  await userEvent.type(screen.getByLabelText('Código'), 'CNE_ECUADOR');
  await userEvent.type(
    screen.getByLabelText('Institución'),
    'Consejo Nacional Electoral del Ecuador',
  );
  await userEvent.type(
    screen.getByLabelText('Nombre del conjunto'),
    'Resultados electorales oficiales',
  );
  await userEvent.click(screen.getByLabelText('Tipo de conjunto'));
  await userEvent.click(
    await screen.findByRole('option', { name: 'CNE · Resultados electorales' }),
  );
}

describe('fuentes de datos administrativas', () => {
  it('muestra estado vacío y crear primera fuente', async () => {
    handlers();
    renderPage('/app/admin/data-sources', <SourcesPage />);
    expect(await screen.findByText('No existen fuentes de datos registradas.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Crear primera fuente' })).toBeVisible();
  });
  it('crea una fuente con el contrato real', async () => {
    handlers();
    renderPage('/app/admin/data-sources', <SourcesPage />);
    await openCreate();
    await fillCreate();
    await userEvent.click(screen.getByRole('button', { name: 'Guardar fuente' }));
    expect(await screen.findByText('Consejo Nacional Electoral del Ecuador')).toBeVisible();
    expect(lastRequest).toMatchObject({
      method: 'POST',
      body: { code: 'CNE_ECUADOR', dataset_type: 'CNE_ELECTORAL_RESULTS' },
    });
  });
  it('edita sin enviar código ni tipo', async () => {
    sources = [source];
    handlers();
    renderPage('/app/admin/data-sources', <SourcesPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const institution = screen.getByLabelText('Institución');
    await userEvent.clear(institution);
    await userEvent.type(institution, 'CNE actualizado');
    await userEvent.click(screen.getByRole('button', { name: 'Guardar fuente' }));
    await waitFor(() => expect(lastRequest?.method).toBe('PATCH'));
    expect(lastRequest?.body).not.toHaveProperty('code');
    expect(lastRequest?.body).not.toHaveProperty('dataset_type');
  });
  it('activa y desactiva mediante PATCH', async () => {
    sources = [source];
    handlers();
    renderPage('/app/admin/data-sources', <SourcesPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Desactivar' }));
    await waitFor(() => expect(lastRequest?.body).toEqual({ is_active: false }));
    expect(await screen.findByText('Inactiva')).toBeVisible();
  });
  it.each([
    [409, 'Ya existe una fuente con este código.'],
    [422, 'Revisa los campos indicados.'],
  ])('muestra error HTTP %s', async (status, message) => {
    createStatus = status;
    handlers();
    renderPage('/app/admin/data-sources', <SourcesPage />);
    await openCreate();
    await fillCreate();
    await userEvent.click(screen.getByRole('button', { name: 'Guardar fuente' }));
    expect(await screen.findByText(message)).toBeVisible();
  });
  it('rechaza la vista administrativa para no ADMIN', async () => {
    auth.user = {
      ...auth.user,
      is_superuser: false,
      roles: [{ code: 'ANALYST', name: 'Analista' }],
    };
    handlers();
    renderPage('/app/admin/data-sources', <SourcesPage />);
    expect(await screen.findByText('Acceso denegado')).toBeVisible();
  });
  it('selecciona la fuente desde URL y filtra sus importaciones', async () => {
    sources = [source];
    handlers();
    renderPage('/app/admin/data-imports?sourceId=source-1', <ImportPage />);
    expect(await screen.findByLabelText('Fuente oficial')).toHaveTextContent(
      'Consejo Nacional Electoral del Ecuador',
    );
    await waitFor(() => expect(jobsUrl).toContain('source_id=source-1'));
  });
});
