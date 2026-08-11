import { expect, test } from '@playwright/test';
import { apiToken, browserLogin } from './support/auth';

test('los botones del informe ejecutivo se muestran sin mojibake', async ({
  page,
  request,
}, testInfo) => {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as Array<{ id: string }>;
  let campaignId = '';
  for (const campaign of campaigns) {
    if (
      (
        await request.get(`/api/v1/campaigns/${campaign.id}/current-election/analysis`, { headers })
      ).status() === 200
    ) {
      campaignId = campaign.id;
      break;
    }
  }
  expect(campaignId).not.toBe('');
  await browserLogin(page);
  await page.goto(`/app/campaigns/${campaignId}/current-election`);
  await expect(page.getByRole('button', { name: 'GENERAR INFORME PDF' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'GENERAR INFORME XLSX' })).toBeVisible();
  const block = page
    .getByText('DESCARGAR INFORME EJECUTIVO')
    .locator('xpath=ancestor::div[contains(@class,"MuiPaper-root")]')
    .first();
  await expect(block).not.toContainText(/Ã|Â|�/);
  await block.screenshot({ path: testInfo.outputPath('current-election-report-buttons.png') });
});
