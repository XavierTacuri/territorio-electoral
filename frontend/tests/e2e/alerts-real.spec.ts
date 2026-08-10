import { test, expect } from '@playwright/test';
const password = process.env.E2E_USER_PASSWORD;
if (!password) throw new Error('E2E_USER_PASSWORD es obligatorio');

test('evaluación, reconocimiento, resolución y deduplicación reales de alerta', async ({
  page,
}) => {
  await page.goto('/login');
  await page.getByLabel('Correo o nombre de usuario').fill('admin_e2e');
  await page.getByRole('textbox', { name: 'Contraseña' }).fill(password);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await page.getByLabel('Campaña').click();
  await page.getByRole('option', { name: 'Gualaceo E2E 2027' }).click();
  await page.getByRole('link', { name: 'Alertas' }).click();
  let response = page.waitForResponse((r) => r.url().endsWith('/evaluate'));
  await page.getByRole('button', { name: 'Evaluar reglas' }).click();
  expect((await response).status()).toBe(200);
  const openResponse = page.waitForResponse((r) => r.url().includes('status=OPEN'));
  await page.getByRole('combobox', { name: /Estado/ }).click();
  await page.getByRole('option', { name: 'OPEN' }).click();
  expect((await openResponse).status()).toBe(200);
  const rowsBefore = await page.getByRole('row').count();
  const row = page
    .getByRole('row')
    .filter({ has: page.getByRole('cell', { name: 'OPEN', exact: true }) })
    .first();
  const title = (await row.getByRole('cell').first().textContent())!;
  await row.getByRole('button', { name: 'Gestionar' }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Nota').fill('Revisión operativa E2E');
  response = page.waitForResponse((r) => r.url().endsWith('/acknowledge'));
  await dialog.getByRole('button', { name: 'Confirmar' }).click();
  expect((await response).status()).toBe(200);
  await page.getByRole('combobox', { name: /Estado/ }).click();
  await page.getByRole('option', { name: 'ACKNOWLEDGED' }).click();
  await page
    .getByRole('row')
    .filter({ hasText: title })
    .getByRole('button', { name: 'Gestionar' })
    .click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Acción').click();
  await page.getByRole('option', { name: 'Resolver' }).click();
  response = page.waitForResponse((r) => r.url().endsWith('/resolve'));
  await dialog.getByRole('button', { name: 'Confirmar' }).click();
  expect((await response).status()).toBe(200);
  await page.getByRole('combobox', { name: /Estado/ }).click();
  await page.getByRole('option', { name: 'RESOLVED' }).click();
  await expect(page.getByRole('row').filter({ hasText: title })).toBeVisible();
  await page.getByRole('combobox', { name: /Estado/ }).click();
  await page.getByRole('option', { name: 'OPEN' }).click();
  response = page.waitForResponse((r) => r.url().endsWith('/evaluate'));
  await page.getByRole('button', { name: 'Evaluar reglas' }).click();
  expect((await response).status()).toBe(200);
  await expect.poll(() => page.getByRole('row').count()).toBe(rowsBefore);
});
