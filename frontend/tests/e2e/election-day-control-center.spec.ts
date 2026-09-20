import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers, logout } from './support/auth';

// Fase 3: reutiliza la campaña "actas-e2e-2027" (ver
// ensure_election_acts_fixture en seed_e2e.py) pero SIEMPRE con la junta J03,
// reservada exclusivamente para este archivo — J01/J02 terminan VALIDATED al
// final de election-day-acts.spec.ts y no deben compartirse con este flujo.
async function actsCampaign(request: APIRequestContext, headers: Record<string, string>) {
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; slug: string }[];
  const campaign = campaigns.find((item) => item.slug === 'actas-e2e-2027');
  if (!campaign) throw new Error('El fixture E2E requiere actas-e2e-2027');
  return campaign;
}

async function managerHeaders(request: APIRequestContext) {
  const token = await apiToken(request, e2eUsers.manager);
  return { Authorization: 'Bearer ' + token };
}

async function controlCenter(
  request: APIRequestContext,
  headers: Record<string, string>,
  campaignId: string,
) {
  const resp = await request.get(`/api/v1/campaigns/${campaignId}/election-day/control-center`, {
    headers,
  });
  expect(resp.status()).toBe(200);
  return resp.json();
}

const JPEG_BYTES = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0]);
const BOARD_3 = 'E2E-ACT-REC-01-J03';

async function fillActForm(
  page: Page,
  title: string,
  candidate1Votes: string,
  candidate2Votes: string,
) {
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText(title)).toBeVisible();
  await dialog.getByLabel('Votos en blanco').fill('1');
  await dialog.getByLabel('Votos nulos').fill('1');
  await dialog
    .getByLabel('Votos válidos (opcional)')
    .fill(String(Number(candidate1Votes) + Number(candidate2Votes)));
  await dialog
    .getByLabel('Total de actas escrutadas (opcional)')
    .fill(String(Number(candidate1Votes) + Number(candidate2Votes) + 2));
  await dialog.getByLabel('Candidata Uno').fill(candidate1Votes);
  await dialog.getByLabel('Candidato Dos').fill(candidate2Votes);
  await dialog.locator('input[type="file"]').setInputFiles({
    name: 'acta.jpg',
    mimeType: 'image/jpeg',
    buffer: JPEG_BYTES,
  });
  await expect(dialog.getByText('Fotos agregadas: 1')).toBeVisible();
  await dialog.getByRole('button', { name: 'Guardar' }).click();
  await expect(
    page.getByText('Acta guardada en el dispositivo. Se sincronizará con el servidor.'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Sincronizar ahora' }).click();
  await expect(page.getByText(/1 registro.*sincronizado/i)).toBeVisible({ timeout: 20000 });
}

test.describe('Jornada Electoral — Centro de Control (Fase 3)', () => {
  test('solo las actas VALIDATED cuentan en el Centro de Control, exactamente una vez', async ({
    page,
    request,
  }) => {
    test.setTimeout(120000);
    const headers = await managerHeaders(request);
    const campaign = await actsCampaign(request, headers);

    // Nunca /acts/contests: exige una asignación de delegado de recinto y
    // el manager (ejecutivo) no tiene una — el propio Centro de Control ya
    // trae candidate_id/display_name por contienda, y es al que el manager
    // sí tiene acceso.
    const initial = await controlCenter(request, headers, campaign.id);
    const contestId = initial.control_center.contests[0].contest_id as string;
    const candidatesMeta = initial.control_center.contests[0].candidates as {
      candidate_id: string;
      display_name: string;
    }[];
    const candUno = candidatesMeta.find((c) => c.display_name === 'Candidata Uno')!;
    const candDos = candidatesMeta.find((c) => c.display_name === 'Candidato Dos')!;

    const votesOf = (data: any, candidateId: string) => {
      const c = data.control_center.contests.find((x: any) => x.contest_id === contestId);
      return c.candidates.find((cd: any) => cd.candidate_id === candidateId).votes as number;
    };

    const unoBefore = votesOf(initial, candUno.candidate_id);
    const dosBefore = votesOf(initial, candDos.candidate_id);

    // 1) Delegado registra el acta de J03 (6/3) — RECEIVED, aún no cuenta.
    await browserLogin(page, e2eUsers.delegateA);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/my`);
    await expect(page.getByText('Recinto Sintético de Actas')).toBeVisible({ timeout: 15000 });
    await page
      .getByTestId(`board-row-${BOARD_3}`)
      .getByRole('button', { name: 'REGISTRAR ACTA' })
      .click();
    await fillActForm(page, 'Registrar acta — Junta 3', '6', '3');
    await logout(page);

    const afterSubmit = await controlCenter(request, headers, campaign.id);
    expect(votesOf(afterSubmit, candUno.candidate_id)).toBe(unoBefore);
    expect(votesOf(afterSubmit, candDos.candidate_id)).toBe(dosBefore);

    // 2) Validador reclama y valida — a partir de aquí SÍ debe contar.
    await browserLogin(page, e2eUsers.analyst);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/validation`);
    const card = page.getByTestId(`act-card-${BOARD_3}`);
    await expect(card).toBeVisible({ timeout: 15000 });
    await card.getByRole('button', { name: 'RECLAMAR PARA REVISAR' }).click();
    const validateResponse = page.waitForResponse((r) => r.url().includes('/validate'));
    await card.getByRole('button', { name: 'VALIDAR' }).click();
    expect((await validateResponse).status()).toBe(200);
    await logout(page);

    // 3) Candidato/Jefe de Campaña ve los votos aparecer EXACTAMENTE una vez.
    const afterValidate = await controlCenter(request, headers, campaign.id);
    expect(votesOf(afterValidate, candUno.candidate_id)).toBe(unoBefore + 6);
    expect(votesOf(afterValidate, candDos.candidate_id)).toBe(dosBefore + 3);

    await browserLogin(page, e2eUsers.manager);
    await page.goto(`/app/campaigns/${campaign.id}/election-day`);
    await expect(page.getByText('NO OFICIAL')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Conteo interno de actas')).toBeVisible();
    await expect(page.getByText('Candidata Uno')).toBeVisible();
    await logout(page);

    // Releer de nuevo no debe duplicar el resultado (idempotencia de lectura).
    const reread = await controlCenter(request, headers, campaign.id);
    expect(votesOf(reread, candUno.candidate_id)).toBe(unoBefore + 6);
    expect(votesOf(reread, candDos.candidate_id)).toBe(dosBefore + 3);
  });

  test('Modo soporte administrativo: ve los mismos números que la campaña, con el aviso correspondiente', async ({
    page,
    request,
  }) => {
    test.setTimeout(60000);
    const headers = await managerHeaders(request);
    const campaign = await actsCampaign(request, headers);
    const adminHeaders = { Authorization: 'Bearer ' + (await apiToken(request, e2eUsers.admin)) };

    // Sesión de soporte limpia: termina cualquier sesión activa previa antes
    // de empezar, para que este test no dependa de una corrida anterior.
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

    // El inicio de la sesión de soporte se hace por API, nunca a través del
    // selector local de campaña de ElectionDaySupportPage: ese selector lista
    // /campaigns bajo la ORGANIZACIÓN ACTIVA de admin_e2e en el conmutador
    // global de la barra superior, que otras specs de la suite pueden dejar
    // apuntando a una organización distinta — este test no debe depender de
    // ese estado global compartido entre archivos.
    const startResp = await request.post(
      `/api/v1/campaigns/${campaign.id}/election-day/admin-support/start`,
      { headers: adminHeaders, data: { reason: 'e2e' } },
    );
    expect(startResp.status()).toBe(201);

    await browserLogin(page, e2eUsers.admin);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/control-center`);
    // Dos avisos distintos mencionan "Modo soporte administrativo": el de la
    // cabecera de la página y el propio del panel del Centro de Control.
    await expect(
      page.getByText('estos números son idénticos a los que ve el equipo de la campaña'),
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('NO OFICIAL')).toBeVisible();

    const execView = await controlCenter(request, headers, campaign.id);
    const adminView = await controlCenter(request, adminHeaders, campaign.id);
    expect(adminView.control_center.acts_coverage).toEqual(execView.control_center.acts_coverage);

    // El botón "SALIR DEL MODO SOPORTE" también vive en la cabecera del
    // propio Centro de Control (no solo en la página de soporte), así que
    // termina la sesión desde ahí mismo.
    await page.getByRole('button', { name: 'SALIR DEL MODO SOPORTE' }).click();
    await expect(
      page.getByText(
        'Necesitas iniciar el modo soporte administrativo para esta campaña antes de consultar el Centro de Control.',
      ),
    ).toBeVisible({ timeout: 15000 });
    await logout(page);
  });

  test('Delegado y Validador no acceden al Centro de Control por URL directa', async ({
    page,
    request,
  }) => {
    const headers = await managerHeaders(request);
    const campaign = await actsCampaign(request, headers);
    const url = `/app/campaigns/${campaign.id}/election-day/control-center`;

    for (const username of [e2eUsers.delegateA, e2eUsers.analyst]) {
      const userHeaders = { Authorization: 'Bearer ' + (await apiToken(request, username)) };
      const apiResp = await request.get(
        `/api/v1/campaigns/${campaign.id}/election-day/control-center`,
        { headers: userHeaders },
      );
      expect(apiResp.status()).toBe(403);

      await browserLogin(page, username);
      await page.goto(url);
      await expect(page.getByText('No tienes permisos para acceder a esta página.')).toBeVisible({
        timeout: 15000,
      });
      // La página /403 es standalone (sin AppShell/topbar): no hay menú de
      // usuario desde el que cerrar sesión ahí. Se navega a /app antes de
      // salir, para que el próximo browserLogin() de esta misma page parta
      // de una sesión limpia.
      await page.goto('/app');
      await logout(page);
    }
  });
});
