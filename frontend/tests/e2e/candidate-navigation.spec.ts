import { expect, test, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

const executivePaths = [
  'dashboard',
  'panorama',
  'territories',
  'surveys',
  'territory-ai',
  'calendar',
  'reports',
  'alerts',
  'debate',
  'election-day',
  'operations',
  'activities',
  'needs',
];

async function assertExecutiveNavigation(page: Parameters<typeof browserLogin>[0]) {
  const navigation = page.getByRole('navigation', { name: 'Navegación principal' });
  await expect(navigation.getByRole('link')).toHaveCount(executivePaths.length);
  for (const path of executivePaths) {
    await expect(navigation.locator(`a[href*="/${path}"]`)).toHaveCount(1);
  }
  await expect(navigation.locator('a[href="/app/campaigns"]')).toHaveCount(0);
  await expect(navigation.locator('a[href="/app/organization"]')).toHaveCount(0);
  await expect(navigation.locator('a[href*="/electoral"]')).toHaveCount(0);
  await expect(navigation.locator('a[href*="/public-intelligence"]')).toHaveCount(0);
  // Seguimientos se retiró de la navegación (retiro de producto): ya no es un
  // módulo productivo, aunque el endpoint legacy siga existiendo.
  await expect(navigation.locator('a[href*="/commitments"]')).toHaveCount(0);
}

async function openExecutiveCampaign(
  page: Parameters<typeof browserLogin>[0],
  request: APIRequestContext,
  username: string,
) {
  const token = await apiToken(request, username);
  const response = await request.get('/api/v1/campaigns?page_size=100', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status()).toBe(200);
  const campaigns = (await response.json()) as { items: { id: string; name: string }[] };
  const campaign = campaigns.items.find((item) => item.name === 'Gualaceo E2E 2027');
  expect(campaign).toBeTruthy();
  await page.goto(`/app/campaigns/${campaign!.id}/dashboard`);
  await expect(page).toHaveURL(/\/app\/campaigns\/[^/]+\/dashboard/);
}

test('CANDIDATE usa navegación ejecutiva y conserva flujos permitidos', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await browserLogin(page, e2eUsers.candidate);
  await openExecutiveCampaign(page, request, e2eUsers.candidate);
  await assertExecutiveNavigation(page);

  const navigation = page.getByRole('navigation', { name: 'Navegación principal' });
  await navigation.locator('a[href*="/panorama"]').click();
  await expect(page.getByRole('heading', { name: 'Panorama electoral' })).toBeVisible();
  await expect(page.getByText(/No constituye una predicción electoral/i)).toBeVisible();
  await navigation.locator('a[href*="/territories"]').click();
  await expect(page).not.toHaveURL(/\/403$/);
  await navigation.locator('a[href*="/activities"]').click();
  await expect(page.getByRole('button', { name: /Crear actividad/ })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
      ),
    )
    .toBe(false);
});

test('CAMPAIGN_MANAGER comparte la navegación ejecutiva con CANDIDATE', async ({
  page,
  request,
}) => {
  await browserLogin(page, e2eUsers.manager);
  await openExecutiveCampaign(page, request, e2eUsers.manager);
  await assertExecutiveNavigation(page);
});
