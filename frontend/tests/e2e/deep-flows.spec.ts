import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';
import { apiToken, browserLogin } from './support/auth';
async function campaign(page: Page) {
  await page.getByLabel('Campaña').click();
  await page.getByRole('option', { name: 'Gualaceo E2E 2027' }).click();
  return page.url().match(/campaigns\/([^/]+)/)![1];
}
test('encuesta anónima real, importaciones, descargas y alertas', async ({ page, request }) => {
  test.setTimeout(240000);
  const suffix = Date.now().toString();
  await browserLogin(page);
  const campaignId = await campaign(page);
  await test.step('encuesta completa y supresión', async () => {
    await page.getByRole('link', { name: 'Encuestas', exact: true }).click();
    await page.getByRole('button', { name: 'Crear encuesta' }).click();
    let dialog = page.getByRole('dialog');
    await dialog.getByLabel('Título').fill('Encuesta profunda ' + suffix);
    await dialog.getByLabel('Slug').fill('encuesta-profunda-' + suffix);
    await dialog.getByRole('button', { name: 'Crear y diseñar' }).click();
    await expect(page.getByRole('heading', { name: /Constructor/ })).toBeVisible();
    const surveyId = page.url().match(/surveys\/([^/]+)/)![1];
    await page.getByRole('button', { name: 'Crear sección' }).click();
    await page.getByLabel('Título').fill('Sección inicial');
    await page.getByRole('button', { name: 'Crear' }).click();
    page.once('dialog', (d) => d.accept('Sección editada'));
    await page.getByRole('button', { name: 'Editar sección', exact: true }).click();
    await expect(page.getByText('Sección editada')).toBeVisible();
    await page.getByRole('button', { name: 'Crear pregunta' }).click();
    dialog = page.getByRole('dialog');
    await dialog.getByRole('combobox', { name: 'Sección' }).click();
    await page.getByRole('option').first().click();
    await dialog.getByLabel('Código').fill('OPCION_UNICA');
    await dialog.getByLabel('Pregunta').fill('Pregunta inicial');
    await dialog.getByLabel('Obligatoria').check();
    await dialog.getByRole('button', { name: 'Crear' }).click();
    page.once('dialog', (d) => d.accept('Pregunta editada'));
    await page.getByRole('button', { name: 'Editar pregunta', exact: true }).click();
    await expect(page.getByText(/Pregunta editada/)).toBeVisible();
    for (const [code, label] of [
      ['A', 'Alternativa A'],
      ['B', 'Alternativa B'],
    ]) {
      await page.getByRole('button', { name: 'Crear opción' }).click();
      dialog = page.getByRole('dialog');
      await dialog.getByRole('combobox', { name: 'Pregunta' }).click();
      await page.getByRole('option').first().click();
      await dialog.getByLabel('Código').fill(code);
      await dialog.getByLabel('Etiqueta').fill(label);
      await dialog.getByRole('button', { name: 'Crear' }).click();
    }
    page.once('dialog', (d) => d.accept('Alternativa editada'));
    await page.getByRole('button', { name: 'Editar opción', exact: true }).first().click();
    await page
      .getByLabel(/Bajar opción/)
      .first()
      .click();
    await page.getByRole('button', { name: 'Publicar' }).click();
    await expect(page.getByText('PUBLISHED')).toBeVisible();
    await page.getByRole('button', { name: 'Vista previa' }).click();
    await page.getByLabel('Parroquia').click();
    await page.getByRole('option').first().click();
    await page.getByLabel('Alternativa editada').check();
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/responses') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: /Enviar respuesta/ }).click();
    expect((await responsePromise).status()).toBe(201);
    await expect(page.getByText(/registrada correctamente/)).toBeVisible();
    for (const personal of ['Nombre', 'Cédula', 'Teléfono', 'Correo'])
      await expect(page.getByRole('textbox', { name: personal, exact: true })).toHaveCount(0);
    await page.goto(`/app/campaigns/${campaignId}/surveys/${surveyId}/results`);
    await expect(page.getByText('1').first()).toBeVisible();
    await expect(page.getByText(/Alternativa editada: 1/)).toBeVisible();
    await expect(page.getByText(/privacidad|suprimid/i)).toBeVisible();
    await page.getByRole('link', { name: 'Volver al constructor' }).click();
    let transitionResponse = page.waitForResponse(
      (r) => r.url().endsWith('/close') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Cerrar', exact: true }).click();
    expect((await transitionResponse).status()).toBe(200);
    await expect(page.getByText('CLOSED')).toBeVisible();
    transitionResponse = page.waitForResponse(
      (r) => r.url().endsWith('/archive') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Archivar', exact: true }).click();
    expect((await transitionResponse).status()).toBe(200);
    await expect(page.getByText('ARCHIVED')).toBeVisible();
  });
  await test.step('CSV validado, importado y conflicto', async () => {
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
      .setInputFiles(path.join(import.meta.dirname, 'fixtures', 'electoral-process.csv'));
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
    await expect(
      page.getByRole('option', { name: /Proceso sintético importado 2024/ }),
    ).toBeVisible();
    await page.keyboard.press('Escape');
  });
  await test.step('GeoJSON real conserva el territorio y publica su feature', async () => {
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
    await page
      .locator('input[type=file]')
      .setInputFiles(path.join(import.meta.dirname, 'fixtures', 'parish.geojson'));
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
    await page.getByRole('link', { name: 'Informes', exact: true }).click();
    for (const format of ['PDF', 'XLSX']) {
      await page.getByRole('button', { name: 'Generar informe' }).click();
      const dialog = page.getByRole('dialog');
      await dialog.getByLabel('Plantilla').click();
      await page
        .getByRole('option', { name: /Resumen ejecutivo/ })
        .first()
        .click();
      await dialog.getByLabel('Formato').click();
      await page.getByRole('option', { name: format }).click();
      await dialog.getByLabel('Título').fill('Descarga ' + format + ' ' + suffix);
      await dialog.getByRole('button', { name: 'Generar' }).click();
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
    await page.getByRole('link', { name: 'Alertas', exact: true }).click();
    let response = page.waitForResponse((r) => r.url().endsWith('/evaluate'));
    const refreshedAlerts = page.waitForResponse(
      (r) => r.url().includes('/alerts?page=') && r.request().method() === 'GET',
    );
    await page.getByRole('button', { name: 'Evaluar reglas' }).click();
    expect((await response).status()).toBe(200);
    expect((await refreshedAlerts).status()).toBe(200);
    const openAlerts = page.waitForResponse((r) => r.url().includes('status=OPEN'));
    await page.getByRole('combobox', { name: /Estado/ }).click();
    await page.getByRole('option', { name: 'OPEN' }).click();
    expect((await openAlerts).status()).toBe(200);
    const count = await page.getByRole('row').count();
    const openRow = page
      .getByRole('row')
      .filter({ has: page.getByRole('cell', { name: 'OPEN', exact: true }) })
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
    await page.getByRole('option', { name: 'ACKNOWLEDGED' }).click();
    await expect(page.getByText('ACKNOWLEDGED').first()).toBeVisible();
    await page
      .getByRole('row')
      .filter({ hasText: alertTitle })
      .getByRole('button', { name: 'Gestionar' })
      .click();
    dialog = page.getByRole('dialog');
    await dialog.getByLabel('Acción').click();
    await page.getByRole('option', { name: 'Resolver' }).click();
    response = page.waitForResponse((r) => r.url().endsWith('/resolve'));
    await dialog.getByRole('button', { name: 'Confirmar' }).click();
    expect((await response).status()).toBe(200);
    await page.getByRole('combobox', { name: /Estado/ }).click();
    await page.getByRole('option', { name: 'RESOLVED' }).click();
    await expect(page.getByText('RESOLVED').first()).toBeVisible();
    await page.getByRole('combobox', { name: /Estado/ }).click();
    await page.getByRole('option', { name: 'OPEN' }).click();
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
