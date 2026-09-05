import { render, screen, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { AuthProvider, useAuth } from './AuthProvider';
import { clearSessionSnapshot, saveSessionSnapshot } from '../offline/sessionRepository';

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, 'onLine', { configurable: true, value });
}

function Probe() {
  const { user, loading, offlineSession } = useAuth();
  if (loading) return <div>cargando</div>;
  return (
    <div>
      <div data-testid="user">{user ? user.username : 'sin-sesion'}</div>
      <div data-testid="offline">{offlineSession ? 'offline' : 'online'}</div>
    </div>
  );
}

beforeEach(async () => {
  setOnline(true);
  await clearSessionSnapshot();
});

describe('AuthProvider offline-shell fallback', () => {
  it('falls back to the cached session snapshot when the session check fails offline', async () => {
    setOnline(false);
    await saveSessionSnapshot({
      id: 'coordinator-1',
      username: 'coordinator_e2e',
      email: 'c@example.test',
      first_name: 'Coord',
      last_name: 'Inator',
      is_active: true,
      is_superuser: false,
      roles: [{ code: 'TERRITORIAL_COORDINATOR', name: 'Coordinador' }],
    });
    server.use(http.get('/api/v1/auth/browser/session', () => HttpResponse.error()));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('coordinator_e2e'));
    expect(screen.getByTestId('offline')).toHaveTextContent('offline');
  });

  it('logs out when the session check fails offline with no cached snapshot', async () => {
    setOnline(false);
    server.use(http.get('/api/v1/auth/browser/session', () => HttpResponse.error()));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('sin-sesion'));
  });

  it('logs out on a genuine 401 even while offline-detection would otherwise apply', async () => {
    setOnline(false);
    await saveSessionSnapshot({
      id: 'coordinator-2',
      username: 'stale_user',
      email: 's@example.test',
      first_name: 'S',
      last_name: 'U',
      is_active: true,
      is_superuser: false,
      roles: [],
    });
    server.use(
      http.get('/api/v1/auth/browser/session', () =>
        HttpResponse.json({ detail: 'nope' }, { status: 401 }),
      ),
    );
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('sin-sesion'));
  });
});
