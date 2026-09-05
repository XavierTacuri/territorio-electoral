import { test, expect, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin } from './support/auth';

async function campaignWithAnalysis(request: APIRequestContext) {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as Array<{ id: string; name: string; slug: string }>;
  const synthetic = campaigns.find((campaign) => campaign.slug === 'territorio-sintetico-e2e');
  if (synthetic) return synthetic;
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

  await expect(
    page.getByRole('heading', { level: 1, name: 'Centro de Comando Territorial' }),
  ).toBeVisible();
  await expect(page.getByText('Padrón electoral', { exact: true })).toBeVisible();
  await expect(page.getByText('Participación central', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Mapa operativo territorial' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Hoy en territorio' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Panorama electoral' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Territorio IA' })).toBeVisible();

  const electionLink = page.getByRole('link', { name: 'VER PANORAMA ELECTORAL' });
  await expect(electionLink).toHaveAttribute('href', `/app/campaigns/${campaignId}/panorama`);

  for (const viewport of [
    { name: 'desktop', width: 1440, height: 900 },
    { name: 'tablet', width: 1024, height: 768 },
    { name: 'mobile', width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Centro de Comando Territorial' }),
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
