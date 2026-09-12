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
  const measurement = studies.find((s) => s.code === 'MEASUREMENT_E2E')!;
  const exit = studies.find((s) => s.study_type === 'CNE_EXIT_POLL')!;
  await browserLogin(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/app/campaigns/${campaign.id}/dashboard`);
  await page.getByRole('link', { name: 'Encuestas y estudios', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/campaigns/${campaign.id}/surveys$`));
  await expect(page.getByRole('heading', { name: 'Encuestas y estudios' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'NUEVA ENCUESTA' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'IMPORTAR CSV' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'REGISTRAR EXIT POLL' })).toBeVisible();
  await expect(page.getByText(published.name)).toBeVisible();
  await expect(page.getByText(measurement.name)).toBeVisible();
  await expect(page.getByText(exit.name)).toBeVisible();
  await page.screenshot({ path: '../quality-artifacts/surveys-list-desktop.png', fullPage: true });
  await page.goto(`/app/campaigns/${campaign.id}/survey-studies/${published.id}`);
  await expect(page.getByRole('heading', { name: 'Metodología' })).toBeVisible();
  await expect(page.getByText('Opción Alfa').first()).toBeVisible();
  await expect(page.getByText(/porcentajes describen exclusivamente/i)).toBeVisible();
  await page.screenshot({ path: '../quality-artifacts/survey-study-desktop.png', fullPage: true });
  await expect(page.getByText(/Parroquia: Parroquia Alfa/).first()).toBeVisible();
  await page.screenshot({
    path: '../quality-artifacts/survey-territory-desktop.png',
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBe(true);
  await page.screenshot({ path: '../quality-artifacts/survey-study-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(
    `/app/campaigns/${campaign.id}/survey-studies/compare?ids=${published.id},${measurement.id}`,
  );
  await expect(page.getByRole('heading', { name: 'COMPARADOR DE ESTUDIOS' })).toBeVisible();
  await expect(page.getByText(published.name)).toBeVisible();
  await page.goto(`/app/campaigns/${campaign.id}/survey-studies/${exit.id}`);
  await expect(page.getByText(/no sustituye los resultados oficiales/i)).toBeVisible();
  await page.goto(`/app/campaigns/${campaign.id}/territories`);
  const selector = page.getByLabel('Seleccionar parroquia');
  await selector.click();
  await page.getByRole('option', { name: /Parroquia Alfa/ }).click();
  await expect(page.getByRole('heading', { name: 'ENCUESTAS Y ESTUDIOS' })).toBeVisible();
  await expect(page.getByText(published.name).first()).toBeVisible();
  await page.goto(`/app/campaigns/${campaign.id}/dashboard`);
  await expect(page.getByRole('heading', { name: 'ENCUESTAS Y ESTUDIOS' })).toBeVisible();
  await expect(page.getByText(exit.name.replace(/^\[DEMO\]\s*/, '')).first()).toBeVisible();
  await expect(page.getByText('Datos simulados para demostración.')).toBeVisible();
});

test('importa CSV agregado después de validar sin UUID manual', async ({ page, request }) => {
  test.setTimeout(120000);
  const { campaign } = await fixture(request);
  await browserLogin(page);
  await page.goto(`/app/campaigns/${campaign.id}/survey-studies/import`);
  const csv =
    'study_code,question_code,question_text,question_type,option_code,option_label,percentage,base_n,parish_dpa\nIMPORT_E2E,Q1,Intención agregada,VOTE_INTENTION,ALFA,Opción Alfa,0.40,100,999901\nIMPORT_E2E,Q1,Intención agregada,VOTE_INTENTION,BETA,Opción Beta,0.35,100,999901\nIMPORT_E2E,Q1,Intención agregada,VOTE_INTENTION,UNDECIDED,Indecisos,0.25,100,999901\n';
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

test('candidate_demo consulta publicada sin controles de escritura', async ({ page, request }) => {
  const token = await apiToken(request, 'candidate_demo');
  const campaigns = (
    await (
      await request.get('/api/v1/campaigns?page_size=100', {
        headers: { Authorization: `Bearer ${token}` },
      })
    ).json()
  ).items as { id: string; slug: string }[];
  const campaign = campaigns.find((item) => item.slug === 'gualaceo2026')!;
  await browserLogin(page, 'candidate_demo');
  await page.goto(`/app/campaigns/${campaign.id}/surveys`);
  await expect(page.getByText('[DEMO] Encuesta general Gualaceo - Agosto 2026')).toBeVisible();
  await expect(page.getByRole('button', { name: 'NUEVA ENCUESTA' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'IMPORTAR CSV' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'REGISTRAR EXIT POLL' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Ver resultados' }).first().click();
  await expect(page.getByRole('heading', { name: 'Metodología' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'PUBLICAR' })).toHaveCount(0);
  await expect(page.getByText(/Datos simulados para demostración/).first()).toBeVisible();
});
