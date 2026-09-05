import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { CampaignProvider } from '../../app/CampaignProvider';
import ReportCenterPage from './ReportCenterPage';
import type { ReportPreview, ReportTypeInfo } from './types';

const REPORT_TYPES: ReportTypeInfo[] = [
  {
    code: 'CAMPAIGN_EXECUTIVE_REPORT',
    name: 'Informe ejecutivo de campaña',
    description: 'Resumen general de la campaña.',
    requires_parish: false,
    requires_theme: false,
    allowed_formats: ['PDF', 'XLSX'],
  },
  {
    code: 'PARISH_TERRITORIAL_PROFILE',
    name: 'Informe territorial por parroquia',
    description: 'Ficha narrativa de una parroquia.',
    requires_parish: true,
    requires_theme: false,
    allowed_formats: ['PDF', 'XLSX'],
  },
  {
    code: 'OPERATION_TERRITORIAL_REPORT',
    name: 'Informe de operación territorial',
    description: 'Actividades y cobertura.',
    requires_parish: false,
    requires_theme: false,
    allowed_formats: ['PDF', 'XLSX'],
  },
  {
    code: 'CURRENT_ELECTION_EXECUTIVE',
    name: 'Informe electoral descriptivo',
    description: 'Padrón y participación.',
    requires_parish: false,
    requires_theme: false,
    allowed_formats: ['PDF', 'XLSX'],
  },
  {
    code: 'THEMATIC_REPORT',
    name: 'Informe temático',
    description: 'Cruce por tema.',
    requires_parish: false,
    requires_theme: true,
    allowed_formats: ['PDF', 'XLSX'],
  },
];

function previewFixture(overrides: Partial<ReportPreview> = {}): ReportPreview {
  return {
    report_kind: 'CAMPAIGN_EXECUTIVE_REPORT',
    title: 'Informe de prueba',
    subtitle: null,
    generated_at: '2026-08-20',
    generated_by: 'usuario',
    is_demo: false,
    narrative: {
      titulo_sugerido: 'Informe ejecutivo de campaña',
      resumen_ejecutivo:
        'La campaña registró actividad territorial constante durante el período analizado.',
      hallazgos_principales: ['12 actividades completadas.', '5 necesidades registradas.'],
      limitations: ['Informe descriptivo generado por Territorio Electoral.'],
      provider: 'deterministic-fallback',
    },
    sections: [
      {
        title: 'Panorama operativo',
        headers: ['Indicador', 'Valor'],
        rows: [['Actividades completadas', 12]],
      },
    ],
    citations: [
      {
        id: 'a1',
        source_type: 'TERRITORIAL_ACTIVITY',
        title: 'Asamblea territorial',
        source_name: 'Territorio Electoral',
        source_url: null,
        deep_link: '/app/campaigns/campaign-1/activities/a1',
        evidence_class: 'CAMPAIGN',
        record_date: '2026-08-10',
      },
    ],
    limitations: ['Informe descriptivo generado por Territorio Electoral.'],
    ...overrides,
  };
}

const server = setupServer(
  http.get('*/api/v1/report-types', () => HttpResponse.json(REPORT_TYPES)),
  http.get('*/api/v1/parishes', () =>
    HttpResponse.json([{ id: 1, name: 'Gualaceo', dpa_code: '010350' }]),
  ),
  http.get('*/api/v1/campaigns/campaign-1/reports', () =>
    HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
beforeEach(() => {
  sessionStorage.setItem(
    'territorio.activeCampaign',
    JSON.stringify({
      id: 'campaign-1',
      organization_id: 'org-1',
      name: 'Campaña',
      canton_id: 1,
      office_type: 'MAYOR',
      election_name: 'Elección',
      election_date: '2027-02-14',
      status: 'ACTIVE',
    }),
  );
});
afterEach(() => {
  server.resetHandlers();
  sessionStorage.clear();
});
afterAll(() => server.close());

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CampaignProvider>
        <MemoryRouter initialEntries={['/app/campaigns/campaign-1/reports']}>
          <Routes>
            <Route path="/app/campaigns/:campaignId/reports" element={<ReportCenterPage />} />
          </Routes>
        </MemoryRouter>
      </CampaignProvider>
    </QueryClientProvider>,
  );
}

describe('Centro de Informes', () => {
  it('muestra el configurador con el tipo ejecutivo por defecto', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Centro de Informes' })).toBeVisible();
    expect(await screen.findByText('Resumen general de la campaña.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Generar' })).toBeEnabled();
  });

  it('genera la previsualización y muestra resumen, hallazgos y citas', async () => {
    server.use(
      http.post('*/api/v1/campaigns/campaign-1/reports/preview', () =>
        HttpResponse.json(previewFixture()),
      ),
    );
    renderPage();
    await screen.findByRole('heading', { name: 'Centro de Informes' });
    await userEvent.click(screen.getByRole('button', { name: 'Generar' }));
    expect(await screen.findByText(/La campaña registró actividad territorial/)).toBeVisible();
    expect(screen.getByText('12 actividades completadas.')).toBeVisible();
    expect(screen.getByText('Asamblea territorial')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Regenerar' })).toBeVisible();
  });

  it('muestra advertencia DEMO cuando el informe incluye datos simulados', async () => {
    server.use(
      http.post('*/api/v1/campaigns/campaign-1/reports/preview', () =>
        HttpResponse.json(previewFixture({ is_demo: true })),
      ),
    );
    renderPage();
    await screen.findByRole('heading', { name: 'Centro de Informes' });
    await userEvent.click(screen.getByRole('button', { name: 'Generar' }));
    expect(await screen.findByText(/datos simulados para demostración/i)).toBeVisible();
  });

  it('requiere parroquia para el informe territorial por parroquia', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Centro de Informes' });
    await userEvent.click(screen.getByLabelText('Tipo de informe'));
    await userEvent.click(
      await screen.findByRole('option', { name: 'Informe territorial por parroquia' }),
    );
    expect(await screen.findByText('Este informe requiere una parroquia.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Generar' })).toBeDisabled();
  });

  it('muestra un error cuando la previsualización falla', async () => {
    server.use(
      http.post('*/api/v1/campaigns/campaign-1/reports/preview', () =>
        HttpResponse.json({ detail: 'Error' }, { status: 500 }),
      ),
    );
    renderPage();
    await screen.findByRole('heading', { name: 'Centro de Informes' });
    await userEvent.click(screen.getByRole('button', { name: 'Generar' }));
    await waitFor(() =>
      expect(screen.getByText('No se pudo generar la previsualización.')).toBeVisible(),
    );
  });

  it('muestra un estado vacío cuando no hay informes generados', async () => {
    renderPage();
    expect(await screen.findByText('Aún no has generado informes en esta campaña.')).toBeVisible();
  });
});
