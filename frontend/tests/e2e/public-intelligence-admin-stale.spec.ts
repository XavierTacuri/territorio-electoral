import { expect, test, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

const auth = (token: string) => ({ Authorization: `Bearer ${token}` });
async function campaign(request: APIRequestContext, token: string) {
  const data = await (
    await request.get('/api/v1/campaigns?page_size=100', { headers: auth(token) })
  ).json();
  return data.items.find((item: { slug: string }) => item.slug === 'gualaceo-e2e-2027');
}
async function openSources(page: Parameters<typeof browserLogin>[0]) {
  await page.getByLabel('Campaña').click();
  await page.getByRole('option', { name: 'Gualaceo E2E 2027' }).click();
  await page.getByRole('link', { name: 'Inteligencia pública', exact: true }).click();
  await page.getByRole('tab', { name: 'Fuentes públicas' }).click();
}

test('administración completa y RBAC de fuentes públicas', async ({ page, request }) => {
  const suffix = Date.now().toString();
  const name = `Fuente Oficial Sintética Administración ${suffix}`;
  await browserLogin(page);
  await openSources(page);
  await page.getByRole('button', { name: 'Nueva fuente' }).click();
  const create = page.getByRole('dialog');
  await create.getByLabel('Código').fill(`RSS_ADMIN_${suffix}`);
  await create.getByLabel('Nombre').fill(name);
  await create.getByLabel('Publisher').fill('Publisher sintético inicial');
  await create.getByLabel('URL base').fill('http://public-fixture:8080');
  await create.getByLabel('RSS URL (opcional)').fill('http://public-fixture:8080/feed.xml');
  await create.getByLabel('Intervalo actualización (min)').fill('60');
  await create.getByRole('button', { name: 'Guardar' }).click();
  const card = page.getByText(name, { exact: true }).locator('..').locator('..').locator('..');
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  await expect(card.getByText('Activa', { exact: true })).toBeVisible();
  await expect(card.getByText('Estado: Nunca actualizada')).toBeVisible();

  await card.getByRole('button', { name: 'Editar' }).click();
  const edit = page.getByRole('dialog');
  const editedName = `${name} Editada`;
  await edit.getByLabel('Nombre').fill(editedName);
  await edit.getByLabel('Publisher').fill('Publisher sintético editado');
  await edit.getByLabel('Intervalo actualización (min)').fill('90');
  await edit.getByRole('button', { name: 'Guardar' }).click();
  const editedCard = page
    .getByText(editedName, { exact: true })
    .locator('..')
    .locator('..')
    .locator('..');
  await expect(editedCard.getByText('Publisher sintético editado')).toBeVisible();

  await editedCard.getByRole('button', { name: 'Actualizar ahora' }).click();
  await expect(
    page.getByText(/\d+ nuevas · \d+ actualizadas · \d+ sin cambios · \d+ errores/),
  ).toBeVisible();
  await editedCard.getByRole('button', { name: 'Ver historial' }).click();
  const history = page.getByRole('dialog', { name: 'HISTORIAL DE ACTUALIZACIONES' });
  await expect(history.getByText('Correcta')).toBeVisible();
  await expect(history.getByText(/Inicio:/)).toBeVisible();
  await expect(history.getByText(/Fin:/)).toBeVisible();
  await expect(
    history.getByText(/Nuevos \d+ · Actualizados \d+ · Sin cambios \d+ · Errores \d+/),
  ).toBeVisible();
  await history.getByRole('button', { name: 'Cerrar' }).click();

  await editedCard.getByRole('button', { name: 'Desactivar' }).click();
  const confirmation = page.getByRole('dialog', { name: 'Desactivar fuente' });
  await expect(confirmation).toContainText(
    'Las publicaciones y el historial existente se conservarán',
  );
  await confirmation.getByRole('button', { name: 'Desactivar' }).click();
  await expect(editedCard.getByText('Inactiva', { exact: true })).toBeVisible();
  await expect(editedCard.getByRole('button', { name: 'Actualizar ahora' })).toBeDisabled();

  const admin = await apiToken(request);
  const currentCampaign = await campaign(request, admin);
  const sources = await (
    await request.get(`/api/v1/campaigns/${currentCampaign.id}/public-sources`, {
      headers: auth(admin),
    })
  ).json();
  const source = sources.find((item: { code: string }) => item.code === `RSS_ADMIN_${suffix}`);
  expect(
    (
      await request.post(`/api/v1/public-sources/${source.id}/fetch`, { headers: auth(admin) })
    ).status(),
  ).toBe(400);
  await editedCard.getByRole('button', { name: 'Reactivar' }).click();
  await expect(editedCard.getByText('Activa', { exact: true })).toBeVisible();

  await page
    .getByRole('button', { name: /Usuario E2E|Cerrar sesión/ })
    .click()
    .catch(() => {});
  await page.goto('/login');
  await browserLogin(page, e2eUsers.analyst);
  await openSources(page);
  await expect(page.getByRole('button', { name: 'Nueva fuente' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Editar' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Desactivar' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Reactivar' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Actualizar ahora' })).toHaveCount(0);
  const analyst = await apiToken(request, e2eUsers.analyst);
  expect(
    (
      await request.patch(`/api/v1/public-sources/${source.id}`, {
        headers: auth(analyst),
        data: { active: false },
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await request.post(`/api/v1/public-sources/${source.id}/fetch`, { headers: auth(analyst) })
    ).status(),
  ).toBe(403);
});

test('SOURCE_STALE determinístico, deduplicado, recuperable e ignora inactivas/nuevas', async ({
  page,
  request,
}) => {
  const admin = await apiToken(request);
  const currentCampaign = await campaign(request, admin);
  const suffix = Date.now().toString();
  const created = await request.post(`/api/v1/campaigns/${currentCampaign.id}/public-sources`, {
    headers: auth(admin),
    data: {
      code: `RSS_STALE_${suffix}`,
      name: `Fuente frescura ${suffix}`,
      publisher: 'Publisher frescura',
      source_type: 'RSS',
      base_url: 'http://public-fixture:8080',
      feed_url: 'http://public-fixture:8080/feed.xml',
      official: true,
      active: true,
      retrieval_method: 'RSS',
      refresh_interval_minutes: 60,
    },
  });
  expect(created.status()).toBe(201);
  const source = await created.json();
  expect(
    (
      await request.post(
        `/api/v1/campaigns/${currentCampaign.id}/public-intelligence/evaluate-stale`,
        { headers: auth(admin) },
      )
    ).status(),
  ).toBe(200);
  let alerts = await (
    await request.get(`/api/v1/campaigns/${currentCampaign.id}/alerts?page=1&page_size=100`, {
      headers: auth(admin),
    })
  ).json();
  expect(
    alerts.items.filter(
      (x: { rule_code: string; resource_id: string }) =>
        x.rule_code === 'SOURCE_STALE' && x.resource_id === source.id,
    ),
  ).toHaveLength(0);

  expect(
    (
      await request.post(`/api/v1/public-sources/${source.id}/fetch`, { headers: auth(admin) })
    ).status(),
  ).toBe(200);
  const realNow = new Date();
  const future = new Date(realNow.getTime() + 76 * 60_000);
  const evaluateAt = `/api/v1/campaigns/${currentCampaign.id}/public-intelligence/evaluate-stale?at=${encodeURIComponent(future.toISOString())}`;
  expect((await request.post(evaluateAt, { headers: auth(admin) })).status()).toBe(200);
  expect((await request.post(evaluateAt, { headers: auth(admin) })).status()).toBe(200);
  alerts = await (
    await request.get(`/api/v1/campaigns/${currentCampaign.id}/alerts?page=1&page_size=100`, {
      headers: auth(admin),
    })
  ).json();
  const stale = alerts.items.filter(
    (x: { rule_code: string; resource_id: string }) =>
      x.rule_code === 'SOURCE_STALE' && x.resource_id === source.id,
  );
  expect(stale).toHaveLength(1);
  expect(stale[0].status).toBe('OPEN');

  await page.clock.install({ time: future });
  await browserLogin(page);
  await openSources(page);
  const card = page
    .getByText(`Fuente frescura ${suffix}`, { exact: true })
    .locator('..')
    .locator('..')
    .locator('..');
  await expect(card.getByText('Estado: Desactualizada')).toBeVisible();
  await page.getByRole('link', { name: 'Alertas' }).click();
  await expect(page.getByText('Fuente pública desactualizada').first()).toBeVisible();

  await page.getByRole('link', { name: 'Inteligencia pública', exact: true }).click();
  await page.getByRole('tab', { name: 'Fuentes públicas' }).click();
  await card.getByRole('button', { name: 'Actualizar ahora' }).click();
  await page.clock.setFixedTime(realNow);
  await expect(card.getByText('Estado: Actualizada')).toBeVisible();
  expect(
    (
      await request.post(
        `/api/v1/campaigns/${currentCampaign.id}/public-intelligence/evaluate-stale`,
        { headers: auth(admin) },
      )
    ).status(),
  ).toBe(200);
  let staleDetail = await (
    await request.get(`/api/v1/campaigns/${currentCampaign.id}/alerts/${stale[0].id}`, {
      headers: auth(admin),
    })
  ).json();
  expect(staleDetail.status).toBe('RESOLVED');

  await request.patch(`/api/v1/public-sources/${source.id}`, {
    headers: auth(admin),
    data: { active: false },
  });
  expect((await request.post(evaluateAt, { headers: auth(admin) })).status()).toBe(200);
  staleDetail = await (
    await request.get(`/api/v1/campaigns/${currentCampaign.id}/alerts/${stale[0].id}`, {
      headers: auth(admin),
    })
  ).json();
  expect(staleDetail.status).toBe('RESOLVED');
});
