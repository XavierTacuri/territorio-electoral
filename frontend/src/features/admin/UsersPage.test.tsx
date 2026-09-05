import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import UsersPage from './UsersPage';

type RequestRecord = { method: string; body: Record<string, unknown> };
const server = setupServer();
const nativeFetch = globalThis.fetch;
const candidateRole = { code: 'CANDIDATE', name: 'Candidato' };
const existingUser = {
  id: 'user-1',
  email: 'existing@example.test',
  username: 'existing',
  first_name: 'Usuario',
  last_name: 'Existente',
  is_active: true,
  roles: [candidateRole],
};
let users: (typeof existingUser)[] = [];
let lastRequest: RequestRecord | null = null;

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  users = [];
  lastRequest = null;
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers() {
  server.use(
    http.get('*/api/v1/users', () =>
      HttpResponse.json({ items: users, page: 1, page_size: 100, total: users.length }),
    ),
    http.get('*/api/v1/roles', () => HttpResponse.json([candidateRole])),
    http.post('*/api/v1/users', async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      lastRequest = { method: request.method, body };
      const created = {
        ...existingUser,
        ...body,
        id: 'created-user',
        is_active: true,
        roles: [candidateRole],
      };
      users = [created as typeof existingUser];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch('*/api/v1/users/:id', async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      lastRequest = { method: request.method, body };
      users = [{ ...existingUser, ...body } as typeof existingUser];
      return HttpResponse.json(users[0]);
    }),
  );
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <UsersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('administración de usuarios', () => {
  it('crea un usuario sin enviar is_active', async () => {
    handlers();
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Crear usuario' }));
    expect(screen.queryByLabelText('Usuario activo')).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Correo'), 'crisave123@hotmail.com');
    await userEvent.type(screen.getByLabelText('Usuario'), 'xavier123');
    await userEvent.type(screen.getByLabelText('Nombres'), 'Xavier');
    await userEvent.type(screen.getByLabelText('Apellidos'), 'Tacuri');
    await userEvent.type(screen.getByLabelText(/Contraseña temporal/), 'Temporary123');
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => expect(lastRequest?.method).toBe('POST'));
    expect(lastRequest?.body).toEqual({
      email: 'crisave123@hotmail.com',
      username: 'xavier123',
      first_name: 'Xavier',
      last_name: 'Tacuri',
      password: 'Temporary123',
      role_codes: ['CANDIDATE'],
    });
    expect(lastRequest?.body).not.toHaveProperty('is_active');
  });

  it('mantiene is_active al editar un usuario', async () => {
    users = [existingUser];
    handlers();
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Editar usuarios' }));
    await userEvent.click(screen.getByLabelText('Usuario activo'));
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => expect(lastRequest?.method).toBe('PATCH'));
    expect(lastRequest?.body).toMatchObject({ is_active: false, role_codes: ['CANDIDATE'] });
    expect(lastRequest?.body).not.toHaveProperty('password');
  });
});
