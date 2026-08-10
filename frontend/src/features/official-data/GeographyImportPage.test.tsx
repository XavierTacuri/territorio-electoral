import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../../api/client';
import GeographyImportPage from './GeographyImportPage';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return { ...actual, apiRequest: vi.fn(), BASE_URL: '/api/v1', tokenStore: { get: () => null } };
});

const source = {
  id: 'source-1',
  code: 'INEC_BOUNDARIES',
  institution: 'INEC',
  dataset_name: 'Límites oficiales',
  dataset_type: 'OTHER_AGGREGATED_OFFICIAL',
  official_url: null,
  publication_date: null,
  reference_date: null,
  reference_year: null,
  license_or_terms: null,
  description: null,
  is_official: true,
  is_active: true,
};
const response = (status: string, rejected = 0) => ({
  job_id: 'job-1',
  status,
  features_read: 9,
  features_valid: 9 - rejected,
  features_updated: 0,
  features_rejected: rejected,
  errors: rejected
    ? [{ row_number: 3, error_code: 'INVALID_GEOMETRY_FEATURE', message: 'Geometría inválida' }]
    : [],
});
const renderPage = () =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <GeographyImportPage />
    </QueryClientProvider>,
  );

describe('GeographyImportPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiRequest).mockResolvedValue([source] as never);
  });
  it('valida primero con PARISH, dpa_code y sin reparación silenciosa', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(response('VALIDATED')), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText('Fuente oficial'));
    await user.click(screen.getByRole('option', { name: /Límites oficiales/ }));
    const file = new File(
      ['{"type":"FeatureCollection","features":[]}'],
      'GUALACEO_PARROQUIAS_CANONICAL.geojson',
      { type: 'application/geo+json' },
    );
    fireEvent.change(screen.getByLabelText('SELECCIONAR GEOJSON'), { target: { files: [file] } });
    expect(screen.getByText(file.name)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'EJECUTAR' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'VALIDAR' }));
    await waitFor(() => expect(screen.getByText(/Resultado · VALIDATED/)).toBeInTheDocument());
    const [, options] = vi.mocked(fetch).mock.calls[0];
    const body = options?.body as FormData;
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/geometry-imports/validate');
    expect(body.get('territory_level')).toBe('PARISH');
    expect(body.get('dpa_code_property')).toBe('dpa_code');
    expect(body.get('allow_make_valid')).toBe('false');
    expect(screen.getByText(/Features leídas:/)).toHaveTextContent('9');
    expect(screen.getByRole('button', { name: 'EJECUTAR' })).toBeEnabled();
  });
  it('mantiene EJECUTAR deshabilitado si hay features rechazadas', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(response('REJECTED', 1)), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText('Fuente oficial'));
    await user.click(screen.getByRole('option', { name: /Límites oficiales/ }));
    fireEvent.change(screen.getByLabelText('SELECCIONAR GEOJSON'), {
      target: { files: [new File(['x'], 'bad.geojson')] },
    });
    await user.click(screen.getByRole('button', { name: 'VALIDAR' }));
    expect(await screen.findByText(/Geometría inválida/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'EJECUTAR' })).toBeDisabled();
  });
  it('ejecuta el mismo archivo únicamente después de validación limpia', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify(response('VALIDATED')), { status: 200 }))
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ ...response('COMPLETED'), features_updated: 9 }), {
            status: 200,
          }),
        ),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText('Fuente oficial'));
    await user.click(screen.getByRole('option', { name: /Límites oficiales/ }));
    fireEvent.change(screen.getByLabelText('SELECCIONAR GEOJSON'), {
      target: { files: [new File(['x'], 'official.geojson')] },
    });
    await user.click(screen.getByRole('button', { name: 'VALIDAR' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'EJECUTAR' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'EJECUTAR' }));
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls[1][0]).toBe('/api/v1/geometry-imports/execute'),
    );
  });
});
