import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { CampaignProvider } from '../../app/CampaignProvider';
import { CampaignSelector } from '../../components/navigation/CampaignSelector';
import CampaignFormPage from './CampaignFormPage';
import CampaignsPage from './CampaignsPage';
import { campaignFormSchema, toCampaignPayload } from './campaignForm';

const auth = vi.hoisted(() => ({
  user: {
    id: 'admin',
    username: 'admin',
    email: 'admin@example.test',
    first_name: 'Admin',
    last_name: 'Test',
    is_active: true,
    is_superuser: true,
    roles: [{ code: 'ADMIN', name: 'Administrador' }],
  } as any,
}));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ user: auth.user }) }));

const server = setupServer();
const nativeFetch = globalThis.fetch;
const province = { id: 1, code: '01', name: 'Azuay', is_active: true };
const otherProvince = { id: 2, code: '02', name: 'Bolívar', is_active: true };
const canton = {
  id: 103,
  province_id: 1,
  code: '03',
  dpa_code: '0103',
  name: 'Gualaceo',
  is_active: true,
};
const otherCanton = {
  id: 201,
  province_id: 2,
  code: '01',
  dpa_code: '0201',
  name: 'Guaranda',
  is_active: true,
};
const campaign = {
  id: 'campaign-1',
  name: 'Campaña inicial',
  slug: 'campana-inicial',
  canton_id: 103,
  office_type: 'MAYOR',
  election_name: 'Elecciones seccionales',
  election_date: '2027-02-14',
  start_date: '2026-10-01',
  end_date: '2027-02-14',
  status: 'ACTIVE',
  description: null,
  candidate: null,
  is_active: true,
  canton_name: 'Gualaceo',
  province_id: 1,
  province_name: 'Azuay',
};
const campaignBeta = {
  ...campaign,
  id: 'campaign-2',
  name: 'CampaÃ±a Beta',
  slug: 'campana-beta',
  canton_id: 201,
  canton_name: 'Guaranda',
  province_id: 2,
  province_name: 'BolÃ­var',
};
let campaigns: (typeof campaign)[] = [];
let postStatus = 201;
let patchStatus = 200;
let lastBody: any;

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  campaigns = [];
  postStatus = 201;
  patchStatus = 200;
  lastBody = undefined;
  auth.user = {
    ...auth.user,
    is_superuser: true,
    roles: [{ code: 'ADMIN', name: 'Administrador' }],
  };
  sessionStorage.clear();
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function handlers() {
  server.use(
    http.get('*/api/v1/campaigns', () =>
      HttpResponse.json({
        items: campaigns,
        page: 1,
        page_size: 100,
        total: campaigns.length,
        total_pages: campaigns.length ? 1 : 0,
      }),
    ),
    http.get('*/api/v1/provinces', () => HttpResponse.json([province, otherProvince])),
    http.get('*/api/v1/cantons', ({ request }) => {
      const id = new URL(request.url).searchParams.get('province_id');
      return HttpResponse.json(
        id === '1' ? [canton] : id === '2' ? [otherCanton] : [canton, otherCanton],
      );
    }),
    http.get('*/api/v1/cantons/:id', () => HttpResponse.json(canton)),
    http.get('*/api/v1/campaigns/:id', () => HttpResponse.json(campaign)),
    http.post('*/api/v1/campaigns', async ({ request }) => {
      lastBody = await request.json();
      if (postStatus !== 201)
        return HttpResponse.json(
          { detail: postStatus === 409 ? 'El slug ya existe' : [] },
          { status: postStatus },
        );
      campaigns = [campaign];
      return HttpResponse.json(campaign, { status: 201 });
    }),
    http.patch('*/api/v1/campaigns/:id', async ({ request }) => {
      lastBody = await request.json();
      return patchStatus === 200
        ? HttpResponse.json(campaign)
        : HttpResponse.json({ detail: 'Sin permisos' }, { status: patchStatus });
    }),
  );
}

function Location() {
  return <div data-testid="location">{useLocation().pathname}</div>;
}
function renderRoutes(path: string, page: React.ReactNode, selector = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const result = render(
    <QueryClientProvider client={client}>
      <CampaignProvider>
        <MemoryRouter initialEntries={[path]}>
          {selector && <CampaignSelector />}
          <Routes>
            <Route path="/app/campaigns" element={page} />
            <Route path="/app/campaigns/new" element={page} />
            <Route path="/app/campaigns/:campaignId/edit" element={page} />
            <Route
              path="/app/campaigns/:campaignId/dashboard"
              element={
                <>
                  <Location />
                  <div>Dashboard de campaña</div>
                </>
              }
            />
            <Route path="/app/campaigns/:campaignId/activities" element={<Location />} />
            <Route path="/403" element={<div>Acceso denegado</div>} />
          </Routes>
        </MemoryRouter>
      </CampaignProvider>
    </QueryClientProvider>,
  );
  return { ...result, client };
}
async function choose(label: string, option: string) {
  await userEvent.click(screen.getByLabelText(label));
  await userEvent.click(await screen.findByRole('option', { name: option }));
}
async function fillValidForm() {
  await userEvent.type(
    screen.getByLabelText('Nombre de campaña'),
    'Elecciones Seccionales 2027 - Gualaceo',
  );
  await choose('Provincia', 'Azuay');
  await choose('Cantón', 'Gualaceo');
  await userEvent.type(
    screen.getByLabelText('Tipo o nombre de elección'),
    'Elecciones seccionales 2027',
  );
  await userEvent.type(screen.getByLabelText('Fecha electoral'), '14/02/2027');
}

describe('módulo de campañas', () => {
  it('muestra estado vacío y crear primera campaña para ADMIN', async () => {
    handlers();
    renderRoutes('/app/campaigns', <CampaignsPage />);
    expect(await screen.findByText('No existen campañas registradas.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Crear primera campaña' })).toBeVisible();
  });
  it('no muestra crear campaña a un usuario no ADMIN', async () => {
    auth.user = {
      ...auth.user,
      is_superuser: false,
      roles: [{ code: 'ANALYST', name: 'Analista' }],
    };
    handlers();
    renderRoutes('/app/campaigns', <CampaignsPage />);
    expect(await screen.findByText('No tienes campañas asignadas.')).toBeVisible();
    expect(screen.queryByText('Crear primera campaña')).not.toBeInTheDocument();
  });
  it('valida formato de fechas y rango', () => {
    const result = campaignFormSchema.safeParse({
      name: 'Campaña',
      slug: 'campana',
      province_id: '1',
      canton_id: '103',
      office_type: 'MAYOR',
      election_name: 'Elección',
      election_date: '14/02/2027',
      start_date: '15/02/2027',
      end_date: '14/02/2027',
      status: 'ACTIVE',
      description: '',
      is_active: true,
    });
    expect(result.success).toBe(false);
  });
  it('convierte fechas DD/MM/AAAA al contrato API', () => {
    const parsed = campaignFormSchema.parse({
      name: 'Campaña',
      slug: 'campana',
      province_id: '1',
      canton_id: '103',
      office_type: 'MAYOR',
      election_name: 'Elección',
      election_date: '14/02/2027',
      start_date: '',
      end_date: '',
      status: 'ACTIVE',
      description: '',
      is_active: true,
    });
    expect(toCampaignPayload(parsed, false)).toMatchObject({
      canton_id: 103,
      election_date: '2027-02-14',
    });
  });
  it('carga cantones por provincia y limpia el cantón al cambiarla', async () => {
    handlers();
    renderRoutes('/app/campaigns/new', <CampaignFormPage />);
    await choose('Provincia', 'Azuay');
    await choose('Cantón', 'Gualaceo');
    expect(screen.getByLabelText('Cantón')).toHaveTextContent('Gualaceo');
    await choose('Provincia', 'Bolívar');
    expect(screen.getByLabelText('Cantón')).not.toHaveTextContent('Gualaceo');
  });
  it.each([
    [422, 'Revisa los campos indicados.'],
    [409, 'Ya existe una campaña con este identificador.'],
  ])('muestra error HTTP %s', async (status, message) => {
    postStatus = status;
    handlers();
    renderRoutes('/app/campaigns/new', <CampaignFormPage />);
    await fillValidForm();
    await userEvent.click(screen.getByRole('button', { name: 'Guardar campaña' }));
    expect(await screen.findByText(message)).toBeVisible();
  });
  it('crea, selecciona, actualiza selector y redirige al dashboard', async () => {
    handlers();
    renderRoutes('/app/campaigns/new', <CampaignFormPage />, true);
    expect(await screen.findByText('No existen campañas')).toBeVisible();
    await fillValidForm();
    await userEvent.click(screen.getByRole('button', { name: 'Guardar campaña' }));
    expect(await screen.findByText('Dashboard de campaña')).toBeVisible();
    expect(screen.getByTestId('location')).toHaveTextContent('/app/campaigns/campaign-1/dashboard');
    await waitFor(() =>
      expect(screen.getByLabelText('Campaña')).toHaveTextContent('Campaña inicial'),
    );
    expect(lastBody).toMatchObject({
      canton_id: 103,
      office_type: 'MAYOR',
      election_date: '2027-02-14',
    });
  });
  it('edita por PATCH sin enviar canton_id', async () => {
    handlers();
    renderRoutes('/app/campaigns/campaign-1/edit', <CampaignFormPage />);
    expect(await screen.findByDisplayValue('Campaña inicial')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Guardar campaña' }));
    await screen.findByText('Dashboard de campaña');
    expect(lastBody).not.toHaveProperty('canton_id');
  });
  it('redirige a 403 si no es ADMIN', async () => {
    auth.user = {
      ...auth.user,
      is_superuser: false,
      roles: [{ code: 'CAMPAIGN_MANAGER', name: 'Director' }],
    };
    handlers();
    renderRoutes('/app/campaigns/new', <CampaignFormPage />);
    expect(await screen.findByText('Acceso denegado')).toBeVisible();
  });
  it('cambia de campaÃ±a, conserva el mÃ³dulo y elimina el cache anterior', async () => {
    campaigns = [campaign, campaignBeta];
    handlers();
    const { client } = renderRoutes('/app/campaigns/campaign-1/activities', <div />, true);
    await userEvent.click(screen.getByRole('combobox'));
    const betaOption = await screen.findByRole('option', { name: /Beta/ });
    client.setQueryData(['private-a', campaign.id], { value: 'A' });
    await userEvent.click(betaOption);
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/app/campaigns/campaign-2/activities',
      ),
    );
    expect(client.getQueryData(['private-a', campaign.id])).toBeUndefined();
    expect(screen.getByRole('combobox')).toHaveTextContent(campaignBeta.name);
  });
});
