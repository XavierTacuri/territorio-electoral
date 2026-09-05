import { expect, test, type Page } from '@playwright/test';
import { browserLogin } from './support/auth';
import { uniqueE2eValue } from './support/run-data';

async function createCampaign(page: Page, province: string, canton: string, baseName: string) {
  const campaignName = uniqueE2eValue(baseName);
  await page.goto('/app/campaigns/new');
  await page.getByLabel('Nombre de campaña').fill(campaignName);
  await page
    .getByLabel('Identificador (slug)')
    .fill(uniqueE2eValue(`demo-${province.toLowerCase()}`));
  await page.getByLabel('Provincia').click();
  await page.getByRole('option', { name: province, exact: true }).click();
  await expect(page.getByLabel('Cantón')).toBeEnabled();
  await page.getByLabel('Cantón').click();
  await page.getByRole('option', { name: canton, exact: true }).click();
  await page.getByLabel('Tipo o nombre de elección').fill('Elecciones Seccionales 2027');
  await page.getByLabel('Fecha electoral').fill('14/02/2027');
  const createResponse = page.waitForResponse(
    (response) => response.request().method() === 'POST' && response.url().endsWith('/api/v1/campaigns'),
  );
  await page.getByRole('button', { name: 'Guardar campaña' }).click();
  const response = await createResponse;
  expect(response.status(), await response.text()).toBe(201);
  await expect(page).toHaveURL(/\/app\/campaigns\/[^/]+\/dashboard/);
  await expect(page.getByRole('combobox', { name: 'Campaña' })).toContainText(campaignName);
  return campaignName;
}

test('crea campañas nacionales Cuenca y Quito con cantones dependientes', async ({ page }) => {
  await browserLogin(page);
  const cuencaName = await createCampaign(page, 'Azuay', 'Cuenca', '[DEMO] Cuenca territorial');
  const quitoName = await createCampaign(page, 'Pichincha', 'Distrito Metropolitano de Quito', '[DEMO] Quito territorial');

  await page.getByRole('combobox', { name: 'Campaña' }).click();
  await expect(page.getByRole('option').filter({ hasText: cuencaName })).toContainText('Cuenca · Azuay');
  await expect(page.getByRole('option').filter({ hasText: quitoName })).toContainText(
    'Distrito Metropolitano de Quito · Pichincha',
  );
});
