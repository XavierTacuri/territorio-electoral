import { expect, test } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

test('workflow V2.4 real y RBAC parroquial', async ({ page, request }) => {
  const suffix = Date.now().toString();
  const managerToken = await apiToken(request, e2eUsers.manager);
  const delegateToken = await apiToken(request, e2eUsers.delegateA);
  const campaigns = await (
    await request.get('/api/v1/campaigns?page_size=100', {
      headers: { Authorization: `Bearer ${managerToken}` },
    })
  ).json();
  const campaign = campaigns.items.find(
    (x: { slug: string }) => x.slug === 'territorio-sintetico-e2e',
  );
  expect(campaign).toBeTruthy();
  const parishes = await (
    await request.get('/api/v1/parishes', { headers: { Authorization: `Bearer ${delegateToken}` } })
  ).json();
  const allParishes = await (
    await request.get('/api/v1/parishes', {
      headers: { Authorization: `Bearer ${managerToken}` },
    })
  ).json();
  const parishA = parishes.find((x: { name: string }) => x.name === 'Parroquia Alfa');
  const parishB = allParishes.find((x: { name: string }) => x.name === 'Parroquia Beta');
  const create = await request.post(`/api/v1/campaigns/${campaign.id}/activities`, {
    headers: { Authorization: `Bearer ${delegateToken}` },
    data: {
      activity_type_code: 'ASSEMBLY',
      title: `Flujo aprobación V2.4 ${suffix}`,
      description: 'Actividad sintética portable',
      activity_date: '2026-08-20',
      status: 'PLANNED',
      parish_id: parishA.id,
    },
  });
  expect(create.status()).toBe(201);
  let activity = await create.json();
  expect(activity.approval_status).toBe('DRAFT');
  expect(
    (
      await request.post(`/api/v1/campaigns/${campaign.id}/activities`, {
        headers: { Authorization: `Bearer ${delegateToken}` },
        data: {
          activity_type_code: 'ASSEMBLY',
          title: 'Fuera de territorio',
          activity_date: '2026-08-20',
          status: 'PLANNED',
          parish_id: parishB.id,
        },
      })
    ).status(),
  ).toBe(403);
  activity = await (
    await request.post(
      `/api/v1/campaigns/${campaign.id}/activities/${activity.id}/submit-for-approval`,
      { headers: { Authorization: `Bearer ${delegateToken}` } },
    )
  ).json();
  expect(activity.approval_status).toBe('PENDING_APPROVAL');
  expect(
    (
      await request.post(`/api/v1/campaigns/${campaign.id}/activities/${activity.id}/approve`, {
        headers: { Authorization: `Bearer ${delegateToken}` },
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await request.post(`/api/v1/campaigns/${campaign.id}/activities/${activity.id}/reject`, {
        headers: { Authorization: `Bearer ${managerToken}` },
        data: { rejection_reason: '' },
      })
    ).status(),
  ).toBe(422);
  activity = await (
    await request.post(`/api/v1/campaigns/${campaign.id}/activities/${activity.id}/reject`, {
      headers: { Authorization: `Bearer ${managerToken}` },
      data: { rejection_reason: 'Conflicto de horario sintético' },
    })
  ).json();
  expect(activity.approval_status).toBe('REJECTED');
  await request.patch(`/api/v1/campaigns/${campaign.id}/activities/${activity.id}`, {
    headers: { Authorization: `Bearer ${delegateToken}` },
    data: { title: `Flujo aprobación V2.4 corregido ${suffix}` },
  });
  await request.post(
    `/api/v1/campaigns/${campaign.id}/activities/${activity.id}/submit-for-approval`,
    { headers: { Authorization: `Bearer ${delegateToken}` } },
  );
  activity = await (
    await request.post(`/api/v1/campaigns/${campaign.id}/activities/${activity.id}/approve`, {
      headers: { Authorization: `Bearer ${managerToken}` },
    })
  ).json();
  expect(activity.approval_status).toBe('APPROVED');
  expect(activity.status).toBe('PLANNED');
  const need = await (
    await request.post(`/api/v1/campaigns/${campaign.id}/activities/${activity.id}/needs`, {
      headers: { Authorization: `Bearer ${delegateToken}` },
      data: {
        need_category_code: 'ROADS',
        title: `Necesidad flujo V2.4 ${suffix}`,
        description: 'Necesidad sintética',
        priority: 'HIGH',
        urgency: 'HIGH',
        status: 'REPORTED',
        source_type: 'CAMPAIGN_ACTIVITY',
        reported_date: '2026-08-20',
        scope: 'PARISH',
      },
    })
  ).json();
  expect(need.activity_id).toBe(activity.id);
  await request.post(`/api/v1/campaigns/${campaign.id}/needs/${need.id}/start-review`, {
    headers: { Authorization: `Bearer ${delegateToken}` },
  });
  expect(
    (
      await request.post(`/api/v1/campaigns/${campaign.id}/needs/${need.id}/validate`, {
        headers: { Authorization: `Bearer ${delegateToken}` },
        data: { validation_notes: 'x' },
      })
    ).status(),
  ).toBe(403);
  await request.post(`/api/v1/campaigns/${campaign.id}/needs/${need.id}/validate`, {
    headers: { Authorization: `Bearer ${managerToken}` },
    data: { validation_notes: 'Validación E2E' },
  });
  const commitment = await (
    await request.post(`/api/v1/campaigns/${campaign.id}/commitments`, {
      headers: { Authorization: `Bearer ${managerToken}` },
      data: {
        need_id: need.id,
        activity_id: activity.id,
        title: `Compromiso flujo V2.4 ${suffix}`,
        priority: 'HIGH',
        status: 'PENDING',
        parish_id: parishA.id,
      },
    })
  ).json();
  expect(commitment.need_id).toBe(need.id);
  await browserLogin(page, e2eUsers.manager);
  await page.goto(`/app/campaigns/${campaign.id}/operations`);
  await expect(page.getByRole('heading', { name: 'Operación territorial' })).toBeVisible();
  await page.goto(`/app/campaigns/${campaign.id}/approvals`);
  await expect(
    page.getByRole('heading', { name: 'Actividades pendientes de aprobación' }),
  ).toBeVisible();
  await page.goto(`/app/campaigns/${campaign.id}/needs/${need.id}`);
  await expect(page.getByText(`Compromiso flujo V2.4 ${suffix}`)).toBeVisible();
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto(`/app/campaigns/${campaign.id}/operations`);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    ).toBe(true);
  }
});
