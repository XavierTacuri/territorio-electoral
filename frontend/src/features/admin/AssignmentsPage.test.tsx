import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import AssignmentsPage, { assignmentPayload } from './AssignmentsPage';

const server = setupServer();
const nativeFetch = globalThis.fetch;
const campaign = { id: 'campaign-1', name: 'Gualaceo E2E 2027', canton_id: 103 };
const user = { id: 'user-1', username: 'coordinator', first_name: 'Usuario', last_name: 'E2E' };
const parishA = { id: 1, name: 'Parroquia A', canton_id: 103 };
const parishB = { id: 2, name: 'Parroquia B', canton_id: 103 };
const communityA = { id: 'community-a', name: 'Comunidad A', parish_id: 1 };
const sectorA = { id: 'sector-a', name: 'Sector A', community_id: 'community-a' };
let payloads: unknown[] = [];

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  server.resetHandlers();
  payloads = [];
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers(status = 201) {
  server.use(
    http.get('*/api/v1/campaigns', () => HttpResponse.json({ items: [campaign] })),
    http.get('*/api/v1/users', () => HttpResponse.json({ items: [user] })),
    http.get('*/api/v1/parishes', () => HttpResponse.json([parishA, parishB])),
    http.get('*/api/v1/communities', ({ request }) => {
      const id = new URL(request.url).searchParams.get('parish_id');
      return HttpResponse.json({ items: id === '1' ? [communityA] : [] });
    }),
    http.get('*/api/v1/sectors', ({ request }) => {
      const id = new URL(request.url).searchParams.get('community_id');
      return HttpResponse.json({ items: id === communityA.id ? [sectorA] : [] });
    }),
    http.get('*/api/v1/campaigns/campaign-1/users', () =>
      HttpResponse.json([{ id: 'member-1', user_id: user.id, is_active: true }]),
    ),
    http.get('*/api/v1/campaigns/campaign-1/territorial-assignments', () => HttpResponse.json([])),
    http.post('*/api/v1/campaigns/campaign-1/territorial-assignments', async ({ request }) => {
      payloads.push(await request.json());
      return status === 201
        ? HttpResponse.json(
            {
              id: 'assignment-1',
              campaign_id: campaign.id,
              ...(payloads.at(-1) as object),
              is_active: true,
            },
            { status },
          )
        : HttpResponse.json({ detail: [] }, { status });
    }),
  );
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AssignmentsPage />
    </QueryClientProvider>,
  );
}

async function choose(label: string, option: string) {
  await userEvent.click(screen.getByLabelText(label));
  await userEvent.click(await screen.findByRole('option', { name: option }));
}

describe('asignaciones territoriales con RTL y MSW', () => {
  it('construye payloads parroquial, comunitario y sectorial', () => {
    expect(assignmentPayload('u', '1', '', '')).toMatchObject({
      parish_id: 1,
      community_id: null,
      sector_id: null,
    });
    expect(assignmentPayload('u', '1', 'c', '')).toMatchObject({
      community_id: 'c',
      sector_id: null,
    });
    expect(assignmentPayload('u', '1', 'c', 's')).toMatchObject({
      community_id: 'c',
      sector_id: 's',
    });
  });
  it('rechaza sector sin comunidad', () =>
    expect(() => assignmentPayload('u', '1', '', 's')).toThrow(/comunidad/));
  it('carga hijos y limpia comunidad y sector al cambiar parroquia', async () => {
    handlers();
    renderPage();
    await choose('Campana', campaign.name);
    await choose('Usuario coordinador', 'Usuario E2E (coordinator)');
    await choose('Parroquia', parishA.name);
    await choose('Comunidad (opcional)', communityA.name);
    await choose('Sector (opcional)', sectorA.name);
    await choose('Parroquia', parishB.name);
    expect(screen.getByLabelText('Comunidad (opcional)')).not.toHaveTextContent(communityA.name);
    expect(screen.getByLabelText('Sector (opcional)')).not.toHaveTextContent(sectorA.name);
    expect(screen.getByLabelText('Sector (opcional)')).toHaveAttribute('aria-disabled', 'true');
  });
  it('limpia el sector al cambiar comunidad', async () => {
    handlers();
    renderPage();
    await choose('Campana', campaign.name);
    await choose('Parroquia', parishA.name);
    await choose('Comunidad (opcional)', communityA.name);
    await choose('Sector (opcional)', sectorA.name);
    await choose('Comunidad (opcional)', 'Toda la parroquia');
    expect(screen.getByLabelText('Sector (opcional)')).not.toHaveTextContent(sectorA.name);
    expect(screen.getByLabelText('Sector (opcional)')).toHaveAttribute('aria-disabled', 'true');
  });
  it('envia una asignacion sectorial con la jerarquia exacta', async () => {
    handlers();
    renderPage();
    await choose('Campana', campaign.name);
    await choose('Usuario coordinador', 'Usuario E2E (coordinator)');
    await choose('Parroquia', parishA.name);
    await choose('Comunidad (opcional)', communityA.name);
    await choose('Sector (opcional)', sectorA.name);
    await userEvent.click(screen.getByRole('button', { name: 'Asignar territorio' }));
    await waitFor(() =>
      expect(payloads).toEqual([
        { user_id: user.id, parish_id: 1, community_id: communityA.id, sector_id: sectorA.id },
      ]),
    );
  });
  it('muestra el error 422 de jerarquia', async () => {
    handlers(422);
    renderPage();
    await choose('Campana', campaign.name);
    await choose('Usuario coordinador', 'Usuario E2E (coordinator)');
    await choose('Parroquia', parishA.name);
    await userEvent.click(screen.getByRole('button', { name: 'Asignar territorio' }));
    expect(await screen.findByText(/Revise la jerarquia territorial/)).toBeVisible();
  });
  it('muestra acceso denegado 403', async () => {
    handlers(403);
    renderPage();
    await choose('Campana', campaign.name);
    await choose('Usuario coordinador', 'Usuario E2E (coordinator)');
    await choose('Parroquia', parishA.name);
    await userEvent.click(screen.getByRole('button', { name: 'Asignar territorio' }));
    expect(await screen.findByText('Acceso denegado.')).toBeVisible();
  });
});
