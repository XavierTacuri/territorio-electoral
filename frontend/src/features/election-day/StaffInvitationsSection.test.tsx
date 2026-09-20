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

function renderSection(
  operationStatus: 'PREPARATION' | 'ACTIVE' | 'SCRUTINY' | 'CLOSED' = 'ACTIVE',
  placesOverride = places,
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StaffInvitationsSection
        campaignId="campaign-1"
        places={placesOverride}
        operationStatus={operationStatus}
      />
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
    expect(
      screen.getByText(
        'El personal recibirá un enlace de invitación y creará su propia contraseña al activar el acceso.',
      ),
    ).toBeVisible();
    expect(
      screen.getByText('El delegado creará su propia contraseña al activar la invitación.'),
    ).toBeVisible();
    await userEvent.type(screen.getByLabelText('Nombre'), 'Juan');
    await userEvent.type(screen.getByLabelText('Apellido'), 'Lopez');
    await userEvent.type(screen.getByLabelText('Correo'), 'juan@example.com');
    await userEvent.click(screen.getByLabelText('Recintos'));
    await userEvent.click(await screen.findByRole('option', { name: 'Escuela Central' }));
    await userEvent.click(screen.getByRole('option', { name: 'Colegio Norte' }));
    await userEvent.keyboard('{Escape}');
    await userEvent.click(screen.getByRole('button', { name: 'Crear invitación' }));

    expect(await screen.findByText('Invitación creada')).toBeVisible();
    const summaryDialog = screen.getByRole('dialog', { name: 'Invitación creada' });
    expect(within(summaryDialog).getByText('Delegado de recinto')).toBeVisible();
    expect(
      within(summaryDialog).getByText(
        'Esta persona deberá crear su propia contraseña al activar el acceso.',
      ),
    ).toBeVisible();
    expect(
      within(summaryDialog).getByText(
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

    await userEvent.click(screen.getByRole('button', { name: 'COPIAR ENLACE DE INVITACIÓN' }));
    expect(await screen.findByText('Enlace copiado.')).toBeVisible();

    await userEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
    await waitFor(() => expect(screen.queryByText('Invitación creada')).not.toBeInTheDocument());
  });

  it('sin recintos cargados, explica por qué el selector no está disponible para un delegado', async () => {
    renderSection('ACTIVE', []);
    await userEvent.click(await screen.findByRole('button', { name: 'AGREGAR PERSONAL' }));
    expect(
      await screen.findByText(/No existen recintos disponibles\. Solicita al ADMIN/),
    ).toBeVisible();
    expect(screen.queryByLabelText('Recintos')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Crear invitación' })).toBeDisabled();
  });

  it('el validador no requiere seleccionar recinto', async () => {
    renderSection('ACTIVE', []);
    await userEvent.click(await screen.findByRole('button', { name: 'AGREGAR PERSONAL' }));
    await userEvent.click(screen.getByLabelText('Perfil'));
    await userEvent.click(await screen.findByRole('option', { name: 'Validador de actas' }));
    expect(screen.queryByText(/No existen recintos disponibles/)).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Nombre'), 'Ana');
    await userEvent.type(screen.getByLabelText('Apellido'), 'Ruiz');
    await userEvent.type(screen.getByLabelText('Correo'), 'ana@example.com');
    expect(screen.getByRole('button', { name: 'Crear invitación' })).toBeEnabled();
  });

  it('con la jornada cerrada, esconde agregar personal y las acciones mutables', async () => {
    items = [invitation()];
    renderSection('CLOSED');
    expect(await screen.findByText('Juan Lopez')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'AGREGAR PERSONAL' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'REVOCAR' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'REEMITIR' })).not.toBeInTheDocument();
    expect(screen.getByText(/La jornada está cerrada/)).toBeVisible();
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
    expect(await screen.findByText('Invitación creada')).toBeVisible();
    expect(
      screen.getByDisplayValue('https://app.test/invite/election-day#token=reissued-token'),
    ).toBeVisible();
    expect(lastAction).toBe('reissue');
  });
});
