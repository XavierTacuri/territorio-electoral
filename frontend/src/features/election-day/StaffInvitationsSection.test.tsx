import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { StaffInvitationsSection } from './StaffInvitationsSection';
import type { ElectionDayStaffInvitation, PollingPlace } from './types';

const server = setupServer();
const nativeFetch = globalThis.fetch;

beforeAll(() => {
  globalThis.fetch = (...args: Parameters<typeof fetch>) =>
    nativeFetch(...args).catch(() => {
      throw new Error('unhandled');
    });
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

const places: PollingPlace[] = [
  {
    id: 'place-1',
    electoral_process_id: 'proc-1',
    province_id: 1,
    canton_id: 1,
    parish_id: 1,
    official_code: 'R-001',
    name: 'Escuela Central',
    address: null,
    latitude: null,
    longitude: null,
    is_active: true,
  },
  {
    id: 'place-2',
    electoral_process_id: 'proc-1',
    province_id: 1,
    canton_id: 1,
    parish_id: 1,
    official_code: 'R-002',
    name: 'Colegio Norte',
    address: null,
    latitude: null,
    longitude: null,
    is_active: true,
  },
];

let items: ElectionDayStaffInvitation[] = [];
let createdBody: unknown = null;
let lastAction: string | null = null;

function invitation(
  overrides: Partial<ElectionDayStaffInvitation> = {},
): ElectionDayStaffInvitation {
  return {
    id: 'inv-1',
    campaign_id: 'campaign-1',
    operation_id: 'op-1',
    email: 'juan@example.com',
    first_name: 'Juan',
    last_name: 'Lopez',
    staff_type: 'POLLING_PLACE_DELEGATE',
    status: 'PENDING',
    invited_by_user_id: 'u1',
    accepted_user_id: null,
    expires_at: '2027-02-17T00:00:00Z',
    accepted_at: null,
    revoked_at: null,
    created_at: '2027-02-14T00:00:00Z',
    polling_place_ids: ['place-1'],
    ...overrides,
  };
}

function handlers() {
  server.use(
    http.get('*/api/v1/campaigns/campaign-1/election-day/staff/invitations', () =>
      HttpResponse.json({ items, total: items.length }),
    ),
    http.post(
      '*/api/v1/campaigns/campaign-1/election-day/staff/invitations',
      async ({ request }) => {
        createdBody = await request.json();
        const created = invitation({
          id: 'inv-new',
          ...(createdBody as object),
        } as Partial<ElectionDayStaffInvitation>);
        items = [...items, created];
        return HttpResponse.json(
          {
            invitation: created,
            invite_token: 'plain-token-value',
            invite_url: 'https://app.test/invite/election-day#token=plain-token-value',
          },
          { status: 201 },
        );
      },
    ),
    http.post(
      '*/api/v1/campaigns/campaign-1/election-day/staff/invitations/:id/revoke',
      ({ params }) => {
        lastAction = 'revoke';
        items = items.map((i) => (i.id === params.id ? { ...i, status: 'REVOKED' } : i));
        return HttpResponse.json(items.find((i) => i.id === params.id));
      },
    ),
    http.post(
      '*/api/v1/campaigns/campaign-1/election-day/staff/invitations/:id/reissue',
      ({ params }) => {
        lastAction = 'reissue';
        const updated = items.find((i) => i.id === params.id)!;
        return HttpResponse.json({
          invitation: updated,
          invite_token: 'reissued-token',
          invite_url: 'https://app.test/invite/election-day#token=reissued-token',
        });
      },
    ),
  );
}

beforeEach(() => {
  items = [];
  createdBody = null;
  lastAction = null;
  handlers();
  Object.assign(navigator, { clipboard: { writeText: () => Promise.resolve() } });
});

function renderSection() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StaffInvitationsSection campaignId="campaign-1" places={places} />
    </QueryClientProvider>,
  );
}

describe('Personal de Jornada', () => {
  it('muestra estados vacíos cuando no hay invitaciones', async () => {
    renderSection();
    expect(await screen.findByText('No hay invitaciones pendientes.')).toBeVisible();
    expect(screen.getByText('Aún no hay delegados con acceso activo.')).toBeVisible();
    expect(screen.getByText('Aún no hay validadores con acceso activo.')).toBeVisible();
  });

  it('crea una invitación de delegado con varios recintos y muestra el enlace una sola vez', async () => {
    renderSection();
    await userEvent.click(await screen.findByRole('button', { name: 'AGREGAR PERSONAL' }));
    await userEvent.type(screen.getByLabelText('Nombre'), 'Juan');
    await userEvent.type(screen.getByLabelText('Apellido'), 'Lopez');
    await userEvent.type(screen.getByLabelText('Correo'), 'juan@example.com');
    await userEvent.click(screen.getByLabelText('Recintos'));
    await userEvent.click(await screen.findByRole('option', { name: 'Escuela Central' }));
    await userEvent.click(screen.getByRole('option', { name: 'Colegio Norte' }));
    await userEvent.keyboard('{Escape}');
    await userEvent.click(screen.getByRole('button', { name: 'Crear invitación' }));

    expect(await screen.findByText('Invitación creada correctamente')).toBeVisible();
    expect(
      screen.getByText(
        'Este enlace se muestra ahora para que puedas compartirlo de forma segura. No volverá a mostrarse después de cerrar esta ventana.',
      ),
    ).toBeVisible();
    expect(
      screen.getByDisplayValue('https://app.test/invite/election-day#token=plain-token-value'),
    ).toBeVisible();
    expect(createdBody).toMatchObject({
      first_name: 'Juan',
      last_name: 'Lopez',
      email: 'juan@example.com',
      staff_type: 'POLLING_PLACE_DELEGATE',
      polling_place_ids: ['place-1', 'place-2'],
    });

    await userEvent.click(screen.getByRole('button', { name: 'COPIAR ENLACE' }));
    expect(await screen.findByText('Enlace copiado.')).toBeVisible();

    await userEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
    await waitFor(() =>
      expect(screen.queryByText('Invitación creada correctamente')).not.toBeInTheDocument(),
    );
  });

  it('revoca una invitación pendiente', async () => {
    items = [invitation()];
    renderSection();
    const pendingSection = (await screen.findByText('Juan Lopez')).closest('.MuiCard-root')!;
    await userEvent.click(
      within(pendingSection as HTMLElement).getByRole('button', { name: 'REVOCAR' }),
    );
    expect(await screen.findByText('Revocada')).toBeVisible();
    expect(lastAction).toBe('revoke');
  });

  it('reemite una invitación pendiente y vuelve a mostrar el enlace', async () => {
    items = [invitation()];
    renderSection();
    const pendingSection = (await screen.findByText('Juan Lopez')).closest('.MuiCard-root')!;
    await userEvent.click(
      within(pendingSection as HTMLElement).getByRole('button', { name: 'REEMITIR' }),
    );
    expect(await screen.findByText('Invitación creada correctamente')).toBeVisible();
    expect(
      screen.getByDisplayValue('https://app.test/invite/election-day#token=reissued-token'),
    ).toBeVisible();
    expect(lastAction).toBe('reissue');
  });
});
