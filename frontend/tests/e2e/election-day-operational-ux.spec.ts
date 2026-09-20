import { expect, test, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers, logout } from './support/auth';
import { uniqueE2eValue } from './support/run-data';

// Fase 3.1: ajustes operativos y UX. Cada flujo usa su propia campaña
// dedicada y aislada — nunca las ya usadas (y mutadas) por otros archivos de
// specs — para que esta suite no dependa de en qué orden corren los demás.

async function campaignBySlug(
  request: APIRequestContext,
  headers: Record<string, string>,
  slug: string,
) {
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; slug: string }[];
  const campaign = campaigns.find((item) => item.slug === slug);
  if (!campaign) throw new Error(`El fixture E2E requiere la campaña ${slug}`);
  return campaign;
}

async function managerHeaders(request: APIRequestContext) {
  const token = await apiToken(request, e2eUsers.manager);
  return { Authorization: 'Bearer ' + token };
}

test.describe('Jornada Electoral — Ajustes operativos y UX (Fase 3.1)', () => {
  test('Flujo A — Campaign Manager recorre el ciclo completo: Preparación → activa → escrutinio → cerrada', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const headers = await managerHeaders(request);
    const campaign = await campaignBySlug(request, headers, 'operational-ux-e2e-2027');

    await browserLogin(page, e2eUsers.manager);
    await page.goto(`/app/campaigns/${campaign.id}/election-day`);
    await expect(page.getByRole('heading', { name: 'Jornada Electoral' })).toBeVisible({
      timeout: 15000,
    });
    // No debe verse vocabulario técnico como texto suelto de un botón/estado.
    await expect(page.getByRole('button', { name: 'PREPARATION' })).toHaveCount(0);

    // Ciclo visible (stepper) + botón correcto para PREPARATION.
    await expect(page.getByText('Preparación').first()).toBeVisible({ timeout: 15000 });
    const openResponse = page.waitForResponse((r) => r.url().endsWith('/operation/open'));
    await page.getByRole('button', { name: 'Activar jornada' }).click();
    expect((await openResponse).status()).toBe(200);

    await expect(page.getByRole('button', { name: 'Iniciar escrutinio' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Activar jornada' })).toHaveCount(0);
    const scrutinyResponse = page.waitForResponse((r) =>
      r.url().endsWith('/operation/start-scrutiny'),
    );
    await page.getByRole('button', { name: 'Iniciar escrutinio' }).click();
    expect((await scrutinyResponse).status()).toBe(200);

    await expect(page.getByRole('button', { name: 'Cerrar jornada' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Iniciar escrutinio' })).toHaveCount(0);
    await page.getByRole('button', { name: 'Cerrar jornada' }).click();
    await expect(page.getByRole('heading', { name: 'Cerrar jornada' })).toBeVisible();
    const closeResponse = page.waitForResponse((r) => r.url().endsWith('/operation/close'));
    await page.getByRole('button', { name: 'Confirmar cierre' }).click();
    expect((await closeResponse).status()).toBe(200);

    // CLOSED: ningún botón de cambio de estado, nunca "reabrir".
    await expect(page.getByRole('button', { name: 'Activar jornada' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Iniciar escrutinio' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Cerrar jornada' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /reabrir/i })).toHaveCount(0);
    await expect(page.getByText(/Esta jornada ya no admite cambios operativos/)).toBeVisible();
    await logout(page);
  });

  test('Flujo B — Admin Support entra al Centro de Control y a Validación de actas con el banner visible, y su salida revoca el acceso', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const headers = await managerHeaders(request);
    const campaign = await campaignBySlug(request, headers, 'actas-e2e-2027');
    const adminHeaders = { Authorization: 'Bearer ' + (await apiToken(request, e2eUsers.admin)) };

    const current = await (
      await request.get(`/api/v1/campaigns/${campaign.id}/election-day/admin-support/current`, {
        headers: adminHeaders,
      })
    ).json();
    if (current) {
      await request.post(`/api/v1/campaigns/${campaign.id}/election-day/admin-support/end`, {
        headers: adminHeaders,
      });
    }

    await browserLogin(page, e2eUsers.admin);
    await page.goto('/app/admin/election-day-support');
    const select = page.locator('main').getByLabel('Campaña');
    await select.click();
    await expect(page.getByRole('option', { name: /Actas E2E 2027/ })).toBeVisible();
    await page.getByRole('option', { name: /Actas E2E 2027/ }).click();
    await page.getByRole('button', { name: 'INICIAR MODO SOPORTE' }).click();
    await expect(page.getByText('Modo soporte administrativo activo')).toBeVisible({
      timeout: 15000,
    });

    await page.getByRole('button', { name: 'ENTRAR AL CENTRO DE CONTROL' }).click();
    await expect(page).toHaveURL(new RegExp(`campaigns/${campaign.id}/election-day`));
    await expect(
      page.getByText(`Modo soporte administrativo · Campaña:`, { exact: false }),
    ).toBeVisible({ timeout: 15000 });

    // Vuelve a la página de soporte: la sesión sigue activa (persistida en
    // base de datos, nunca en estado local del navegador).
    await page.goto('/app/admin/election-day-support');
    await page.locator('main').getByLabel('Campaña').click();
    await page.getByRole('option', { name: /Actas E2E 2027/ }).click();
    await expect(page.getByText('Modo soporte administrativo activo')).toBeVisible({
      timeout: 15000,
    });
    await page.getByRole('button', { name: 'VALIDACIÓN DE ACTAS' }).click();
    await expect(page).toHaveURL(new RegExp(`campaigns/${campaign.id}/election-day/validation`));
    await expect(
      page.getByText(`Modo soporte administrativo · Campaña:`, { exact: false }),
    ).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'SALIR DEL MODO SOPORTE' }).click();
    await expect(
      page.getByText('No tienes una asignación de validador de actas en esta jornada.'),
    ).toBeVisible({ timeout: 15000 });

    const revoked = await request.get(
      `/api/v1/campaigns/${campaign.id}/election-day/control-center`,
      { headers: adminHeaders },
    );
    expect(revoked.status()).toBe(403);
    await logout(page);
  });

  test('Flujo C — Campaign Manager ve el aviso de contraseña propia al invitar personal y en el resumen posterior', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const headers = await managerHeaders(request);
    const campaign = await campaignBySlug(request, headers, 'actas-e2e-2027');
    const email = uniqueE2eValue('operational-ux-delegate') + '@example.com';

    await browserLogin(page, e2eUsers.manager);
    // Cada page.goto es una navegación completa, que vuelve a disparar el
    // refresh-token silencioso al cargar; sin una pequeña pausa, navegar de
    // inmediato tras el login puede competir con esa rotación (mismo gotcha
    // ya documentado en election-day.spec.ts).
    await page.waitForTimeout(500);
    await page.goto(`/app/campaigns/${campaign.id}/election-day`);
    await expect(page.getByRole('heading', { name: 'Jornada Electoral' })).toBeVisible({
      timeout: 20000,
    });
    await page.getByRole('button', { name: 'AGREGAR PERSONAL' }).click({ timeout: 20000 });
    await expect(
      page.getByText(
        'El personal recibirá un enlace de invitación y creará su propia contraseña al activar el acceso.',
      ),
    ).toBeVisible();
    await expect(
      page.getByText('El delegado creará su propia contraseña al activar la invitación.'),
    ).toBeVisible();

    await page.getByLabel('Nombre').fill('Operativo');
    await page.getByLabel('Apellido').fill('UX E2E');
    await page.getByLabel('Correo').fill(email);
    // Nunca getByLabel: colisiona con aria-label="Mapa operativo de recintos"
    // del mapa (mismo patrón ya usado en election-day-staff-invitations.spec.ts).
    await page.getByRole('combobox', { name: 'Recintos' }).click();
    await page.getByRole('option', { name: 'Recinto Sintético de Actas' }).click();
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Crear invitación' }).click();

    const summary = page.getByRole('dialog', { name: 'Invitación creada' });
    await expect(summary).toBeVisible({ timeout: 15000 });
    await expect(summary.getByText('Delegado de recinto')).toBeVisible();
    await expect(
      summary.getByText('Esta persona deberá crear su propia contraseña al activar el acceso.'),
    ).toBeVisible();
    await expect(
      summary.getByRole('button', { name: 'COPIAR ENLACE DE INVITACIÓN' }),
    ).toBeVisible();
    await summary.locator('input[readonly]').first().inputValue();
    await page.getByRole('button', { name: 'Cerrar' }).click();
    await logout(page);
  });
});
