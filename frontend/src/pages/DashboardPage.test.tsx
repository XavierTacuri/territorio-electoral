import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import DashboardPage from './DashboardPage';

vi.mock('../features/dashboard/CommandCenterMap', () => ({ CommandCenterMap: () => <div role="region" aria-label="Mapa operativo territorial">Territorio en operación</div> }));

const parishes = Array.from({ length: 9 }, (_, index) => ({ parish_id: index + 1, name: index ? `Parroquia ${index + 1}` : 'Gualaceo', dpa_code: `01035${index}`, registered_voters_current: index ? 1700 : 21184, data_quality_status: 'MEDIUM', demographics: {} }));
const analysis = { context: { campaign_name: 'Gualaceo2026', canton_name: 'Gualaceo', election_name: 'Seccionales 2027' }, snapshot: { snapshot_date: '2026-07-16', registered_voters: 34784 }, historical: { '2019': { turnout_rate: .6858 }, '2023': { turnout_rate: .7189 } }, projection: { model_code: 'TURNOUT_HISTORICAL_WEIGHTED_V1', expected_voters_central: 24697 }, parishes };
const operations = { activities: { total: 8, demo: 4, upcoming: 3, pending_approval: 2, completed: 4 }, needs: { total: 5, demo: 2, open: 4, under_review: 1, validated: 2 }, commitments: { pending: 2, in_progress: 1, overdue: 1, completed: 4 }, coverage: { total_parishes: 9, with_activities: 7, with_needs: 4, with_commitments: 3 }, can_approve: true };
const agenda = { activities: [{ id: 'a1', title: 'Visita', activity_date: new Date().toISOString().slice(0, 10) }], pending_approval: [{ id: 'a2' }, { id: 'a3' }], commitments: [{ id: 'c1' }] };
const territory = { parishes: [{ parish_id: 1, activities: 3, needs_open: 2, commitments_pending: 1, commitments_completed: 1, latest_activities: [{ id: 'a1', title: '[DEMO] Reunión territorial en Jadán', date: '2026-08-30', status: 'COMPLETED' }], latest_needs: [], latest_commitments: [] }] };
const published = { items: [{ id: 's1', name: '[DEMO] Encuesta general', status: 'PUBLISHED', fieldwork_start_date: '2026-08-15', fieldwork_end_date: '2026-08-18', sample_size_total: 800 }], total: 1, page: 1, page_size: 3, total_pages: 1 };
const openAlerts = { items: [{ id: 'al1', title: 'Actividad pendiente de aprobación', message: 'Asamblea Jadán', severity: 'WARNING', status: 'OPEN', detected_date: '2026-08-30' }] };
const upcomingEvents = { events: [{ id: 'ev1', event_type: 'CAMPAIGN_ACTIVITY', title: 'Asamblea territorial', starts_at: '2026-09-05T00:00:00', is_official: false, deep_link: null }] };
const handlers = [
  http.get('*/api/v1/campaigns/campaign-1/current-election/analysis', () => HttpResponse.json(analysis)),
  http.get('*/api/v1/campaigns/campaign-1/operations/summary', () => HttpResponse.json(operations)),
  http.get('*/api/v1/campaigns/campaign-1/operations/agenda', () => HttpResponse.json(agenda)),
  http.get('*/api/v1/campaigns/campaign-1/territories/summary', () => HttpResponse.json(territory)),
  http.get('*/api/v1/campaigns/campaign-1/survey-studies', () => HttpResponse.json(published)),
  http.get('*/api/v1/campaigns/campaign-1', () => HttpResponse.json({ id: 'campaign-1', name: 'Gualaceo2026', canton_name: 'Gualaceo', province_name: 'Azuay' })),
  http.get('*/api/v1/campaigns/campaign-1/alerts', () => HttpResponse.json(openAlerts)),
  http.get('*/api/v1/campaigns/campaign-1/calendar', () => HttpResponse.json(upcomingEvents)),
];
const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers(...handlers));
afterAll(() => server.close());

function renderDashboard(studyData: typeof published | 'error' = published) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryOnMount: false, staleTime: Infinity } } });
  client.setQueryData(['current-election-analysis', 'campaign-1'], analysis);
  client.setQueryData(['campaign', 'campaign-1', 'operations-overview'], operations);
  client.setQueryData(['campaign', 'campaign-1', 'operations-agenda'], agenda);
  client.setQueryData(['campaign', 'campaign-1', 'territories-summary'], territory);
  client.setQueryData(['campaign', 'campaign-1'], { id: 'campaign-1', name: 'Gualaceo2026', canton_name: 'Gualaceo', province_name: 'Azuay' });
  client.setQueryData(['campaign', 'campaign-1', 'alerts-open'], openAlerts);
  client.setQueryData(['campaign', 'campaign-1', 'calendar-upcoming'], upcomingEvents);
  if (studyData === 'error') {
    const query = client.getQueryCache().build(client, {
      queryKey: ['recent-survey-studies', 'campaign-1'],
      queryFn: async () => published,
    });
    query.setState({
      ...query.state,
      error: Object.assign(new Error('HTTP 500'), { status: 500 }),
      errorUpdateCount: 1,
      errorUpdatedAt: Date.now(),
      fetchStatus: 'idle',
      status: 'error',
    });
  } else client.setQueryData(['recent-survey-studies', 'campaign-1'], studyData);
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/app/campaigns/campaign-1/dashboard']}><Routes><Route path="/app/campaigns/:campaignId/dashboard" element={<DashboardPage />} /><Route path="/app/campaigns/:campaignId/territory-ai" element={<div>IA abierta</div>} /></Routes></MemoryRouter></QueryClientProvider>);
}

describe('Centro de Comando Territorial', () => {
  it('renderiza KPIs persistidos, operación, mapa y solo estudios publicados', async () => {
    renderDashboard();
    expect(await screen.findByRole('heading', { level: 1, name: 'Centro de Comando Territorial' })).toBeVisible();
    expect(screen.getAllByText('34.784').length).toBeGreaterThan(0);
    expect(screen.getAllByText('71,00 %').length).toBeGreaterThan(0);
    expect(screen.getAllByText('24.697').length).toBeGreaterThan(0);
    expect(screen.getByRole('region', { name: 'Mapa operativo territorial' })).toBeVisible();
    expect(screen.getByText('Datos simulados para demostración.')).toBeVisible();
    expect(screen.getByText('2 actividades pendientes de aprobación')).toBeVisible();
    expect(screen.getByText('Actividad pendiente de aprobación')).toBeVisible();
    expect(screen.getByRole('link', { name: 'VER TODAS' })).toHaveAttribute(
      'href',
      '/app/campaigns/campaign-1/alerts',
    );
    expect(screen.getByText(/Asamblea territorial/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'VER CALENDARIO' })).toHaveAttribute(
      'href',
      '/app/campaigns/campaign-1/calendar',
    );
  });

  it('mantiene el Dashboard cuando una fuente secundaria no tiene datos', async () => {
    renderDashboard({ ...published, items: [], total: 0 });
    expect(await screen.findByText('Padrón electoral')).toBeVisible();
    expect(screen.getByText('Aún no existen encuestas publicadas para esta campaña.')).toBeVisible();
  });

  it('mantiene el Dashboard cuando Encuestas devuelve un error HTTP', async () => {
    renderDashboard('error');
    expect(await screen.findByRole('heading', { level: 1, name: 'Centro de Comando Territorial' })).toBeVisible();
    expect(screen.getByText('Padrón electoral')).toBeVisible();
    expect(await screen.findAllByText('No fue posible cargar esta sección.')).toHaveLength(1);
  });

  it('muestra empty state de encuestas', async () => {
    renderDashboard({ ...published, items: [], total: 0 });
    expect(await screen.findByText('Aún no existen encuestas publicadas para esta campaña.')).toBeVisible();
  });

  it('abre Territorio IA con la pregunta sugerida', async () => {
    renderDashboard();
    const suggestion = await screen.findByRole('button', { name: '¿Cuál es el panorama electoral actual?' });
    fireEvent.click(suggestion);
    await waitFor(() => expect(screen.getByText('IA abierta')).toBeVisible());
  });
});
