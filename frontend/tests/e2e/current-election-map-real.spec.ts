import { test, expect } from '@playwright/test';
import { apiToken, browserLogin } from './support/auth';

test('elección actual solicita boundaries y monta MapLibre con tamaño visible', async ({
  page,
  request,
}, testInfo) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as Array<{ id: string }>;
  let campaignId = '';
  for (const campaign of campaigns) {
    const analysis = await request.get(
      `/api/v1/campaigns/${campaign.id}/current-election/analysis`,
      { headers },
    );
    if (analysis.status() === 200) {
      campaignId = campaign.id;
      break;
    }
  }
  expect(campaignId, 'Debe existir una campaña con análisis de elección actual').not.toBe('');

  await browserLogin(page);

  const boundaryResponse = page.waitForResponse((response) =>
    response
      .url()
      .includes(`/api/v1/campaigns/${campaignId}/map/boundaries?level=PARISH&limit=5000`),
  );
  await page.goto(`/app/campaigns/${campaignId}/current-election`);
  const response = await boundaryResponse;
  expect(response.status()).toBe(200);
  const geojson = await response.json();
  if (geojson.features.length === 0) {
    await expect(page.getByText('No existen geometrías parroquiales disponibles.')).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath('current-election-map-empty.png'),
      fullPage: true,
    });
    testInfo.annotations.push({ type: 'features', description: '0' });
    return;
  }

  const map = page.getByRole('region', { name: 'Mapa de elección actual' });
  await expect(map).toBeVisible();
  const centralLegend = page.getByLabel('Leyenda — Participación estimada');
  await expect(centralLegend).toBeVisible();
  await expect(centralLegend.getByText('Muy alta', { exact: true })).toBeVisible();
  await expect(centralLegend.getByText('Alta', { exact: true })).toBeVisible();
  await expect(centralLegend.getByText('Media', { exact: true })).toBeVisible();
  await expect(map.locator('canvas.maplibregl-canvas')).toBeVisible();
  const size = await map
    .locator('canvas.maplibregl-canvas')
    .evaluate((canvas: HTMLCanvasElement) => ({
      width: canvas.clientWidth,
      height: canvas.clientHeight,
    }));
  expect(size.width).toBeGreaterThan(0);
  expect(size.height).toBeGreaterThan(0);
  await expect(map).toHaveAttribute('data-metric', 'projected_central_rate');
  await expect(map).toHaveAttribute('data-feature-count', String(geojson.features.length));
  const paint = JSON.parse((await map.getAttribute('data-fill-color-expression')) || 'null');
  expect(paint).toEqual([
    'case',
    ['has', 'projected_central_rate'],
    [
      'step',
      ['to-number', ['get', 'projected_central_rate']],
      '#D6E6F2',
      0.67,
      '#8DB9D3',
      0.69,
      '#4C86A8',
      0.71,
      '#1D5F87',
      0.73,
      '#0B3C5D',
    ],
    '#E5E7EB',
  ]);
  await page.screenshot({
    path: testInfo.outputPath('current-election-central-colors.png'),
    fullPage: true,
  });
  const initialZoom = Number(await map.getAttribute('data-zoom'));
  const initialScroll = await page.evaluate(() => window.scrollY);
  await map.hover();
  await page.mouse.wheel(0, 500);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(initialScroll);
  expect(Number(await map.getAttribute('data-zoom'))).toBe(initialZoom);
  await map.locator('.maplibregl-ctrl-zoom-in').click();
  await expect
    .poll(async () => Number(await map.getAttribute('data-zoom')))
    .toBeGreaterThan(initialZoom);
  await map.locator('.maplibregl-ctrl-zoom-out').click();
  await expect
    .poll(async () => Number(await map.getAttribute('data-zoom')))
    .toBeLessThanOrEqual(initialZoom);

  await page.getByRole('combobox').filter({ hasText: 'Participación estimada' }).click();
  await page.getByRole('option', { name: 'Participación observada 2019' }).click();
  await expect(page.getByLabel('Leyenda — Participación observada 2019')).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath('current-election-participation-2019.png'),
    fullPage: true,
  });
  await page.getByRole('combobox').filter({ hasText: 'Participación observada 2019' }).click();
  await page.getByRole('option', { name: 'Electores actuales' }).click();
  await expect(page.getByLabel('Leyenda — Electores actuales')).toBeVisible();
  await page.getByRole('combobox').filter({ hasText: 'Electores actuales' }).click();
  await page.getByRole('option', { name: 'Población INEC 2022' }).click();
  await expect(page.getByLabel('Leyenda — Población INEC 2022')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('current-election-map.png'), fullPage: true });
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 1024, height: 768 },
    { width: 1366, height: 768 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
  }
  testInfo.annotations.push({ type: 'features', description: String(geojson.features.length) });
});
