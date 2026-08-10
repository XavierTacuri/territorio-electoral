import { expect, test } from '@playwright/test';

test('los botones del informe ejecutivo se muestran sin mojibake', async ({ page, request }, testInfo) => {
  const password = process.env.CURRENT_ELECTION_E2E_PASSWORD || 'admin';
  const login = await request.post('/api/v1/auth/login', { form: { username: 'admin', password } });
  expect(login.status()).toBe(200);
  const token = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = (await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()).items as Array<{ id: string }>;
  let campaignId = '';
  for (const campaign of campaigns) {
    if ((await request.get(`/api/v1/campaigns/${campaign.id}/current-election/analysis`, { headers })).status() === 200) {
      campaignId = campaign.id;
      break;
    }
  }
  expect(campaignId).not.toBe('');
  await page.goto('/login');
  await page.getByLabel('Correo o nombre de usuario').fill('admin');
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole('button', { name: /Iniciar sesi/ }).click();
  await expect(page).toHaveURL(/\/app/);
  await page.goto(`/app/campaigns/${campaignId}/current-election`);
  await expect(page.getByRole('button', { name: 'GENERAR INFORME PDF' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'GENERAR INFORME XLSX' })).toBeVisible();
  const block = page.getByText('DESCARGAR INFORME EJECUTIVO').locator('xpath=ancestor::div[contains(@class,"MuiPaper-root")]').first();
  await expect(block).not.toContainText(/Ã|Â|�/);
  await block.screenshot({ path: testInfo.outputPath('current-election-report-buttons.png') });
});
