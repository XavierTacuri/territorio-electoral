import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import ImportPage, { appendMappingProfile, importErrorMessage } from './ImportPage';

const server = setupServer(
  http.get('*/api/v1/data-sources', () =>
    HttpResponse.json([
      {
        id: 'source-cne',
        code: 'CNE_ECUADOR',
        institution: 'Consejo Nacional Electoral del Ecuador',
        dataset_name: 'Resultados electorales oficiales históricos',
        dataset_type: 'CNE_ELECTORAL_RESULTS',
        is_active: true,
      },
    ]),
  ),
  http.get('*/api/v1/data-imports', () => HttpResponse.json([])),
);
const nativeFetch = globalThis.fetch;

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function profileData(profile: string) {
  const data = new FormData();
  appendMappingProfile(data, profile);
  return data;
}

describe('perfil de mapeo de importación CSV', () => {
  it('muestra Automático y omite mapping_profile', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/app/admin/data-imports?sourceId=source-cne']}>
          <ImportPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Automático: el sistema seleccionará/)).toBeVisible();
    expect(profileData('').has('mapping_profile')).toBe(false);
  });

  it('CNE_ELECTORAL_RESULTS conserva selección automática', () => {
    const data = new FormData();
    data.set('dataset_type', 'CNE_ELECTORAL_RESULTS');
    appendMappingProfile(data, '');
    expect(data.get('dataset_type')).toBe('CNE_ELECTORAL_RESULTS');
    expect(data.has('mapping_profile')).toBe(false);
  });

  it('envía un perfil explícito correctamente', () => {
    expect(profileData('CANONICAL_ELECTORAL_CANDIDATE_RESULT').get('mapping_profile')).toBe(
      'CANONICAL_ELECTORAL_CANDIDATE_RESULT',
    );
  });

  it('nunca envía el valor legado DEFAULT', () => {
    expect(profileData('DEFAULT').has('mapping_profile')).toBe(false);
    expect(profileData(' default ').has('mapping_profile')).toBe(false);
  });

  it('conserva el detalle de error devuelto por backend', async () => {
    const response = new Response(
      JSON.stringify({ detail: 'Cabeceras faltantes: candidate_code' }),
      {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      },
    );
    expect(await importErrorMessage(response)).toBe('Cabeceras faltantes: candidate_code');
  });
});
