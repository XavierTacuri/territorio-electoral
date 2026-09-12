import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import type { Parish } from './territoryShared';
import TerritorialProfilePage from './TerritorialProfilePage';

vi.mock('../../api/client', () => ({ apiRequest: vi.fn() }));
vi.mock('../../api/downloads', () => ({ downloadReport: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../historical/CurrentElectionMap', () => ({
  CurrentElectionMap: () => (
    <div role="region" aria-label="Mapa de elección actual">
      Mapa resaltado
    </div>
  ),
}));

const mockApiRequest = vi.mocked(apiRequest);

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
  mockApiRequest.mockResolvedValue(undefined);
});
afterEach(() => vi.restoreAllMocks());

const jadan: Parish = {
  parish_id: 1,
  name: 'Jadán',
  dpa_code: '010353',
  registered_voters_current: 3382,
  male_voters: 1620,
  female_voters: 1762,
  juntas: 9,
  historical_2019: { registered_voters: 3000, ballots_cast: 2400, turnout_rate: 0.8 },
  historical_2023: { registered_voters: 3200, ballots_cast: 2390, turnout_rate: 0.7469 },
  projection: {
    low: 0.72,
    central: 0.76,
    high: 0.81,
    expected_voters_low: 2435,
    expected_voters_central: 2570,
    expected_voters_high: 2740,
  },
  data_quality_status: 'MEDIUM',
  demographics: { POP_TOTAL: 4200, POP_MALE: 2100, POP_FEMALE: 2100 },
  demographics_2010: { POP_TOTAL: 3800 },
  population_growth_2010_2022: 0.105,
  availability: {
    cne_2019: true,
    cne_2023: true,
    current_registration: true,
    inec_2022: true,
    geometry: true,
  },
};
const sanJuanSinDatos: Parish = {
  ...jadan,
  parish_id: 2,
  name: 'San Juan',
  dpa_code: '010357',
  historical_2019: undefined,
  historical_2023: undefined,
  demographics: {},
  availability: { ...jadan.availability, inec_2022: false },
};
const analysis = {
  context: {
    campaign_name: 'Gualaceo 2026',
    canton_name: 'Gualaceo',
    election_name: 'Proceso sintético 2027',
  },
  snapshot: { snapshot_date: '2026-07-01' },
  projection: { model_code: 'TURNOUT_HISTORICAL_WEIGHTED_V1', model_version: '1.0' },
  warnings: [],
  sources: [{ code: 'CNE', institution: 'CNE', dataset_name: 'Padrón' }],
  parishes: [jadan, sanJuanSinDatos],
};
const operation = {
  parishes: [
    {
      parish_id: 1,
      activities: 3,
      needs_open: 2,
      needs_under_review: 1,
      needs_validated: 1,
      commitments_related: 1,
      needs_by_category: [{ category: 'Vialidad', count: 1 }],
      commitments_pending: 1,
      commitments_completed: 1,
      latest_activities: [],
      latest_needs: [],
      latest_commitments: [],
    },
  ],
};
const activitiesPage = {
  items: [
    {
      id: 'a1',
      campaign_id: 'campaign-1',
      activity_type_id: 1,
      title: 'Reunión territorial',
      activity_date: '2026-08-28',
      status: 'COMPLETED',
      approval_status: 'APPROVED',
      parish_id: 1,
      is_active: true,
      created_by_user_id: 'u1',
    },
  ],
  page: 1,
  page_size: 5,
  total: 3,
  total_pages: 1,
};
const needsPage = {
  items: [
    {
      id: 'n1',
      activity_id: null,
      need_category_id: 10,
      title: 'Vialidad rural',
      mentions_count: 2,
      priority: 'MEDIUM',
      urgency: 'MEDIUM',
      status: 'REPORTED',
      parish_id: 1,
      source_type: 'FIELD_VISIT',
      reported_date: '2026-08-27',
      assigned_to_user_id: null,
      is_active: true,
    },
  ],
  page: 1,
  page_size: 5,
  total: 2,
  total_pages: 1,
};
const studiesPage = {
  items: [
    {
      id: 's1',
      name: 'Encuesta general',
      fieldwork_end_date: '2026-08-20',
      sample_size_total: 400,
      pollster_name: 'Firma X',
    },
  ],
};
const publicItemsPage = { items: [] };
const needCategories = [{ id: 10, code: 'ROADS', name: 'Vialidad' }];
const cantonRow = { id: 5, province_id: 7, name: 'Gualaceo' };
const provinceRows = [{ id: 7, name: 'Azuay' }];

function seed(client: QueryClient, parishId: number, parish: typeof jadan) {
  client.setQueryData(['parish-access', String(parishId)], {
    id: parishId,
    name: parish.name,
    dpa_code: parish.dpa_code,
    parish_type: 'RURAL',
    canton_id: 5,
  });
  client.setQueryData(['canton', 5], cantonRow);
  client.setQueryData(['provinces'], provinceRows);
  client.setQueryData(['current-election-analysis', 'campaign-1'], analysis);
  client.setQueryData(['territory-operation-summary', 'campaign-1'], operation);
  client.setQueryData(['territory-activities', 'campaign-1', String(parishId)], activitiesPage);
  client.setQueryData(['territory-needs', 'campaign-1', String(parishId)], needsPage);
  client.setQueryData(['need-categories'], needCategories);
  client.setQueryData(['territory-survey-studies', 'campaign-1', String(parishId)], studiesPage);
  client.setQueryData(['territory-public-items', 'campaign-1', String(parishId)], publicItemsPage);
}

function renderPage(
  parishId = 1,
  seedClient: (client: QueryClient) => void = (c) => seed(c, parishId, jadan),
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  seedClient(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/app/campaigns/campaign-1/territories/${parishId}`]}>
        <Routes>
          <Route
            path="/app/campaigns/:campaignId/territories/:parishId"
            element={<TerritorialProfilePage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('expediente territorial', () => {
  it('muestra encabezado, breadcrumb y KPIs', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' }),
    ).toBeVisible();
    expect(screen.getByText('Centro de Comando')).toBeVisible();
    expect(screen.getByText('Inteligencia territorial')).toBeVisible();
    expect(screen.getAllByText('Jadán').length).toBeGreaterThan(0);
    expect(screen.getAllByText('3.382').length).toBeGreaterThan(0);
    expect(screen.getByRole('region', { name: 'Mapa de elección actual' })).toBeVisible();
    expect(screen.getAllByText('Electores actuales').length).toBeGreaterThan(0);
    expect(screen.getByText('Votantes esperados')).toBeVisible();
    expect(screen.getAllByText('Datos oficiales del CNE').length).toBeGreaterThan(0);
    expect(screen.getByText('Estimación de participación')).toBeVisible();
    expect(screen.getByText('Bajo')).toBeVisible();
    expect(screen.getByText('Estimado')).toBeVisible();
    expect(screen.getByText('Alto')).toBeVisible();
    expect(screen.getByText('Estimación basada en elecciones anteriores')).toBeVisible();
    expect(screen.queryByText(/OBSERVADO · CNE/)).not.toBeInTheDocument();
    expect(screen.queryByText(/PROYECTADO · ESCENARIOS V1/)).not.toBeInTheDocument();
    expect(screen.queryByText(/TURNOUT_HISTORICAL_WEIGHTED_V1/)).not.toBeInTheDocument();
    expect(screen.queryByText('BAJO')).not.toBeInTheDocument();
    expect(screen.queryByText('CENTRAL')).not.toBeInTheDocument();
    expect(screen.queryByText('ALTO')).not.toBeInTheDocument();
    expect(screen.queryByText('Padrón electoral')).not.toBeInTheDocument();
  });
  it('muestra "Sin datos disponibles" en vez de un cero artificial cuando falta información', async () => {
    renderPage(2, (c) => seed(c, 2, sanJuanSinDatos));
    await screen.findByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' });
    expect(screen.getAllByText('Sin datos disponibles').length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        'No existen resultados históricos desagregados disponibles para esta parroquia.',
      ),
    ).toBeVisible();
  });
  it('presenta un 403 cuando el backend deniega el acceso territorial', async () => {
    mockApiRequest.mockRejectedValueOnce(new ApiError(403, 'No tienes permisos para esta acción.'));
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/app/campaigns/campaign-1/territories/9']}>
          <Routes>
            <Route
              path="/app/campaigns/:campaignId/territories/:parishId"
              element={<TerritorialProfilePage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('403')).toBeVisible();
    expect(screen.getByText('No tienes acceso territorial a esta parroquia.')).toBeVisible();
  });
  it('mantiene el resto del expediente visible si falla una sección independiente', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
    });
    seed(client, 1, jadan);
    client.setQueryData(['territory-needs', 'campaign-1', '1'], undefined);
    client.removeQueries({ queryKey: ['territory-needs', 'campaign-1', '1'] });
    mockApiRequest.mockImplementation((path: string) => {
      if (path.includes('/needs?')) return Promise.reject(new ApiError(500, 'Error'));
      return Promise.resolve(undefined);
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/app/campaigns/campaign-1/territories/1']}>
          <Routes>
            <Route
              path="/app/campaigns/:campaignId/territories/:parishId"
              element={<TerritorialProfilePage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      await screen.findByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' }),
    ).toBeVisible();
    expect(
      await screen.findByText(
        'No fue posible cargar las necesidades territoriales.',
        {},
        { timeout: 5000 },
      ),
    ).toBeVisible();
    expect(screen.getByRole('heading', { name: 'OPERACIÓN TERRITORIAL' })).toBeVisible();
  });
  it('no incluye la sección de Seguimientos retirada del expediente', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' });
    expect(
      screen.queryByRole('heading', { name: 'SEGUIMIENTOS DE CAMPAÑA' }),
    ).not.toBeInTheDocument();
  });
  it('filtra la cronología territorial', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' });
    expect(screen.getByRole('heading', { name: 'CRONOLOGÍA TERRITORIAL' })).toBeVisible();
    expect(screen.getByText('Reunión territorial · Completada')).toBeVisible();
    const activitiesFilter = screen.getByRole('button', { name: 'Actividades' });
    activitiesFilter.click();
    expect(screen.getByText('Reunión territorial · Completada')).toBeVisible();
  });
  it('ofrece preguntas sugeridas de Territorio IA con deep link', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' });
    const link = screen.getByText('¿Qué necesidades se han registrado en Jadán?');
    expect(link.closest('a')).toHaveAttribute(
      'href',
      expect.stringContaining('/app/campaigns/campaign-1/territory-ai?parish_id=1'),
    );
  });
});

describe('expediente territorial · TERRITORIAL_COORDINATOR', () => {
  beforeEach(() => {
    auth.user.roles = [{ code: 'TERRITORIAL_COORDINATOR', name: 'Coordinador territorial' }];
  });

  it('no ofrece ninguna acción de Territorio IA ni de generación de informes, pero conserva el mapa', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' }),
    ).toBeVisible();
    expect(screen.queryByText('PREGUNTAR A TERRITORIO IA')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'TERRITORIO IA' })).not.toBeInTheDocument();
    expect(
      screen.queryByText('¿Qué necesidades se han registrado en Jadán?'),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'DESCARGAR EXPEDIENTE' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'GENERAR PDF' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'GENERAR XLSX' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'GENERAR INFORME EN EL CENTRO DE INFORMES' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'VER EN MAPA' })).toBeVisible();
    expect(screen.getAllByText('Jadán').length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: 'FUENTES' })).toBeVisible();
  });
});
