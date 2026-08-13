import { expect, test, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin } from './support/auth';

async function fixture(request: APIRequestContext) {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; name: string }[];
  for (const campaign of campaigns) {
    const response = await request.get(
      `/api/v1/campaigns/${campaign.id}/survey-studies?page=1&page_size=100`,
      { headers },
    );
    if (response.ok()) {
      const studies = (await response.json()).items as {
        id: string;
        code: string;
        name: string;
        study_type: string;
        status: string;
      }[];
      if (studies.some((s) => s.code === 'STUDY_E2E')) return { campaign, studies, headers };
    }
  }
  throw new Error('El seed no contiene STUDY_E2E');
}

test('cierre portable de encuestas y estudios territoriales', async ({ page, request }) => {
  test.setTimeout(180000);
  const { campaign, studies } = await fixture(request);
  const published = studies.find((s) => s.code === 'STUDY_E2E')!;
  const tracking = studies.find((s) => s.study_type === 'TRACKING_POLL')!;
  const exit = studies.find((s) => s.study_type === 'EXIT_POLL')!;
  await browserLogin(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/app/campaigns/${campaign.id}/dashboard`);
  await page.getByRole('link', { name: 'Encuestas', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/campaigns/${campaign.id}/surveys$`));
  await expect(page.getByRole('heading', { name: 'ENCUESTAS Y ESTUDIOS' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Nuevo estudio' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Importar resultados' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Gestionar cuestionarios' })).toBeVisible();
  await expect(page.getByText(published.name)).toBeVisible();
  await expect(page.getByText(tracking.name)).toBeVisible();
  await expect(page.getByText(exit.name)).toBeVisible();
  await page.screenshot({ path: '../quality-artifacts/surveys-list-desktop.png', fullPage: true });
  await page.goto(`/app/campaigns/${campaign.id}/survey-studies/${published.id}`);
  await expect(page.getByText('Ficha metodológica')).not.toBeVisible();
  await page.getByRole('tab', { name: 'Metodología' }).click();
  await expect(page.getByRole('heading', { name: 'Ficha metodológica' })).toBeVisible();
  await page.getByRole('tab', { name: 'Resultados' }).click();
  await expect(page.getByText('Opción Alfa').first()).toBeVisible();
  await expect(page.getByText(/Porcentaje observado en el estudio/)).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Mapa neutral de resultados del estudio' }),
  ).toBeVisible();
  await page.screenshot({ path: '../quality-artifacts/survey-study-desktop.png', fullPage: true });
  await page.getByRole('tab', { name: 'Territorio' }).click();
  await expect(page.getByText('Parroquia Alfa')).toBeVisible();
  await page.screenshot({
    path: '../quality-artifacts/survey-territory-desktop.png',
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: '../quality-artifacts/survey-study-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(
    `/app/campaigns/${campaign.id}/survey-studies/compare?ids=${published.id},${tracking.id}`,
  );
  await expect(page.getByRole('heading', { name: 'COMPARADOR DE ESTUDIOS' })).toBeVisible();
  await expect(page.getByText(published.name)).toBeVisible();
  await page.goto(`/app/campaigns/${campaign.id}/survey-studies/${exit.id}`);
  await expect(page.getByText('NO OFICIAL CNE')).toBeVisible();
  await expect(page.getByText(/No corresponde al escrutinio oficial/)).toBeVisible();
  for (const label of ['PDF', 'XLSX']) {
    const response = page.waitForResponse(
      (r) => r.url().includes('/reports/generate') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: label, exact: true }).click();
    expect((await response).status()).toBeLessThan(400);
  }
  await page.goto(`/app/campaigns/${campaign.id}/territories`);
  const selector = page.getByLabel('Seleccionar parroquia');
  await selector.click();
  await page.getByRole('option', { name: /Parroquia Alfa/ }).click();
  await expect(page.getByRole('heading', { name: 'ENCUESTAS Y ESTUDIOS' })).toBeVisible();
  await expect(page.getByText(published.name)).toBeVisible();
  await page.goto(`/app/campaigns/${campaign.id}/dashboard`);
  await expect(page.getByRole('heading', { name: 'ESTUDIOS RECIENTES' })).toBeVisible();
  await expect(page.getByText(exit.name)).toBeVisible();
});

test('importa CSV agregado después de validar sin UUID manual', async ({ page, request }) => {
  test.setTimeout(120000);
  const { campaign } = await fixture(request);
  await browserLogin(page);
  await page.goto(`/app/campaigns/${campaign.id}/survey-studies/import`);
  const csv =
    'study_code,territory_level,parish_dpa,option_code,option_label,option_type,response_count,percentage\nIMPORT_E2E,PARISH,999901,ALFA,Opción Alfa,CANDIDATE,40,0.40\nIMPORT_E2E,PARISH,999901,BETA,Opción Beta,CANDIDATE,35,0.35\nIMPORT_E2E,PARISH,999901,UNDECIDED,Indecisos,UNDECIDED,25,0.25\n';
  await page
    .locator('input[type=file]')
    .setInputFiles({ name: 'survey-results.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await page.getByRole('button', { name: '1. Validar' }).click();
  await expect(page.getByText('Resultado: VALIDATED')).toBeVisible();
  await expect(page.getByText('3', { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: '../quality-artifacts/survey-import-desktop.png', fullPage: true });
  await page.getByRole('button', { name: '2. Ejecutar' }).click();
  await expect(page.getByText('Resultado: COMPLETED')).toBeVisible();
});

test('responsive sin overflow global en lista detalle comparador e importación', async ({
  page,
  request,
}) => {
  const { campaign, studies } = await fixture(request);
  await browserLogin(page);
  const routes = [
    `/app/campaigns/${campaign.id}/surveys`,
    `/app/campaigns/${campaign.id}/survey-studies/${studies[0].id}`,
    `/app/campaigns/${campaign.id}/survey-studies/compare?ids=${studies[0].id},${studies[1].id}`,
    `/app/campaigns/${campaign.id}/survey-studies/import`,
  ];
  for (const size of [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(size);
    for (const route of routes) {
      await page.goto(route);
      await expect(page.locator('main')).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
        `${route} ${size.width}`,
      ).toBe(true);
    }
  }
});
