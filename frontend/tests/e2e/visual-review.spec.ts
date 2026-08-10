import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

const password = process.env.E2E_USER_PASSWORD;
if (!password) throw new Error('E2E_USER_PASSWORD es obligatorio');
const sizes = [
  { width: 320, height: 800 },
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
];

async function adminData(request: APIRequestContext) {
  const login = await request.post('/api/v1/auth/login', {
    form: { username: 'admin_e2e', password: password! },
  });
  const access = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${access}` };
  const campaign = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items[0];
  const activities = await (
    await request.get(`/api/v1/campaigns/${campaign.id}/activities?page=1&page_size=10`, {
      headers,
    })
  ).json();
  const surveys = await (
    await request.get(`/api/v1/campaigns/${campaign.id}/surveys?page=1&page_size=20`, { headers })
  ).json();
  return {
    campaignId: campaign.id as string,
    activityId: activities.items[0].id as string,
    draftId: surveys.items.find((x: { status: string }) => x.status === 'DRAFT').id as string,
    publishedId: surveys.items.find((x: { status: string }) => x.status === 'PUBLISHED')
      .id as string,
  };
}

async function browserLogin(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Correo o nombre de usuario').fill('admin_e2e');
  await page.getByRole('textbox', { name: 'Contraseña' }).fill(password!);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await expect(page).toHaveURL(/\/app/);
}

test('revisión visual completa sin desbordamiento horizontal', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(300000);
  const data = await adminData(request);
  await page.setViewportSize(sizes[0]);
  await page.goto('/login');
  for (const size of sizes) {
    await page.setViewportSize(size);
    await page.screenshot({
      path: testInfo.outputPath(`login-${size.width}x${size.height}.png`),
      fullPage: true,
    });
  }
  await browserLogin(page);
  const base = `/app/campaigns/${data.campaignId}`;
  const routes = [
    ['dashboard', `${base}/dashboard`],
    ['actividades', `${base}/activities`],
    ['detalle-actividad', `${base}/activities/${data.activityId}`],
    ['necesidades', `${base}/needs`],
    ['compromisos', `${base}/commitments`],
    ['encuestas', `${base}/surveys`],
    ['constructor', `${base}/surveys/${data.draftId}`],
    ['captura', `${base}/surveys/${data.publishedId}/collect`],
    ['resultados', `${base}/surveys/${data.publishedId}/results`],
    ['csv', '/app/admin/data-imports'],
    ['geojson', '/app/admin/geometry-imports'],
    ['electoral', `${base}/electoral`],
    ['demografia', `${base}/demographics`],
    ['mapas', `${base}/maps`],
    ['informes', `${base}/reports`],
    ['alertas', `${base}/alerts`],
    ['usuarios', '/app/admin/users'],
    ['asignaciones', '/app/admin/assignments'],
    ['auditoria', '/app/admin/security-audit'],
    ['/403', '/403'],
    ['/404', '/ruta-visual-inexistente'],
  ] as const;
  for (const size of sizes) {
    await page.setViewportSize(size);
    for (const [name, route] of routes) {
      await page.evaluate((url) => {
        history.pushState({}, '', url);
        dispatchEvent(new PopStateEvent('popstate'));
      }, route);
      await expect(page.locator('main').first()).toBeVisible();
      await expect(page.getByText(/Cargando informaci/)).toHaveCount(0, { timeout: 15000 });
      const overflow = await page.evaluate(() => {
        if (document.documentElement.scrollWidth <= window.innerWidth + 1) return [];
        return [...document.querySelectorAll('body *')]
          .map((element) => {
            const rect = element.getBoundingClientRect();
            return {
              tag: element.tagName,
              role: element.getAttribute('role'),
              className: element.className?.toString().slice(0, 100),
              left: Math.round(rect.left),
              right: Math.round(rect.right),
              width: Math.round(rect.width),
            };
          })
          .filter((x) => x.right > window.innerWidth + 1 && x.left >= 0)
          .slice(0, 12);
      });
      expect(overflow, `${name} ${size.width}x${size.height} excede el viewport`).toEqual([]);
      await page.screenshot({
        path: testInfo.outputPath(`${name.replace('/', '')}-${size.width}x${size.height}.png`),
        fullPage: true,
      });
    }
  }
});
