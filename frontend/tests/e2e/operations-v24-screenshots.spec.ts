import { test, expect } from '@playwright/test';
import path from 'node:path';
import { apiToken, browserLogin, e2eUsers } from './support/auth';
test('capturas V2.4 solicitadas', async ({ page, request }) => {
  const token = await apiToken(request, e2eUsers.manager);
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = await (
    await request.get('/api/v1/campaigns?page_size=100', { headers })
  ).json();
  const campaign = campaigns.items.find(
    (x: { slug: string }) => x.slug === 'territorio-sintetico-e2e',
  );
  const needs = await (
    await request.get(`/api/v1/campaigns/${campaign.id}/needs?page_size=100`, { headers })
  ).json();
  const need = needs.items[0];
  const output = (name: string) => path.resolve('../quality-artifacts', name);
  await browserLogin(page, e2eUsers.manager);
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const [route, name, heading] of [
    [`operations`, 'operations-dashboard-desktop.png', 'Operación territorial'],
    ['approvals', 'activities-approval-desktop.png', 'Actividades pendientes de aprobación'],
    ['needs', 'needs-list-desktop.png', 'Necesidades'],
    [`needs/${need.id}`, 'need-detail-desktop.png', 'Necesidad territorial'],
    ['operations/map', 'operations-map-desktop.png', 'Mapa operacional'],
  ] as const) {
    await page.goto(`/app/campaigns/${campaign.id}/${route}`);
    await expect(page.getByRole('heading', { name: heading }).first()).toBeVisible();
    await page.screenshot({ path: output(name), fullPage: true });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/app/campaigns/${campaign.id}/operations`);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: output('operations-mobile.png'), fullPage: true });
});
