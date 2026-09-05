import { expect, test, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

async function campaignWithAnalysis(request: APIRequestContext) {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = (await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()).items as { id: string; name: string; slug: string }[];
  const campaign = campaigns.find((item) => item.slug === 'gualaceo-e2e-2027');
  if (!campaign) throw new Error('El fixture E2E requiere gualaceo-e2e-2027');
  return campaign;
}

test('Candidate consulta el Centro de Comando y sus módulos', async ({ page, request }) => {
  test.setTimeout(120_000);
  const campaign = await campaignWithAnalysis(request);
  await browserLogin(page, e2eUsers.candidate);
  await page.getByLabel(/Campa/).click();
  await page.getByRole('option', { name: campaign.name }).click();
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Centro de Comando Territorial' })).toBeVisible();
  for (const text of ['Padrón electoral', 'Participación central', 'Actividades', 'Necesidades', 'Encuestas y estudios', 'Territorio IA']) await expect(page.getByText(text, { exact: true }).first()).toBeVisible();
  for (const value of ['34.784', '71,00 %', '24.697', '68,58 %', '71,89 %']) await expect(page.getByText(value, { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('region', { name: 'Mapa operativo territorial' })).toBeVisible();
  const candidateToken = await apiToken(request, e2eUsers.candidate);
  const boundaries = await request.get(`/api/v1/campaigns/${campaign.id}/map/boundaries?level=PARISH&limit=5000`, { headers: { Authorization: `Bearer ${candidateToken}` } });
  expect(boundaries.status()).toBe(200);
  expect((await boundaries.json()).features).toHaveLength(9);
  await expect(page.getByRole('link', { name: 'VER PANORAMA ELECTORAL' })).toHaveAttribute('href', `/app/campaigns/${campaign.id}/panorama`);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: '../quality-artifacts/command-center-candidate-desktop.png', fullPage: true });
  await page.getByRole('button', { name: '¿Cuál es el panorama electoral actual?' }).click();
  await expect(page).toHaveURL(/territory-ai\?question=/);
});

test('Centro de Comando no produce overflow en móvil', async ({ page, request }) => {
  const campaign = await campaignWithAnalysis(request);
  await page.setViewportSize({ width: 375, height: 812 });
  await browserLogin(page, e2eUsers.candidate);
  await page.goto(`/app/campaigns/${campaign.id}/dashboard`);
  await expect(page.getByRole('heading', { level: 1, name: 'Centro de Comando Territorial' })).toBeVisible();
  const overflow = await page.locator('body *').evaluateAll((elements) => elements.filter((element) => element.getBoundingClientRect().right > document.documentElement.clientWidth + 1).map((element) => ({ tag: element.tagName, text: element.textContent?.trim().slice(0, 80), right: Math.round(element.getBoundingClientRect().right), width: Math.round(element.getBoundingClientRect().width) })).slice(0, 10));
  expect(overflow).toEqual([]);
  await page.screenshot({ path: '../quality-artifacts/command-center-candidate-mobile-375.png', fullPage: true });
  await page.setViewportSize({ width: 768, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
});

test('Campaign Manager conserva la experiencia ejecutiva', async ({ page, request }) => {
  const campaign = await campaignWithAnalysis(request);
  await browserLogin(page, e2eUsers.manager);
  await page.goto(`/app/campaigns/${campaign.id}/dashboard`);
  await expect(page.getByRole('heading', { level: 1, name: 'Centro de Comando Territorial' })).toBeVisible();
  await expect(page.getByText('Padrón electoral', { exact: true })).toBeVisible();
  await expect(page.getByText('Territorio IA', { exact: true })).toBeVisible();
});
