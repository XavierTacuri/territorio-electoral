import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import DataHubPage from './DataHubPage';
import type { DataHubCatalog } from './types';

const auth = vi.hoisted(() => ({
  user: {
    id: 'admin',
    username: 'admin',
    email: 'admin@example.test',
    first_name: 'Admin',
    last_name: 'Test',
    is_active: true,
    is_superuser: false,
    roles: [{ code: 'ADMIN', name: 'Administrador' }],
  } as any,
}));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ user: auth.user }) }));

const server = setupServer();
const nativeFetch = globalThis.fetch;
let catalog: DataHubCatalog = {
  summary: { active_sources: 0, datasets: 0, recent_imports: 0, imports_with_errors: 0, datasets_without_active_version: 0 },
  entries: [],
};

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'), init)) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  auth.user = { ...auth.user, is_superuser: false, roles: [{ code: 'ADMIN', name: 'Administrador' }] };
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers() {
  server.use(http.get('*/api/v1/data-hub/catalog', () => HttpResponse.json(catalog)));
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/admin/data-hub']}>
        <Routes>
          <Route path="/app/admin/data-hub" element={<DataHubPage />} />
          <Route path="/app/admin/data-hub/:datasetType" element={<div>Detalle dataset</div>} />
          <Route path="/403" element={<div>Acceso denegado</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Centro de datos — catálogo', () => {
  it('muestra estado vacío cuando no hay datasets', async () => {
    catalog = { summary: { active_sources: 0, datasets: 0, recent_imports: 0, imports_with_errors: 0, datasets_without_active_version: 0 }, entries: [] };
    handlers();
    renderPage();
    expect(await screen.findByText('No hay datasets administrados todavía.')).toBeVisible();
  });

  it('muestra KPIs y datasets con advertencia de versión faltante', async () => {
    catalog = {
      summary: { active_sources: 2, datasets: 1, recent_imports: 3, imports_with_errors: 1, datasets_without_active_version: 1 },
      entries: [
        {
          dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT',
          dataset_label: 'CNE · Registro electoral preelectoral',
          version_kind: 'SNAPSHOT_VERSIONED',
          version_kind_label: 'Histórico por corte',
          sources: [
            {
              id: 's1', code: 'CNE_ECUADOR', institution: 'Consejo Nacional Electoral', dataset_name: 'Registro',
              dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT', official_url: null, publication_date: null,
              reference_date: null, reference_year: null, license_or_terms: null, description: null,
              is_official: true, is_active: true,
            } as any,
          ],
          active_version: null,
          last_job: null,
          versions_count: 0,
        },
      ],
    };
    handlers();
    renderPage();
    expect(await screen.findByText('2')).toBeVisible();
    expect(screen.getByText('CNE · Registro electoral preelectoral')).toBeVisible();
    expect(screen.getAllByText('Sin versión vigente').length).toBeGreaterThan(0);
  });

  it('rechaza el acceso a roles sin visibilidad del Centro de datos', async () => {
    auth.user = { ...auth.user, roles: [{ code: 'CANDIDATE', name: 'Candidato' }] };
    handlers();
    renderPage();
    expect(await screen.findByText('Acceso denegado')).toBeVisible();
  });

  it('permite el acceso de solo lectura a ANALYST', async () => {
    auth.user = { ...auth.user, roles: [{ code: 'ANALYST', name: 'Analista' }] };
    catalog = { summary: { active_sources: 0, datasets: 0, recent_imports: 0, imports_with_errors: 0, datasets_without_active_version: 0 }, entries: [] };
    handlers();
    renderPage();
    expect(await screen.findByText('Centro de datos de Ecuador')).toBeVisible();
  });
});
