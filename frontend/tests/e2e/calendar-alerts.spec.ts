import { test, expect, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';
import { e2eRunId, uniqueE2eValue } from './support/run-data';

function jwtUserId(token: string): string {
  const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
  return payload.sub as string;
}

async function gualaceoCampaign(request: APIRequestContext, headers: Record<string, string>) {
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; slug: string; canton_id: number; office_type: string }[];
  const campaign = campaigns.find((item) => item.slug === 'gualaceo-e2e-2027');
  if (!campaign) throw new Error('El fixture E2E requiere gualaceo-e2e-2027');
  return campaign;
}

test('Calendario de campaña y Centro de alertas: actividades, hitos oficiales retirados del calendario y RBAC', async ({
  page,
  request,
}) => {
  test.setTimeout(180000);
  const runId = e2eRunId;
  const adminToken = await apiToken(request);
  const headers = { Authorization: 'Bearer ' + adminToken };
  const campaign = await gualaceoCampaign(request, headers);

  const sourceCode = uniqueE2eValue('CAL_E2E_SOURCE').toUpperCase().replace(/-/g, '_');
  const source = await (
    await request.post('/api/v1/data-sources', {
      headers,
      data: {
        code: sourceCode,
        institution: 'Consejo Nacional Electoral',
        dataset_name: `Calendario sintético E2E ${runId}`,
        dataset_type: 'OTHER_AGGREGATED_OFFICIAL',
        is_official: true,
      },
    })
  ).json();

  const processCode = uniqueE2eValue('CAL_E2E_PROC').toUpperCase().replace(/-/g, '_');
  const process = await (
    await request.post('/api/v1/electoral-processes', {
      headers,
      data: {
        code: processCode,
        name: `Proceso calendario ${runId}`,
        process_type: 'SECTIONAL',
        election_date: '2027-02-14',
        year: 2027,
        status: 'VALIDATED',
        source_id: source.id,
      },
    })
  ).json();

  const contestResponse = await request.post(`/api/v1/electoral-processes/${process.id}/contests`, {
    headers,
    data: {
      office_type: campaign.office_type,
      name: `CONTEST_CAL_${runId}`,
      vote_method: 'SINGLE_CHOICE',
      canton_id: campaign.canton_id,
      seats: 1,
    },
  });
  expect(contestResponse.status()).toBe(201);

  const milestoneDate = new Date();
  milestoneDate.setDate(milestoneDate.getDate() + 5);
  const milestoneTitle = `Debate sintético ${runId}`;

  const parishes = (await (
    await request.get(`/api/v1/parishes?canton_id=${campaign.canton_id}`, { headers })
  ).json()) as { id: number; name: string }[];
  const parishId = parishes[0].id;

  const approvedActivity = await (
    await request.post(`/api/v1/campaigns/${campaign.id}/activities`, {
      headers,
      data: {
        activity_type_code: 'ASSEMBLY',
        title: `Asamblea calendario ${runId}`,
        description: 'Actividad sintética E2E',
        activity_date: new Date(Date.now() + 6 * 86400000).toISOString().slice(0, 10),
        parish_id: parishId,
        status: 'PLANNED',
      },
    })
  ).json();

  await request.post(`/api/v1/campaigns/${campaign.id}/commitments`, {
    headers,
    data: {
      title: `Seguimiento calendario ${runId}`,
      due_date: new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10),
      parish_id: parishId,
    },
  });

  // Use the coordinator's real assigned parish (not an arbitrary one) so the
  // pending-approval activity it creates actually passes territorial_access.
  const coordinatorToken = await apiToken(request, e2eUsers.coordinator);
  const coordinatorHeaders = { Authorization: 'Bearer ' + coordinatorToken };
  const coordinatorUserId = jwtUserId(coordinatorToken);
  const assignments = (await (
    await request.get(`/api/v1/campaigns/${campaign.id}/territorial-assignments`, { headers })
  ).json()) as { user_id: string; parish_id: number; is_active: boolean }[];
  const coordinatorAssignment = assignments.find(
    (a) => a.user_id === coordinatorUserId && a.is_active,
  );
  if (!coordinatorAssignment)
    throw new Error('coordinator_e2e requiere una asignación territorial activa en el fixture E2E');
  const coordinatorParishId = coordinatorAssignment.parish_id;
  await request.post(`/api/v1/campaigns/${campaign.id}/activities`, {
    headers: coordinatorHeaders,
    data: {
      activity_type_code: 'ASSEMBLY',
      title: `Pendiente aprobación ${runId}`,
      description: 'Actividad sintética pendiente E2E',
      // Dated in the past (not asserted anywhere in this spec) so it sorts to the
      // bottom of the activities list (ordered by activity_date desc) instead of
      // outranking other specs' own same-day fixtures via `.first()` selectors.
      activity_date: new Date(Date.now() - 3 * 86400000).toISOString().slice(0, 10),
      parish_id: coordinatorParishId,
      status: 'PLANNED',
    },
  });

  await test.step('ADMIN crea un hito electoral oficial sintético desde el panel administrativo', async () => {
    await browserLogin(page, e2eUsers.admin);
    await page.goto('/app/admin/electoral-milestones');
    await page.getByRole('button', { name: 'Nuevo hito' }).click();
    await page.getByLabel('Proceso electoral').click();
    await page.getByRole('option', { name: new RegExp(process.name) }).click();
    await page.getByLabel('Título').fill(milestoneTitle);
    await page.getByLabel('Tipo de hito').click();
    await page.getByRole('option', { name: 'Debate' }).click();
    await page.getByLabel('Fecha y hora').fill(milestoneDate.toISOString().slice(0, 16));
    await page.getByLabel('Fuente oficial').click();
    await page.getByRole('option', { name: new RegExp(source.dataset_name) }).click();
    const created = page.waitForResponse(
      (r) => r.url().endsWith('/electoral-milestones') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Crear hito' }).click();
    expect((await created).status()).toBe(201);
    await expect(page.getByText(milestoneTitle)).toBeVisible();
  });

  await test.step('CANDIDATE ve la actividad en el Calendario de campaña; el hito oficial y el seguimiento nunca aparecen ahí', async () => {
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await browserLogin(page, e2eUsers.candidate);
    await page.goto(`/app/campaigns/${campaign.id}/calendar`);
    await expect(page.getByRole('heading', { name: 'Calendario de campaña' })).toBeVisible();
    await page.getByRole('button', { name: 'Agenda' }).click();
    await expect(page.getByText(`Asamblea calendario ${runId}`)).toBeVisible();
    await expect(page.getByText('Próxima').first()).toBeVisible();
    await expect(page.getByText(milestoneTitle)).toHaveCount(0);
    await expect(page.getByText(`Seguimiento calendario ${runId}`)).toHaveCount(0);
    await page.getByText(`Asamblea calendario ${runId}`).click();
    await expect(page.getByRole('link', { name: 'Ver detalle' })).toHaveAttribute(
      'href',
      new RegExp(`/activities/${approvedActivity.id}`),
    );
  });

  await test.step('CANDIDATE revisa el Centro de alertas y reconoce la aprobación pendiente', async () => {
    await page.goto(`/app/campaigns/${campaign.id}/alerts`);
    const evaluated = page.waitForResponse(
      (r) => r.url().endsWith('/alerts/evaluate') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Evaluar reglas' }).click();
    await evaluated;
    // Filtrar por Módulo=Operación y Estado=Pendiente ANTES de la primera
    // aserción visible: ACTIVITY_PENDING_APPROVAL es severidad INFO, la de
    // menor prioridad de orden — en la base E2E compartida, tras muchas
    // corridas, puede haber más de 50 alertas de severidad WARNING/CRITICAL
    // acumuladas que empujen esta alerta fuera de la primera página si se
    // consulta sin filtrar. Con ambos filtros el conjunto queda acotado al
    // módulo Operación en estado abierto, donde sí cabe en una página.
    await page.getByRole('combobox', { name: /Módulo/ }).click();
    await page.getByRole('option', { name: 'Operación' }).click();
    await page.getByRole('combobox', { name: /Estado/ }).click();
    await page.getByRole('option', { name: 'Pendiente' }).click();
    const openRow = page
      .getByRole('row')
      .filter({ hasText: 'Actividad pendiente de aprobación' })
      .first();
    await expect(openRow).toBeVisible();
    await openRow.getByRole('button', { name: 'Gestionar' }).click();
    const acknowledged = page.waitForResponse(
      (r) => r.url().endsWith('/acknowledge') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Confirmar' }).click();
    expect((await acknowledged).status()).toBe(200);
    await page.getByRole('combobox', { name: /Estado/ }).click();
    await page.getByRole('option', { name: 'Revisada' }).click();
    await expect(page.getByText('Actividad pendiente de aprobación').first()).toBeVisible();
  });

  await test.step('COORDINATOR no ve una alerta de aprobación que no puede resolver', async () => {
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await browserLogin(page, e2eUsers.coordinator);
    await page.goto(`/app/campaigns/${campaign.id}/alerts`);
    await expect(page.getByText(`Pendiente aprobación ${runId}`)).toHaveCount(0);
  });

  await test.step('Territorio IA responde sobre próximos hitos y qué requiere atención, con citas', async () => {
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await browserLogin(page, e2eUsers.candidate);
    await page.goto(`/app/campaigns/${campaign.id}/territory-ai`);
    const response1 = page.waitForResponse((r) => r.url().endsWith('/territory-ai/query'));
    await page.getByLabel(/Pregunta|Escribe/).fill('¿Cuáles son los próximos hitos electorales?');
    await page.getByRole('button', { name: 'ENVIAR' }).click();
    expect((await response1).status()).toBe(200);
    await expect(page.getByText(/hito|calendario/i).first()).toBeVisible();
    const response2 = page.waitForResponse((r) => r.url().endsWith('/territory-ai/query'));
    await page.getByLabel(/Pregunta|Escribe/).fill('¿Qué requiere atención hoy?');
    await page.getByRole('button', { name: 'ENVIAR' }).click();
    const body2 = await (await response2).json();
    expect(body2.status).not.toBe('BLOCKED');
    for (const banned of ['debería priorizarse', 'aprovecha esta oportunidad', 'persuade']) {
      expect(body2.answer.toLowerCase()).not.toContain(banned);
    }
  });
});
