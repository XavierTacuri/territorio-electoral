import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers, logout } from './support/auth';

// Fase 2: usa una campaña dedicada ("actas-e2e-2027", ver
// ensure_election_acts_fixture en seed_e2e.py) que nace directamente en
// SCRUTINY con 1 recinto / 2 juntas / 2 candidatos — nunca la campaña de
// election-day.spec.ts, que otro archivo mueve a SCRUTINY/CLOSED por su
// cuenta al final de su propia suite. Cada prueba usa una junta distinta
// (J01/J02) y localizadores por data-testid (nunca `.first()`), para que el
// orden real de ejecución — o un acta que quedó de una corrida anterior —
// nunca haga que una prueba opere sobre el acta equivocada.
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

const JPEG_BYTES = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0]);
const BOARD_1 = 'E2E-ACT-REC-01-J01';
const BOARD_2 = 'E2E-ACT-REC-01-J02';

async function fillActForm(
  page: Page,
  title: string,
  candidate1Votes: string,
  candidate2Votes: string,
  correctionReason?: string,
) {
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText(title)).toBeVisible();
  if (correctionReason) await dialog.getByLabel('Motivo de la corrección').fill(correctionReason);
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

async function registerAct(
  page: Page,
  campaignId: string,
  boardCode: string,
  boardLabel: string,
  candidate1Votes: string,
  candidate2Votes: string,
) {
  await page.goto(`/app/campaigns/${campaignId}/election-day/my`);
  await expect(page.getByText('Recinto Sintético de Actas')).toBeVisible({ timeout: 15000 });
  await page
    .getByTestId(`board-row-${boardCode}`)
    .getByRole('button', { name: 'REGISTRAR ACTA' })
    .click();
  await fillActForm(page, `Registrar acta — ${boardLabel}`, candidate1Votes, candidate2Votes);
}

test.describe('Jornada Electoral — Actas (Fase 2)', () => {
  test('Delegado registra un acta offline con foto; el validador la reclama y la valida', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const headers = await managerHeaders(request);
    const campaign = await actsCampaign(request, headers);

    await browserLogin(page, e2eUsers.delegateA);
    await registerAct(page, campaign.id, BOARD_1, 'Junta 1', '10', '5');

    await logout(page);
    await browserLogin(page, e2eUsers.analyst);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/validation`);
    const card = page.getByTestId(`act-card-${BOARD_1}`);
    await expect(card).toBeVisible({ timeout: 15000 });
    await expect(card.getByText('10 votos')).toBeVisible();
    await expect(card.getByText('5 votos')).toBeVisible();
    await card.getByRole('button', { name: 'RECLAMAR PARA REVISAR' }).click();
    const validateResponse = page.waitForResponse((r) => r.url().includes('/validate'));
    await card.getByRole('button', { name: 'VALIDAR' }).click();
    expect((await validateResponse).status()).toBe(200);
    await expect(page.getByText('Acta validada.')).toBeVisible();
  });

  test('Validador observa un acta; el Delegado la corrige y el validador la valida', async ({
    page,
    request,
  }) => {
    test.setTimeout(120000);
    const headers = await managerHeaders(request);
    const campaign = await actsCampaign(request, headers);

    await browserLogin(page, e2eUsers.delegateA);
    await registerAct(page, campaign.id, BOARD_2, 'Junta 2', '8', '4');

    await logout(page);
    await browserLogin(page, e2eUsers.analyst);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/validation`);
    const card = page.getByTestId(`act-card-${BOARD_2}`);
    await expect(card).toBeVisible({ timeout: 15000 });
    await expect(card.getByText('8 votos')).toBeVisible();
    await card.getByRole('button', { name: 'RECLAMAR PARA REVISAR' }).click();
    await card.getByRole('button', { name: 'OBSERVAR' }).click();
    await page
      .getByLabel('Motivo de la observación')
      .fill('Los totales no cuadran con el acta física.');
    const observeResponse = page.waitForResponse((r) => r.url().includes('/observe'));
    await page.getByRole('button', { name: 'Confirmar observación' }).click();
    expect((await observeResponse).status()).toBe(200);
    await expect(page.getByText('Acta observada.')).toBeVisible();

    await logout(page);
    await browserLogin(page, e2eUsers.delegateA);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/my`);
    const boardRow = page.getByTestId(`board-row-${BOARD_2}`);
    await expect(boardRow.getByText('Observada')).toBeVisible({ timeout: 15000 });
    await boardRow.getByRole('button', { name: 'CORREGIR ACTA' }).click();
    await fillActForm(
      page,
      'Corregir acta — Junta 2',
      '8',
      '4',
      'Se recontaron las actas físicas y se corrigió el total.',
    );

    await logout(page);
    await browserLogin(page, e2eUsers.analyst);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/validation`);
    const correctedCard = page.getByTestId(`act-card-${BOARD_2}`);
    await expect(correctedCard.getByText('Revisión #2')).toBeVisible({ timeout: 15000 });
    await correctedCard.getByRole('button', { name: 'RECLAMAR PARA REVISAR' }).click();
    const validateResponse = page.waitForResponse((r) => r.url().includes('/validate'));
    await correctedCard.getByRole('button', { name: 'VALIDAR' }).click();
    expect((await validateResponse).status()).toBe(200);
    await expect(page.getByText('Acta validada.')).toBeVisible();
  });

  test('RBAC: CANDIDATE/CAMPAIGN_MANAGER no puede reclamar actas; solo un ACT_VALIDATOR o ADMIN en soporte', async ({
    request,
  }) => {
    // require_act_reviewer se evalúa antes de siquiera buscar el acta (§14):
    // un id inexistente basta para probar el 403 sin depender de que otra
    // prueba de este archivo haya dejado un acta en un estado concreto.
    const headers = await managerHeaders(request);
    const campaign = await actsCampaign(request, headers);
    const fakeActId = '00000000-0000-0000-0000-000000000000';
    const denied = await request.post(
      `/api/v1/campaigns/${campaign.id}/election-day/acts/${fakeActId}/claim`,
      { headers },
    );
    expect(denied.status()).toBe(403);
  });

  test('Centro de Control muestra cobertura documental de actas sin votos agregados', async ({
    page,
    request,
  }) => {
    const headers = await managerHeaders(request);
    const campaign = await actsCampaign(request, headers);
    const coverage = await (
      await request.get(`/api/v1/campaigns/${campaign.id}/election-day/acts/coverage`, {
        headers,
      })
    ).json();
    expect(coverage).toHaveProperty('expected_boards');
    expect(coverage).not.toHaveProperty('votes');
    expect(coverage).not.toHaveProperty('winner');

    await browserLogin(page, e2eUsers.manager);
    await page.goto(`/app/campaigns/${campaign.id}/election-day`);
    await expect(page.getByText('JRV esperadas')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Validadas', { exact: true })).toBeVisible();
  });
});
