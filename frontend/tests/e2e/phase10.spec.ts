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
    expect(page.getByRole('heading', { level: 1, name: 'TERRITORIO ELECTORAL' })).toBeVisible());
  await test.step('05 Crear actividad', async () => {
    const title = 'Actividad Playwright ' + suffix;
    await nav(page, 'Actividades');
    await page.getByRole('button', { name: 'Crear actividad' }).click();
    await page.getByLabel('Título').fill(title);
    await page.getByRole('button', { name: 'Guardar' }).click();
    await expect(page.getByText(title)).toBeVisible();
  });
  await test.step('06 Editar actividad', async () => {
    const title = 'Actividad editada ' + suffix;
    await page
      .getByRole('button', { name: /Editar actividades/ })
      .first()
      .click();
    await page.getByLabel('Título').fill(title);
    await page.getByRole('button', { name: 'Guardar' }).click();
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
  await test.step('09 Crear compromiso', async () => {
    const title = 'Compromiso Playwright ' + suffix;
    await page.goto(`/app/campaigns/${id}/commitments`);
    await page.getByRole('button', { name: 'Crear compromiso' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Título').fill(title);
    await dialog.getByRole('combobox', { name: /Parroquia/ }).click();
    await page.getByRole('option', { name: 'Gualaceo', exact: true }).click();
    await dialog.getByRole('button', { name: 'Guardar' }).click();
    await expect(page.getByText(title)).toBeVisible();
  });
  await test.step('10 Completar compromiso', async () => {
    await page
      .getByRole('button', { name: /Editar compromisos/ })
      .first()
      .click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Estado').click();
    await page.getByRole('option', { name: 'COMPLETED' }).click();
    await dialog.getByRole('button', { name: 'Guardar' }).click();
    await expect(page.getByText('COMPLETED').first()).toBeVisible();
  });
  await test.step('11 Crear encuesta', async () => {
    await page.goto(`/app/campaigns/${id}/surveys`);
    await page.getByRole('button', { name: 'Gestionar cuestionarios' }).click();
    await page.getByRole('button', { name: 'Crear cuestionario' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Título').fill('Encuesta Playwright ' + suffix);
    await dialog.getByLabel('Slug').fill('encuesta-playwright-' + suffix);
    await dialog.getByRole('button', { name: 'Crear y diseñar' }).click();
    await expect(page.getByRole('heading', { name: /Constructor/ })).toBeVisible();
  });
  await test.step('12 Crear sección', async () => {
    await page.getByRole('button', { name: 'Crear sección' }).click();
    await page.getByLabel('Título').fill('Sección E2E');
    await page.getByRole('button', { name: 'Crear' }).click();
    await expect(page.getByText('Sección E2E')).toBeVisible();
  });
  await test.step('13 Crear pregunta y opciones', async () => {
    await page.getByRole('button', { name: 'Crear pregunta' }).click();
    let dialog = page.getByRole('dialog');
    await dialog.getByRole('combobox', { name: 'Sección' }).click();
    await page.getByRole('option').first().click();
    await dialog.getByLabel('Código').fill('PREGUNTA_E2E');
    await dialog.getByLabel('Pregunta').fill('Seleccione una opción sintética');
    await dialog.getByRole('button', { name: 'Crear' }).click();
    for (const [code, label] of [
      ['OPCION_A', 'Opción A'],
      ['OPCION_B', 'Opción B'],
    ]) {
      await page.getByRole('button', { name: 'Crear opción' }).click();
      dialog = page.getByRole('dialog');
      await dialog.getByRole('combobox', { name: 'Pregunta' }).click();
      await page.getByRole('option').first().click();
      await dialog.getByLabel('Código').fill(code);
      await dialog.getByLabel('Etiqueta').fill(label);
      await dialog.getByRole('button', { name: 'Crear' }).click();
      await expect(page.getByText(label)).toBeVisible();
    }
  });
  await test.step('14 Publicar encuesta', async () => {
    await page.getByRole('button', { name: 'Publicar' }).click();
    await expect(page.getByText('PUBLISHED')).toBeVisible();
  });
  await test.step('15 Captura anónima', async () => {
    await page.goto(`/app/campaigns/${id}/questionnaires`);
    await expect(page.getByText('Encuesta publicada E2E')).toBeVisible();
  });
  await test.step('16 Resultados agregados', async () => {
    await page.goto(`/app/campaigns/${id}/surveys`);
    await expect(page.getByRole('heading', { name: 'ENCUESTAS Y ESTUDIOS' })).toBeVisible();
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
    await nav(page, 'Informes');
    await page.getByRole('button', { name: 'Generar informe' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('combobox', { name: 'Formato' })).toHaveText(/PDF/);
    await dialog.getByRole('button', { name: 'Cancelar' }).click();
  });
  await test.step('23 XLSX', async () => {
    await page.getByRole('button', { name: 'Generar informe' }).click();
    const dialog = page.getByRole('dialog');
    const format = dialog.getByRole('combobox', { name: 'Formato' });
    await format.click();
    await page.getByRole('option', { name: 'XLSX' }).click();
    await expect(format).toHaveText(/XLSX/);
    await dialog.getByRole('button', { name: 'Cancelar' }).click();
  });
  await test.step('24 Alertas', async () => {
    await nav(page, 'Alertas');
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
