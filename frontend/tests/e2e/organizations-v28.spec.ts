import { expect, test } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

test('V2.8 aisla organizaciones y rechaza IDOR de campaña', async ({ request }) => {
  const adminHeaders = {
    Authorization: `Bearer ${await apiToken(request, e2eUsers.platformAdmin)}`,
  };
  const alphaHeaders = { Authorization: `Bearer ${await apiToken(request, e2eUsers.alphaOwner)}` };
  const betaHeaders = { Authorization: `Bearer ${await apiToken(request, e2eUsers.betaOwner)}` };
  const organizations = (await (
    await request.get('/api/v1/organizations', { headers: adminHeaders })
  ).json()) as { id: string; slug: string; plan_code: string }[];
  const alpha = organizations.find((item) => item.slug === 'organization-alpha')!;
  const beta = organizations.find((item) => item.slug === 'organization-beta')!;
  expect(alpha.plan_code).toBe('PRO');
  expect(beta.plan_code).toBe('STANDARD');
  expect(
    (await (await request.get('/api/v1/organizations', { headers: alphaHeaders })).json()).map(
      (item: { id: string }) => item.id,
    ),
  ).toEqual([alpha.id]);
  expect(
    (await (await request.get('/api/v1/organizations', { headers: betaHeaders })).json()).map(
      (item: { id: string }) => item.id,
    ),
  ).toEqual([beta.id]);

  const alphaCampaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers: alphaHeaders })).json()
  ).items as { id: string; slug: string; organization_id: string }[];
  const betaCampaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers: betaHeaders })).json()
  ).items as { id: string; slug: string; organization_id: string; canton_id: number }[];
  expect(alphaCampaigns.every((item) => item.organization_id === alpha.id)).toBe(true);
  expect(betaCampaigns.every((item) => item.organization_id === beta.id)).toBe(true);
  const alphaCampaign = alphaCampaigns.find((item) => item.slug === 'territorio-sintetico-e2e')!;
  const betaCampaign = betaCampaigns.find((item) => item.slug === 'gualaceo-e2e-2027')!;
  expect(
    (await request.get(`/api/v1/campaigns/${betaCampaign.id}`, { headers: alphaHeaders })).status(),
  ).toBe(403);
  expect(
    (await request.get(`/api/v1/campaigns/${alphaCampaign.id}`, { headers: betaHeaders })).status(),
  ).toBe(403);

  const alphaAi = await request.post(`/api/v1/campaigns/${alphaCampaign.id}/territory-ai/query`, {
    headers: alphaHeaders,
    data: { question: 'Resume Parroquia Alfa' },
  });
  expect(alphaAi.status()).toBe(200);
  const betaAi = await request.post(`/api/v1/campaigns/${betaCampaign.id}/territory-ai/query`, {
    headers: betaHeaders,
    data: { question: '¿Cuál es el panorama electoral de Gualaceo ahora?' },
  });
  expect(betaAi.status()).toBe(200);
  const betaGrounded = (await betaAi.json()) as { citations: { internal_path?: string }[] };
  expect(
    betaGrounded.citations.every(
      (citation) => !citation.internal_path || !citation.internal_path.includes(alphaCampaign.id),
    ),
  ).toBe(true);

  const limit = await request.post('/api/v1/campaigns', {
    headers: betaHeaders,
    data: {
      organization_id: beta.id,
      name: 'Segunda Beta',
      slug: 'segunda-beta-e2e',
      canton_id: betaCampaign.canton_id,
      office_type: 'MAYOR',
      election_name: 'Elección sintética',
      election_date: '2027-05-01',
      status: 'DRAFT',
    },
  });
  expect(limit.status()).toBe(409);
  expect((await limit.json()).detail.code).toBe('PLAN_CAMPAIGN_LIMIT_REACHED');
});

test('V2.8 suspensión bloquea operación y plataforma puede reactivar', async ({ request }) => {
  const adminHeaders = {
    Authorization: `Bearer ${await apiToken(request, e2eUsers.platformAdmin)}`,
  };
  const alphaHeaders = { Authorization: `Bearer ${await apiToken(request, e2eUsers.alphaOwner)}` };
  const organizations = (await (
    await request.get('/api/v1/organizations', { headers: adminHeaders })
  ).json()) as { id: string; slug: string }[];
  const alpha = organizations.find((item) => item.slug === 'organization-alpha')!;
  const campaign = (
    (await (await request.get('/api/v1/campaigns?page_size=100', { headers: alphaHeaders })).json())
      .items as { id: string }[]
  )[0];
  try {
    expect(
      (
        await request.patch(`/api/v1/organizations/${alpha.id}`, {
          headers: adminHeaders,
          data: { status: 'SUSPENDED' },
        })
      ).status(),
    ).toBe(200);
    const denied = await request.get(`/api/v1/campaigns/${campaign.id}`, { headers: alphaHeaders });
    expect(denied.status()).toBe(403);
    expect((await denied.json()).detail.code).toBe('ORGANIZATION_SUSPENDED');
    expect(
      (await request.get(`/api/v1/organizations/${alpha.id}`, { headers: adminHeaders })).status(),
    ).toBe(200);
  } finally {
    expect(
      (
        await request.patch(`/api/v1/organizations/${alpha.id}`, {
          headers: adminHeaders,
          data: { status: 'ACTIVE' },
        })
      ).status(),
    ).toBe(200);
  }
});

test('V2.8 selector cambia tenant y elimina campañas del contexto anterior', async ({ page }) => {
  await browserLogin(page, e2eUsers.crossOrganization);
  await expect(page.getByLabel('Organización')).toBeVisible();
  await page.getByLabel('Organización').click();
  await page.getByRole('option', { name: 'Organization Alpha' }).click();
  await page.getByLabel('Campaña').click();
  await expect(page.getByRole('option', { name: /Territorio Sint/ })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByLabel('Organización').click();
  await page.getByRole('option', { name: 'Organization Beta' }).click();
  await page.getByLabel('Campaña').click();
  await expect(page.getByRole('option', { name: /Gualaceo E2E/ })).toBeVisible();
  await expect(page.getByRole('option', { name: /Territorio Sint/ })).toHaveCount(0);
});

test('V2.8 UI muestra PLAN_USER_LIMIT_REACHED sin exponer error técnico', async ({ page }) => {
  await browserLogin(page, e2eUsers.platformAdmin);
  await page.goto('/app/admin/organizations');
  await page.getByRole('heading', { name: 'Organization User Limit' }).click();
  await page.getByRole('tab', { name: 'Usuarios' }).click();
  await page.getByRole('button', { name: 'Agregar miembro' }).click();
  await page.getByLabel('Email o nombre de usuario exacto').fill('alpha-owner@example.test');
  await page.getByRole('button', { name: 'Buscar usuario' }).click();
  await expect(page.getByText(/alpha-owner@example\.test/)).toBeVisible();
  const response = page.waitForResponse(
    (item) => item.url().includes('/memberships') && item.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Guardar miembro' }).click();
  const result = await response;
  expect(result.status()).toBe(409);
  expect((await result.json()).detail.code).toBe('PLAN_USER_LIMIT_REACHED');
  await expect(page.getByText('Has alcanzado el límite de usuarios de tu plan.')).toBeVisible();
});

test('V2.8 Organization Admin gestiona miembros solo en su tenant', async ({ page, request }) => {
  const managerHeaders = {
    Authorization: `Bearer ${await apiToken(request, e2eUsers.alphaManager)}`,
  };
  const organizations = (await (
    await request.get('/api/v1/organizations', { headers: managerHeaders })
  ).json()) as { id: string; slug: string }[];
  const alpha = organizations.find((item) => item.slug === 'organization-alpha')!;
  const platformHeaders = {
    Authorization: `Bearer ${await apiToken(request, e2eUsers.platformAdmin)}`,
  };
  const allOrganizations = (await (
    await request.get('/api/v1/organizations', { headers: platformHeaders })
  ).json()) as { id: string; slug: string }[];
  const beta = allOrganizations.find((item) => item.slug === 'organization-beta')!;
  const users = await request.get('/api/v1/users?search=candidate_e2e', {
    headers: platformHeaders,
  });
  const candidate = (await users.json()).items.find(
    (item: { username: string }) => item.username === 'candidate_e2e',
  ) as { id: string };
  const crossTenant = await request.post(`/api/v1/organizations/${beta.id}/memberships`, {
    headers: managerHeaders,
    data: { user_id: candidate.id, organization_role: 'MEMBER', status: 'ACTIVE' },
  });
  expect(crossTenant.status()).toBe(403);
  expect((await crossTenant.json()).detail.code).toBe('ORGANIZATION_ACCESS_DENIED');

  await browserLogin(page, e2eUsers.alphaManager);
  await page.goto('/app/organization');
  await page.getByRole('tab', { name: 'Usuarios' }).click();
  await page.getByRole('button', { name: 'Agregar miembro' }).click();
  await page.getByLabel('Email o nombre de usuario exacto').fill('candidate_e2e');
  await page.getByRole('button', { name: 'Buscar usuario' }).click();
  await expect(page.getByText(/candidate-e2e@example\.com/)).toBeVisible();
  const added = page.waitForResponse(
    (item) => item.url().includes('/memberships') && item.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Guardar miembro' }).click();
  expect((await added).status()).toBe(201);
  await expect(page.getByText('candidate-e2e@example.com')).toBeVisible();
  const memberships = (await (
    await request.get(`/api/v1/organizations/${alpha.id}/memberships`, {
      headers: managerHeaders,
    })
  ).json()) as { id: string; user_id: string }[];
  const membership = memberships.find((item) => item.user_id === candidate.id)!;
  expect(
    (
      await request.delete(`/api/v1/organizations/${alpha.id}/memberships/${membership.id}`, {
        headers: managerHeaders,
      })
    ).status(),
  ).toBe(204);
});

test('V2.8 onboarding visual crea tenant, owner, plan y campaña', async ({ page, request }) => {
  const suffix = Date.now().toString();
  const organizationName = `Organization Onboarding ${suffix}`;
  const organizationSlug = `organization-onboarding-${suffix}`;
  const campaignName = `Campaign Onboarding ${suffix}`;
  await browserLogin(page, e2eUsers.platformAdmin);
  await page.goto('/app/admin/organizations/onboarding');
  await expect(page.getByText('Paso 1 de 6')).toBeVisible();
  await page.getByRole('textbox', { name: 'Nombre', exact: true }).fill(organizationName);
  await page.getByRole('textbox', { name: 'Slug', exact: true }).fill(organizationSlug);
  await page.getByLabel('Email de contacto').fill(`onboarding-${suffix}@example.test`);
  await page.getByRole('button', { name: 'Siguiente' }).click();
  await expect(page.getByText('Paso 2 de 6')).toBeVisible();
  await page.getByLabel('Propietario').click();
  await page.getByRole('option', { name: /candidate-e2e@example\.com/ }).click();
  await page.getByRole('button', { name: 'Siguiente' }).click();
  await page.getByText('PRO', { exact: true }).click();
  await page.getByLabel('Máximo de campañas').fill('2');
  await page.getByLabel('Máximo de usuarios').fill('4');
  await page.getByRole('button', { name: 'Siguiente' }).click();
  await page.getByLabel('Nombre de campaña').fill(campaignName);
  await page.getByLabel('Slug de campaña').fill(`campaign-onboarding-${suffix}`);
  await page.getByLabel('Elección').fill('Elección E2E 2027');
  await page.getByLabel('Fecha electoral').fill('2027-05-01');
  await page.getByRole('button', { name: 'Siguiente' }).click();
  await page.getByLabel('Provincia').click();
  await page.getByRole('option', { name: /Sintética E2E/ }).click();
  await page.getByLabel('Cantón').click();
  await page.getByRole('option', { name: /Cantón Sintético E2E/ }).click();
  await page.getByRole('button', { name: 'Siguiente' }).click();
  await expect(page.getByText('Paso 6 de 6')).toBeVisible();
  await expect(page.getByText(`Organización: ${organizationName}`)).toBeVisible();
  const created = page.waitForResponse(
    (item) => item.url().endsWith('/api/v1/organizations/onboarding') && item.status() === 201,
  );
  await page.getByRole('button', { name: 'Crear organización' }).click();
  const body = await (await created).json();
  await expect(page).toHaveURL(new RegExp(`/app/admin/organizations/${body.organization.id}$`));
  await expect(page.getByRole('heading', { name: organizationName })).toBeVisible();
  expect(body.membership.organization_role).toBe('OWNER');
  expect(body.subscription.plan_code).toBe('PRO');
  const token = await apiToken(request, e2eUsers.platformAdmin);
  const campaigns = await request.get(
    `/api/v1/campaigns?page_size=100&organization_id=${body.organization.id}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect((await campaigns.json()).items.map((item: { name: string }) => item.name)).toContain(
    campaignName,
  );
});

test('V2.8 suscripción es editable solo por Platform Admin', async ({ page, request }) => {
  const adminHeaders = {
    Authorization: `Bearer ${await apiToken(request, e2eUsers.platformAdmin)}`,
  };
  const ownerHeaders = { Authorization: `Bearer ${await apiToken(request, e2eUsers.alphaOwner)}` };
  const organizations = (await (
    await request.get('/api/v1/organizations', { headers: adminHeaders })
  ).json()) as { id: string; slug: string }[];
  const alpha = organizations.find((item) => item.slug === 'organization-alpha')!;
  const original = await (
    await request.get(`/api/v1/organizations/${alpha.id}/subscription`, { headers: adminHeaders })
  ).json();
  const denied = await request.put(`/api/v1/organizations/${alpha.id}/subscription`, {
    headers: ownerHeaders,
    data: { ...original, metadata: {} },
  });
  expect(denied.status()).toBe(403);
  await browserLogin(page, e2eUsers.platformAdmin);
  await page.goto(`/app/admin/organizations/${alpha.id}`);
  await page.getByRole('tab', { name: 'Plan y límites' }).click();
  await page.getByRole('button', { name: 'Editar suscripción' }).click();
  await page.getByLabel('Máximo de usuarios').fill('11');
  await page.getByRole('button', { name: 'Guardar suscripción' }).click();
  await expect(page.getByText('Máximo de usuarios: 11')).toBeVisible();
  await request.put(`/api/v1/organizations/${alpha.id}/subscription`, {
    headers: adminHeaders,
    data: { ...original, metadata: {} },
  });
});

test('V2.8 suspende y reactiva una organización desde su detalle', async ({ page, request }) => {
  const adminHeaders = {
    Authorization: `Bearer ${await apiToken(request, e2eUsers.platformAdmin)}`,
  };
  const organizations = (await (
    await request.get('/api/v1/organizations', { headers: adminHeaders })
  ).json()) as { id: string; slug: string }[];
  const beta = organizations.find((item) => item.slug === 'organization-beta')!;
  const ownerHeaders = {
    Authorization: `Bearer ${await apiToken(request, e2eUsers.betaOwner)}`,
  };
  const campaign = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers: ownerHeaders })).json()
  ).items[0] as { id: string };
  await browserLogin(page, e2eUsers.platformAdmin);
  await page.goto(`/app/admin/organizations/${beta.id}`);
  try {
    await page.getByRole('button', { name: 'Suspender' }).click();
    await expect(page.getByRole('heading', { name: 'Suspender organización' })).toBeVisible();
    await page.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.getByText('Suspendida', { exact: true })).toBeVisible();
    const campaignAccess = await request.get(`/api/v1/campaigns/${campaign.id}`, {
      headers: ownerHeaders,
    });
    expect(campaignAccess.status()).toBe(403);
    expect((await campaignAccess.json()).detail.code).toBe('ORGANIZATION_SUSPENDED');
    await page.getByRole('button', { name: 'Reactivar' }).click();
    await page.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.getByText('Activa', { exact: true })).toBeVisible();
  } finally {
    await request.patch(`/api/v1/organizations/${beta.id}`, {
      headers: adminHeaders,
      data: { status: 'ACTIVE' },
    });
  }
});

test('V2.8 organizaciones y onboarding no generan overflow global responsive', async ({ page }) => {
  await browserLogin(page, e2eUsers.platformAdmin);
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/app/admin/organizations');
    await expect(page.getByRole('heading', { name: 'Organizaciones' })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    ).toBe(true);
    await page.goto('/app/admin/organizations/onboarding');
    await expect(page.getByText('Paso 1 de 6')).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    ).toBe(true);
  }
});
