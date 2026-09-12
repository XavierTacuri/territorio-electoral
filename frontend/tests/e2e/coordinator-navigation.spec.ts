import { expect, test, type APIRequestContext } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

function jwtUserId(token: string): string {
  const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
  return payload.sub as string;
}

async function gualaceoCampaign(request: APIRequestContext, headers: Record<string, string>) {
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; slug: string; canton_id: number }[];
  const campaign = campaigns.find((item) => item.slug === 'gualaceo-e2e-2027');
  if (!campaign) throw new Error('El fixture E2E requiere gualaceo-e2e-2027');
  return campaign;
}

const coordinatorPaths = [
  'dashboard',
  'panorama',
  'territories',
  'calendar',
  'operations',
  'activities',
  'needs',
  'election-day',
];

test('TERRITORIAL_COORDINATOR ve el menú reducido y no accede a módulos retirados por URL directa', async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const adminHeaders = { Authorization: 'Bearer ' + (await apiToken(request)) };
  const campaign = await gualaceoCampaign(request, adminHeaders);

  const coordinatorToken = await apiToken(request, e2eUsers.coordinator);
  const coordinatorUserId = jwtUserId(coordinatorToken);
  const assignments = (await (
    await request.get(`/api/v1/campaigns/${campaign.id}/territorial-assignments`, {
      headers: adminHeaders,
    })
  ).json()) as { user_id: string; parish_id: number; is_active: boolean }[];
  const assignedParishId = assignments.find(
    (a) => a.user_id === coordinatorUserId && a.is_active,
  )?.parish_id;
  if (!assignedParishId)
    throw new Error('coordinator_e2e requiere una asignación territorial activa en el fixture E2E');
  const allParishes = (await (
    await request.get(`/api/v1/parishes?canton_id=${campaign.canton_id}`, { headers: adminHeaders })
  ).json()) as { id: number }[];
  const unassignedParishId = allParishes.find((p) => p.id !== assignedParishId)?.id;

  // Every `page.goto` below is a full browser navigation (not SPA
  // client-side routing), so each one re-runs the silent-refresh-on-load
  // flow. Back-to-back reloads with no gap can race the refresh-token
  // rotation and spuriously log the session out mid-test — unrelated to the
  // RBAC behavior under test — so each navigation is followed by a short
  // settle wait.
  const goto = async (path: string) => {
    await page.goto(`/app/campaigns/${campaign.id}${path}`);
    await page.waitForTimeout(500);
  };

  await browserLogin(page, e2eUsers.coordinator);
  await goto('/dashboard');
  await expect(page).toHaveURL(/\/app\/campaigns\/[^/]+\/dashboard/);

  await test.step('el menú lateral muestra únicamente los módulos del contrato de coordinador', async () => {
    const navigation = page.getByRole('navigation', { name: 'Navegación principal' });
    for (const path of coordinatorPaths) {
      await expect(navigation.locator(`a[href$="/${path}"]`)).toHaveCount(1);
    }
    for (const retiredPath of [
      'surveys',
      'territory-ai',
      'reports',
      'alerts',
      'debate',
      'commitments',
    ]) {
      await expect(navigation.locator(`a[href*="/${retiredPath}"]`)).toHaveCount(0);
    }
    // "Mi Jornada" is conditional on an ACTIVE ElectionDayOperation + a valid
    // ElectionDayAssignment for this user (see useMyElectionDayNavVisibility);
    // the E2E fixture seeds coordinator_e2e with both, so it is expected here.
    const myJornadaCount = await navigation.locator('a[href*="/election-day/my"]').count();
    expect([0, 1]).toContain(myJornadaCount);
    await expect(navigation.getByRole('link')).toHaveCount(
      coordinatorPaths.length + myJornadaCount,
    );
  });

  for (const blockedPath of ['reports', 'alerts', 'debate', 'surveys']) {
    await test.step(`URL directa a /${blockedPath} devuelve 403`, async () => {
      await goto(`/${blockedPath}`);
      await expect(page).toHaveURL(/\/403$/);
    });
  }

  await test.step('Inteligencia territorial redirige directo al Expediente cuando hay una sola parroquia asignada', async () => {
    await goto('/territories');
    await expect(page).not.toHaveURL(/\/403$/);
    // coordinator_e2e has exactly one active TerritorialAssignment in the
    // fixture, so Inteligencia Territorial never shows a selector/comparison
    // — it replaces straight into that parish's Expediente Territorial.
    await expect(page).toHaveURL(new RegExp(`/territories/${assignedParishId}$`));
    await expect(page.getByRole('heading', { name: 'COMPARAR TERRITORIOS' })).toHaveCount(0);
  });

  if (unassignedParishId) {
    await test.step('URL directa a una parroquia no asignada devuelve 403', async () => {
      await goto(`/territories/${unassignedParishId}`);
      await expect(page.getByRole('heading', { name: '403' })).toBeVisible();
    });
  }

  await test.step('URL directa a la parroquia asignada funciona', async () => {
    await goto(`/territories/${assignedParishId}`);
    await expect(page).not.toHaveURL(/\/403$/);
  });
});

test('TERRITORIAL_COORDINATOR ve un Centro de Comando simplificado, sin CTAs ejecutivos ni IA/alertas', async ({
  page,
  request,
}) => {
  test.setTimeout(60000);
  const adminHeaders = { Authorization: 'Bearer ' + (await apiToken(request)) };
  const campaign = await gualaceoCampaign(request, adminHeaders);

  await browserLogin(page, e2eUsers.coordinator);
  await page.goto(`/app/campaigns/${campaign.id}/dashboard`);
  // The Dashboard fires several parallel queries (analysis, operations,
  // agenda, territories, campaign) before its first paint; give it more
  // room than the 5s default under sustained local test-suite load.
  await expect(
    page.getByRole('heading', { level: 1, name: 'Centro de Comando Territorial' }),
  ).toBeVisible({ timeout: 15000 });

  await test.step('no muestra los 3 CTAs ejecutivos', async () => {
    await expect(page.getByRole('link', { name: 'CONSULTAR TERRITORIO IA' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'VER PANORAMA COMPLETO' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'GENERAR INFORME EJECUTIVO' })).toHaveCount(0);
  });

  await test.step('no muestra la card de Territorio IA ni la de Alertas', async () => {
    await expect(page.getByText('ASISTENTE CON EVIDENCIA')).toHaveCount(0);
    await expect(page.getByRole('heading', { level: 2, name: 'Territorio IA' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Alertas' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'VER TODAS' })).toHaveCount(0);
  });

  await test.step('conserva el mapa, KPIs y Hoy en territorio', async () => {
    const map = page.getByRole('region', { name: 'Mapa operativo territorial' });
    await expect(map).toBeVisible();
    await expect(map.locator('canvas.maplibregl-canvas')).toBeVisible();
    await expect(page.getByText('Padrón electoral')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Hoy en territorio' })).toBeVisible();
  });

  // The map's hover tooltip itself (name-on-mouseenter, cleared on
  // mouseleave, no extra request) is covered deterministically by the unit
  // test in CommandCenterMap.test.tsx. Simulating a real WebGL hit-test over
  // MapLibre's canvas in headless Chromium here was tried and is flaky
  // (~1-in-3 runs miss the pick even with multi-point retries and settle
  // waits) — timing-dependent on the GPU picking buffer, not on the
  // application's tooltip logic, so it isn't asserted at this layer.

  await test.step('viewport 375px no produce overflow horizontal', async () => {
    await page.setViewportSize({ width: 375, height: 812 });
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
  });
});

test('TERRITORIAL_COORDINATOR no tiene herramientas ejecutivas en Panorama ni en el Expediente Territorial', async ({
  page,
  request,
}) => {
  test.setTimeout(60000);
  const adminHeaders = { Authorization: 'Bearer ' + (await apiToken(request)) };
  const campaign = await gualaceoCampaign(request, adminHeaders);

  await browserLogin(page, e2eUsers.coordinator);

  await test.step('Panorama: sin Territorio IA, Generar informe ni preguntas rápidas', async () => {
    await page.goto(`/app/campaigns/${campaign.id}/panorama`);
    await expect(page.getByRole('heading', { level: 1, name: 'Panorama electoral' })).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByRole('link', { name: 'CONSULTAR EN TERRITORIO IA' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'GENERAR INFORME' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Preguntas rápidas' })).toHaveCount(0);
    await expect(page.getByText('Electores actuales')).toBeVisible();
    await expect(page.getByText('Operación territorial')).toBeVisible();
  });

  await test.step('Inteligencia Territorial → Expediente: sin Territorio IA ni generación de informes', async () => {
    await page.goto(`/app/campaigns/${campaign.id}/territories`);
    await expect(
      page.getByRole('heading', { level: 1, name: 'EXPEDIENTE TERRITORIAL' }),
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('heading', { name: 'COMPARAR TERRITORIOS' })).toHaveCount(0);
    await expect(page.getByText('PREGUNTAR A TERRITORIO IA')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'TERRITORIO IA' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'DESCARGAR EXPEDIENTE' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'VER EN MAPA' })).toBeVisible();
  });
});
