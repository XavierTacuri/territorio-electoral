import { expect, test, type Page } from '@playwright/test';
import { browserLogin } from '../e2e/support/auth';

const unexpectedConsole: string[] = [];
const unexpectedResponses: string[] = [];
const observedEndpoints = new Set<string>();
const watch = (page: Page) => {
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().includes('401'))
      unexpectedConsole.push(message.text());
  });
  page.on('pageerror', (error) => unexpectedConsole.push(error.message));
  page.on('response', (response) => {
    const url = response.url();
    for (const key of [
      '/public-intelligence/summary',
      '/public-intelligence/items',
      '/public-sources',
      '/public-intelligence/map',
      '/map/boundaries',
      '/current-election/analysis',
      '/territories/summary',
      '/survey-studies',
      '/needs',
    ])
      if (url.includes(key)) observedEndpoints.add(key);
    if (response.status() >= 400 && !url.includes('/auth/browser/session'))
      unexpectedResponses.push(`${response.status()} ${url}`);
  });
};
const noOverflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);

test('recorrido real Gualaceo V2.5, consola, red y responsive', async ({ page }) => {
  watch(page);
  await browserLogin(page, process.env.E2E_USER_NAME);
  await page.getByLabel('Campaña').click();
  await page.getByRole('option', { name: 'Gualaceo2026' }).click();
  await page.getByRole('link', { name: 'Inteligencia pública', exact: true }).click();
  await expect(page).toHaveURL(/\/app\/campaigns\/.+\/public-intelligence$/);
  await expect(page.getByRole('heading', { name: 'INTELIGENCIA PÚBLICA' })).toBeVisible();
  for (const value of [
    'Fuentes activas',
    'Últimas 24 h',
    'Últimos 7 días',
    'Fuentes oficiales',
    'Documentos nuevos',
    'Fuentes con error',
  ])
    await expect(page.getByText(value, { exact: true })).toBeVisible();
  await expect(page.getByText('No hay publicaciones públicas registradas.')).toBeVisible();
  await page.screenshot({
    path: '../quality-artifacts/public-intelligence-real-dashboard.png',
    fullPage: true,
  });

  await page.getByRole('tab', { name: 'Feed' }).click();
  await expect(page.getByText(/No hay información pública/)).toBeVisible();
  await page.getByLabel('Buscar').fill('consulta vacía');
  await expect(page.getByText(/No hay información pública/)).toBeVisible();
  await page.getByLabel('Buscar').fill('');

  await page.getByRole('tab', { name: 'Fuentes públicas' }).click();
  await expect(page.getByText(/No hay fuentes públicas configuradas/)).toBeVisible();
  await page.getByRole('button', { name: 'Nueva fuente' }).click();
  const dialog = page.getByRole('dialog');
  for (const label of [
    'Código',
    'Nombre',
    'Publisher',
    'URL base',
    'RSS URL (opcional)',
    'Intervalo actualización (min)',
    'Tipo',
  ])
    await expect(dialog.getByLabel(label)).toBeVisible();
  await dialog.getByRole('button', { name: 'Cancelar' }).click();

  await page.getByRole('tab', { name: 'Mapa' }).click();
  const map = page.getByRole('region', { name: 'Mapa de información pública' });
  await expect(map.locator('canvas.maplibregl-canvas')).toBeVisible();
  await expect(map).toHaveAttribute('data-feature-count', '9');
  await expect(map).toHaveAttribute('data-scroll-zoom', 'false');
  for (const period of ['Últimos 7 días', 'Últimos 30 días', 'Total']) {
    await page.getByRole('combobox', { name: /Periodo \/ Métrica/ }).click();
    await page.getByRole('option', { name: period }).click();
    await expect(page.getByText('0 publicaciones')).toBeVisible();
  }
  await page.getByRole('combobox', { name: /Tema/ }).click();
  await page.getByRole('option', { name: 'Todos' }).click();
  const canvas = map.locator('canvas.maplibregl-canvas');
  const canvasBox = await canvas.boundingBox();
  expect(canvasBox).toBeTruthy();
  if (canvasBox)
    for (const y of [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]) {
      for (const x of [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]) {
        await canvas.click({ position: { x: canvasBox.width * x, y: canvasBox.height * y } });
        if (await page.getByRole('button', { name: 'Ver publicaciones' }).count()) break;
      }
      if (await page.getByRole('button', { name: 'Ver publicaciones' }).count()) break;
    }
  expect(unexpectedConsole, 'Console durante interacción MapLibre').toEqual([]);
  await expect(page.getByRole('button', { name: 'Ver publicaciones' })).toBeVisible();
  const tooltip = page.locator('.maplibregl-popup');
  await expect(tooltip).toContainText('Publicaciones: 0');
  await expect(tooltip).toContainText('Periodo:');
  await expect(tooltip).toContainText('Tema:');
  await page.getByRole('button', { name: 'Ver publicaciones' }).click();
  await expect(page.getByRole('tab', { name: 'Feed', selected: true })).toBeVisible();
  await expect(page.getByText(/No hay información pública/)).toBeVisible();
  await page.getByRole('tab', { name: 'Mapa' }).click();
  await page.screenshot({
    path: '../quality-artifacts/public-intelligence-real-map.png',
    fullPage: true,
  });

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    for (const tab of ['Resumen', 'Feed', 'Fuentes públicas', 'Mapa']) {
      await page.getByRole('tab', { name: tab }).click();
      expect(await noOverflow(page), `${viewport.width}x${viewport.height} ${tab}`).toBe(true);
    }
    if (viewport.width === 390)
      await page.screenshot({
        path: '../quality-artifacts/public-intelligence-real-mobile.png',
        fullPage: true,
      });
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'INTELIGENCIA PÚBLICA' })).toBeVisible();
  await expect(page.getByText('34.784', { exact: true })).toBeVisible();

  await page.getByRole('link', { name: 'Inteligencia territorial', exact: true }).click();
  await page.getByLabel('Seleccionar parroquia').click();
  await page.getByRole('option', { name: /Jadán/ }).click();
  await expect(page.getByRole('heading', { name: 'INFORMACIÓN PÚBLICA RECIENTE' })).toBeVisible();
  for (const heading of [
    'PARTICIPACIÓN HISTÓRICA',
    'PROYECCIÓN DE PARTICIPACIÓN',
    'CONTEXTO TERRITORIAL',
    'ENCUESTAS Y ESTUDIOS',
  ])
    await expect(page.getByRole('heading', { name: heading })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Mapa de elección actual' })).toBeVisible();

  await page.getByRole('link', { name: 'Necesidades', exact: true }).click();
  const rows = page.getByRole('row').filter({ has: page.getByRole('button', { name: 'Ver' }) });
  if (await rows.count()) {
    await rows.first().getByRole('button', { name: 'Ver' }).click();
    await expect(
      page.getByRole('heading', { name: 'FUENTES PÚBLICAS RELACIONADAS' }),
    ).toBeVisible();
  }

  expect(unexpectedConsole, 'Console funcional').toEqual([]);
  expect(unexpectedResponses, 'Network 4xx/5xx').toEqual([]);
  for (const endpoint of [
    '/public-intelligence/summary',
    '/public-intelligence/items',
    '/public-sources',
    '/public-intelligence/map',
    '/map/boundaries',
    '/current-election/analysis',
    '/territories/summary',
  ])
    expect(observedEndpoints.has(endpoint), endpoint).toBe(true);
});
