import { test, expect, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { apiToken, browserLogin } from './support/auth';
import { e2eRunId, uniqueE2eValue } from './support/run-data';
async function campaign(page: Page) {
  await page.getByLabel('Campaña').click();
  await page.getByRole('option', { name: 'Gualaceo E2E 2027' }).click();
  return page.url().match(/campaigns\/([^/]+)/)![1];
}
test('encuesta anónima real, importaciones, descargas y alertas', async ({ page, request }) => {
  test.setTimeout(240000);
  const suffix = e2eRunId;
  await browserLogin(page);
  const campaignId = await campaign(page);
  await test.step('encuesta general agregada y publicación', async () => {
    await page.getByRole('link', { name: 'Encuestas y estudios', exact: true }).click();
    await page.getByRole('button', { name: 'NUEVA ENCUESTA' }).click();
    const dialog = page.getByRole('dialog', { name: 'Nueva encuesta general' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel('Campaña')).toHaveValue('Gualaceo E2E 2027');
    await expect(dialog.getByLabel('Provincia')).not.toHaveValue('');
    await expect(dialog.getByLabel('Cantón')).not.toHaveValue('');
    const surveyName = 'Encuesta profunda ' + suffix;
    await dialog.getByLabel('Nombre').fill(surveyName);
    await dialog.getByLabel('Fecha inicio trabajo de campo').fill('2026-08-01');
    await dialog.getByLabel('Fecha fin trabajo de campo').fill('2026-08-15');
    await dialog.getByLabel('Tamaño de muestra').fill('100');
    await dialog.getByLabel('Metodología').fill('Muestra sintética agregada E2E');
    await dialog.getByLabel('Texto de la pregunta').fill('Preferencia agregada');
    await dialog.getByRole('textbox', { name: 'Opción', exact: true }).nth(0).fill('Alternativa A');
    await dialog.getByLabel('Porcentaje').nth(0).fill('60');
    await dialog.getByLabel('Base N').nth(0).fill('60');
    await dialog.getByRole('textbox', { name: 'Opción', exact: true }).nth(1).fill('Alternativa B');
    await dialog.getByLabel('Porcentaje').nth(1).fill('40');
    await dialog.getByLabel('Base N').nth(1).fill('40');
    await dialog.getByRole('button', { name: 'Crear encuesta' }).click();
    await expect(page.getByRole('heading', { name: surveyName })).toBeVisible();
    await expect(page.getByText('Cobertura cantonal')).toBeVisible();
    await expect(page.getByText('Alternativa A')).toBeVisible();
    await expect(page.getByText('60,00 %')).toBeVisible();
    const publishResponse = page.waitForResponse(
      (r) => r.url().endsWith('/publish') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'PUBLICAR' }).click();
    expect((await publishResponse).status()).toBe(200);
    await expect(page.getByRole('button', { name: 'ARCHIVAR' })).toBeVisible();
  });
  await test.step('CSV validado, importado y conflicto', async () => {
    const processCode = uniqueE2eValue('E2E_IMPORTED_2024').toUpperCase();
    const processName = uniqueE2eValue('Proceso sintético importado 2024');
    const csv = (
      await readFile(path.join(import.meta.dirname, 'fixtures', 'electoral-process.csv'), 'utf8')
    )
      .replace('E2E_IMPORTED_2024', processCode)
      .replace('Proceso sintético importado 2024', processName);
    await page.goto('/app/admin/data-imports');
    await page.getByLabel('Fuente oficial').click();
    await page.getByRole('option').first().click();
    await page.getByLabel('Tipo de conjunto').click();
    await page.getByRole('option', { name: 'CNE_TURNOUT' }).click();
    await page
      .getByRole('textbox', { name: 'Perfil explícito (opcional)' })
      .fill('CANONICAL_ELECTORAL_PROCESS');
    await page
      .locator('input[type=file]')
      .setInputFiles({
        name: 'electoral-process.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(csv),
      });
    let response = page.waitForResponse((r) => r.url().endsWith('/data-imports/validate'));
    await page.getByRole('button', { name: '1. Validar' }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByText(/Resultado: VALIDATED/)).toBeVisible();
    response = page.waitForResponse((r) => r.url().endsWith('/data-imports/execute'));
    await page.getByRole('button', { name: '2. Ejecutar' }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByText(/Resultado: COMPLETED/)).toBeVisible();
    response = page.waitForResponse((r) => r.url().endsWith('/data-imports/execute'));
    await page.getByRole('button', { name: '2. Ejecutar' }).click();
    expect((await response).status()).toBe(409);
    await page.getByLabel(/Forzar actualización/).check();
    response = page.waitForResponse((r) => r.url().endsWith('/data-imports/execute'));
    await page.getByRole('button', { name: '2. Ejecutar' }).click();
    expect((await response).status()).toBe(200);
    await page.goto(`/app/campaigns/${campaignId}/dashboard`);
    await page.getByRole('link', { name: 'Datos electorales', exact: true }).click();
    await page.getByLabel('Proceso').click();
    await expect(page.getByRole('option', { name: processName })).toBeVisible();
    await page.keyboard.press('Escape');
  });
  await test.step('GeoJSON real conserva el territorio y publica su feature', async () => {
    const geojson = JSON.parse(
      await readFile(path.join(import.meta.dirname, 'fixtures', 'parish.geojson'), 'utf8'),
    );
    geojson.e2e_run_id = e2eRunId;
    const token = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + token };
    const parishesBefore = await (await request.get('/api/v1/parishes', { headers })).json();
    const targetBefore = parishesBefore.find(
      (item: { dpa_code: string }) => item.dpa_code === '010350',
    );
    expect(targetBefore).toBeTruthy();
    const detailBeforeResponse = await request.get(
      '/api/v1/campaigns/' + campaignId + '/map/features/PARISH/' + targetBefore.id,
      { headers },
    );
    const initialGeometry =
      detailBeforeResponse.status() === 200 ? (await detailBeforeResponse.json()).geometry : null;

    await page.goto('/app/admin/geometry-imports');
    await page.getByLabel('Fuente oficial').click();
    await page.getByRole('option').nth(1).click();
    await expect(page.getByText(/Nivel territorial:/)).toContainText('PARISH');
    await expect(page.getByText(/Propiedad de unión:/)).toContainText('dpa_code');
    await page.locator('input[type=file]').setInputFiles({
      name: 'parish.geojson',
      mimeType: 'application/geo+json',
      buffer: Buffer.from(JSON.stringify(geojson)),
    });
    let response = page.waitForResponse((item) =>
      item.url().endsWith('/geometry-imports/validate'),
    );
    await page.getByRole('button', { name: 'VALIDAR', exact: true }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByRole('heading', { name: /Resultado.*VALIDATED/ })).toBeVisible();
    response = page.waitForResponse((item) => item.url().endsWith('/geometry-imports/execute'));
    await page.getByRole('button', { name: 'EJECUTAR', exact: true }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByRole('heading', { name: /Resultado.*COMPLETED/ })).toBeVisible();

    const parishesAfter = await (await request.get('/api/v1/parishes', { headers })).json();
    expect(parishesAfter).toHaveLength(parishesBefore.length);
    const targetAfter = parishesAfter.find(
      (item: { dpa_code: string }) => item.dpa_code === '010350',
    );
    expect(targetAfter.id).toBe(targetBefore.id);
    const detail = await (
      await request.get(
        '/api/v1/campaigns/' + campaignId + '/map/features/PARISH/' + targetAfter.id,
        { headers },
      )
    ).json();
    expect(detail.geometry.type).toBe('MultiPolygon');
    expect(detail.geometry.coordinates.length).toBeGreaterThan(0);
    if (!initialGeometry) expect(detail.geometry).toBeTruthy();

    const boundaries = await (
      await request.get(
        '/api/v1/campaigns/' +
          campaignId +
          '/map/boundaries?level=PARISH&limit=5000&simplify=false',
        { headers },
      )
    ).json();
    const importedFeatures = boundaries.features.filter(
      (feature: { properties: { resource_id: string } }) =>
        feature.properties.resource_id === String(targetAfter.id),
    );
    expect(importedFeatures).toHaveLength(1);
    expect(importedFeatures[0].geometry.type).toBe('MultiPolygon');

    await expect(page.getByRole('button', { name: 'EJECUTAR', exact: true })).toBeDisabled();

    const layerResponse = page.waitForResponse((item) =>
      item.url().includes('/map/boundaries?level=PARISH'),
    );
    await page.goto('/app/campaigns/' + campaignId + '/maps');
    const loaded = await layerResponse;
    expect(loaded.status()).toBe(200);
    const source = await loaded.json();
    expect(
      source.features.filter(
        (feature: { properties: { resource_id: string } }) =>
          feature.properties.resource_id === String(targetAfter.id),
      ),
    ).toHaveLength(1);
    await expect(page.getByRole('region', { name: 'Mapa territorial' })).toBeVisible();
    await expect(page.getByText('Parroquias', { exact: true }).first()).toBeVisible();
  });
  await test.step('PDF y XLSX descargables y protegidos', async () => {
    await page.goto(`/app/campaigns/${campaignId}/dashboard`);
    await page.getByRole('link', { name: 'Centro de Informes', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Centro de Informes' })).toBeVisible();
    for (const format of ['PDF', 'XLSX']) {
      await page.getByLabel('Título del informe').fill('Descarga ' + format + ' ' + suffix);
      await page.getByLabel('Formato de exportación').click();
      await page
        .getByRole('option', { name: format === 'PDF' ? 'PDF' : 'Excel (XLSX)' })
        .click();
      const generateResponse = page.waitForResponse(
        (r) => r.url().endsWith('/reports/generate') && r.request().method() === 'POST',
      );
      await page.getByRole('button', { name: `Exportar ${format}` }).click();
      expect((await generateResponse).status()).toBe(201);
      await expect(page.getByText('Descarga ' + format + ' ' + suffix)).toBeVisible();
      const row = page.getByRole('row').filter({ hasText: 'Descarga ' + format + ' ' + suffix });
      const responsePromise = page.waitForResponse((r) => r.url().includes('/download'));
      const downloadPromise = page.waitForEvent('download');
      await row.getByRole('button', { name: 'Descargar' }).click();
      const [response, download] = await Promise.all([responsePromise, downloadPromise]);
      expect(response.headers()['content-disposition']).toContain('attachment');
      expect(download.suggestedFilename().toLowerCase()).toMatch(
        format === 'PDF' ? /\.pdf$/ : /\.xlsx$/,
      );
      const stream = await download.createReadStream();
      const chunks: Buffer[] = [];
      for await (const chunk of stream) chunks.push(Buffer.from(chunk));
      const bytes = Buffer.concat(chunks);
      expect(bytes.length).toBeGreaterThan(10);
      expect(bytes.subarray(0, format === 'PDF' ? 4 : 2).toString()).toBe(
        format === 'PDF' ? '%PDF' : 'PK',
      );
      expect(await row.getByText(/storage_key/i).count()).toBe(0);
      const unauth = await request.get(response.url());
      expect(unauth.status()).toBe(401);
    }
  });
  await test.step('alerta reconocida, resuelta y deduplicada', async () => {
    await page.getByRole('link', { name: 'Centro de alertas', exact: true }).click();
    let response = page.waitForResponse((r) => r.url().endsWith('/evaluate'));
    const refreshedAlerts = page.waitForResponse(
      (r) => r.url().includes('/alerts?page=') && r.request().method() === 'GET',
    );
    await page.getByRole('button', { name: 'Evaluar reglas' }).click();
    expect((await response).status()).toBe(200);
    expect((await refreshedAlerts).status()).toBe(200);
    const openAlerts = page.waitForResponse((r) => r.url().includes('status=OPEN'));
    await page.getByRole('combobox', { name: /Estado/ }).click();
    await page.getByRole('option', { name: 'Pendiente' }).click();
    expect((await openAlerts).status()).toBe(200);
    const count = await page.getByRole('row').count();
    const openRow = page
      .getByRole('row')
      .filter({ has: page.getByRole('cell', { name: 'Pendiente', exact: true }) })
      .first();
    const alertTitle = (await openRow.getByRole('cell').first().textContent())!;
    await openRow.getByRole('button', { name: 'Gestionar' }).click();
    let dialog = page.getByRole('dialog');
    await dialog.getByLabel('Acción').click();
    await page.getByRole('option', { name: 'Reconocer' }).click();
    await dialog.getByLabel('Nota').fill('Revisión operativa E2E');
    response = page.waitForResponse((r) => r.url().endsWith('/acknowledge'));
    await dialog.getByRole('button', { name: 'Confirmar' }).click();
    expect((await response).status()).toBe(200);
    await page.getByRole('combobox', { name: /Estado/ }).click();
    await page.getByRole('option', { name: 'Revisada' }).click();
    await expect(page.getByText('Revisada').first()).toBeVisible();
    await page
      .getByRole('row')
      .filter({ hasText: alertTitle })
      .getByRole('button', { name: 'Gestionar' })
      .first()
      .click();
    dialog = page.getByRole('dialog');
    await dialog.getByLabel('Acción').click();
    await page.getByRole('option', { name: 'Resolver' }).click();
    response = page.waitForResponse((r) => r.url().endsWith('/resolve'));
    await dialog.getByRole('button', { name: 'Confirmar' }).click();
    expect((await response).status()).toBe(200);
    await page.getByRole('combobox', { name: /Estado/ }).click();
    await page.getByRole('option', { name: 'Resuelta' }).click();
    await expect(page.getByText('Resuelta').first()).toBeVisible();
    await page.getByRole('combobox', { name: /Estado/ }).click();
    await page.getByRole('option', { name: 'Pendiente' }).click();
    const reevaluation = page.waitForResponse((r) => r.url().endsWith('/evaluate'));
    const deduplicatedList = page.waitForResponse(
      (r) => r.url().includes('status=OPEN') && r.request().method() === 'GET',
    );
    await page.getByRole('button', { name: 'Evaluar reglas' }).click();
    expect((await reevaluation).status()).toBe(200);
    expect((await deduplicatedList).status()).toBe(200);
    await expect.poll(() => page.getByRole('row').count()).toBe(count);
  });
});
