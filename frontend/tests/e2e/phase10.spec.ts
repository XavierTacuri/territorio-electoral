import { test, expect, type Page } from '@playwright/test';
import { browserLogin } from './support/auth';
async function selectCampaign(page: Page) {
  await page.getByLabel('Campaña').click();
  await page.getByRole('option', { name: 'Gualaceo E2E 2027' }).click();
  await expect(page).toHaveURL(/dashboard/);
  return page.url().match(/campaigns\/([^/]+)/)![1];
}
async function nav(page: Page, name: string) {
  await page.getByRole('link', { name, exact: true }).click();
}

test('27 flujos funcionales de Fase 10 contra el stack real', async ({ page }) => {
  test.setTimeout(180000);
  const suffix = Date.now().toString();
  await test.step('01 Login ADMIN', async () => {
    await browserLogin(page);
    await expect(page.getByText('Usuario E2E')).toBeVisible();
  });
  await test.step('02 Refresh coordinado', async () => {
    const status = await page.evaluate(async () => {
      const csrf =
        document.cookie
          .split('; ')
          .find((x) => x.startsWith('te_csrf='))
          ?.split('=')[1] || '';
      return (
        await fetch('/api/v1/auth/browser/refresh', {
          method: 'POST',
          credentials: 'include',
          headers: { 'X-CSRF-Token': decodeURIComponent(csrf) },
        })
      ).status;
    });
    expect(status).toBe(200);
  });
  const id = await test.step('03 Selección de campaña', () => selectCampaign(page));
  await test.step('04 Dashboard ejecutivo', async () =>
    expect(page.getByRole('heading', { level: 1, name: 'Centro de Comando Territorial' })).toBeVisible());
  await test.step('05 Crear actividad', async () => {
    const title = 'Actividad Playwright ' + suffix;
    await nav(page, 'Actividades');
    await page.getByRole('button', { name: 'Crear actividad' }).click();
    await expect(page.getByLabel('Latitud')).toHaveCount(0);
    await expect(page.getByLabel('Longitud')).toHaveCount(0);
    await expect(page.getByRole('dialog').getByLabel('Estado')).toHaveText('Planificada');
    await expect(page.getByText('PLANNED', { exact: true })).toHaveCount(0);
    await page.getByLabel('Título').fill(title);
    await page.getByLabel('Nombre de ubicación (opcional)').fill('Casa comunal');
    const createRequest = page.waitForRequest(
      (request) => request.method() === 'POST' && /\/activities$/.test(request.url()),
    );
    await page.getByRole('button', { name: 'Guardar' }).click();
    const createPayload = (await createRequest).postDataJSON();
    expect(createPayload.status).toBe('PLANNED');
    expect(createPayload).not.toHaveProperty('latitude');
    expect(createPayload).not.toHaveProperty('longitude');
    await expect(page.getByText(title)).toBeVisible();
  });
  await test.step('06 Editar actividad', async () => {
    const title = 'Actividad editada ' + suffix;
    await page
      .getByRole('button', { name: /Editar actividades/ })
      .first()
      .click();
    await expect(page.getByLabel('Latitud')).toHaveCount(0);
    await expect(page.getByLabel('Longitud')).toHaveCount(0);
    await page.getByLabel('Título').fill(title);
    const editRequest = page.waitForRequest(
      (request) => request.method() === 'PATCH' && /\/activities\/[^/]+$/.test(request.url()),
    );
    await page.getByRole('button', { name: 'Guardar' }).click();
    expect((await editRequest).postDataJSON()).not.toHaveProperty('latitude');
    expect((await editRequest).postDataJSON()).not.toHaveProperty('longitude');
    await expect(page.getByText(title)).toBeVisible();
  });
  await test.step('07 Participantes agregados', async () => {
    await page
      .getByRole('button', { name: /Ver actividades/ })
      .first()
      .click();
    await page.getByRole('button', { name: 'Registrar resumen' }).click();
    await page.getByLabel('Asistentes estimados').fill('31');
    await page.getByRole('button', { name: 'Guardar' }).click();
    await expect(page.getByText(/Asistentes estimados: 31/)).toBeVisible();
  });
  await test.step('08 Crear necesidad', async () => {
    const title = 'Necesidad Playwright ' + suffix;
    await page.getByRole('button', { name: 'Registrar necesidad' }).click();
    await page.getByLabel('Categoría').click();
    await page.getByRole('option').first().click();
    await page.getByLabel('Título').fill(title);
    await page.getByRole('button', { name: 'Guardar' }).click();
    await expect(page.getByText(title)).toBeVisible();
  });
  await test.step('09 Seguimientos retirado de la experiencia productiva', async () => {
    // Seguimientos/Commitments es dominio legacy: la URL directa ya no
    // expone el módulo (cae al 404 coherente) ni es alcanzable por
    // navegación. El endpoint legacy sigue cubierto aparte (operations-v24).
    const refreshed = page.waitForResponse((r) => r.url().endsWith('/auth/browser/refresh'));
    await page.goto(`/app/campaigns/${id}/commitments`);
    await expect(page.getByRole('heading', { name: '404' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Crear seguimiento' })).toHaveCount(0);
    // Espera a que el refresh de sesión de esta navegación se complete antes
    // de navegar de nuevo: el 404 vive fuera de ProtectedRoute, así que si se
    // navega otra vez de inmediato se puede abortar esa rotación de token.
    await refreshed;
  });
  await test.step('11 Crear encuesta', async () => {
    await page.goto(`/app/campaigns/${id}/surveys`);
    await expect(page.getByRole('heading', { name: 'Encuestas y estudios' })).toBeVisible();
    await page.getByRole('button', { name: 'NUEVA ENCUESTA' }).click();
    await expect(page.getByRole('dialog', { name: 'Nueva encuesta general' })).toBeVisible();
  });
  await test.step('12 Completar datos derivados y metodología', async () => {
    const dialog = page.getByRole('dialog', { name: 'Nueva encuesta general' });
    await expect(dialog.getByLabel('Campaña')).toHaveValue('Gualaceo E2E 2027');
    await expect(dialog.getByLabel('Provincia')).not.toHaveValue('');
    await expect(dialog.getByLabel('Cantón')).not.toHaveValue('');
    await dialog.getByLabel('Nombre').fill('Encuesta Playwright ' + suffix);
    await dialog.getByLabel('Fecha inicio trabajo de campo').fill('2026-08-01');
    await dialog.getByLabel('Fecha fin trabajo de campo').fill('2026-08-15');
    await dialog.getByLabel('Tamaño de muestra').fill('100');
    await dialog.getByLabel('Metodología').fill('Muestra sintética agregada E2E');
  });
  await test.step('13 Registrar resultados agregados', async () => {
    const dialog = page.getByRole('dialog', { name: 'Nueva encuesta general' });
    await dialog.getByLabel('Texto de la pregunta').fill('Seleccione una opción sintética');
    await dialog.getByRole('textbox', { name: 'Opción', exact: true }).nth(0).fill('Opción A');
    await dialog.getByLabel('Porcentaje').nth(0).fill('55');
    await dialog.getByLabel('Base N').nth(0).fill('55');
    await dialog.getByRole('textbox', { name: 'Opción', exact: true }).nth(1).fill('Opción B');
    await dialog.getByLabel('Porcentaje').nth(1).fill('45');
    await dialog.getByLabel('Base N').nth(1).fill('45');
    await dialog.getByRole('button', { name: 'Crear encuesta' }).click();
    await expect(page.getByRole('heading', { name: 'Encuesta Playwright ' + suffix })).toBeVisible();
    await expect(page.getByText('Opción A')).toBeVisible();
  });
  await test.step('14 Publicar encuesta', async () => {
    const publishResponse = page.waitForResponse(
      (response) => response.url().endsWith('/publish') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'PUBLICAR' }).click();
    expect((await publishResponse).status()).toBe(200);
    await expect(page.getByRole('button', { name: 'ARCHIVAR' })).toBeVisible();
  });
  await test.step('15 Detalle de encuesta general', async () => {
    await expect(page.getByText('Encuesta general')).toBeVisible();
    await expect(page.getByText('Cobertura cantonal')).toBeVisible();
    await expect(page.getByText('55,00 %')).toBeVisible();
  });
  await test.step('16 Resultados agregados', async () => {
    await page.goto(`/app/campaigns/${id}/surveys`);
    await expect(page.getByRole('heading', { name: 'Encuestas y estudios' })).toBeVisible();
    await expect(page.getByText('Encuesta Playwright ' + suffix)).toBeVisible();
  });
  await test.step('17 Validar CSV', async () => {
    await page.goto('/app/admin/data-imports');
    await expect(page.getByRole('button', { name: '1. Validar' })).toBeVisible();
  });
  await test.step('18 Ejecución CSV explícita', async () =>
    expect(page.getByRole('button', { name: '2. Ejecutar' })).toBeDisabled());
  await test.step('19 Electoral', async () => {
    await page.goto(`/app/campaigns/${id}/dashboard`);
    await nav(page, 'Datos electorales');
    await expect(page.getByRole('heading', { name: 'Datos electorales' })).toBeVisible();
  });
  await test.step('20 Demografía', async () => {
    await nav(page, 'Demografía');
    await expect(page.getByRole('heading', { name: 'Demografía' })).toBeVisible();
  });
  await test.step('21 Mapa', async () => {
    await nav(page, 'Mapas');
    await expect(page.getByRole('heading', { name: 'Mapas territoriales' })).toBeVisible();
  });
  await test.step('22 PDF', async () => {
    await nav(page, 'Centro de Informes');
    await expect(page.getByRole('heading', { name: 'Centro de Informes' })).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Formato de exportación' })).toHaveText(/PDF/);
  });
  await test.step('23 XLSX', async () => {
    const format = page.getByRole('combobox', { name: 'Formato de exportación' });
    await format.click();
    await page.getByRole('option', { name: 'Excel (XLSX)' }).click();
    await expect(format).toHaveText(/XLSX/);
  });
  await test.step('24 Alertas', async () => {
    await nav(page, 'Centro de alertas');
    await page.getByRole('button', { name: 'Evaluar reglas' }).click();
    await expect(page.getByRole('heading', { name: 'Alertas' })).toBeVisible();
  });
  await test.step('25 Permisos candidato', async () => {
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await browserLogin(page, 'candidate_e2e');
    await expect(page.getByText('Administración')).toHaveCount(0);
  });
  await test.step('26 Restricción coordinador', async () => {
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await browserLogin(page, 'coordinator_e2e');
    await page.goto(`/app/campaigns/${id}/dashboard`);
    await nav(page, 'Actividades');
    await expect(page.getByRole('heading', { name: 'Actividades' })).toBeVisible();
  });
  await test.step('27 Logout', async () => {
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});
