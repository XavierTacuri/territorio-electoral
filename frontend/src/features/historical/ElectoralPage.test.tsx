import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import ElectoralPage from './ElectoralPage';

const server = setupServer();
const nativeFetch = globalThis.fetch;
const process = {
  id: 'process-1',
  code: 'SEC_2023',
  name: 'Elecciones Seccionales 2023',
  process_type: 'SECTIONAL',
  year: 2023,
  election_date: '2023-02-05',
  status: 'VALIDATED',
  is_final: true,
};
const contest = {
  id: 'contest-1',
  name: 'MAYOR_GUALACEO',
  office_type: 'MAYOR',
  vote_method: 'SINGLE_CHOICE',
  canton_id: 10,
};
const parishNames = [
  ['010350', 'Gualaceo'],
  ['010352', 'Daniel Córdova Toral'],
  ['010353', 'Jadán'],
  ['010354', 'Mariano Moreno'],
  ['010356', 'Remigio Crespo Toral'],
  ['010357', 'San Juan'],
  ['010358', 'Zhidmad'],
  ['010359', 'Luis Cordero Vega'],
  ['010360', 'Simón Bolívar'],
] as const;
const candidates = [
  ['candidate-1', 'Marco Tapia', 30],
  ['candidate-2', 'Pedro Lopez', 25],
  ['candidate-3', 'Gustavo Vera', 15],
  ['candidate-4', 'Omar Alvarado', 10],
  ['candidate-5', 'Carlos Ordoñez', 10],
] as const;

function fixture(unmapped = true) {
  const geographies = parishNames.map(([code], index) => ({
    id: `geo-${index + 1}`,
    level: 'PARISH',
    external_code: code,
    name: code,
    parish_id: unmapped && index === 1 ? null : index + 1,
    canton_id: 10,
    is_mapped: !(unmapped && index === 1),
  }));
  const parishes = parishNames
    .map(([dpa, name], index) => ({
      id: index + 1,
      canton_id: 10,
      dpa_code: dpa,
      name,
      is_active: true,
    }))
    .filter((parish) => !unmapped || parish.id !== 2);
  const turnout = geographies.map((geo) => ({
    id: `turnout-${geo.id}`,
    electoral_geography_id: geo.id,
    aggregation_level: 'PARISH',
    registered_voters: 100,
    ballots_cast: 80,
    absentee_count: 20,
    valid_votes: 70,
    blank_votes: 5,
    null_votes: 5,
  }));
  const results = geographies.flatMap((geo) =>
    candidates.map(([id, name, votes], index) => ({
      candidate: {
        id,
        external_code: `C${index + 1}`,
        full_name: name,
        display_name: null,
        list_number: String(index + 1),
      },
      organization: {
        id: `org-${index + 1}`,
        name: `Organización ${index + 1}`,
        short_name: index === 0 ? 'ASI' : null,
        list_number: String(index + 1),
      },
      votes,
      geography_id: geo.id,
      geography_code: geo.external_code,
      geography_name: geo.name,
      geography_level: geo.level,
    })),
  );
  return { geographies, parishes, turnout, results };
}

function handlers(data = fixture()) {
  server.use(
    http.get('*/api/v1/electoral-processes', () => HttpResponse.json([process])),
    http.get('*/api/v1/electoral-processes/process-1/contests', () => HttpResponse.json([contest])),
    http.get('*/api/v1/electoral-processes/process-1/geographies', () =>
      HttpResponse.json(data.geographies),
    ),
    http.get('*/api/v1/parishes', () => HttpResponse.json(data.parishes)),
    http.get('*/api/v1/cantons/10', () =>
      HttpResponse.json({ id: 10, name: 'Gualaceo', dpa_code: '0103' }),
    ),
    http.get('*/api/v1/electoral-processes/process-1/contests/contest-1/turnout', () =>
      HttpResponse.json(data.turnout),
    ),
    http.get('*/api/v1/electoral-processes/process-1/contests/contest-1/candidate-results', () =>
      HttpResponse.json(data.results),
    ),
  );
}

beforeAll(() => {
  class TestResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', TestResizeObserver);
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  server.close();
  vi.unstubAllGlobals();
  globalThis.fetch = nativeFetch;
});

function renderPage(data = fixture()) {
  handlers(data);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ElectoralPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function selectContest() {
  await userEvent.click(await screen.findByLabelText('Proceso'));
  await userEvent.click(await screen.findByRole('option', { name: /Elecciones Seccionales/ }));
  await userEvent.click(await screen.findByLabelText('Contienda'));
  await userEvent.click(await screen.findByRole('option', { name: 'MAYOR_GUALACEO' }));
  await screen.findByText('Resumen cantonal — Gualaceo');
}

describe('datos electorales históricos', () => {
  it('muestra nombres reales, DPA y nueve agrupaciones parroquiales', async () => {
    renderPage(fixture(false));
    await selectContest();
    expect(screen.getByText('Gualaceo')).toBeVisible();
    expect(screen.getByText(/DPA\s+010350/)).toBeVisible();
    expect(screen.getByText(/Daniel/)).toBeVisible();
    expect(screen.getByText(/DPA\s+010360/)).toBeVisible();
    expect(
      screen
        .getAllByRole('button')
        .filter((button) => button.getAttribute('aria-expanded') !== null),
    ).toHaveLength(9);
  });

  it('calcula KPIs cantonales, ordena candidatos y muestra ganador/margen', async () => {
    renderPage(fixture(false));
    await selectContest();
    expect(screen.getByText('Electores registrados')).toBeVisible();
    expect(screen.getByText('900')).toBeVisible();
    expect(screen.getByText('720')).toBeVisible();
    expect(screen.getAllByText('80,00 %').length).toBeGreaterThan(0);
    const rows = screen.getAllByRole('row');
    expect(rows[1]).toHaveTextContent('Marco Tapia');
    expect(rows[1]).toHaveTextContent('270');
    expect(screen.getByText('Ganador oficial histórico')).toBeVisible();
    expect(screen.getAllByText('Diferencia con segundo lugar: 45 votos (5,56 %)')).toHaveLength(1);
  });

  it('filtra una parroquia y deja visible solo su participación y resultados', async () => {
    renderPage(fixture(false));
    await selectContest();
    await userEvent.click(screen.getByLabelText('Parroquia'));
    await userEvent.click(await screen.findByRole('option', { name: 'Jadán' }));
    expect(await screen.findByText('Datos de Jadán')).toBeVisible();
    expect(screen.getByText('Resultados de la parroquia')).toBeVisible();
    expect(screen.queryByText('Resultados por parroquia')).not.toBeInTheDocument();
  });

  it('informa geografía sin mapear y la diferencia entre válidos y candidatos', async () => {
    renderPage();
    await selectContest();
    expect(screen.getByText('Parroquia sin mapear · DPA 010352')).toBeVisible();
    await userEvent.click(screen.getByText('Parroquia sin mapear · DPA 010352'));
    await waitFor(() =>
      expect(
        screen.getAllByText(/Los votos válidos registrados difieren en 20/).length,
      ).toBeGreaterThan(0),
    );
  });
});
