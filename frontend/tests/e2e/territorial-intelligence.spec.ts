import { expect, test, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin } from './support/auth';

async function fixtureCampaign(request: APIRequestContext) {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; name: string }[];
  for (const campaign of campaigns) {
    const response = await request.get(
      `/api/v1/campaigns/${campaign.id}/current-election/analysis`,
      { headers },
    );
    if (response.status() === 200) return { campaign, analysis: await response.json() };
  }
  throw new Error('El seed E2E requiere análisis territorial sintético');
}

test('dashboard abre ficha territorial, mapa, INEC, comparador y PDF portables', async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const { campaign, analysis } = await fixtureCampaign(request);
  await browserLogin(page);
  await page.getByLabel(/Campa/).click();
  await page.getByRole('option', { name: campaign.name }).click();
  await page.getByRole('link', { name: 'Inteligencia territorial', exact: true }).click();
  await expect(page).toHaveURL(`/app/campaigns/${campaign.id}/territories`);
  const selector = page.getByLabel('Seleccionar parroquia');
  await selector.click();
  await page.getByRole('option', { name: new RegExp(analysis.parishes[0].name) }).click();
  await expect(page).toHaveURL(new RegExp(`/territories/${analysis.parishes[0].parish_id}$`));
  await expect(
    page.getByRole('heading', {
      level: 2,
      name: new RegExp(`${analysis.parishes[0].name}.*DPA`, 'i'),
    }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'PARTICIPACIÓN HISTÓRICA' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'PROYECCIÓN DE PARTICIPACIÓN' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Mapa de elección actual' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'CONTEXTO TERRITORIAL' })).toBeVisible();
  const compare = page.getByLabel('Seleccione entre 2 y 3 parroquias');
  for (const parish of analysis.parishes.slice(0, 3)) {
    await compare.click();
    await page.getByRole('option', { name: new RegExp(parish.name) }).click();
  }
  for (const parish of analysis.parishes.slice(0, 3))
    await expect(page.getByRole('columnheader', { name: parish.name })).toBeVisible();
  const report = page.waitForResponse(
    (response) =>
      response.url().includes('/reports/generate') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'GENERAR FICHA PDF' }).click();
  expect((await report).status()).toBeLessThan(400);
  await expect(page.getByText('Ficha generada')).toBeVisible();
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 1366, height: 768 },
  ]) {
    await page.setViewportSize(viewport);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    ).toBe(true);
  }
});
