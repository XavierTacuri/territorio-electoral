import { test, expect, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';
import { e2eRunId, uniqueE2eValue } from './support/run-data';

// Covers the new Candidate/Manager alerts contract (§23-30): only two alert
// families are ever visible to these roles — activities pending approval and
// newly published surveys/studies — enforced by the backend, not just hidden
// in the UI. See test_candidate_manager_alerts.py for the backend-level
// equivalent of this contract.

async function gualaceoCampaign(request: APIRequestContext, headers: Record<string, string>) {
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; slug: string; canton_id: number; office_type: string }[];
  const campaign = campaigns.find((item) => item.slug === 'gualaceo-e2e-2027');
  if (!campaign) throw new Error('El fixture E2E requiere gualaceo-e2e-2027');
  return campaign;
}

test('Candidate/Manager solo ven aprobaciones y encuestas publicadas en el Centro de alertas', async ({
  page,
  request,
}) => {
  test.setTimeout(180000);
  const runId = e2eRunId;
  const adminToken = await apiToken(request);
  const adminHeaders = { Authorization: 'Bearer ' + adminToken };
  const campaign = await gualaceoCampaign(request, adminHeaders);

  const analystToken = await apiToken(request, e2eUsers.analyst);
  const analystHeaders = { Authorization: 'Bearer ' + analystToken };
  const studyCode = uniqueE2eValue('CMA_E2E_STUDY').toUpperCase().replace(/-/g, '_');
  const study = await (
    await request.post(`/api/v1/campaigns/${campaign.id}/survey-studies`, {
      headers: analystHeaders,
      data: {
        code: studyCode,
        name: `Estudio sintético ${runId}`,
        study_type: 'GENERAL_SURVEY',
        fieldwork_start_date: '2027-01-01',
        fieldwork_end_date: '2027-01-03',
        publication_date: '2027-01-04',
        geography_level: 'CANTON',
        sample_size_total: 400,
        universe_description: 'Universo cantonal sintético',
        sampling_method: 'Aleatorio simple',
        collection_method: 'Telefónica',
      },
    })
  ).json();

  const territory = await (
    await request.post(`/api/v1/survey-studies/${study.id}/territories`, {
      headers: analystHeaders,
      data: { sample_size: 400 },
    })
  ).json();
  const optionA = await (
    await request.post(`/api/v1/survey-studies/${study.id}/options`, {
      headers: analystHeaders,
      data: { code: 'OPCION_A', label: 'Opción sintética A' },
    })
  ).json();
  const optionB = await (
    await request.post(`/api/v1/survey-studies/${study.id}/options`, {
      headers: analystHeaders,
      data: { code: 'OPCION_B', label: 'Opción sintética B' },
    })
  ).json();
  await request.put(`/api/v1/survey-studies/${study.id}/results`, {
    headers: analystHeaders,
    data: [
      { study_territory_id: territory.id, option_id: optionA.id, percentage: 0.55 },
      { study_territory_id: territory.id, option_id: optionB.id, percentage: 0.3 },
    ],
  });
  const published = await request.post(`/api/v1/survey-studies/${study.id}/publish`, {
    headers: analystHeaders,
  });
  expect(published.status()).toBe(200);

  const evaluated = await request.post(`/api/v1/campaigns/${campaign.id}/alerts/evaluate`, {
    headers: adminHeaders,
    data: {
      rule_codes: ['SURVEY_STUDY_PUBLISHED', 'CAMPAIGN_WITHOUT_ACTIVE_ROLL'],
      as_of_date: '2027-01-04',
    },
  });
  expect(evaluated.status()).toBe(200);

  await test.step('CANDIDATE ve solo dos categorías y la nueva encuesta publicada, nunca la alerta técnica', async () => {
    await browserLogin(page, e2eUsers.candidate);
    await page.goto(`/app/campaigns/${campaign.id}/alerts`);
    await expect(page.getByRole('combobox', { name: /Categoría/ })).toBeVisible();
    await expect(page.getByRole('combobox', { name: /Módulo/ })).toHaveCount(0);
    await page.getByRole('combobox', { name: /Categoría/ }).click();
    await expect(page.getByRole('option', { name: 'Todas' })).toBeVisible();
    await expect(page.getByRole('option', { name: 'Aprobaciones' })).toBeVisible();
    await expect(page.getByRole('option', { name: 'Encuestas y estudios' })).toBeVisible();
    await page.getByRole('option', { name: 'Encuestas y estudios' }).click();
    await expect(page.getByText('Nueva encuesta o estudio publicado').first()).toBeVisible();
    await expect(page.getByText('Campaña sin padrón vigente')).toHaveCount(0);
    await page.getByRole('combobox', { name: /Categoría/ }).click();
    await page.getByRole('option', { name: 'Todas' }).click();
    await expect(page.getByText('Campaña sin padrón vigente')).toHaveCount(0);
  });
});
