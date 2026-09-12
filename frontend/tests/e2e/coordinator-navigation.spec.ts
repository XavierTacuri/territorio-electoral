import { expect, test, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

function jwtUserId(token: string): string {
  const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
  return payload.sub as string;
}

async function gualaceoCampaign(request: APIRequestContext, headers: Record<string, string>) {
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; slug: string; canton_id: number }[];
  const campaign = campaigns.find((item) => item.slug === 'gualaceo-e2e-2027');
  if (!campaign) throw new Error('El fixture E2E requiere gualaceo-e2e-2027');
  return campaign;
}

test('TERRITORIAL_COORDINATOR mantiene su redirección directa al Expediente de su parroquia asignada', async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const adminHeaders = { Authorization: 'Bearer ' + (await apiToken(request)) };
  const campaign = await gualaceoCampaign(request, adminHeaders);

  const coordinatorToken = await apiToken(request, e2eUsers.coordinator);
  const coordinatorUserId = jwtUserId(coordinatorToken);
  const assignments = (await (
    await request.get(`/api/v1/campaigns/${campaign.id}/territorial-assignments`, {
      headers: adminHeaders,
    })
  ).json()) as { user_id: string; parish_id: number; is_active: boolean }[];
  const assignedParishId = assignments.find(
    (a) => a.user_id === coordinatorUserId && a.is_active,
  )?.parish_id;
  if (!assignedParishId)
    throw new Error('coordinator_e2e requiere una asignación territorial activa en el fixture E2E');
  const allParishes = (await (
    await request.get(`/api/v1/parishes?canton_id=${campaign.canton_id}`, { headers: adminHeaders })
  ).json()) as { id: number }[];
  const unassignedParishId = allParishes.find((p) => p.id !== assignedParishId)?.id;

  // Every `page.goto` below is a full browser navigation (not SPA
  // client-side routing), so each one re-runs the silent-refresh-on-load
  // flow. Back-to-back reloads with no gap can race the refresh-token
  // rotation and spuriously log the session out mid-test — unrelated to the
  // RBAC behavior under test — so each navigation is followed by a short
  // settle wait.
  const goto = async (path: string) => {
    await page.goto(`/app/campaigns/${campaign.id}${path}`);
    await page.waitForTimeout(500);
  };

  await browserLogin(page, e2eUsers.coordinator);
  await goto('/dashboard');
  await expect(page).toHaveURL(/\/app\/campaigns\/[^/]+\/dashboard/);

  await test.step('Inteligencia territorial redirige directo al Expediente cuando hay una sola parroquia asignada', async () => {
    await goto('/territories');
    await expect(page).not.toHaveURL(/\/403$/);
    // coordinator_e2e has exactly one active TerritorialAssignment in the
    // fixture, so Inteligencia Territorial never shows a selector/comparison
    // — it replaces straight into that parish's Expediente Territorial.
    await expect(page).toHaveURL(new RegExp(`/territories/${assignedParishId}$`));
    await expect(page.getByRole('heading', { name: 'COMPARAR TERRITORIOS' })).toHaveCount(0);
  });

  if (unassignedParishId) {
    await test.step('URL directa a una parroquia no asignada devuelve 403', async () => {
      await goto(`/territories/${unassignedParishId}`);
      await expect(page.getByRole('heading', { name: '403' })).toBeVisible();
    });
  }

  await test.step('URL directa a la parroquia asignada funciona', async () => {
    await goto(`/territories/${assignedParishId}`);
    await expect(page).not.toHaveURL(/\/403$/);
  });
});

test('TERRITORIAL_COORDINATOR no tiene herramientas ejecutivas en Panorama ni en el Expediente Territorial', async ({
  page,
  request,
}) => {
  test.setTimeout(60000);
  const adminHeaders = { Authorization: 'Bearer ' + (await apiToken(request)) };
  const campaign = await gualaceoCampaign(request, adminHeaders);

  await browserLogin(page, e2eUsers.coordinator);

  await test.step('Panorama: sin Territorio IA, Generar informe ni preguntas rápidas', async () => {
    await page.goto(`/app/campaigns/${campaign.id}/panorama`);
    await expect(page.getByRole('heading', { level: 1, name: 'Panorama electoral' })).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByRole('link', { name: 'CONSULTAR EN TERRITORIO IA' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'GENERAR INFORME' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Preguntas rápidas' })).toHaveCount(0);
    // Esta página no tiene loading state propio (a diferencia de Dashboard/
    // Expediente): los KPIs dependen de que la query de análisis resuelva,
    // así que se les da el mismo margen que al heading principal.
    await expect(page.getByText('Electores actuales')).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('heading', { name: 'Operación territorial' })).toBeVisible();
  });

  await test.step('Inteligencia Territorial → Expediente: sin Territorio IA ni generación de informes', async () => {
    await page.goto(`/app/campaigns/${campaign.id}/territories`);
    await expect(
      page.getByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' }),
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('heading', { name: 'COMPARAR TERRITORIOS' })).toHaveCount(0);
    await expect(page.getByText('PREGUNTAR A TERRITORIO IA')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'TERRITORIO IA' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'DESCARGAR EXPEDIENTE' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'VER EN MAPA' })).toBeVisible();
  });
});
