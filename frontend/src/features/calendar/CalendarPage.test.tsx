import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import CalendarPage from './CalendarPage';
import type { CalendarEvent } from './types';

const server = setupServer();
const nativeFetch = globalThis.fetch;
let events: CalendarEvent[] = [];
let lastUrl = '';

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  events = [];
  lastUrl = '';
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers() {
  server.use(
    http.get('*/api/v1/campaigns/campaign-1/calendar', ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ events });
    }),
  );
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/campaigns/campaign-1/calendar']}>
        <Routes>
          <Route path="/app/campaigns/:campaignId/calendar" element={<CalendarPage />} />
          <Route
            path="/app/campaigns/:campaignId/activities/:activityId"
            element={<div>Detalle actividad</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function ymd(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
const today = new Date();
const inFiveDays = new Date(today);
inFiveDays.setDate(inFiveDays.getDate() + 5);
const yesterday = new Date(today);
yesterday.setDate(yesterday.getDate() - 1);

const upcoming: CalendarEvent = {
  id: 'activity:1',
  event_type: 'CAMPAIGN_ACTIVITY',
  title: 'Asamblea territorial',
  description: null,
  starts_at: `${ymd(inFiveDays)}T14:30:00`,
  ends_at: null,
  start_time: '14:30',
  parish_id: 1,
  parish_name: 'Gualaceo',
  is_official: false,
  status: 'PLANNED',
  source_name: null,
  source_url: null,
  deep_link: '/app/campaigns/campaign-1/activities/act-1',
};
const done: CalendarEvent = {
  id: 'activity:2',
  event_type: 'CAMPAIGN_ACTIVITY',
  title: 'Recorrido barrial',
  description: null,
  starts_at: `${ymd(yesterday)}T09:00:00`,
  ends_at: null,
  start_time: '09:00',
  parish_id: 1,
  parish_name: 'Gualaceo',
  is_official: false,
  status: 'COMPLETED',
  source_name: null,
  source_url: null,
  deep_link: '/app/campaigns/campaign-1/activities/act-2',
};

describe('Calendario de campaña', () => {
  it('muestra estado vacío cuando no hay actividades', async () => {
    handlers();
    renderPage();
    expect(
      await screen.findByText('No hay actividades de campaña programadas para este periodo.'),
    ).toBeVisible();
  });

  it('lista actividades en Agenda con estado Próxima y Realizada', async () => {
    events = [upcoming, done];
    handlers();
    renderPage();
    expect(await screen.findByText('Asamblea territorial')).toBeVisible();
    expect(screen.getByText('Recorrido barrial')).toBeVisible();
    expect(screen.getByText('Próxima')).toBeVisible();
    expect(screen.getByText('Realizada')).toBeVisible();
    expect(screen.getByText('PRÓXIMAMENTE')).toBeVisible();
    expect(screen.getByText('REALIZADAS RECIENTEMENTE')).toBeVisible();
  });

  it('filtra por Próximas y por Realizadas', async () => {
    events = [upcoming, done];
    handlers();
    renderPage();
    await screen.findByText('Asamblea territorial');
    await userEvent.click(screen.getByRole('button', { name: 'Próximas' }));
    await waitFor(() => expect(screen.queryByText('Recorrido barrial')).not.toBeInTheDocument());
    expect(screen.getByText('Asamblea territorial')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Realizadas' }));
    await waitFor(() => expect(screen.queryByText('Asamblea territorial')).not.toBeInTheDocument());
    expect(screen.getByText('Recorrido barrial')).toBeVisible();
  });

  it('muestra un vacío específico cuando el filtro Realizadas no tiene resultados', async () => {
    events = [upcoming];
    handlers();
    renderPage();
    await screen.findByText('Asamblea territorial');
    await userEvent.click(screen.getByRole('button', { name: 'Realizadas' }));
    expect(await screen.findByText('No hay actividades realizadas en este periodo.')).toBeVisible();
  });

  it('abre el detalle de una actividad con enlace de profundización', async () => {
    events = [upcoming];
    handlers();
    renderPage();
    await userEvent.click(await screen.findByText('Asamblea territorial'));
    expect(await screen.findByRole('link', { name: 'Ver detalle' })).toHaveAttribute(
      'href',
      '/app/campaigns/campaign-1/activities/act-1',
    );
  });

  it('cambia a vista Mes y envía un rango de mes completo al backend', async () => {
    events = [upcoming];
    handlers();
    renderPage();
    await screen.findByText('Asamblea territorial');
    await userEvent.click(screen.getByRole('button', { name: 'Mes' }));
    await waitFor(() => expect(lastUrl).toContain('date_from='));
    expect(lastUrl).toMatch(/date_from=\d{4}-\d{2}-01/);
  });
});
