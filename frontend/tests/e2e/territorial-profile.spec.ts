import { expect, test, type Page } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

async function selectCampaign(page: Page, name: string) {
  await page.getByLabel('Campaña').click();
  await page.getByRole('option', { name }).click();
  return page.url().match(/campaigns\/([^/]+)/)![1];
}

test('candidato abre el Expediente Territorial desde Inteligencia Territorial', async ({
  page,
  request,
}) => {
  test.setTimeout(60000);
  const token = await apiToken(request, e2eUsers.candidate);
  const headers = { Authorization: `Bearer ${token}` };
  const campaignsResponse = await request.get('/api/v1/campaigns?page_size=100', { headers });
  const campaign = (await campaignsResponse.json()).items.find(
    (item: { slug: string }) => item.slug === 'gualaceo-e2e-2027',
  );
  expect(campaign).toBeTruthy();
  const analysisResponse = await request.get(
    `/api/v1/campaigns/${campaign.id}/current-election/analysis`,
    { headers },
  );
  expect(analysisResponse.status()).toBe(200);
  const analysis = await analysisResponse.json();
  const jadan = analysis.parishes.find((p: { name: string }) => p.name === 'Jadán');
  expect(jadan).toBeTruthy();
  const registeredVoters = jadan.registered_voters_current.toLocaleString('es-EC');

  await browserLogin(page, e2eUsers.candidate);
  await selectCampaign(page, 'Gualaceo E2E 2027');
  await page.getByRole('link', { name: 'Inteligencia territorial', exact: true }).click();
  await page.getByLabel('Seleccionar parroquia').click();
  await page.getByRole('option', { name: /^Jadán/ }).click();
  await page.getByRole('button', { name: 'VER EXPEDIENTE' }).click();

  await expect(
    page.getByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' }),
  ).toBeVisible();
  const breadcrumb = page.getByRole('navigation').filter({ hasText: 'Centro de Comando' });
  await expect(breadcrumb.getByText('Centro de Comando')).toBeVisible();
  await expect(breadcrumb.getByText('Inteligencia territorial')).toBeVisible();
  await expect(page.getByRole('heading', { level: 3, name: 'Jadán' })).toBeVisible();
  await expect(page.getByText(registeredVoters).first()).toBeVisible();
  await expect(page.getByRole('heading', { name: 'OPERACIÓN TERRITORIAL' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'NECESIDADES TERRITORIALES' })).toBeVisible();
  // Seguimientos de campaña se retiró del expediente territorial (retiro de producto).
  await expect(page.getByRole('heading', { name: 'SEGUIMIENTOS DE CAMPAÑA' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'CRONOLOGÍA TERRITORIAL' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Mapa de elección actual' })).toBeVisible();

  const iaLink = page.getByRole('link', {
    name: `Resume el expediente territorial de Jadán.`,
  });
  await expect(iaLink).toHaveAttribute(
    'href',
    new RegExp(`territory-ai\\?parish_id=${jadan.parish_id}&question=`),
  );
});

test('coordinador solo accede al expediente de su parroquia asignada', async ({
  page,
  request,
}) => {
  test.setTimeout(60000);
  const token = await apiToken(request, e2eUsers.candidate);
  const headers = { Authorization: `Bearer ${token}` };
  const campaignsResponse = await request.get('/api/v1/campaigns?page_size=100', { headers });
  const campaign = (await campaignsResponse.json()).items.find(
    (item: { slug: string }) => item.slug === 'gualaceo-e2e-2027',
  );
  const analysis = await (
    await request.get(`/api/v1/campaigns/${campaign.id}/current-election/analysis`, { headers })
  ).json();
  const assigned = analysis.parishes.find((p: { name: string }) => p.name === 'Gualaceo');
  const notAssigned = analysis.parishes.find((p: { name: string }) => p.name === 'Jadán');
  expect(assigned).toBeTruthy();
  expect(notAssigned).toBeTruthy();

  await browserLogin(page, e2eUsers.coordinator);
  await page.goto(`/app/campaigns/${campaign.id}/territories/${assigned.parish_id}`);
  await expect(
    page.getByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { level: 3, name: 'Gualaceo' })).toBeVisible();

  await page.goto(`/app/campaigns/${campaign.id}/territories/${notAssigned.parish_id}`);
  await expect(page.getByText('403')).toBeVisible();
});
