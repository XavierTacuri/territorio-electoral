import { expect, test } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

async function gotoField(page: import('@playwright/test').Page, campaignId: string) {
  await page.goto(`/app/campaigns/${campaignId}/field`);
  await expect(page.getByRole('heading', { name: 'Operación de campo' })).toBeVisible();
  // "En línea" reflects navigator.onLine, which is already true the instant
  // the page loads — it says nothing about whether useFieldContext's online
  // fetch has actually finished writing campaign/assignments to IndexedDB
  // yet. Wait for the one thing that's only rendered after that write
  // completes: the coordinator's assigned-territory chip.
  await expect(page.getByText('Gualaceo', { exact: true })).toBeVisible({ timeout: 15000 });
}

async function resolveCampaign(request: import('@playwright/test').APIRequestContext) {
  const token = await apiToken(request, e2eUsers.coordinator);
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; slug: string }[];
  return campaigns.find((item) => item.slug === 'gualaceo-e2e-2027')!;
}

// This spec shares "Gualaceo E2E 2027" with several other specs (operations,
// phase10) whose selectors assume a stable activity/need list. Deactivate
// what a synced test created so it never lingers as extra rows for later
// specs in the same suite run.
async function cleanupByTitle(
  request: import('@playwright/test').APIRequestContext,
  campaignId: string,
  resource: 'activities' | 'needs',
  title: string,
) {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const items = (
    await (await request.get(`/api/v1/campaigns/${campaignId}/${resource}?page_size=100`, { headers })).json()
  ).items as { id: string; title: string }[];
  for (const item of items.filter((i) => i.title === title)) {
    await request.delete(`/api/v1/campaigns/${campaignId}/${resource}/${item.id}`, { headers });
  }
}

test('coordinador registra una necesidad sin conexión y sincroniza sin duplicar', async ({
  page,
  request,
  context,
}) => {
  test.setTimeout(120000);
  const campaign = await resolveCampaign(request);
  const title = `Necesidad offline ${Date.now()}`;

  await browserLogin(page, e2eUsers.coordinator);
  await gotoField(page, campaign.id);

  await context.setOffline(true);
  await expect(page.getByRole('status').getByText('Sin conexión')).toBeVisible();

  // In-app (client-side) navigation — no full reload — matching how a real
  // installed PWA session moves between screens while offline.
  await page.getByRole('button', { name: 'Registrar necesidad' }).click();
  await expect(page.getByRole('heading', { name: 'Registrar necesidad' })).toBeVisible();
  await page.getByLabel('Categoría').click();
  await page.getByRole('option').first().click();
  await page.getByLabel('Título').fill(title);
  await page.getByLabel('Descripción / observaciones').fill('Registrado en campo sin conexión.');
  await expect(page.getByText('Guardado en el dispositivo')).toBeVisible({ timeout: 10000 });

  // Now exercise the actual reload-while-offline survival requirement.
  await page.reload();
  await expect(page.getByLabel('Título')).toHaveValue(title);
  await expect(page.getByRole('status').getByText('Sin conexión')).toBeVisible();

  await page.getByRole('button', { name: 'Guardar y enviar a sincronización' }).click();
  await expect(page).toHaveURL(new RegExp(`/field/drafts$`));
  await expect(page.getByText(title)).toBeVisible();
  await expect(page.getByText(/· Pendiente/)).toBeVisible();

  await context.setOffline(false);
  await expect(page.getByText('En línea')).toBeVisible();
  await page.getByRole('button', { name: 'Sincronizar ahora' }).click();
  await expect(page.getByText(/registro.*sincronizado/i)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/· Sincronizado/)).toBeVisible();

  // Double sync must never duplicate: with nothing left pending the button
  // itself becomes disabled, so a second press cannot resend anything.
  await expect(page.getByRole('button', { name: 'Sincronizar ahora' })).toBeDisabled();

  const token = await apiToken(request, e2eUsers.coordinator);
  const headers = { Authorization: `Bearer ${token}` };
  const needs = (
    await (await request.get(`/api/v1/campaigns/${campaign.id}/needs?page_size=100`, { headers })).json()
  ).items as { title: string }[];
  expect(needs.filter((n) => n.title === title)).toHaveLength(1);

  await cleanupByTitle(request, campaign.id, 'needs', title);
});

test('coordinador registra una actividad sin conexión, sincroniza y queda PENDING_APPROVAL', async ({
  page,
  request,
  context,
}) => {
  test.setTimeout(120000);
  const campaign = await resolveCampaign(request);
  const title = `Actividad offline ${Date.now()}`;

  await browserLogin(page, e2eUsers.coordinator);
  await gotoField(page, campaign.id);

  await context.setOffline(true);
  await page.getByRole('button', { name: 'Registrar actividad' }).click();
  await expect(page.getByRole('heading', { name: 'Registrar actividad' })).toBeVisible();
  await page.getByLabel('Tipo de actividad').click();
  await page.getByRole('option').first().click();
  await page.getByLabel('Nombre de la actividad').fill(title);
  await expect(page.getByText('Guardado en el dispositivo')).toBeVisible({ timeout: 10000 });

  await page.reload();
  await expect(page.getByLabel('Nombre de la actividad')).toHaveValue(title);

  await page.getByRole('button', { name: 'Guardar y enviar a sincronización' }).click();
  await expect(page).toHaveURL(new RegExp(`/field/drafts$`));

  await context.setOffline(false);
  await expect(page.getByText('En línea')).toBeVisible();
  await page.getByRole('button', { name: 'Sincronizar ahora' }).click();
  await expect(page.getByText(/registro.*sincronizado/i)).toBeVisible({ timeout: 15000 });

  const token = await apiToken(request, e2eUsers.coordinator);
  const headers = { Authorization: `Bearer ${token}` };
  const activities = (
    await (await request.get(`/api/v1/campaigns/${campaign.id}/activities?page_size=100`, { headers })).json()
  ).items as { title: string; approval_status: string }[];
  const created = activities.filter((a) => a.title === title);
  expect(created).toHaveLength(1);
  expect(created[0].approval_status).toBe('PENDING_APPROVAL');

  await cleanupByTitle(request, campaign.id, 'activities', title);
});

test('el backend rechaza un client_generated_id offline reenviado por un coordinador sin asignación', async ({
  request,
}) => {
  // delegate_e2e_a is a real CampaignUser of this campaign (TERRITORIAL_COORDINATOR)
  // but has no TerritorialAssignment inside it — every parish is out of scope,
  // which is exactly the "manipulated request from an unassigned device" case.
  const campaign = await resolveCampaign(request);
  const adminToken = await apiToken(request);
  const parishes = (
    await (
      await request.get(`/api/v1/campaigns/${campaign.id}/current-election/analysis`, {
        headers: { Authorization: `Bearer ${adminToken}` },
      })
    ).json()
  ).parishes as { parish_id: number; name: string }[];
  const target = parishes.find((p) => p.name === 'Gualaceo')!;

  const token = await apiToken(request, e2eUsers.delegateA);
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  const response = await request.post(`/api/v1/campaigns/${campaign.id}/needs`, {
    headers,
    data: {
      need_category_code: 'ROADS',
      title: 'Intento fuera de escenario',
      parish_id: target.parish_id,
      client_generated_id: '11111111-1111-1111-1111-111111111111',
    },
  });
  expect(response.status()).toBe(403);

  // Retrying the exact same offline payload must still be rejected, not
  // silently accepted the second time.
  const retry = await request.post(`/api/v1/campaigns/${campaign.id}/needs`, {
    headers,
    data: {
      need_category_code: 'ROADS',
      title: 'Intento fuera de escenario',
      parish_id: target.parish_id,
      client_generated_id: '11111111-1111-1111-1111-111111111111',
    },
  });
  expect(retry.status()).toBe(403);
});

test('los borradores de un coordinador no son visibles para otro usuario en el mismo dispositivo', async ({
  page,
  request,
}) => {
  test.setTimeout(60000);
  const campaign = await resolveCampaign(request);

  await browserLogin(page, e2eUsers.coordinator);
  await gotoField(page, campaign.id);
  await page.getByRole('button', { name: 'Registrar necesidad' }).click();
  await page.getByLabel('Categoría').click();
  await page.getByRole('option').first().click();
  const title = `Aislamiento usuario ${Date.now()}`;
  await page.getByLabel('Título').fill(title);
  await expect(page.getByText('Guardado en el dispositivo')).toBeVisible({ timeout: 10000 });
  await page.getByRole('button', { name: 'Guardar y enviar a sincronización' }).click();
  await expect(page.getByText(title)).toBeVisible();

  // The pending item is still queued: logging out must warn before discarding
  // the session, and only actually log out once confirmed (section 38).
  await page.getByRole('button', { name: 'Cerrar sesión' }).first().click();
  await expect(page.getByRole('heading', { name: 'Registros pendientes de sincronizar' })).toBeVisible();
  await page.getByRole('button', { name: 'Cerrar sesión de todas formas' }).click();
  await expect(page).toHaveURL(/\/login/);

  await browserLogin(page, e2eUsers.delegateA);
  await page.goto(`/app/campaigns/${campaign.id}/field/drafts`);
  await expect(page.getByText(title)).toHaveCount(0);
});

test('Territorio IA muestra el aviso de conexión requerida cuando Field está sin conexión', async ({
  page,
  request,
  context,
}) => {
  const campaign = await resolveCampaign(request);
  await browserLogin(page, e2eUsers.coordinator);
  await gotoField(page, campaign.id);
  await context.setOffline(true);
  await expect(page.getByRole('status').getByText('Sin conexión')).toBeVisible();
  await page.getByRole('button', { name: 'Territorio IA' }).click();
  await expect(page.getByText('Territorio IA necesita conexión a internet.')).toBeVisible();
  await expect(page).toHaveURL(new RegExp('/field$'));
});

test('actividad offline con foto: sincroniza, espera aprobación y luego sincroniza la evidencia', async ({
  page,
  request,
  context,
}) => {
  test.setTimeout(120000);
  const campaign = await resolveCampaign(request);
  const title = `Actividad con evidencia ${Date.now()}`;

  await browserLogin(page, e2eUsers.coordinator);
  await gotoField(page, campaign.id);

  await context.setOffline(true);
  await page.getByRole('button', { name: 'Registrar actividad' }).click();
  await page.getByLabel('Tipo de actividad').click();
  await page.getByRole('option').first().click();
  await page.getByLabel('Nombre de la actividad').fill(title);
  await page.setInputFiles('input[type="file"][accept*="image"]', {
    name: 'evidencia.jpg',
    mimeType: 'image/jpeg',
    buffer: Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0]),
  });
  await expect(page.getByText('1 adjunto(s) guardado(s) en el dispositivo.')).toBeVisible();
  await page.getByRole('button', { name: 'Guardar y enviar a sincronización' }).click();
  await expect(page).toHaveURL(new RegExp('/field/drafts$'));

  await context.setOffline(false);
  await expect(page.getByText('En línea')).toBeVisible();
  await page.getByRole('button', { name: 'Sincronizar ahora' }).click();
  // The activity itself syncs (PENDING_APPROVAL); the photo cannot upload yet.
  await expect(page.getByText(/1 registro sincronizado/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/1 evidencia pendiente de sincronizar/)).toBeVisible({
    timeout: 15000,
  });

  const token = await apiToken(request, e2eUsers.coordinator);
  const headers = { Authorization: `Bearer ${token}` };
  const activities = (
    await (await request.get(`/api/v1/campaigns/${campaign.id}/activities?page_size=100`, { headers })).json()
  ).items as { id: string; title: string; approval_status: string }[];
  const created = activities.find((a) => a.title === title)!;
  expect(created.approval_status).toBe('PENDING_APPROVAL');

  // An executive approves the activity server-side (out of band, as staff would).
  const adminToken = await apiToken(request);
  const adminHeaders = { Authorization: `Bearer ${adminToken}` };
  const approve = await request.post(
    `/api/v1/campaigns/${campaign.id}/activities/${created.id}/approve`,
    { headers: adminHeaders },
  );
  expect(approve.status()).toBe(200);

  // Coordinator retries sync: now the same queued attachment uploads for real.
  await page.reload();
  await page.getByRole('button', { name: 'Sincronizar ahora' }).click();
  await expect(page.getByRole('alert').getByText(/evidencia.*sincronizada/)).toBeVisible({ timeout: 15000 });

  const evidence = (
    await (
      await request.get(`/api/v1/campaigns/${campaign.id}/activities/${created.id}/evidence`, { headers })
    ).json()
  ) as { id: string; mime_type: string | null }[];
  expect(evidence).toHaveLength(1);
  expect(evidence[0].mime_type).toBe('image/jpeg');

  await cleanupByTitle(request, campaign.id, 'activities', title);
});

test('reintentar la carga de una evidencia con el mismo client_generated_id no la duplica', async ({ request }) => {
  const campaign = await resolveCampaign(request);
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const activityCreate = await request.post(`/api/v1/campaigns/${campaign.id}/activities`, {
    headers,
    data: {
      activity_type_code: 'COMMUNITY_MEETING',
      title: `Actividad evidencia retry ${Date.now()}`,
      activity_date: new Date().toISOString().slice(0, 10),
      status: 'PLANNED',
      parish_id: (
        await (
          await request.get(`/api/v1/campaigns/${campaign.id}/current-election/analysis`, { headers })
        ).json()
      ).parishes.find((p: { name: string }) => p.name === 'Gualaceo').parish_id,
    },
  });
  expect(activityCreate.status()).toBe(201);
  const activity = await activityCreate.json();
  expect(activity.approval_status).toBe('APPROVED'); // admin token auto-approves

  const clientGeneratedId = '22222222-2222-2222-2222-222222222222';
  const uploadOnce = () =>
    request.post(`/api/v1/campaigns/${campaign.id}/activities/${activity.id}/evidence/upload`, {
      headers,
      multipart: {
        file: {
          name: 'evidencia.jpg',
          mimeType: 'image/jpeg',
          buffer: Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0]),
        },
        evidence_type: 'PHOTO',
        title: 'Evidencia de reintento',
        client_generated_id: clientGeneratedId,
      },
    });

  const first = await uploadOnce();
  expect(first.status()).toBe(201);
  const retry = await uploadOnce();
  expect(retry.status()).toBe(201);
  expect((await retry.json()).id).toBe((await first.json()).id);

  const evidence = (
    await (
      await request.get(`/api/v1/campaigns/${campaign.id}/activities/${activity.id}/evidence`, { headers })
    ).json()
  ) as unknown[];
  expect(evidence).toHaveLength(1);

  await cleanupByTitle(request, campaign.id, 'activities', activity.title);
});

test('un conflicto del servidor muestra REQUIRES_REVIEW y "Conservar servidor" resuelve sin sobrescribir', async ({
  page,
  request,
  context,
}) => {
  test.setTimeout(60000);
  const campaign = await resolveCampaign(request);
  const title = `Necesidad en conflicto ${Date.now()}`;

  await browserLogin(page, e2eUsers.coordinator);
  await gotoField(page, campaign.id);
  await context.setOffline(true);
  await page.getByRole('button', { name: 'Registrar necesidad' }).click();
  await page.getByLabel('Categoría').click();
  await page.getByRole('option').first().click();
  await page.getByLabel('Título').fill(title);
  await expect(page.getByText('Guardado en el dispositivo')).toBeVisible({ timeout: 10000 });
  await page.getByRole('button', { name: 'Guardar y enviar a sincronización' }).click();
  await expect(page).toHaveURL(new RegExp('/field/drafts$'));

  await context.setOffline(false);
  await expect(page.getByText('En línea')).toBeVisible();
  // Force the real sync request to come back as a conflict, so the app's own
  // syncEngine code produces REQUIRES_REVIEW — not an injected fake state.
  await page.route('**/api/v1/campaigns/**/needs', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'Conflicto de datos' }) });
    } else {
      await route.continue();
    }
  });
  await page.getByRole('button', { name: 'Sincronizar ahora' }).click();
  await expect(page.getByText(/en conflicto, requieren revisión/)).toBeVisible({ timeout: 15000 });
  await page.unroute('**/api/v1/campaigns/**/needs');

  await expect(page.getByText(/· Requiere revisión/)).toBeVisible();
  await page.getByRole('button', { name: 'Revisar' }).click();
  await expect(page.getByRole('heading', { name: 'Este registro requiere revisión' })).toBeVisible();
  await expect(page.getByText('Versión del dispositivo')).toBeVisible();
  await expect(page.getByText('Versión del servidor')).toBeVisible();

  await page.getByRole('button', { name: 'Conservar servidor' }).click();
  await expect(page.getByText(title)).toHaveCount(0);

  const token = await apiToken(request, e2eUsers.coordinator);
  const headers = { Authorization: `Bearer ${token}` };
  const needs = (
    await (await request.get(`/api/v1/campaigns/${campaign.id}/needs?page_size=100`, { headers })).json()
  ).items as { title: string }[];
  expect(needs.filter((n) => n.title === title)).toHaveLength(0);
});

test('"Revisar borrador" ante un conflicto abre el formulario de edición', async ({ page, request, context }) => {
  test.setTimeout(60000);
  const campaign = await resolveCampaign(request);
  const title = `Necesidad a revisar ${Date.now()}`;

  await browserLogin(page, e2eUsers.coordinator);
  await gotoField(page, campaign.id);
  await context.setOffline(true);
  await page.getByRole('button', { name: 'Registrar necesidad' }).click();
  await page.getByLabel('Categoría').click();
  await page.getByRole('option').first().click();
  await page.getByLabel('Título').fill(title);
  await expect(page.getByText('Guardado en el dispositivo')).toBeVisible({ timeout: 10000 });
  await page.getByRole('button', { name: 'Guardar y enviar a sincronización' }).click();
  await expect(page).toHaveURL(new RegExp('/field/drafts$'));

  await context.setOffline(false);
  await page.route('**/api/v1/campaigns/**/needs', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'Conflicto de datos' }) });
    } else {
      await route.continue();
    }
  });
  await page.getByRole('button', { name: 'Sincronizar ahora' }).click();
  await expect(page.getByText(/en conflicto, requieren revisión/)).toBeVisible({ timeout: 15000 });
  await page.unroute('**/api/v1/campaigns/**/needs');

  await page.getByRole('button', { name: 'Revisar' }).click();
  await page.getByRole('button', { name: 'Revisar borrador' }).click();
  await expect(page.getByRole('heading', { name: 'Registrar necesidad' })).toBeVisible();
  await expect(page.getByLabel('Título')).toHaveValue(title);

  // Clean up the local draft so it doesn't linger for later runs.
  await page.goto(`/app/campaigns/${campaign.id}/field/drafts`);
  await page.getByRole('button', { name: 'Eliminar' }).first().click();
  await page.getByRole('button', { name: 'Eliminar', exact: true }).last().click();
});

test('Operación de campo es usable en viewports móviles sin overflow horizontal', async ({
  page,
  request,
}) => {
  const campaign = await resolveCampaign(request);
  await browserLogin(page, e2eUsers.coordinator);
  for (const size of [
    { width: 375, height: 812 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
  ]) {
    await page.setViewportSize(size);
    for (const path of ['field', 'field/agenda', 'field/drafts', 'field/needs/new']) {
      await page.goto(`/app/campaigns/${campaign.id}/${path}`);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
        `${path} ${size.width}`,
      ).toBe(true);
    }
  }
});
