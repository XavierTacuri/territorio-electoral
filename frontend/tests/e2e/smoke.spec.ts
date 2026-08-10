import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
test('login, layout responsive y accesibilidad básica', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: 'Territorio Electoral' })).toBeVisible();
  await expect(page.getByLabel('Correo o nombre de usuario')).toBeVisible();
  const results = await new AxeBuilder({ page: page as never }).analyze();
  expect(results.violations).toEqual([]);
});
test('móvil no tiene desbordamiento global', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/login');
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflow).toBe(false);
});
