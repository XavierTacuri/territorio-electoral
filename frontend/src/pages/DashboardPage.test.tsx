import { useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardPage from './DashboardPage';

vi.mock('../features/historical/CurrentElectionMap', () => ({
  CurrentElectionMap: ({ onStatusChange }: { onStatusChange?: (status: string) => void }) => {
    useEffect(() => onStatusChange?.('success'), [onStatusChange]);
    return (
      <div role="region" aria-label="Mapa de elección actual">
        PANORAMA TERRITORIAL
      </div>
    );
  },
}));
vi.mock('../api/downloads', () => ({ downloadReport: vi.fn().mockResolvedValue(undefined) }));

const parishes = Array.from({ length: 9 }, (_, index) => ({
  parish_id: index + 1,
  name: index === 0 ? 'Gualaceo' : index === 8 ? 'Zhidmad' : `Parroquia ${index + 1}`,
  dpa_code: `01035${index}`,
  registered_voters_current: index === 0 ? 21085 : 1800 - index * 100,
  male_voters: 700,
  female_voters: 900,
  juntas: 10,
  historical_2019: { registered_voters: 1600, ballots_cast: 1100, turnout_rate: 0.6858 },
  historical_2023: { registered_voters: 1600, ballots_cast: 1150, turnout_rate: 0.7189 },
  projection: {
    low: 0.6808,
    central: index === 8 ? 0.7902 : 0.7 + index * 0.005,
    high: 0.7307,
    expected_voters_low: 1200,
    expected_voters_central: index === 0 ? 14970 : 1200,
    expected_voters_high: 1300,
  },
  data_quality_status: 'MEDIUM',
  demographics: {
    POP_TOTAL: index === 0 ? 43188 : 0,
    POP_MALE: index === 0 ? 19421 : 0,
    POP_FEMALE: index === 0 ? 23767 : 0,
    AGE_0_14: 800,
    AGE_15_29: 900,
    AGE_30_44: 800,
    AGE_45_64: 700,
    AGE_65_PLUS: 400,
  },
}));

const analysis = {
  context: {
    campaign_name: 'Gualaceo2026',
    canton_name: 'Gualaceo',
    election_name: 'Elecciones Seccionales y CPCCS 2027',
  },
  snapshot: {
    id: 'snapshot-1',
    snapshot_date: '2026-07-16',
    registered_voters: 34784,
    male_voters: 15432,
    female_voters: 19352,
    juntas: 112,
  },
  historical: {
    '2019': { registered_voters: 44019, ballots_cast: 30190, turnout_rate: 0.6858 },
    '2023': { registered_voters: 38406, ballots_cast: 27610, turnout_rate: 0.7189 },
  },
  projection: {
    model_code: 'TURNOUT_HISTORICAL_WEIGHTED_V1',
    model_version: '1.0',
    parameters: { historical_weight_old: '0.35', historical_weight_recent: '0.65' },
    expected_voters_low: 23680,
    expected_voters_central: 24697,
    expected_voters_high: 25416,
  },
  warnings: [{ code: 'REGISTRATION_SERIES_BREAK' }],
  demographics: { year: 2022, parishes },
  parishes,
};
const operational = {
  total_activities: 8,
  open_needs: 3,
  completed_activities: 5,
  planned_activities: 2,
  cancelled_activities: 1,
  activities_by_parish: [{ parish_id: 1 }, { parish_id: 2 }],
  needs_by_parish: [{ parish_id: 1 }],
  parishes_with_commitments: 2,
  commitments: { pending: 2, in_progress: 1, completed: 4, cancelled: 0 },
};

const server = setupServer(
  http.get('*/api/v1/campaigns/campaign-1/current-election/analysis', () =>
    HttpResponse.json(analysis),
  ),
  http.get('*/api/v1/campaigns/campaign-1/operational-summary', () =>
    HttpResponse.json(operational),
  ),
  http.post('*/api/v1/campaigns/campaign-1/reports/generate', () =>
    HttpResponse.json({ id: 'report-1', artifact: { original_download_name: 'informe.pdf' } }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
beforeEach(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderDashboard(seed = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (seed) {
    client.setQueryData(['current-election-analysis', 'campaign-1'], analysis);
    client.setQueryData(
      ['campaign', 'campaign-1', 'operational-summary', 'campaign-to-date'],
      operational,
    );
  } else {
    client.setQueryData(
      ['campaign', 'campaign-1', 'operational-summary', 'campaign-to-date'],
      operational,
    );
  }
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/campaigns/campaign-1/dashboard']}>
        <Routes>
          <Route path="/app/campaigns/:campaignId/dashboard" element={<DashboardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('dashboard ejecutivo', () => {
  it('muestra encabezado, analítica, mapa, contexto, calidad, operación y accesos', async () => {
    renderDashboard();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'TERRITORIO ELECTORAL' }),
    ).toBeVisible();
    expect(screen.getByText('Gualaceo2026')).toBeVisible();
    expect(screen.getByText('16/07/2026')).toBeVisible();
    expect(screen.getByText('34.784')).toBeVisible();
    expect(screen.getByText('15.432')).toBeVisible();
    expect(screen.getByText('19.352')).toBeVisible();
    expect(screen.getByText('24.697 votantes')).toBeVisible();
    expect(screen.getByText('23.680')).toBeVisible();
    expect(screen.getByText('25.416')).toBeVisible();
    expect(screen.getByText('68,58 %')).toBeVisible();
    expect(screen.getByText('71,89 %')).toBeVisible();
    expect(screen.getByRole('region', { name: 'Mapa de elección actual' })).toBeVisible();
    expect(screen.getByText('Mayor participación central')).toBeVisible();
    expect(screen.getAllByText('Zhidmad').length).toBeGreaterThan(0);
    expect(screen.getByText('43.188')).toBeVisible();
    expect(
      screen.getByText('Contexto territorial. No interviene en la fórmula de participación V1.'),
    ).toBeVisible();
    expect(screen.getByText('Variación significativa del registro electoral')).toBeVisible();
    expect(screen.getByText('TURNOUT_HISTORICAL_WEIGHTED_V1')).toBeVisible();
    expect(await screen.findByText('Necesidades abiertas')).toBeVisible();
    expect(screen.getByRole('link', { name: 'VER ELECCIÓN ACTUAL' })).toHaveAttribute(
      'href',
      '/app/campaigns/campaign-1/current-election',
    );
    expect(screen.getByRole('button', { name: 'Generar informe PDF' })).toBeVisible();
  });

  it('distingue loading y conserva operación ante error del análisis', async () => {
    server.use(
      http.get('*/api/v1/campaigns/campaign-1/current-election/analysis', async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return new HttpResponse(null, { status: 500 });
      }),
    );
    renderDashboard(false);
    expect(screen.getByRole('status', { name: 'Cargando dashboard ejecutivo' })).toBeVisible();
    expect(
      await screen.findByText('No fue posible cargar el análisis de la elección actual.'),
    ).toBeVisible();
    expect(await screen.findByText('OPERACIÓN TERRITORIAL')).toBeVisible();
    expect(screen.getByRole('button', { name: /reintentar/i })).toBeVisible();
  });

  it('genera el informe ejecutivo existente y presenta el estado', async () => {
    renderDashboard();
    const button = await screen.findByRole('button', { name: 'Generar informe PDF' });
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText('Generado: informe PDF')).toBeVisible());
  });
});
