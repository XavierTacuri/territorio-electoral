import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import ElectionDaySupportPage from './ElectionDaySupportPage';

const server = setupServer();
const nativeFetch = globalThis.fetch;

const navigateSpy = vi.hoisted(() => vi.fn());
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => navigateSpy };
});

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
  navigateSpy.mockClear();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

const campaigns = [
  {
    campaign_id: 'campaign-1',
    campaign_name: 'Gualaceo 2027',
    organization_name: 'Territorio Electoral',
    operation_id: 'op-1',
    operation_status: 'ACTIVE',
    election_date: '2027-02-14',
  },
  {
    campaign_id: 'campaign-2',
    campaign_name: 'Cuenca 2027',
    organization_name: 'Territorio Electoral',
    operation_id: 'op-2',
    operation_status: 'PREPARATION',
    election_date: '2027-02-14',
  },
];

let currentByCampaign: Record<string, unknown> = {};
let startError: { status: number; detail: string } | null = null;
let lastStartedCampaign: string | null = null;
let ended = false;

function handlers() {
  server.use(
    http.get('*/api/v1/election-day/admin-support/campaigns', () => HttpResponse.json(campaigns)),
    http.get('*/api/v1/campaigns/:id/election-day/admin-support/current', ({ params }) => {
      const session = currentByCampaign[params.id as string] as
        | { ended_at: string | null }
        | undefined;
      // El backend real filtra ended_at IS NULL — una sesión ya terminada
      // nunca vuelve a aparecer como "actual".
      return HttpResponse.json(session && !session.ended_at ? session : null);
    }),
    http.post('*/api/v1/campaigns/:id/election-day/admin-support/start', ({ params }) => {
      if (startError)
        return HttpResponse.json({ detail: startError.detail }, { status: startError.status });
      lastStartedCampaign = params.id as string;
      const session = {
        id: 'sess-1',
        admin_user_id: 'admin-1',
        organization_id: 'org-1',
        campaign_id: params.id,
        operation_id: 'op-1',
        reason: null,
        started_at: '2027-02-14T10:00:00Z',
        ended_at: null,
      };
      currentByCampaign[params.id as string] = session;
      return HttpResponse.json(session, { status: 201 });
    }),
    http.post('*/api/v1/campaigns/:id/election-day/admin-support/end', ({ params }) => {
      ended = true;
      const session = currentByCampaign[params.id as string] as Record<string, unknown>;
      const updated = { ...session, ended_at: '2027-02-14T12:00:00Z' };
      currentByCampaign[params.id as string] = updated;
      return HttpResponse.json(updated);
    }),
  );
}

beforeEach(() => {
  currentByCampaign = {};
  startError = null;
  lastStartedCampaign = null;
  ended = false;
  handlers();
});

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ElectionDaySupportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Soporte Jornada Electoral (Fase 3.1)', () => {
  it('el selector solo lista campañas con Jornada configurada, mostrando su estado', async () => {
    renderPage();
    const input = await screen.findByLabelText('Campaña');
    await userEvent.click(input);
    expect(
      await screen.findByRole('option', { name: /Gualaceo 2027 · Jornada activa/ }),
    ).toBeVisible();
    expect(screen.getByRole('option', { name: /Cuenca 2027 · Preparación/ })).toBeVisible();
  });

  it('inicia soporte y ofrece Centro de Control, Validación de actas y salir', async () => {
    renderPage();
    const input = await screen.findByLabelText('Campaña');
    await userEvent.click(input);
    await userEvent.click(await screen.findByRole('option', { name: /Gualaceo 2027/ }));

    expect(
      await screen.findByText('No tienes una sesión de soporte activa en esta campaña.', {
        exact: false,
      }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'INICIAR MODO SOPORTE' }));

    expect(await screen.findByText('Modo soporte administrativo activo')).toBeVisible();
    expect(screen.getByText('Campaña: Gualaceo 2027')).toBeVisible();
    expect(screen.getByText('Estado: Jornada activa')).toBeVisible();
    expect(lastStartedCampaign).toBe('campaign-1');

    await userEvent.click(screen.getByRole('button', { name: 'ENTRAR AL CENTRO DE CONTROL' }));
    expect(navigateSpy).toHaveBeenCalledWith(
      '/app/campaigns/campaign-1/election-day/control-center',
    );

    await userEvent.click(screen.getByRole('button', { name: 'VALIDACIÓN DE ACTAS' }));
    expect(navigateSpy).toHaveBeenCalledWith('/app/campaigns/campaign-1/election-day/validation');

    await userEvent.click(screen.getByRole('button', { name: 'SALIR DEL MODO SOPORTE' }));
    expect(
      await screen.findByText('No tienes una sesión de soporte activa en esta campaña.', {
        exact: false,
      }),
    ).toBeVisible();
    expect(ended).toBe(true);
  });

  it('no cambia silenciosamente de campaña: muestra el mensaje claro cuando ya hay soporte activo en otra', async () => {
    startError = {
      status: 400,
      detail:
        'Ya tienes una sesión de soporte activa en la campaña «Gualaceo 2027». Ciérrala antes de iniciar soporte en otra campaña.',
    };
    renderPage();
    const input = await screen.findByLabelText('Campaña');
    await userEvent.click(input);
    await userEvent.click(await screen.findByRole('option', { name: /Cuenca 2027/ }));
    await userEvent.click(screen.getByRole('button', { name: 'INICIAR MODO SOPORTE' }));

    expect(
      await screen.findByText(
        /Ya tienes una sesión de soporte activa en la campaña «Gualaceo 2027»/,
      ),
    ).toBeVisible();
    // Nunca entra en modo soporte "silenciosamente" para la otra campaña.
    expect(screen.queryByText('Modo soporte administrativo activo')).not.toBeInTheDocument();
  });
});
