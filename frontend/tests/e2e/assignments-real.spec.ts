import { expect, test, type Page } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';
const auth = (token: string) => ({ Authorization: 'Bearer ' + token });
async function choose(page: Page, label: string | RegExp, option: string | RegExp) {
  await page.getByLabel(label).click();
  await page.getByRole('option', { name: option }).click();
}

test('asignaciones reales de parroquia, comunidad y sector respetan la jerarquia', async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const admin = await apiToken(request);
  const coordinator = await apiToken(request, e2eUsers.coordinator);
  const campaigns = await (
    await request.get('/api/v1/campaigns?page_size=100', { headers: auth(admin) })
  ).json();
  const campaign = campaigns.items.find(
    (item: { slug: string }) => item.slug === 'gualaceo-e2e-2027',
  );
  const users = await (
    await request.get('/api/v1/users?page=1&page_size=100', { headers: auth(admin) })
  ).json();
  const coordinatorUser = users.items.find(
    (item: { username: string }) => item.username === 'coordinator_e2e',
  );
  const parishes = await (
    await request.get('/api/v1/parishes?canton_id=' + campaign.canton_id, { headers: auth(admin) })
  ).json();
  expect(parishes.length).toBeGreaterThan(1);
  let assignedParish: (typeof parishes)[number] | undefined;
  let community: { id: string; name: string; code: string } | undefined;
  for (const parish of parishes) {
    const communities = await (
      await request.get('/api/v1/communities?parish_id=' + parish.id + '&page_size=100', {
        headers: auth(admin),
      })
    ).json();
    const match = communities.items.find(
      (item: { code: string }) => item.code === 'E2E_COMMUNITY',
    );
    if (match) {
      assignedParish = parish;
      community = match;
      break;
    }
  }
  expect(assignedParish).toBeDefined();
  expect(community).toBeDefined();
  const fixtureParish = assignedParish!;
  const fixtureCommunity = community!;
  const outsideParish = parishes.find(
    (parish: { id: string }) => parish.id !== fixtureParish.id,
  );
  const sectors = await (
    await request.get('/api/v1/sectors?community_id=' + fixtureCommunity.id + '&page_size=100', {
      headers: auth(admin),
    })
  ).json();
  const sector = sectors.items.find((item: { code: string }) => item.code === 'E2E_SECTOR');

  const existing = await (
    await request.get('/api/v1/campaigns/' + campaign.id + '/territorial-assignments', {
      headers: auth(admin),
    })
  ).json();
  for (const item of existing.filter(
    (x: { user_id: string }) => x.user_id === coordinatorUser.id,
  )) {
    expect(
      (
        await request.delete(
          '/api/v1/campaigns/' + campaign.id + '/territorial-assignments/' + item.id,
          { headers: auth(admin) },
        )
      ).status(),
    ).toBe(200);
  }

  await browserLogin(page);
  await page.getByRole('link', { name: 'Asignaciones' }).click();
  await expect(page.getByRole('heading', { name: 'Asignaciones' })).toBeVisible();
  await page.getByRole('main').getByLabel('Campana').click();
  await page.getByRole('option', { name: campaign.name }).click();
  await choose(page, 'Usuario coordinador', /coordinator_e2e/);
  await choose(page, 'Parroquia', fixtureParish.name);

  const createdStatuses: number[] = [];
  page.on('response', (response) => {
    if (
      response.request().method() === 'POST' &&
      response.url().endsWith('/territorial-assignments')
    )
      createdStatuses.push(response.status());
  });
  await page.getByRole('button', { name: 'Asignar territorio' }).click();
  await choose(page, 'Comunidad (opcional)', fixtureCommunity.name);
  await page.getByRole('button', { name: 'Asignar territorio' }).click();
  await choose(page, 'Sector (opcional)', sector.name);
  await page.getByRole('button', { name: 'Asignar territorio' }).click();
  await expect.poll(() => createdStatuses).toEqual([201, 201, 201]);

  const listed = await (
    await request.get('/api/v1/campaigns/' + campaign.id + '/territorial-assignments', {
      headers: auth(admin),
    })
  ).json();
  const ours = listed.filter((item: { user_id: string }) => item.user_id === coordinatorUser.id);
  expect(ours).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        parish_id: fixtureParish.id,
        community_id: null,
        sector_id: null,
      }),
      expect.objectContaining({
        parish_id: fixtureParish.id,
        community_id: fixtureCommunity.id,
        sector_id: null,
      }),
      expect.objectContaining({
        parish_id: fixtureParish.id,
        community_id: fixtureCommunity.id,
        sector_id: sector.id,
      }),
    ]),
  );
  await expect(page.getByRole('cell', { name: fixtureCommunity.name }).first()).toBeVisible();
  await expect(page.getByRole('cell', { name: sector.name }).first()).toBeVisible();

  expect(
    (
      await request.get('/api/v1/parishes/' + fixtureParish.id, { headers: auth(coordinator) })
    ).status(),
  ).toBe(200);
  expect(
    (
      await request.get('/api/v1/communities/' + fixtureCommunity.id, { headers: auth(coordinator) })
    ).status(),
  ).toBe(200);
  expect(
    (await request.get('/api/v1/sectors/' + sector.id, { headers: auth(coordinator) })).status(),
  ).toBe(200);
  const denied = await request.get('/api/v1/parishes/' + outsideParish.id, {
    headers: auth(coordinator),
  });
  expect(denied.status()).toBe(403);
  expect(await denied.text()).not.toContain(outsideParish.name);
});
