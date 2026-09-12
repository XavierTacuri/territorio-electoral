import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TerritorialIntelligencePage from './TerritorialIntelligencePage';

// El Expediente Territorial (TerritorialProfileContent) tiene su propia
// batería exhaustiva de pruebas en TerritorialProfileContent/TerritorialProfilePage;
// aquí solo importa que TerritorialIntelligencePage lo monte inline con los
// props correctos, así que se reemplaza por un marcador simple.
vi.mock('./TerritorialProfileContent', () => ({
  TerritorialProfileContent: ({
    campaignId,
    parishId,
  }: {
    campaignId: string;
    parishId: string;
  }) => (
    <h1>
      EXPEDIENTE TERRITORIAL — parroquia {parishId} de la campaña {campaignId}
    </h1>
  ),
}));

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

const auth = vi.hoisted(() => ({
  user: {
    id: 'u1',
    username: 'candidate',
    email: 'candidate@example.test',
    first_name: 'Candidata',
    last_name: 'Test',
    is_active: true,
    is_superuser: false,
    roles: [{ code: 'CANDIDATE', name: 'Candidato' }],
  } as { roles: { code: string; name: string }[]; is_superuser: boolean; [key: string]: unknown },
}));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ user: auth.user }) }));

beforeEach(() => {
  auth.user.roles = [{ code: 'CANDIDATE', name: 'Candidato' }];
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

function renderPage(assignedParishes: typeof parishes = parishes, initialPath?: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  client.setQueryData(['current-election-analysis', 'campaign-1'], {
    ...analysis,
    parishes: assignedParishes,
  });
  client.setQueryData(['territory-operation-summary', 'campaign-1'], operation);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath ?? '/app/campaigns/campaign-1/territories']}>
        <LocationDisplay />
        <Routes>
          <Route
            path="/app/campaigns/:campaignId/territories/:parishId?"
            element={<TerritorialIntelligencePage />}
          />
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

  it('al elegir una parroquia, el Expediente aparece debajo del mismo selector sin navegar a otra pantalla', async () => {
    renderPage();
    const user = userEvent.setup();
    const input = screen.getByLabelText('Seleccionar parroquia');
    await user.click(input);
    await user.click(screen.getByRole('option', { name: /Jadán/ }));

    expect(
      await screen.findByRole('heading', { level: 1, name: /EXPEDIENTE TERRITORIAL/ }),
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: 'VER EXPEDIENTE' })).not.toBeInTheDocument();
    // El selector de parroquia sigue visible: el contexto no se pierde.
    expect(screen.getByLabelText('Seleccionar parroquia')).toBeInTheDocument();
    // La comparación multi-parroquia se oculta mientras hay una selección activa.
    expect(screen.queryByRole('heading', { name: 'COMPARAR TERRITORIOS' })).not.toBeInTheDocument();
    // La URL refleja la parroquia seleccionada (deep link / refresh / back-forward).
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/app/campaigns/campaign-1/territories/1',
    );
  });

  it('deep link directo a una parroquia renderiza el Expediente inline de una vez', async () => {
    renderPage(parishes, '/app/campaigns/campaign-1/territories/2');
    expect(
      await screen.findByRole('heading', { level: 1, name: /EXPEDIENTE TERRITORIAL/ }),
    ).toBeVisible();
    expect(screen.getByLabelText('Seleccionar parroquia')).toBeInTheDocument();
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
  it('la comparación muestra exactamente 5 indicadores, sin LOW/HIGH/histórico/densidad/edad/crecimiento', async () => {
    renderPage();
    const user = userEvent.setup();
    const input = screen.getByLabelText('Seleccione entre 2 y 3 parroquias');
    for (const name of ['Jadán', 'Zhidmad']) {
      await user.click(input);
      await user.click(screen.getByRole('option', { name: new RegExp(name) }));
    }
    const [, ...bodyRows] = screen.getAllByRole('row');
    const labels = bodyRows.map((row) => within(row).getAllByRole('cell')[0].textContent);
    expect(labels).toEqual([
      'Electores actuales',
      'Votantes esperados',
      'Población',
      'Actividades',
      'Necesidades',
    ]);
    for (const removed of [
      'LOW',
      'HIGH',
      'CENTRAL',
      'Participación 2019',
      'Densidad',
      'Crecimiento',
    ]) {
      expect(screen.queryByText(removed)).not.toBeInTheDocument();
    }
    // Votantes esperados viene de la proyección V1 ya persistida por el
    // backend (expected_voters_central), nunca recalculada en el frontend.
    const votantesRow = bodyRows[1];
    expect(votantesRow).toHaveTextContent('761');
    expect(votantesRow).toHaveTextContent('762');
  });

  it('no presenta la comparación como un ranking', async () => {
    renderPage();
    expect(
      screen.getByText(/no constituye un ranking ni una recomendación de prioridad electoral/i),
    ).toBeVisible();
  });
});

describe('inteligencia territorial · TERRITORIAL_COORDINATOR', () => {
  beforeEach(() => {
    auth.user.roles = [{ code: 'TERRITORIAL_COORDINATOR', name: 'Coordinador territorial' }];
  });

  it('con una sola parroquia asignada, redirige directo al Expediente sin selector ni comparación', async () => {
    renderPage([parishes[0]]);
    expect(
      await screen.findByRole('heading', { level: 1, name: /EXPEDIENTE TERRITORIAL/ }),
    ).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'COMPARAR TERRITORIOS' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'VER EXPEDIENTE' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Seleccionar parroquia')).not.toBeInTheDocument();
  });

  it('con varias parroquias asignadas, un selector simple abre el Expediente de inmediato', async () => {
    renderPage([parishes[0], parishes[2]]);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'INTELIGENCIA TERRITORIAL' }),
    ).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'COMPARAR TERRITORIOS' })).not.toBeInTheDocument();
    const input = screen.getByLabelText('Seleccionar parroquia');
    const user = userEvent.setup();
    await user.click(input);
    await user.click(screen.getByRole('option', { name: /San Juan/ }));
    expect(
      await screen.findByRole('heading', { level: 1, name: /EXPEDIENTE TERRITORIAL/ }),
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: 'VER EXPEDIENTE' })).not.toBeInTheDocument();
    // A diferencia de Candidate/Manager, el coordinador no conserva el selector
    // visible una vez dentro del Expediente: su experiencia no cambia.
    expect(screen.queryByLabelText('Seleccionar parroquia')).not.toBeInTheDocument();
  });

  it('sin parroquias asignadas, muestra un mensaje orientador en vez de la comparación', async () => {
    renderPage([]);
    expect(
      await screen.findByText('No tienes parroquias asignadas para esta campaña.'),
    ).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'COMPARAR TERRITORIOS' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Seleccionar parroquia')).not.toBeInTheDocument();
  });

  it('no solicita el resumen de operaciones territoriales (usado solo por la comparación)', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
    });
    client.setQueryData(['current-election-analysis', 'campaign-1'], {
      ...analysis,
      parishes: [parishes[0], parishes[2]],
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/app/campaigns/campaign-1/territories']}>
          <Routes>
            <Route
              path="/app/campaigns/:campaignId/territories/:parishId?"
              element={<TerritorialIntelligencePage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 1, name: 'INTELIGENCIA TERRITORIAL' }),
      ).toBeVisible(),
    );
    // `enabled: false` still registers a query observer (status "pending"),
    // but it must never actually fetch.
    const state = client.getQueryState(['territory-operation-summary', 'campaign-1']);
    expect(state?.fetchStatus).toBe('idle');
    expect(state?.dataUpdateCount).toBe(0);
  });
});
