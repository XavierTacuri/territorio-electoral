import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import InvitationAcceptPage from './InvitationAcceptPage';
import type { ElectionDayInvitationPreview } from './types';

const server = setupServer();
const nativeFetch = globalThis.fetch;

const auth = vi.hoisted(() => ({ user: null as any, login: vi.fn() }));
vi.mock('../../auth/AuthProvider', () => ({
  useAuth: () => ({ user: auth.user, login: auth.login }),
}));

const navigateSpy = vi.hoisted(() => vi.fn());
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => navigateSpy };
});

beforeAll(() => {
  globalThis.fetch = (...args: Parameters<typeof fetch>) => nativeFetch(...args);
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  server.resetHandlers();
  navigateSpy.mockClear();
  auth.login.mockReset();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});
beforeEach(() => {
  auth.user = null;
  sessionStorage.clear();
});

const basePreview: ElectionDayInvitationPreview = {
  campaign_name: 'Campaña Norte',
  election_date: '2027-02-14',
  staff_type: 'POLLING_PLACE_DELEGATE',
  email: 'juan@example.com',
  first_name: 'Juan',
  last_name: 'Lopez',
  polling_places: [{ id: 'place-1', name: 'Escuela Central' }],
  expires_at: '2027-02-17T00:00:00Z',
  requires_login: false,
  status: 'PENDING',
};

function mockPreview(overrides: Partial<ElectionDayInvitationPreview> = {}) {
  server.use(
    http.post('*/api/v1/election-day/invitations/preview', async ({ request }) => {
      const body = (await request.json()) as { token: string };
      expect(body.token).toBe('abc123');
      return HttpResponse.json({ ...basePreview, ...overrides });
    }),
  );
}

function renderPage(hash = '#token=abc123') {
  window.location.hash = hash;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/invite/election-day${hash}`]}>
        <Routes>
          <Route path="/invite/election-day" element={<InvitationAcceptPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Invitación a Jornada Electoral', () => {
  it('extrae el token del fragment y limpia la URL de inmediato', async () => {
    mockPreview();
    renderPage();
    expect(await screen.findByText('Campaña Norte')).toBeVisible();
    expect(window.location.hash).toBe('');
    expect(window.location.href).not.toContain('abc123');
  });

  it('sin token en el fragment: enlace no válido, sin llamar a la API', async () => {
    renderPage('');
    expect(await screen.findByText('Este enlace de invitación no es válido.')).toBeVisible();
  });

  it('cuenta nueva: crea la cuenta, inicia sesión automáticamente y muestra la confirmación', async () => {
    mockPreview();
    server.use(
      http.post('*/api/v1/election-day/invitations/accept-new-account', async ({ request }) => {
        const body = (await request.json()) as Record<string, string>;
        expect(body.token).toBe('abc123');
        expect(body).not.toHaveProperty('token_hash');
        return HttpResponse.json({
          campaign_id: 'campaign-1',
          operation_id: 'op-1',
          message: 'Tu acceso a la Jornada Electoral está listo.',
        });
      }),
    );
    auth.login.mockResolvedValue(undefined);
    renderPage();
    expect(await screen.findByText('Campaña Norte')).toBeVisible();
    expect(screen.getByDisplayValue('juan@example.com')).toBeVisible();
    await userEvent.type(
      await screen.findByLabelText('Nueva contraseña', { exact: false }),
      'Passw0rd1',
    );
    await userEvent.type(
      await screen.findByLabelText('Confirmar contraseña', { exact: false }),
      'Passw0rd1',
    );
    await userEvent.click(screen.getByRole('button', { name: 'ACTIVAR MI ACCESO' }));
    expect(await screen.findByText('Tu acceso a la Jornada Electoral está listo.')).toBeVisible();
    expect(auth.login).toHaveBeenCalledWith('juan@example.com', 'Passw0rd1');
    expect(screen.getByRole('button', { name: 'IR A MI JORNADA' })).toBeVisible();
  });

  it('cuenta existente sin sesión: inicia sesión en la misma página y acepta, sin navegar a /login', async () => {
    mockPreview({ requires_login: true });
    server.use(
      http.post('*/api/v1/election-day/invitations/accept', async ({ request }) => {
        const body = (await request.json()) as { token: string };
        expect(body.token).toBe('abc123');
        return HttpResponse.json({
          campaign_id: 'campaign-1',
          operation_id: 'op-1',
          message: 'Tu acceso a la Jornada Electoral está listo.',
        });
      }),
    );
    auth.login.mockResolvedValue(undefined);
    renderPage();
    expect(await screen.findByText('Ya tienes una cuenta en Territorio Electoral.')).toBeVisible();
    await userEvent.type(screen.getByLabelText('Contraseña', { exact: false }), 'MiPassw0rd1');
    await userEvent.click(screen.getByRole('button', { name: 'INICIAR SESIÓN Y ACEPTAR' }));
    expect(await screen.findByText('Tu acceso a la Jornada Electoral está listo.')).toBeVisible();
    expect(auth.login).toHaveBeenCalledWith('juan@example.com', 'MiPassw0rd1');
    expect(navigateSpy).not.toHaveBeenCalledWith('/login', expect.anything());
  });

  it('cuenta existente sin sesión: credenciales inválidas muestran error y no aceptan', async () => {
    mockPreview({ requires_login: true });
    auth.login.mockRejectedValue(new Error('bad credentials'));
    renderPage();
    await userEvent.type(
      await screen.findByLabelText('Contraseña', { exact: false }),
      'Incorrecta1',
    );
    await userEvent.click(screen.getByRole('button', { name: 'INICIAR SESIÓN Y ACEPTAR' }));
    expect(await screen.findByText('Las credenciales ingresadas no son válidas.')).toBeVisible();
    expect(
      screen.queryByText('Tu acceso a la Jornada Electoral está listo.'),
    ).not.toBeInTheDocument();
  });

  it('cuenta existente con sesión iniciada: acepta con la cuenta actual', async () => {
    auth.user = { id: 'u1', email: 'juan@example.com' };
    mockPreview({ requires_login: true });
    server.use(
      http.post('*/api/v1/election-day/invitations/accept', () =>
        HttpResponse.json({
          campaign_id: 'campaign-1',
          operation_id: 'op-1',
          message: 'Tu acceso a la Jornada Electoral está listo.',
        }),
      ),
    );
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'ACEPTAR CON ESTA CUENTA' }));
    expect(await screen.findByText('Tu acceso a la Jornada Electoral está listo.')).toBeVisible();
  });

  it('invitación expirada: no muestra formulario', async () => {
    mockPreview({ status: 'EXPIRED' });
    renderPage();
    expect(
      await screen.findByText('Esta invitación expiró. Solicita una nueva al equipo de campaña.'),
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: 'ACTIVAR MI ACCESO' })).not.toBeInTheDocument();
  });

  it('invitación revocada: no muestra formulario', async () => {
    mockPreview({ status: 'REVOKED' });
    renderPage();
    expect(await screen.findByText('Esta invitación fue revocada.')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'ACTIVAR MI ACCESO' })).not.toBeInTheDocument();
  });

  it('invitación ya aceptada: muestra mensaje informativo', async () => {
    mockPreview({ status: 'ACCEPTED' });
    renderPage();
    expect(await screen.findByText('Esta invitación ya fue aceptada.')).toBeVisible();
  });

  it('token inválido: muestra mensaje de enlace no válido', async () => {
    server.use(
      http.post('*/api/v1/election-day/invitations/preview', () =>
        HttpResponse.json({ detail: 'Invitación no encontrada' }, { status: 404 }),
      ),
    );
    renderPage();
    expect(await screen.findByText('Este enlace de invitación no es válido.')).toBeVisible();
  });
});
