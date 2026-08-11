import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TerritorialIntelligencePage from './TerritorialIntelligencePage';

vi.mock('../historical/CurrentElectionMap', () => ({
  CurrentElectionMap: () => (
    <div role="region" aria-label="Mapa de elección actual">
      Mapa resaltado
    </div>
  ),
}));
vi.mock('../../api/downloads', () => ({ downloadReport: vi.fn().mockResolvedValue(undefined) }));

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

function renderPage(path = '/app/campaigns/campaign-1/territories/1') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  client.setQueryData(['current-election-analysis', 'campaign-1'], analysis);
  client.setQueryData(['territory-operation-summary', 'campaign-1'], operation);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/app/campaigns/:campaignId/territories"
            element={<TerritorialIntelligencePage />}
          />
          <Route
            path="/app/campaigns/:campaignId/territories/:parishId"
            element={<TerritorialIntelligencePage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.restoreAllMocks());

describe('inteligencia territorial', () => {
  it('abre deep link y muestra ficha, histórico, proyección, INEC, mapa, calidad y operación', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'INTELIGENCIA TERRITORIAL' }),
    ).toBeVisible();
    expect(screen.getByRole('heading', { name: /JADÁN.*DPA 010351/ })).toBeVisible();
    for (const title of [
      'REGISTRO ELECTORAL',
      'PARTICIPACIÓN HISTÓRICA',
      'PROYECCIÓN DE PARTICIPACIÓN',
      'CONTEXTO TERRITORIAL',
      'CALIDAD DEL ANÁLISIS',
      'OPERACIÓN TERRITORIAL',
    ])
      expect(screen.getByRole('heading', { name: title })).toBeVisible();
    expect(screen.getByText('¿CÓMO SE CALCULÓ?')).toBeVisible();
    expect(screen.getByRole('region', { name: 'Mapa de elección actual' })).toBeVisible();
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
  it('ofrece PDF y XLSX territorial', async () => {
    renderPage();
    expect(screen.getByRole('button', { name: 'GENERAR FICHA PDF' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'GENERAR FICHA XLSX' })).toBeVisible();
  });
});
