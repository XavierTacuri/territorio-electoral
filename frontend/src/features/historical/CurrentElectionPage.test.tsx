import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { CampaignProvider } from '../../app/CampaignProvider';
import CurrentElectionPage from './CurrentElectionPage';

const server = setupServer(
  http.get('/api/v1/campaigns/campaign-1/current-election/analysis', () =>
    HttpResponse.json({
      snapshot: {
        id: 'snapshot-1',
        snapshot_date: '2026-06-01',
        registered_voters: 100,
        male_voters: 40,
        female_voters: 60,
        juntas: 1,
      },
      historical: {
        '2019': { registered_voters: 100, ballots_cast: 68, turnout_rate: 0.68 },
        '2023': { registered_voters: 100, ballots_cast: 72, turnout_rate: 0.72 },
      },
      projection: {
        model_code: 'TURNOUT_HISTORICAL_WEIGHTED_V1',
        model_version: '1.0',
        parameters: { historical_weight_old: '0.35', historical_weight_recent: '0.65' },
        expected_voters_low: 68,
        expected_voters_central: 71,
        expected_voters_high: 72,
      },
      warnings: [],
      parishes: [
        {
          parish_id: 1,
          name: 'San Juan',
          dpa_code: '010357',
          registered_voters_current: 100,
          male_voters: 40,
          female_voters: 60,
          juntas: 1,
          historical_2019: { registered_voters: 100, ballots_cast: 68, turnout_rate: 0.68 },
          historical_2023: { registered_voters: 100, ballots_cast: 72, turnout_rate: 0.72 },
          projection: {
            low: 0.68,
            central: 0.71,
            high: 0.72,
            expected_voters_low: 68,
            expected_voters_central: 71,
            expected_voters_high: 72,
          },
          data_quality_status: 'HIGH',
          demographics: { AGE_0_14: 10 },
        },
      ],
      demographics: { year: 2022, parishes: [] },
    }),
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

describe('elección actual', () => {
  it('muestra snapshot observado, escenarios proyectados y explicación', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <CampaignProvider>
          <MemoryRouter initialEntries={['/app/campaigns/campaign-1/current-election']}>
            <Routes>
              <Route
                path="/app/campaigns/:campaignId/current-election"
                element={<CurrentElectionPage />}
              />
            </Routes>
          </MemoryRouter>
        </CampaignProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('REGISTRO ELECTORAL ACTUAL')).toBeInTheDocument();
    expect(await screen.findByText('Escenario central')).toBeInTheDocument();
    expect(screen.getAllByText(/OBSERVADO/).length).toBeGreaterThan(0);
    expect(screen.getByText(/PROYECTADO/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'GENERAR INFORME PDF' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'GENERAR INFORME XLSX' })).toBeVisible();
    expect(document.body.textContent).not.toMatch(/Ã|Â|�/);
  });
});
