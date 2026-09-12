import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ElectoralPanoramaPage from './ElectoralPanoramaPage';

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
});

const analysis = {
  snapshot: { registered_voters: 34784 },
  projection: { expected_voters_central: 24697 },
  historical: {
    '2019': { ballots_cast: 20000, turnout_rate: 0.68 },
    '2023': { ballots_cast: 21000, turnout_rate: 0.71 },
  },
  demographics: { year: 2022, parishes: [{ demographics: { POP_TOTAL: 40000 } }] },
};
const operation = {
  activities: { total: 8, completed: 4 },
  needs: { total: 5, open: 4 },
  commitments: { pending: 2, in_progress: 1 },
  coverage: { total_parishes: 9, with_activities: 7 },
};
const studies = { items: [] };
const publicSummary = { total_items: 0, recent_items: 0 };
const demoOperation = { ...operation, activities: { ...operation.activities, demo: 2 } };

function renderPage(operationOverride: typeof operation = operation) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  client.setQueryData(['panorama-analysis', 'campaign-1'], analysis);
  client.setQueryData(['panorama-operation', 'campaign-1'], operationOverride);
  client.setQueryData(['panorama-studies', 'campaign-1'], studies);
  client.setQueryData(['panorama-public', 'campaign-1'], publicSummary);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/campaigns/campaign-1/panorama']}>
        <Routes>
          <Route path="/app/campaigns/:campaignId/panorama" element={<ElectoralPanoramaPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Panorama electoral · CANDIDATE', () => {
  it('conserva los CTAs ejecutivos y las preguntas rápidas', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Panorama electoral' }),
    ).toBeVisible();
    expect(screen.getByRole('link', { name: 'CONSULTAR EN TERRITORIO IA' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'GENERAR INFORME' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Preguntas rápidas' })).toBeVisible();
    expect(
      screen.getByRole('link', { name: '¿Cuál es el panorama electoral actual?' }),
    ).toBeVisible();
  });

  it('muestra exactamente 6 KPIs de primer nivel con la terminología consistente', async () => {
    renderPage();
    const kpiRow = await screen.findByLabelText('Indicadores descriptivos del panorama electoral');
    expect(within(kpiRow).getByText('Electores actuales')).toBeVisible();
    expect(within(kpiRow).getByText('Votantes esperados')).toBeVisible();
    expect(within(kpiRow).getByText('Participación estimada')).toBeVisible();
    expect(within(kpiRow).getByText('Actividades')).toBeVisible();
    expect(within(kpiRow).getByText('Necesidades')).toBeVisible();
    expect(within(kpiRow).getByText('Parroquias con actividad')).toBeVisible();
    expect(within(kpiRow).queryByText('Padrón actual')).not.toBeInTheDocument();
    expect(within(kpiRow).queryByText('Participación central')).not.toBeInTheDocument();
    expect(within(kpiRow).queryByText('Participación 2019')).not.toBeInTheDocument();
    expect(within(kpiRow).queryByText('Participación 2023')).not.toBeInTheDocument();
    expect(kpiRow.children.length).toBe(6);
  });

  it('conserva 2019/2023 solo dentro de Antecedentes electorales', async () => {
    renderPage();
    const antecedentes = (await screen.findByText('Antecedentes electorales')).closest(
      '.MuiCard-root',
    ) as HTMLElement;
    expect(within(antecedentes).getByText('2019')).toBeVisible();
    expect(within(antecedentes).getByText('2023')).toBeVisible();
    expect(within(antecedentes).getByText(/Participación: 68,00 %/)).toBeVisible();
  });

  it('muestra un único aviso de datos DEMO cuando existen datos simulados', async () => {
    renderPage(demoOperation);
    await screen.findByRole('heading', { level: 1, name: 'Panorama electoral' });
    expect(screen.getAllByText('Esta campaña contiene datos de demostración.').length).toBe(1);
  });

  it('no muestra el aviso de datos DEMO cuando no hay datos simulados', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1, name: 'Panorama electoral' });
    expect(
      screen.queryByText('Esta campaña contiene datos de demostración.'),
    ).not.toBeInTheDocument();
  });
});

describe('Panorama electoral · TERRITORIAL_COORDINATOR', () => {
  beforeEach(() => {
    auth.user.roles = [{ code: 'TERRITORIAL_COORDINATOR', name: 'Coordinador territorial' }];
  });

  it('no muestra Territorio IA, Generar informe ni preguntas rápidas, pero conserva el contenido permitido', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Panorama electoral' }),
    ).toBeVisible();
    expect(screen.queryByText('CONSULTAR EN TERRITORIO IA')).not.toBeInTheDocument();
    expect(screen.queryByText('GENERAR INFORME')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Preguntas rápidas' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '¿Cuál es el panorama electoral actual?' }),
    ).not.toBeInTheDocument();
    expect(screen.getByText('Electores actuales')).toBeVisible();
    expect(screen.getByText('Participación estimada')).toBeVisible();
    expect(screen.getByText('Antecedentes electorales')).toBeVisible();
    expect(screen.getByText('Contexto demográfico')).toBeVisible();
    expect(screen.getByText('Operación territorial')).toBeVisible();
  });
});
