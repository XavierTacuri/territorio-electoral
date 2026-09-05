import { expect, test } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';
import { uniqueE2eValue } from './support/run-data';

type Campaign = { id: string; slug: string; canton_id?: number };
type Parish = { id: number; name: string };
type Activity = { id: string; status: string; approval_status: string; parish_id: number };

async function e2eCampaign(request: Parameters<typeof apiToken>[0], token: string) {
  const response = await request.get('/api/v1/campaigns?page_size=100', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBeTruthy();
  const campaigns = (await response.json()).items as Campaign[];
  const campaign = campaigns.find((item) => item.slug === 'gualaceo-e2e-2027') ?? campaigns.find((item) => item.slug === 'territorio-sintetico-e2e');
  expect(campaign).toBeTruthy();
  return campaign as Campaign;
}

async function prepareActivity(request: Parameters<typeof apiToken>[0], token: string, title: string) {
  const campaign = await e2eCampaign(request, token);
  const parishResponse = await request.get(`/api/v1/parishes${campaign.canton_id ? `?canton_id=${campaign.canton_id}` : ''}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(parishResponse.ok()).toBeTruthy();
  const parishes = (await parishResponse.json()) as Parish[];
  const parish = parishes.find((item) => item.name === 'Parroquia Alfa') ?? parishes[0];
  const response = await request.post(`/api/v1/campaigns/${campaign.id}/activities`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      activity_type_code: 'ASSEMBLY',
      title,
      description: 'Actividad sintética creada por la prueba de cierre.',
      activity_date: '2026-08-20',
      status: 'PLANNED',
      parish_id: parish.id,
    },
  });
  const responseBody = await response.text();
  expect(response.status(), responseBody).toBe(201);
  const activity = JSON.parse(responseBody) as Activity;
  expect(activity.approval_status).toBe('APPROVED');
  expect(activity.status).toBe('PLANNED');
  return { campaign, parish, activity };
}

test('CANDIDATE completa una actividad con necesidad detectada (el cierre ya no crea seguimientos)', async ({ page, request }) => {
  const managerToken = await apiToken(request, e2eUsers.manager);
  const { campaign, activity } = await prepareActivity(request, managerToken, uniqueE2eValue('[E2E] Actividad cierre completa'));
  await browserLogin(page, e2eUsers.candidate);
  await page.goto(`/app/campaigns/${campaign.id}/activities`);

  const row = page.getByRole('row').filter({ hasText: activity.id }).or(page.getByRole('row').filter({ hasText: uniqueE2eValue('[E2E] Actividad cierre completa') }));
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: 'Editar actividades' }).click();
  const editDialog = page.getByRole('dialog', { name: 'Editar actividad' });
  await editDialog.getByLabel('Estado').click();
  await page.getByRole('option', { name: 'Completada' }).click();
  await editDialog.getByRole('button', { name: 'Guardar' }).click();
  await expect(page.getByRole('heading', { name: 'Cerrar actividad' })).toBeVisible();
  const pendingDetail = await request.get(
    `/api/v1/campaigns/${campaign.id}/activities/${activity.id}`,
    { headers: { Authorization: `Bearer ${managerToken}` } },
  );
  expect((await pendingDetail.json()).status).toBe('PLANNED');
  await page.getByRole('button', { name: 'Completar actividad' }).click();
  await expect(page.getByText('Ingresa un resumen de la actividad.')).toBeVisible();

  const summary = 'Se realizó la actividad territorial programada y se registraron los principales resultados del encuentro.';
  await page.getByLabel('Resumen de la actividad').fill(summary);
  await page.getByLabel('Resultados u observaciones').fill('Observaciones sintéticas del encuentro E2E.');
  await expect(page.getByLabel('Prioridad')).toHaveCount(0);
  await expect(page.getByLabel('Fecha límite')).toHaveCount(0);
  await page.getByLabel('Necesidad detectada (opcional)').fill(uniqueE2eValue('[E2E] Necesidad de cierre'));
  await page.getByLabel('Descripción de la necesidad').fill('Necesidad sintética creada durante el cierre E2E.');
  await expect(page.getByLabel('Seguimiento de campaña (opcional)')).toHaveCount(0);
  const complete = page.getByRole('button', { name: 'Completar actividad' });
  await expect(complete).toBeEnabled();
  await complete.click();
  await expect(page.getByRole('heading', { name: 'Cerrar actividad' })).toBeHidden();
  await expect(page.getByRole('row').filter({ hasText: uniqueE2eValue('[E2E] Actividad cierre completa') })).toContainText('Completada');

  const detailResponse = await request.get(`/api/v1/campaigns/${campaign.id}/activities/${activity.id}`, { headers: { Authorization: `Bearer ${managerToken}` } });
  expect((await detailResponse.json()).status).toBe('COMPLETED');
  await page.getByRole('row').filter({ hasText: uniqueE2eValue('[E2E] Actividad cierre completa') }).getByRole('button', { name: 'Ver actividades' }).click();
  await expect(page.getByRole('heading', { name: 'Historial de actividad' })).toBeVisible();
  await expect(page.getByText(summary)).toBeVisible();
  await expect(page.getByText('Observaciones sintéticas del encuentro E2E.')).toBeVisible();
  await expect(page.getByText(uniqueE2eValue('[E2E] Necesidad de cierre'))).toBeVisible();
  await expect(page.getByText(/Completado por:/)).toBeVisible();
  // Seguimientos/Commitments es dominio legacy retirado de la experiencia
  // productiva: el detalle de actividad ya no expone esa sección, ni siquiera
  // en modo solo lectura.
  await expect(page.getByRole('heading', { name: 'Seguimientos generados' })).toHaveCount(0);
});

test('CANDIDATE suspende con motivo y no expone el cierre estructurado', async ({ page, request }) => {
  const managerToken = await apiToken(request, e2eUsers.manager);
  const { campaign, activity } = await prepareActivity(request, managerToken, uniqueE2eValue('[E2E] Actividad cancelada'));
  await browserLogin(page, e2eUsers.candidate);
  await page.goto(`/app/campaigns/${campaign.id}/activities`);
  const row = page.getByRole('row').filter({ hasText: uniqueE2eValue('[E2E] Actividad cancelada') });
  await row.getByRole('button', { name: 'Editar actividades' }).click();
  const editDialog = page.getByRole('dialog', { name: 'Editar actividad' });
  await editDialog.getByLabel('Estado').click();
  await page.getByRole('option', { name: 'Suspendida' }).click();
  await editDialog.getByRole('button', { name: 'Guardar' }).click();
  await expect(page.getByRole('heading', { name: 'Suspender actividad' })).toBeVisible();
  const cancel = page.getByRole('button', { name: 'Suspender actividad' });
  await cancel.click();
  await expect(page.getByText('Ingresa un motivo de suspensión.')).toBeVisible();
  await page.getByLabel('Motivo de suspensión').fill('Actividad suspendida durante prueba E2E.');
  await cancel.click();
  await expect(page.getByRole('heading', { name: 'Suspender actividad' })).toBeHidden();
  await expect(page.getByRole('row').filter({ hasText: uniqueE2eValue('[E2E] Actividad cancelada') })).toContainText('Suspendida');
  const detailResponse = await request.get(`/api/v1/campaigns/${campaign.id}/activities/${activity.id}`, { headers: { Authorization: `Bearer ${managerToken}` } });
  expect((await detailResponse.json()).status).toBe('SUSPENDED');
});
