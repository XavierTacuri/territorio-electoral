import { test, expect, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin } from './support/auth';

async function campaignWithAnalysis(request: APIRequestContext) {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as Array<{ id: string; name: string }>;
  for (const campaign of campaigns) {
    const response = await request.get(
      `/api/v1/campaigns/${campaign.id}/current-election/analysis`,
      { headers },
    );
    if (response.status() === 200) return campaign;
  }
  throw new Error('El fixture E2E debe incluir una campaña con análisis de elección actual');
}

test('dashboard ejecutivo: KPIs, mapa, operación, navegación, informe y responsive', async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const campaign = await campaignWithAnalysis(request);
  const campaignId = campaign.id;
  await browserLogin(page);
  await page.getByLabel(/Campa/).click();
  await page.getByRole('option', { name: campaign.name }).click();
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await expect(page).toHaveURL(`/app/campaigns/${campaignId}/dashboard`);

  await expect(page.getByRole('heading', { level: 1, name: 'TERRITORIO ELECTORAL' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'REGISTRO ELECTORAL' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'PARTICIPACIÓN PROYECTADA' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'PARTICIPACIÓN HISTÓRICA' })).toBeVisible();
  await expect(page.getByText('PANORAMA TERRITORIAL')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'CONTEXTO TERRITORIAL' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'ESTADO DE DATOS' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'OPERACIÓN TERRITORIAL' })).toBeVisible();
  await expect(page.getByText('330 votantes', { exact: true })).toBeVisible();
  await expect(page.getByText('73,33 %', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('450', { exact: true })).toBeVisible();

  const electionLink = page.getByRole('link', { name: 'VER ELECCIÓN ACTUAL' });
  await expect(electionLink).toHaveAttribute(
    'href',
    `/app/campaigns/${campaignId}/current-election`,
  );

  const reportResponse = page.waitForResponse(
    (response) =>
      response.url().includes(`/api/v1/campaigns/${campaignId}/reports/generate`) &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Generar informe PDF' }).click();
  expect((await reportResponse).status()).toBeLessThan(400);
  await expect(page.getByText('Generado: informe PDF')).toBeVisible();

  for (const viewport of [
    { name: 'desktop', width: 1440, height: 900 },
    { name: 'tablet', width: 1024, height: 768 },
    { name: 'mobile', width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(
      page.getByRole('heading', { level: 1, name: 'TERRITORIO ELECTORAL' }),
    ).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    );
    expect(overflow, `${viewport.name} no debe tener overflow horizontal global`).toBe(false);
    await page.screenshot({
      path: `../quality-artifacts/dashboard-v2-${viewport.name}.png`,
      fullPage: true,
    });
  }
});
