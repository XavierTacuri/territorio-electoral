import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TerritorialIntelligencePage from './TerritorialIntelligencePage';

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

const parish = (id: number, name: string, central: number) => ({
  parish_id: id,
  name,
  dpa_code: `01035${id}`,
  registered_voters_current: 1000 + id,
  male_voters: 480,
  female_voters: 521,
  juntas: 5,
  historical_2019: { registered_voters: 900, ballots_cast: 720, turnout_rate: 0.8 },
  historical_2023: { registered_voters: 950, ballots_cast: 710, turnout_rate: 0.7474 },
  projection: {
    low: 0.72,
    central,
    high: 0.81,
    expected_voters_low: 720,
    expected_voters_central: 760 + id,
    expected_voters_high: 810,
  },
  data_quality_status: 'MEDIUM',
  demographics: {
    POP_TOTAL: 1400,
    POP_MALE: 680,
    POP_FEMALE: 720,
    AGE_0_14: 300,
    AGE_15_29: 300,
    AGE_30_44: 280,
    AGE_45_64: 350,
    AGE_65_PLUS: 170,
    DENSITY: 80,
  },
  demographics_2010: { POP_TOTAL: 1200 },
  population_growth_2010_2022: 0.1667,
  availability: {
    cne_2019: true,
    cne_2023: true,
    current_registration: true,
    inec_2022: true,
    geometry: true,
  },
});
const parishes = [
  parish(1, 'Jadán', 0.7642),
  parish(2, 'Zhidmad', 0.7902),
  parish(3, 'San Juan', 0.6703),
  parish(4, 'Parroquia Alfa', 0.7),
];
const analysis = {
  context: {
    campaign_name: 'Campaña sintética',
    canton_name: 'Cantón sintético',
    election_name: 'Proceso sintético 2027',
  },
  snapshot: { snapshot_date: '2026-07-01' },
  projection: { model_code: 'TURNOUT_HISTORICAL_WEIGHTED_V1', model_version: '1.0' },
  warnings: [],
  sources: [{ code: 'E2E', institution: 'Fuente sintética', dataset_name: 'Dataset territorial' }],
  parishes,
};
const operation = {
  parishes: parishes.map((p) => ({
    parish_id: p.parish_id,
    activities: p.parish_id,
    needs_open: 1,
    commitments_pending: 1,
    commitments_completed: 0,
    latest_activities: [],
    latest_needs: [],
    latest_commitments: [],
  })),
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  client.setQueryData(['current-election-analysis', 'campaign-1'], analysis);
  client.setQueryData(['territory-operation-summary', 'campaign-1'], operation);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/campaigns/campaign-1/territories']}>
        <Routes>
          <Route
            path="/app/campaigns/:campaignId/territories"
            element={<TerritorialIntelligencePage />}
          />
          <Route path="/app/campaigns/:campaignId/territories/:parishId" element={<div>Expediente</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.restoreAllMocks());

describe('inteligencia territorial', () => {
  it('muestra el panorama comparado y permite elegir una parroquia', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'INTELIGENCIA TERRITORIAL' }),
    ).toBeVisible();
    expect(screen.getByRole('heading', { name: 'COMPARAR TERRITORIOS' })).toBeVisible();
  });
  it('navega al expediente al elegir una parroquia', async () => {
    renderPage();
    const user = userEvent.setup();
    const input = screen.getByLabelText('Seleccionar parroquia');
    await user.click(input);
    await user.click(screen.getByRole('option', { name: /Jadán/ }));
    await user.click(screen.getByRole('button', { name: 'VER EXPEDIENTE' }));
    expect(await screen.findByText('Expediente')).toBeVisible();
  });
  it('compara tres parroquias y bloquea una cuarta', async () => {
    renderPage();
    const user = userEvent.setup();
    const input = screen.getByLabelText('Seleccione entre 2 y 3 parroquias');
    for (const name of ['Jadán', 'Zhidmad', 'San Juan']) {
      await user.click(input);
      await user.click(screen.getByRole('option', { name: new RegExp(name) }));
    }
    expect(screen.getByRole('columnheader', { name: 'Jadán' })).toBeVisible();
    expect(screen.getByRole('columnheader', { name: 'Zhidmad' })).toBeVisible();
    expect(screen.getByRole('columnheader', { name: 'San Juan' })).toBeVisible();
    expect(screen.getAllByRole('columnheader')).toHaveLength(4);
    await user.click(input);
    expect(screen.getByRole('option', { name: /Parroquia Alfa/ })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });
  it('no presenta la comparación como un ranking', async () => {
    renderPage();
    expect(
      screen.getByText(/no constituye un ranking ni una recomendación de prioridad electoral/i),
    ).toBeVisible();
  });
});
