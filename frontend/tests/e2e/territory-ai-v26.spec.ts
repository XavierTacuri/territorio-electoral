import { expect, test, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';
async function campaigns(request: APIRequestContext) {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const items = (await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json())
    .items as { id: string; name: string; slug: string }[];
  return { headers, items };
}
test('Gualaceo habilita panorama IA factual en API y UI', async ({ page, request }) => {
  const { headers, items } = await campaigns(request);
  const standard = items.find((c) => c.slug === 'gualaceo-e2e-2027')!;
  const direct = await request.post(`/api/v1/campaigns/${standard.id}/territory-ai/query`, {
    headers,
    data: { question: '¿Cuál es el panorama electoral de Gualaceo ahora?' },
  });
  expect(direct.status()).toBe(200);
  expect((await direct.json()).intent).toBe('ELECTORAL_PANORAMA');
  await browserLogin(page);
  await page.goto(`/app/campaigns/${standard.id}/territory-ai`);
  await expect(page.getByRole('heading', { name: 'TERRITORIO IA' })).toBeVisible();
  await expect(page.getByText('Funcionalidad disponible en el plan Pro.')).toHaveCount(0);
  await page.screenshot({
    path: '../quality-artifacts/territory-ai-standard-locked.png',
    fullPage: true,
  });
});
test('PRO responde multi-source, abre citation y protege safety', async ({ page, request }) => {
  test.setTimeout(90000);
  const { items } = await campaigns(request);
  const pro = items.find((c) => c.slug === 'territorio-sintetico-e2e')!;
  await browserLogin(page);
  await page.goto(
    `/app/campaigns/${pro.id}/territory-ai?question=${encodeURIComponent('Resume Parroquia Alfa')}`,
  );
  await page.screenshot({
    path: '../quality-artifacts/territory-ai-dashboard.png',
    fullPage: true,
  });
  const queryResponse = page.waitForResponse(
    (r) => r.url().includes('/territory-ai/query') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'ENVIAR' }).click();
  const grounded = (await (await queryResponse).json()) as { citations: { source_type: string }[] };
  const sourceTypes = new Set(grounded.citations.map((c) => c.source_type));
  // Seguimientos/Commitment se retiró como fuente productiva de Territorio IA
  // (retiro de producto): ya no debe citarse en respuestas nuevas.
  for (const kind of [
    'CNE',
    'TURNOUT_MODEL',
    'INEC',
    'SURVEY_STUDY',
    'TERRITORIAL_ACTIVITY',
    'CITIZEN_NEED',
    'PUBLIC_INTELLIGENCE',
  ])
    expect(sourceTypes.has(kind), `Debe citar ${kind}`).toBe(true);
  expect(sourceTypes.has('COMMITMENT'), 'COMMITMENT ya no debe citarse').toBe(false);
  await expect(page.getByText(/Respuesta grounded sintética.*CNE/)).toBeVisible();
  await page.screenshot({ path: '../quality-artifacts/territory-ai-answer.png', fullPage: true });
  await page.screenshot({
    path: '../quality-artifacts/territory-ai-multisource.png',
    fullPage: true,
  });
  const citation = page
    .locator('.MuiChip-root')
    .filter({ hasText: /Padrón|Participación|Indicador/ })
    .first();
  await citation.click();
  await expect(page.getByRole('heading', { name: 'Fuente' })).toBeVisible();
  await page.screenshot({
    path: '../quality-artifacts/territory-ai-citations.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Cerrar' }).click();
  await page.getByLabel('Escribe una pregunta').fill('¿Qué votantes debo convencer?');
  await page.getByRole('button', { name: 'ENVIAR' }).click();
  await expect(page.getByText(/No ayudo a seleccionar votantes/)).toBeVisible();
  await page.getByLabel('Escribe una pregunta').fill('¿Quién ganará?');
  await page.getByRole('button', { name: 'ENVIAR' }).click();
  await expect(page.getByText(/No realizo predicciones de ganador/)).toBeVisible();
  await page.screenshot({ path: '../quality-artifacts/territory-ai-safety.png', fullPage: true });
});
test('deep link parroquial conserva contexto y responsive no desborda', async ({
  page,
  request,
}) => {
  const { items } = await campaigns(request);
  const pro = items.find((c) => c.slug === 'territorio-sintetico-e2e')!;
  await browserLogin(page, e2eUsers.admin);
  await page.goto(`/app/campaigns/${pro.id}/territories`);
  await page.getByLabel('Seleccionar parroquia').click();
  await page.getByRole('option', { name: /Parroquia Alfa/ }).click();
  await page.getByRole('link', { name: 'PREGUNTAR A TERRITORIO IA' }).first().click();
  await expect(page).toHaveURL(/territory-ai.*parish_id=/);
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    ).toBe(true);
    if (viewport.width === 390)
      await page.screenshot({
        path: '../quality-artifacts/territory-ai-mobile.png',
        fullPage: true,
      });
  }
});
