import { test, expect, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';
import { e2eRunId } from './support/run-data';

async function gualaceoCampaign(request: APIRequestContext, headers: Record<string, string>) {
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; slug: string; canton_id: number }[];
  const campaign = campaigns.find((item) => item.slug === 'gualaceo-e2e-2027');
  if (!campaign) throw new Error('El fixture E2E requiere gualaceo-e2e-2027');
  return campaign;
}

test.describe('Centro de Informes', () => {
  test('CANDIDATE genera un informe ejecutivo de campaña con previsualización grounded', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);

    await browserLogin(page, e2eUsers.candidate);
    await page.goto(`/app/campaigns/${campaign.id}/reports`);
    await expect(page.getByRole('heading', { name: 'Centro de Informes' })).toBeVisible();
    await expect(page.getByText('Resumen general de la campaña')).toBeVisible();

    const previewResponse = page.waitForResponse(
      (r) => r.url().endsWith('/reports/preview') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Generar' }).click();
    expect((await previewResponse).status()).toBe(200);

    await expect(page.getByText('Resumen ejecutivo')).toBeVisible();
    await expect(
      page.getByText('Informe descriptivo. No constituye predicción electoral'),
    ).toBeVisible();
    await expect(page.getByText(/Redacción del sistema|Redactado por IA grounded/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Regenerar' })).toBeVisible();
  });

  test('CAMPAIGN_MANAGER genera un informe territorial por parroquia', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    const parishes = (await (
      await request.get(`/api/v1/parishes?canton_id=${campaign.canton_id}`, { headers })
    ).json()) as { id: number; name: string }[];
    const parish = parishes.find((p) => p.name === 'Gualaceo') ?? parishes[0];

    await browserLogin(page, e2eUsers.manager);
    await page.goto(`/app/campaigns/${campaign.id}/reports`);
    await page.getByLabel('Tipo de informe').click();
    await page.getByRole('option', { name: 'Informe territorial por parroquia' }).click();
    await page.locator('main').getByRole('combobox').nth(1).click();
    await page.getByRole('option', { name: parish.name }).click();

    const previewResponse = page.waitForResponse((r) => r.url().endsWith('/reports/preview'));
    await page.getByRole('button', { name: 'Generar' }).click();
    expect((await previewResponse).status()).toBe(200);
    await expect(page.getByText('Resumen ejecutivo')).toBeVisible();
  });

  test('ANALYST genera un informe temático con cruce por tema', async ({ page, request }) => {
    test.setTimeout(90000);
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);

    await browserLogin(page, e2eUsers.analyst);
    await page.goto(`/app/campaigns/${campaign.id}/reports?type=THEMATIC_REPORT`);
    await expect(page.getByLabel('Tema')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Generar' })).toBeDisabled();

    await page.getByLabel('Tema').click();
    await page.getByRole('option', { name: 'Vialidad' }).click();
    const previewResponse = page.waitForResponse((r) => r.url().endsWith('/reports/preview'));
    await page.getByRole('button', { name: 'Generar' }).click();
    expect((await previewResponse).status()).toBe(200);
    await expect(page.getByText('Resumen ejecutivo')).toBeVisible();
  });

  test('TERRITORIAL_COORDINATOR solo puede generar informes de su parroquia asignada', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    const parishes = (await (
      await request.get(`/api/v1/parishes?canton_id=${campaign.canton_id}`, { headers })
    ).json()) as { id: number; name: string }[];
    const assigned = parishes.find((p) => p.name === 'Gualaceo');
    const notAssigned = parishes.find((p) => p.name === 'Jadán');
    if (!assigned || !notAssigned)
      throw new Error('El fixture E2E requiere las parroquias Gualaceo y Jadán');

    await browserLogin(page, e2eUsers.coordinator);
    await page.goto(`/app/campaigns/${campaign.id}/reports`);
    await page.getByLabel('Tipo de informe').click();
    await page.getByRole('option', { name: 'Informe territorial por parroquia' }).click();
    await page.locator('main').getByRole('combobox').nth(1).click();

    // El listado de parroquias ya está restringido territorialmente en origen
    // (endpoint /parishes filtra por allowed_parish): el coordinador nunca ve
    // Jadán como opción seleccionable.
    await expect(page.getByRole('option', { name: assigned.name })).toBeVisible();
    await expect(page.getByRole('option', { name: notAssigned.name })).toHaveCount(0);
    await page.getByRole('option', { name: assigned.name }).click();

    const okPreview = page.waitForResponse((r) => r.url().endsWith('/reports/preview'));
    await page.getByRole('button', { name: 'Generar' }).click();
    expect((await okPreview).status()).toBe(200);
    await expect(page.getByText('No se pudo generar la previsualización.')).toHaveCount(0);

    // Defensa en profundidad: si se fuerza el parish_id fuera de alcance
    // directamente contra la API (evitando el selector de la UI), el backend
    // igual lo rechaza con 403.
    const coordinatorToken = await apiToken(request, e2eUsers.coordinator);
    const forbidden = await request.post(`/api/v1/campaigns/${campaign.id}/reports/preview`, {
      headers: { Authorization: 'Bearer ' + coordinatorToken },
      data: {
        template_code: 'PARISH_TERRITORIAL_PROFILE',
        format: 'PDF',
        title: 'Fuera de alcance',
        report_date: '2026-09-03',
        parish_id: notAssigned.id,
      },
    });
    expect(forbidden.status()).toBe(403);
  });

  test('exportación PDF descargable desde el historial y configurador responsivo', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    const title = 'Informe centro de informes ' + e2eRunId;

    await browserLogin(page, e2eUsers.candidate);
    await page.goto(`/app/campaigns/${campaign.id}/reports`);
    await page.getByLabel('Título del informe').fill(title);
    const generateResponse = page.waitForResponse(
      (r) => r.url().endsWith('/reports/generate') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Exportar PDF' }).click();
    expect((await generateResponse).status()).toBe(201);
    await expect(page.getByText(title)).toBeVisible();

    const row = page.getByRole('row').filter({ hasText: title });
    const downloadResponse = page.waitForResponse((r) => r.url().includes('/download'));
    const downloadPromise = page.waitForEvent('download');
    await row.getByRole('button', { name: 'Descargar' }).click();
    const [response, download] = await Promise.all([downloadResponse, downloadPromise]);
    expect(response.headers()['content-disposition']).toContain('attachment');
    expect(download.suggestedFilename().toLowerCase()).toMatch(/\.pdf$/);
    const stream = await download.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream) chunks.push(Buffer.from(chunk));
    expect(Buffer.concat(chunks).subarray(0, 4).toString()).toBe('%PDF');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Centro de Informes' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Generar' })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
      ),
    ).toBe(true);
  });

  test('el wizard conserva parroquia, periodo e inclusiones al abrir un enlace de versión actualizada', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    const parishes = (await (
      await request.get(`/api/v1/parishes?canton_id=${campaign.canton_id}`, { headers })
    ).json()) as { id: number; name: string }[];
    const jadan = parishes.find((p) => p.name === 'Jadán');
    if (!jadan) throw new Error('El fixture E2E requiere la parroquia Jadán');

    await browserLogin(page, e2eUsers.candidate);
    await page.goto(
      `/app/campaigns/${campaign.id}/reports?type=PARISH_TERRITORIAL_PROFILE&parish_id=${jadan.id}&date_from=2026-08-01&date_to=2026-08-31&include_public_intelligence=false`,
    );
    await expect(page.getByRole('heading', { name: 'Centro de Informes' })).toBeVisible();
    await expect(page.locator('main').getByRole('combobox').nth(1)).toHaveText(jadan.name);
    await expect(page.getByLabel('Encuestas publicadas')).toBeChecked();
    await expect(page.getByLabel('Información pública')).not.toBeChecked();

    const title = 'Versión actualizada ' + e2eRunId;
    await page.getByLabel('Título del informe').fill(title);
    const generateResponse = page.waitForResponse(
      (r) => r.url().endsWith('/reports/generate') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Exportar PDF' }).click();
    expect((await generateResponse).status()).toBe(201);
    await expect(page.getByText(title)).toBeVisible();
  });

  test('nueva medición comparable dispara alerta y abre el comparador de estudios', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    // STUDY_E2E/MEASUREMENT_E2E (el par comparable del seed) vive en la
    // campaña sintética separada, no en gualaceo-e2e-2027.
    const campaigns = (
      await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
    ).items as { id: string; slug: string }[];
    const campaign = campaigns.find((item) => item.slug === 'territorio-sintetico-e2e');
    if (!campaign) throw new Error('El fixture E2E requiere territorio-sintetico-e2e');

    const evaluateResponse = await request.post(
      `/api/v1/campaigns/${campaign.id}/alerts/evaluate`,
      {
        headers,
        data: { rule_codes: ['SURVEY_COMPARISON_CHANGE'], as_of_date: '2026-09-20' },
      },
    );
    expect(evaluateResponse.status()).toBe(200);

    await browserLogin(page, e2eUsers.admin);
    await page.goto(`/app/campaigns/${campaign.id}/alerts`);
    await expect(page.getByText('Nueva medición comparable disponible').first()).toBeVisible();
    await page.getByRole('link', { name: 'Ver comparación' }).first().click();
    await expect(page.getByRole('heading', { name: 'COMPARADOR DE ESTUDIOS' })).toBeVisible();
  });
});
