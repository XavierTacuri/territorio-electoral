import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import ReportRunDetailPage from './ReportRunDetailPage';
import type { ReportPreview, ReportRun } from './types';

function runFixture(overrides: Partial<ReportRun> = {}): ReportRun {
  return {
    id: 'run-1',
    campaign_id: 'campaign-1',
    template_code: 'CAMPAIGN_EXECUTIVE_REPORT',
    requested_format: 'PDF',
    status: 'COMPLETED',
    report_date: '2026-08-20',
    date_from: null,
    date_to: null,
    title: 'Informe base',
    artifact: {
      id: 'a1',
      format: 'PDF',
      original_download_name: 'informe.pdf',
      is_available: true,
    },
    filters: { parish_id: 3382, theme: null, include_surveys: true },
    ...overrides,
  };
}

function previewFixture(): ReportPreview {
  return {
    report_kind: 'CAMPAIGN_EXECUTIVE_REPORT',
    title: 'Informe base',
    subtitle: null,
    generated_at: '2026-08-20',
    generated_by: 'usuario',
    is_demo: false,
    narrative: {
      titulo_sugerido: 'Informe',
      resumen_ejecutivo: 'Resumen',
      hallazgos_principales: [],
      limitations: [],
      provider: 'deterministic-fallback',
    },
    sections: [],
    citations: [],
    limitations: [],
  };
}

const server = setupServer(
  http.get('*/api/v1/campaigns/campaign-1/reports/run-1', () => HttpResponse.json(runFixture())),
  http.get('*/api/v1/campaigns/campaign-1/reports/run-1/preview', () =>
    HttpResponse.json(previewFixture()),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/campaigns/campaign-1/reports/run-1']}>
        <Routes>
          <Route
            path="/app/campaigns/:campaignId/reports/:runId"
            element={<ReportRunDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Detalle de informe', () => {
  it('no muestra aviso de actualización cuando no hay alertas de informe', async () => {
    server.use(
      http.get('*/api/v1/campaigns/campaign-1/alerts', () =>
        HttpResponse.json({ items: [], page: 1, page_size: 50, total: 0 }),
      ),
    );
    renderPage();
    await screen.findByRole('heading', { name: 'Detalle de informe' });
    expect(screen.queryByText(/información oficial más reciente/i)).not.toBeInTheDocument();
  });

  it('muestra el aviso de nueva versión disponible cuando existe una alerta de informe desactualizado', async () => {
    server.use(
      http.get('*/api/v1/campaigns/campaign-1/alerts', () =>
        HttpResponse.json({
          items: [
            {
              id: 'al1',
              resource_type: 'REPORT_RUN',
              resource_id: 'run-1',
              evidence: { reasons: ['nueva encuesta publicada (2026-08-25)'] },
            },
          ],
          page: 1,
          page_size: 50,
          total: 1,
        }),
      ),
    );
    renderPage();
    expect(await screen.findByText(/información oficial más reciente/i)).toBeVisible();
    expect(screen.getByText(/nueva encuesta publicada/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'GENERAR VERSIÓN ACTUALIZADA' })).toBeVisible();
  });

  it('el enlace de versión actualizada conserva parroquia, periodo e inclusiones originales', async () => {
    server.use(
      http.get('*/api/v1/campaigns/campaign-1/reports/run-1', () =>
        HttpResponse.json(
          runFixture({
            template_code: 'PARISH_TERRITORIAL_PROFILE',
            filters: {
              parish_id: 3382,
              date_from: '2026-08-01',
              date_to: '2026-08-31',
              include_surveys: true,
              include_public_intelligence: false,
            },
          }),
        ),
      ),
      http.get('*/api/v1/campaigns/campaign-1/alerts', () =>
        HttpResponse.json({
          items: [{ id: 'al1', resource_type: 'REPORT_RUN', resource_id: 'run-1', evidence: {} }],
          page: 1,
          page_size: 50,
          total: 1,
        }),
      ),
    );
    renderPage();
    const link = await screen.findByRole('link', { name: 'GENERAR VERSIÓN ACTUALIZADA' });
    const href = link.getAttribute('href') || '';
    expect(href).toContain('type=PARISH_TERRITORIAL_PROFILE');
    expect(href).toContain('parish_id=3382');
    expect(href).toContain('date_from=2026-08-01');
    expect(href).toContain('date_to=2026-08-31');
    expect(href).toContain('include_public_intelligence=false');
    expect(href).not.toContain('include_surveys=false');
  });
});
