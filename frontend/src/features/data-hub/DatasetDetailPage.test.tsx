import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import DatasetDetailPage from './DatasetDetailPage';
import type { DatasetDetail } from './types';

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
let detail: DatasetDetail;
let activated: string | null = null;

const source = {
  id: 's1', code: 'CNE_ECUADOR', institution: 'Consejo Nacional Electoral', dataset_name: 'Registro',
  dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT', official_url: null, publication_date: null,
  reference_date: '2026-07-16', reference_year: null, license_or_terms: null, description: null,
  is_official: true, is_active: true,
} as any;
const version = {
  id: 'v1', data_source_id: 's1', dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT', reference_date: '2026-07-16',
  version_label: 'Corte 2026-07-16', checksum: 'abc', import_job_id: 'j1', status: 'VALIDATED',
  activated_at: null, activated_by_user_id: null, superseded_by_id: null,
};
const job = {
  id: 'j1', source_id: 's1', dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT', original_filename: 'roll.csv',
  file_sha256: 'abc', file_size_bytes: 100, status: 'COMPLETED', validation_only: false, rows_read: 10,
  rows_valid: 10, rows_inserted: 10, rows_updated: 0, rows_skipped: 0, rows_failed: 0, encoding_used: 'utf-8',
  delimiter_used: ',', mapping_profile: 'CANONICAL_ELECTORAL_ROLL_SNAPSHOT', error_summary: null,
};

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'), init)) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  auth.user = { ...auth.user, is_superuser: false, roles: [{ code: 'ADMIN', name: 'Administrador' }] };
  activated = null;
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers() {
  server.use(
    http.get('*/api/v1/data-hub/datasets/:type', () => HttpResponse.json(detail)),
    http.post('*/api/v1/data-hub/versions/:id/activate', ({ params }) => {
      activated = params.id as string;
      return HttpResponse.json({ ...version, status: 'ACTIVE' });
    }),
  );
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/admin/data-hub/CNE_ELECTORAL_ROLL_SNAPSHOT']}>
        <Routes>
          <Route path="/app/admin/data-hub/:datasetType" element={<DatasetDetailPage />} />
          <Route path="/403" element={<div>Acceso denegado</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Centro de datos — detalle de dataset', () => {
  it('muestra advertencia cuando no hay versión vigente', async () => {
    detail = { dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT', dataset_label: 'CNE · Registro electoral', version_kind: 'SNAPSHOT_VERSIONED', version_kind_label: 'Histórico por corte', sources: [source], active_version: null, versions: [version], jobs: [job] };
    handlers();
    renderPage();
    expect(await screen.findByText('Este dataset no tiene una versión vigente activada.')).toBeVisible();
    expect(screen.getByText('Corte 2026-07-16')).toBeVisible();
  });

  it('permite a ADMIN activar una versión', async () => {
    detail = { dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT', dataset_label: 'CNE · Registro electoral', version_kind: 'SNAPSHOT_VERSIONED', version_kind_label: 'Histórico por corte', sources: [source], active_version: null, versions: [version], jobs: [job] };
    handlers();
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Activar' }));
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    await waitFor(() => expect(activated).toBe('v1'));
  });

  it('oculta las acciones de administración para ANALYST', async () => {
    auth.user = { ...auth.user, roles: [{ code: 'ANALYST', name: 'Analista' }] };
    detail = { dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT', dataset_label: 'CNE · Registro electoral', version_kind: 'SNAPSHOT_VERSIONED', version_kind_label: 'Histórico por corte', sources: [source], active_version: null, versions: [version], jobs: [job] };
    handlers();
    renderPage();
    await screen.findByText('Corte 2026-07-16');
    expect(screen.queryByRole('button', { name: 'Activar' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Nueva importación' })).not.toBeInTheDocument();
  });

  it('rechaza el acceso para roles sin visibilidad', async () => {
    auth.user = { ...auth.user, roles: [{ code: 'CANDIDATE', name: 'Candidato' }] };
    detail = { dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT', dataset_label: 'CNE · Registro electoral', version_kind: 'SNAPSHOT_VERSIONED', version_kind_label: 'Histórico por corte', sources: [], active_version: null, versions: [], jobs: [] };
    handlers();
    renderPage();
    expect(await screen.findByText('Acceso denegado')).toBeVisible();
  });

  it('muestra estado vacío de versiones e importaciones', async () => {
    detail = { dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT', dataset_label: 'CNE · Registro electoral', version_kind: 'SNAPSHOT_VERSIONED', version_kind_label: 'Histórico por corte', sources: [], active_version: null, versions: [], jobs: [] };
    handlers();
    renderPage();
    expect(await screen.findByText('Todavía no hay versiones para este dataset.')).toBeVisible();
    expect(screen.getByText('No hay importaciones registradas.')).toBeVisible();
  });

  it('etiqueta la acción como referencia administrativa (no rollback) para datasets upsert-governed', async () => {
    detail = {
      dataset_type: 'CNE_TURNOUT',
      dataset_label: 'CNE · Participación electoral',
      version_kind: 'UPSERT_GOVERNED',
      version_kind_label: 'Versión administrativa',
      sources: [source],
      active_version: null,
      versions: [{ ...version, dataset_type: 'CNE_TURNOUT' }],
      jobs: [job],
    };
    handlers();
    renderPage();
    expect(await screen.findByText('Versión administrativa')).toBeVisible();
    const button = await screen.findByRole('button', { name: 'Marcar como versión de referencia' });
    expect(screen.queryByRole('button', { name: 'Activar' })).not.toBeInTheDocument();
    await userEvent.click(button);
    expect(
      screen.getByText(
        /No restaura automáticamente los valores reemplazados durante importaciones anteriores\./,
      ),
    ).toBeVisible();
    expect(screen.queryByText(/rollback/i)).not.toBeInTheDocument();
  });
});
