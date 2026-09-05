import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { CampaignProvider } from '../../app/CampaignProvider';
import DebateAssistantPage from './DebateAssistantPage';
import type { ReportPreview } from '../reports/types';
import type { ClaimCheckResponse } from './types';

function briefFixture(): ReportPreview {
  return {
    report_kind: 'DEBATE_BRIEF_REPORT',
    title: 'Preparación para debate · Vialidad',
    subtitle: null,
    generated_at: '2026-08-20',
    generated_by: 'usuario',
    is_demo: false,
    narrative: {
      titulo_sugerido: 'Preparación para debate · Vialidad',
      resumen_ejecutivo:
        'Se registraron actividades y necesidades relacionadas con vialidad en el período analizado.',
      hallazgos_principales: ['3 necesidades relacionadas con vialidad.'],
      limitations: ['Redacción determinística: proveedor de IA no disponible en este momento.'],
      provider: 'deterministic-fallback',
    },
    sections: [
      {
        title: 'Datos oficiales',
        headers: ['Indicador', 'Valor', 'Fuente'],
        rows: [['Padrón electoral actual', '34.784', 'Padrón electoral actual']],
      },
      {
        title: 'Preguntas que podrían surgir',
        headers: ['Pregunta', 'Hechos disponibles', 'Respuesta factual sugerida', 'Fuentes'],
        rows: [
          [
            '¿Qué evidencia existe sobre el estado de vialidad?',
            'Recorrido vial',
            'Existen 1 actividades registradas.',
            'Recorrido vial',
          ],
        ],
      },
    ],
    citations: [],
    limitations: ['Informe descriptivo generado por Territorio Electoral.'],
  };
}

const server = setupServer(
  http.get('*/api/v1/parishes', () =>
    HttpResponse.json([{ id: 1, name: 'Gualaceo', dpa_code: '010350' }]),
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
        <MemoryRouter initialEntries={['/app/campaigns/campaign-1/debate']}>
          <Routes>
            <Route path="/app/campaigns/:campaignId/debate" element={<DebateAssistantPage />} />
          </Routes>
        </MemoryRouter>
      </CampaignProvider>
    </QueryClientProvider>,
  );
}

describe('Preparación para debate', () => {
  it('muestra el configurador con el tema por defecto', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Preparación para debate' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Generar briefing' })).toBeEnabled();
  });

  it('genera el briefing y muestra las preguntas factuales con fuentes', async () => {
    server.use(
      http.post('*/api/v1/campaigns/campaign-1/reports/preview', () =>
        HttpResponse.json(briefFixture()),
      ),
    );
    renderPage();
    await screen.findByRole('heading', { name: 'Preparación para debate' });
    await userEvent.click(screen.getByRole('button', { name: 'Generar briefing' }));
    expect(await screen.findByText(/Se registraron actividades y necesidades/)).toBeVisible();
    expect(screen.getByText('Datos oficiales')).toBeVisible();
    expect(screen.getByText('Preguntas que podrían surgir')).toBeVisible();
    expect(screen.getByText('¿Qué evidencia existe sobre el estado de vialidad?')).toBeVisible();
  });

  it('verifica una afirmación y muestra el veredicto sin usar verdadero/falso', async () => {
    const claimResponse: ClaimCheckResponse = {
      claim_text: 'En Gualaceo hay 43.188 habitantes.',
      verdict: 'SUPPORTED',
      verdict_label: 'RESPALDADA',
      evidence: [
        {
          id: '1',
          title: 'Población total',
          source_name: 'INEC',
          evidence_class: 'OFFICIAL',
          source_label: 'Oficial',
          record_date: '2022-01-01',
          external_url: null,
        },
      ],
      warnings: ['El dato corresponde al año 2022.'],
    };
    server.use(
      http.post('*/api/v1/campaigns/campaign-1/debate/claim-check', () =>
        HttpResponse.json(claimResponse),
      ),
    );
    renderPage();
    await screen.findByRole('heading', { name: 'Preparación para debate' });
    await userEvent.type(
      screen.getByLabelText('Afirmación a verificar'),
      'En Gualaceo hay 43.188 habitantes.',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Verificar afirmación' }));
    expect(await screen.findByText('RESPALDADA')).toBeVisible();
    expect(screen.getByText('Población total')).toBeVisible();
    expect(screen.queryByText(/verdadero/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/falso/i)).not.toBeInTheDocument();
  });

  it('muestra un error cuando el briefing falla', async () => {
    server.use(
      http.post('*/api/v1/campaigns/campaign-1/reports/preview', () =>
        HttpResponse.json({ detail: 'Error' }, { status: 500 }),
      ),
    );
    renderPage();
    await screen.findByRole('heading', { name: 'Preparación para debate' });
    await userEvent.click(screen.getByRole('button', { name: 'Generar briefing' }));
    await waitFor(() => expect(screen.getByText('No se pudo generar el briefing.')).toBeVisible());
  });
});
