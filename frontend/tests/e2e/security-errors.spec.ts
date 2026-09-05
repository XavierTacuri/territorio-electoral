import { test, expect } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';
const auth = (accessToken: string) => ({ Authorization: `Bearer ${accessToken}` });

test('403 reales respetan campaña, territorio, alertas y administración', async ({
  page,
  request,
}) => {
  const adminToken = await apiToken(request);
  const campaigns = await (
    await request.get('/api/v1/campaigns?page_size=100', { headers: auth(adminToken) })
  ).json();
  const campaign = campaigns.items.find(
    (item: { slug: string }) => item.slug === 'gualaceo-e2e-2027',
  );
  expect(campaign).toBeTruthy();
  const campaignId = campaign.id as string;
  let unassigned = campaigns.items.find(
    (x: { slug: string }) => x.slug === 'security-e2e-unassigned',
  );
  if (!unassigned) {
    const created = await request.post('/api/v1/campaigns', {
      headers: auth(adminToken),
      data: {
        name: 'Campaña aislada E2E',
        slug: 'security-e2e-unassigned',
        canton_id: campaign.canton_id,
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
    await request.get(`/api/v1/parishes?canton_id=${campaign.canton_id}`, {
      headers: auth(adminToken),
    })
  ).json();
  const activityTypes = await (
    await request.get('/api/v1/activity-types', { headers: auth(adminToken) })
  ).json();
  const candidateToken = await apiToken(request, e2eUsers.candidate);
  const coordinatorToken = await apiToken(request, e2eUsers.coordinator);
  const analystToken = await apiToken(request, e2eUsers.analyst);
  const coordinatorParishes = await (
    await request.get(`/api/v1/parishes?canton_id=${campaign.canton_id}`, {
      headers: auth(coordinatorToken),
    })
  ).json();
  const coordinatorParishIds = new Set(
    coordinatorParishes.map((parish: { id: number }) => parish.id),
  );
  const outsideParish = parishes.find(
    (parish: { id: number }) => !coordinatorParishIds.has(parish.id),
  );
  expect(outsideParish).toBeTruthy();

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
      parish_id: outsideParish.id,
    },
  });
  expect(outsideTerritory.status()).toBe(403);

  await request.post(`/api/v1/campaigns/${campaignId}/alerts/evaluate`, {
    headers: auth(adminToken),
    data: { rule_codes: ['MISSING_PARISH_GEOMETRY'], as_of_date: '2026-08-03' },
  });
  const alertList = await (
    await request.get(`/api/v1/campaigns/${campaignId}/alerts?page=1&page_size=20&status=OPEN`, {
      headers: auth(candidateToken),
    })
  ).json();
  const candidateAction = await request.post(
    `/api/v1/campaigns/${campaignId}/alerts/${alertList.items[0].id}/acknowledge`,
    { headers: auth(candidateToken), data: { action_date: '2026-08-03', note: 'No autorizada' } },
  );
  // CANDIDATE is an executive campaign role and may acknowledge alerts in-scope.
  expect(candidateAction.status()).toBe(200);
  expect(
    (
      await request.get('/api/v1/users?page=1&page_size=20', { headers: auth(analystToken) })
    ).status(),
  ).toBe(403);

  await browserLogin(page, e2eUsers.analyst);
  await page.goto('/app/admin/users');
  await expect(page).toHaveURL(/\/403$/);
  await expect(page.getByRole('heading', { name: '403' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Volver al inicio' })).toBeVisible();
});

test('404 frontend y recursos inexistentes son controlados', async ({ page, request }) => {
  await page.goto('/ruta-que-no-existe');
  await expect(page.getByRole('heading', { name: '404' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Volver al inicio' })).toBeVisible();

  const adminToken = await apiToken(request);
  const campaigns = await (
    await request.get('/api/v1/campaigns?page_size=100', { headers: auth(adminToken) })
  ).json();
  const campaignId = campaigns.items[0].id as string;

  // Seguimientos/Commitments es dominio legacy retirado de la experiencia
  // productiva: la URL directa ya no expone el módulo, cae al 404 coherente.
  await browserLogin(page, e2eUsers.admin);
  await page.goto(`/app/campaigns/${campaignId}/commitments`);
  await expect(page.getByRole('heading', { name: '404' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Crear seguimiento' })).toHaveCount(0);

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
