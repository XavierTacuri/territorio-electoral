import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

const password = process.env.E2E_USER_PASSWORD;
if (!password) throw new Error('E2E_USER_PASSWORD es obligatorio');

async function token(request: APIRequestContext, username: string) {
  const response = await request.post('/api/v1/auth/login', {
    form: { username, password: password! },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).access_token as string;
}
const auth = (accessToken: string) => ({ Authorization: `Bearer ${accessToken}` });

async function browserLogin(page: Page, username: string) {
  await page.goto('/login');
  await page.getByLabel('Correo o nombre de usuario').fill(username);
  await page.getByRole('textbox', { name: 'Contraseña' }).fill(password!);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await expect(page).toHaveURL(/\/app/);
}

test('403 reales respetan campaña, territorio, alertas y administración', async ({
  page,
  request,
}) => {
  const adminToken = await token(request, 'admin_e2e');
  const campaigns = await (
    await request.get('/api/v1/campaigns?page_size=100', { headers: auth(adminToken) })
  ).json();
  const campaignId = campaigns.items[0].id as string;
  let unassigned = campaigns.items.find(
    (x: { slug: string }) => x.slug === 'security-e2e-unassigned',
  );
  if (!unassigned) {
    const created = await request.post('/api/v1/campaigns', {
      headers: auth(adminToken),
      data: {
        name: 'Campaña aislada E2E',
        slug: 'security-e2e-unassigned',
        canton_id: campaigns.items[0].canton_id,
        office_type: 'MAYOR',
        election_name: 'Proceso sintético de autorización',
        election_date: '2027-02-14',
        start_date: '2026-08-03',
        status: 'DRAFT',
        is_active: true,
      },
    });
    expect(created.status()).toBe(201);
    unassigned = await created.json();
  }
  const parishes = await (
    await request.get('/api/v1/parishes', { headers: auth(adminToken) })
  ).json();
  const activityTypes = await (
    await request.get('/api/v1/activity-types', { headers: auth(adminToken) })
  ).json();
  const candidateToken = await token(request, 'candidate_e2e');
  const coordinatorToken = await token(request, 'coordinator_e2e');
  const analystToken = await token(request, 'analyst_e2e');

  const notAssigned = await request.get(`/api/v1/campaigns/${unassigned.id}/activities`, {
    headers: auth(candidateToken),
  });
  expect(notAssigned.status()).toBe(403);
  expect(await notAssigned.text()).not.toContain('Gualaceo E2E');

  const outsideTerritory = await request.post(`/api/v1/campaigns/${campaignId}/activities`, {
    headers: auth(coordinatorToken),
    data: {
      activity_type_code: activityTypes[0].code,
      title: 'Actividad fuera de alcance',
      activity_date: '2026-08-03',
      status: 'PLANNED',
      parish_id: parishes[1].id,
    },
  });
  expect(outsideTerritory.status()).toBe(403);

  const alertList = await (
    await request.get(`/api/v1/campaigns/${campaignId}/alerts?page=1&page_size=20`, {
      headers: auth(candidateToken),
    })
  ).json();
  const candidateAction = await request.post(
    `/api/v1/campaigns/${campaignId}/alerts/${alertList.items[0].id}/acknowledge`,
    { headers: auth(candidateToken), data: { action_date: '2026-08-03', note: 'No autorizada' } },
  );
  expect(candidateAction.status()).toBe(403);
  expect(
    (
      await request.get('/api/v1/users?page=1&page_size=20', { headers: auth(analystToken) })
    ).status(),
  ).toBe(403);

  await browserLogin(page, 'analyst_e2e');
  await page.goto('/app/admin/users');
  await expect(page).toHaveURL(/\/403$/);
  await expect(page.getByRole('heading', { name: '403' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Volver al inicio' })).toBeVisible();
});

test('404 frontend y recursos inexistentes son controlados', async ({ page, request }) => {
  await page.goto('/ruta-que-no-existe');
  await expect(page.getByRole('heading', { name: '404' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Volver al inicio' })).toBeVisible();

  const adminToken = await token(request, 'admin_e2e');
  const campaigns = await (
    await request.get('/api/v1/campaigns?page_size=100', { headers: auth(adminToken) })
  ).json();
  const campaignId = campaigns.items[0].id as string;
  const missing = '00000000-0000-4000-8000-000000000099';
  for (const endpoint of [
    `/api/v1/campaigns/${campaignId}/activities/${missing}`,
    `/api/v1/campaigns/${campaignId}/surveys/${missing}`,
    `/api/v1/campaigns/${campaignId}/reports/${missing}`,
  ]) {
    const response = await request.get(endpoint, { headers: auth(adminToken) });
    expect(response.status()).toBe(404);
    expect(await response.text()).not.toMatch(/storage_key|refresh_token|password_hash/);
  }
});
