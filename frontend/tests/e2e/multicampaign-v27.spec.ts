import { expect, test } from '@playwright/test';
import { apiToken, browserLogin } from './support/auth';
import { e2eUsers } from './support/auth';

test('V2.7 aisla campanas, licencia y cache visual al cambiar de canton', async ({
  page,
  request,
}) => {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const campaignsResponse = await request.get('/api/v1/campaigns?page_size=100', { headers });
  expect(campaignsResponse.status()).toBe(200);
  const campaigns = (await campaignsResponse.json()).items as {
    id: string;
    name: string;
    slug: string;
    canton_name?: string;
  }[];
  const pro = campaigns.find((item) => item.slug === 'territorio-sintetico-e2e')!;
  const standard = campaigns.find((item) => item.slug === 'gualaceo-e2e-2027')!;
  expect(pro).toBeTruthy();
  expect(standard).toBeTruthy();

  const proActivities = await (
    await request.get(`/api/v1/campaigns/${pro.id}/activities?page_size=100`, { headers })
  ).json();
  const standardActivities = await (
    await request.get(`/api/v1/campaigns/${standard.id}/activities?page_size=100`, { headers })
  ).json();
  expect(
    proActivities.items.some((item: { title: string }) =>
      item.title.startsWith('Asamblea territorial'),
    ),
  ).toBe(true);
  expect(
    standardActivities.items.some((item: { title: string }) =>
      item.title.startsWith('Asamblea territorial'),
    ),
  ).toBe(false);
  expect(
    standardActivities.items.some((item: { title: string }) =>
      item.title.startsWith('Asamblea sint'),
    ),
  ).toBe(true);
  expect(
    proActivities.items.some((item: { title: string }) => item.title.startsWith('Asamblea sint')),
  ).toBe(false);

  const proNeeds = await (
    await request.get(`/api/v1/campaigns/${pro.id}/needs?page_size=100`, { headers })
  ).json();
  const standardNeeds = await (
    await request.get(`/api/v1/campaigns/${standard.id}/needs?page_size=100`, { headers })
  ).json();
  expect(proNeeds.items.some((item: { title: string }) => item.title.includes('principal'))).toBe(
    true,
  );
  expect(
    standardNeeds.items.some((item: { title: string }) => item.title.includes('principal')),
  ).toBe(false);

  const proCne = await request.get(`/api/v1/campaigns/${pro.id}/current-election/analysis`, {
    headers,
  });
  const standardCne = await request.get(
    `/api/v1/campaigns/${standard.id}/current-election/analysis`,
    { headers },
  );
  expect(proCne.status()).toBe(200);
  expect(standardCne.status()).toBe(404);
  expect((await proCne.json()).snapshot.registered_voters).toBeGreaterThan(0);

  const proInec = await request.get(`/api/v1/campaigns/${pro.id}/dashboard/demographics`, {
    headers,
  });
  const standardInec = await request.get(
    `/api/v1/campaigns/${standard.id}/dashboard/demographics`,
    { headers },
  );
  expect(proInec.status()).toBe(200);
  expect(standardInec.status()).toBe(200);
  expect(JSON.stringify(await proInec.json())).not.toBe(JSON.stringify(await standardInec.json()));

  const proStudies = await (
    await request.get(`/api/v1/campaigns/${pro.id}/survey-studies?page_size=100`, { headers })
  ).json();
  const standardStudies = await (
    await request.get(`/api/v1/campaigns/${standard.id}/survey-studies?page_size=100`, { headers })
  ).json();
  expect(proStudies.items.some((item: { code: string }) => item.code === 'STUDY_E2E')).toBe(true);
  expect(standardStudies.items.some((item: { code: string }) => item.code === 'STUDY_E2E')).toBe(
    false,
  );

  const proPublic = await (
    await request.get(`/api/v1/campaigns/${pro.id}/public-intelligence/items?page_size=100`, {
      headers,
    })
  ).json();
  const standardPublic = await (
    await request.get(`/api/v1/campaigns/${standard.id}/public-intelligence/items?page_size=100`, {
      headers,
    })
  ).json();
  expect(
    proPublic.items.some((item: { title: string }) => item.title.includes('territorial')),
  ).toBe(true);
  expect(
    standardPublic.items.some((item: { title: string }) => item.title.includes('territorial')),
  ).toBe(false);

  const allowed = await request.post(`/api/v1/campaigns/${pro.id}/territory-ai/query`, {
    headers,
    data: { question: 'Resume Parroquia Alfa' },
  });
  expect(allowed.status()).toBe(200);
  const grounded = (await allowed.json()) as {
    citations: { campaign_id?: string; territory?: string }[];
  };
  expect(grounded.citations.length).toBeGreaterThan(0);
  expect(
    grounded.citations.every(
      (citation) => !citation.campaign_id || citation.campaign_id === pro.id,
    ),
  ).toBe(true);
  const denied = await request.post(`/api/v1/campaigns/${standard.id}/territory-ai/query`, {
    headers,
    data: { question: 'Resume la campaÃ±a' },
  });
  expect(denied.status()).toBe(403);
  expect((await denied.json()).detail.code).toBe('FEATURE_NOT_ENTITLED');

  await browserLogin(page);
  await page.goto(`/app/campaigns/${pro.id}/activities`);
  await expect(page.getByText(/Asamblea territorial/)).toBeVisible();
  await page.getByRole('combobox', { name: /Campa/ }).click();
  await page.getByRole('option', { name: new RegExp(standard.name) }).click();
  await expect(page).toHaveURL(new RegExp(`/app/campaigns/${standard.id}/activities`));
  await expect(page.getByText(/Asamblea sint.*E2E/)).toBeVisible();
  await expect(page.getByText(/Asamblea territorial/)).toHaveCount(0);
});

test('V2.7 rechaza RBAC cross-campaign en todos los modulos sensibles', async ({ request }) => {
  const adminToken = await apiToken(request);
  const analystToken = await apiToken(request, e2eUsers.analyst);
  const adminHeaders = { Authorization: `Bearer ${adminToken}` };
  const analystHeaders = { Authorization: `Bearer ${analystToken}` };
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers: adminHeaders })).json()
  ).items as { id: string; slug: string }[];
  const inaccessible = campaigns.find((item) => item.slug === 'territorio-sintetico-e2e')!;
  for (const path of [
    `/api/v1/campaigns/${inaccessible.id}/dashboard/overview`,
    `/api/v1/campaigns/${inaccessible.id}/survey-studies`,
    `/api/v1/campaigns/${inaccessible.id}/activities`,
    `/api/v1/campaigns/${inaccessible.id}/needs`,
  ]) {
    const response = await request.get(path, { headers: analystHeaders });
    expect(response.status(), path).toBe(403);
  }
  const ai = await request.post(`/api/v1/campaigns/${inaccessible.id}/territory-ai/query`, {
    headers: analystHeaders,
    data: { question: 'Resume la campana' },
  });
  expect(ai.status()).toBe(403);
  expect((await ai.json()).detail.code).toBe('CAMPAIGN_ACCESS_DENIED');
});
