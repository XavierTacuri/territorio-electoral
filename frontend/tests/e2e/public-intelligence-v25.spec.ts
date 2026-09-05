import { expect, test } from '@playwright/test';
import { browserLogin } from './support/auth';

test('inteligencia pública trazable sin Internet', async ({ page }) => {
  test.setTimeout(120000);
  await browserLogin(page);
  await page.getByLabel('Campaña').click();
  await page.getByRole('option', { name: 'Gualaceo E2E 2027' }).click();
  await page.getByRole('link', { name: 'Fuentes públicas', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'INTELIGENCIA PÚBLICA' })).toBeVisible();
  await page.screenshot({
    path: '../quality-artifacts/public-intelligence-dashboard.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Nueva fuente' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Código').fill(`RSS_SYNTH_${Date.now()}`);
  await dialog.getByLabel('Nombre').fill('Fuente Oficial Sintética');
  await dialog.getByLabel('Publicador').fill('Municipio Sintético');
  await dialog.getByLabel('URL base').fill('http://public-fixture:8080');
  await dialog.getByLabel('Método de recuperación').click();
  await page.getByRole('option', { name: 'RSS' }).click();
  await dialog.getByLabel('RSS URL').fill('http://public-fixture:8080/feed.xml');
  await dialog.getByRole('button', { name: 'Guardar' }).click();
  await page.getByRole('tab', { name: 'Fuentes públicas' }).click();
  await expect(page.getByText('Fuente Oficial Sintética').last()).toBeVisible();
  await page.screenshot({
    path: '../quality-artifacts/public-intelligence-sources.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Actualizar ahora' }).last().click();
  await page.getByRole('tab', { name: 'Feed' }).click();
  await page.getByLabel('Buscar').fill('vialidad');
  await expect(page.getByText('Boletín de mantenimiento vial').first()).toBeVisible();
  await page.screenshot({
    path: '../quality-artifacts/public-intelligence-feed.png',
    fullPage: true,
  });
  await expect(page.getByText('script', { exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'Ver detalle' }).first().click();
  await expect(page.getByRole('heading', { name: 'INTELIGENCIA PÚBLICA — DETALLE' })).toBeVisible();
  await expect(page.getByText(/^Fuente:/)).toBeVisible();
  await expect(page.getByText(/^Publicador:/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Abrir fuente' })).toHaveAttribute(
    'rel',
    'noopener noreferrer',
  );
  await page.screenshot({
    path: '../quality-artifacts/public-intelligence-detail.png',
    fullPage: true,
  });
  await page.getByRole('link', { name: 'Fuentes públicas', exact: true }).click();
  await page.getByLabel('Campaña').click();
  await page.getByRole('option', { name: 'Territorio Sintético E2E' }).click();
  await page.getByRole('link', { name: 'Fuentes públicas', exact: true }).click();
  await page.getByRole('tab', { name: 'Mapa' }).click();
  const map = page.getByRole('region', { name: 'Mapa de información pública' });
  await expect(map.locator('canvas.maplibregl-canvas')).toBeVisible();
  await expect.poll(() => map.getAttribute('data-scroll-zoom')).toBe('false');
  await page.screenshot({
    path: '../quality-artifacts/public-intelligence-map.png',
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('tab', { name: 'Resumen' }).click();
  await page.screenshot({
    path: '../quality-artifacts/public-intelligence-mobile.png',
    fullPage: true,
  });
});
