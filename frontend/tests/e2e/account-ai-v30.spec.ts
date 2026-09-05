import { expect, test } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

const originalPassword = process.env.E2E_USER_PASSWORD;
if (!originalPassword) throw new Error('E2E_USER_PASSWORD es obligatorio');
const temporaryPassword = 'TemporalE2E456!';
const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

test('cambio de contraseña desde Mi cuenta revoca sesión y permite restauración legítima', async ({ page, request }) => {
  test.setTimeout(60_000);
  await browserLogin(page, e2eUsers.candidate);
  await page.waitForTimeout(1_000);
  await page.getByLabel('Abrir menú de usuario').click();
  await page.getByRole('menuitem', { name: 'Mi cuenta' }).click();
  await expect(page).toHaveURL(/\/app\/account/);
  await page.getByRole('tab', { name: 'Seguridad' }).click();
  await page.locator('input[type="password"]').nth(0).fill(originalPassword);
  await page.locator('input[type="password"]').nth(1).fill(temporaryPassword);
  await page.locator('input[type="password"]').nth(2).fill(temporaryPassword);
  await page.getByRole('button', { name: 'Cambiar contraseña' }).click();
  await expect(page.getByText('Contraseña actualizada correctamente. Inicia sesión nuevamente.')).toBeVisible();
  await expect(page).toHaveURL(/\/login/, { timeout: 5000 });

  expect((await request.post('/api/v1/auth/login', { form: { username: e2eUsers.candidate, password: originalPassword } })).status()).toBe(401);
  expect((await request.post('/api/v1/auth/login', { form: { username: e2eUsers.candidate, password: temporaryPassword } })).status()).toBe(200);

  await page.getByLabel('Correo o nombre de usuario').fill(e2eUsers.candidate);
  await page.locator('input[type="password"]').fill(temporaryPassword);
  await page.getByRole('button', { name: /Iniciar sesi/ }).click();
  await page.waitForTimeout(1_000);
  await page.getByLabel('Abrir menú de usuario').click();
  await page.getByRole('menuitem', { name: 'Mi cuenta' }).click();
  await page.getByRole('tab', { name: 'Seguridad' }).click();
  await page.locator('input[type="password"]').nth(0).fill(temporaryPassword);
  await page.locator('input[type="password"]').nth(1).fill(originalPassword);
  await page.locator('input[type="password"]').nth(2).fill(originalPassword);
  await page.getByRole('button', { name: 'Cambiar contraseña' }).click();
  await expect(page.getByText('Contraseña actualizada correctamente. Inicia sesión nuevamente.')).toBeVisible();
  await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
  expect((await request.post('/api/v1/auth/login', { form: { username: e2eUsers.candidate, password: originalPassword } })).status()).toBe(200);
});

test('ADMIN navega a configuración IA segura y prueba FakeProvider', async ({ page, request }) => {
  await browserLogin(page, e2eUsers.admin);
  await page.getByRole('link', { name: 'Configuración de IA' }).click();
  await expect(page).toHaveURL(/\/app\/admin\/ai-configuration/);
  await expect(page.getByRole('heading', { name: 'Configuración de IA' })).toBeVisible();
  await expect(page.getByText('Proveedor de pruebas')).toBeVisible();
  await expect(page.getByText('territory-ai-fake-v1')).toBeVisible();
  await page.getByRole('button', { name: 'Probar conexión' }).click();
  await expect(page.getByText('Conexión correcta.')).toBeVisible();
  const token = await apiToken(request);
  const response = await request.get('/api/v1/admin/ai-provider', { headers: auth(token) });
  const body = await response.json();
  expect(Object.keys(body).sort()).toEqual(['api_key_configured', 'model', 'provider', 'provider_label', 'status']);
  expect(JSON.stringify(body).toLowerCase()).not.toMatch(/authorization|secret|openai_api_key|bearer|hash/);
});

test('usuario no ADMIN no ve ni accede a configuración IA', async ({ page, request }) => {
  await browserLogin(page, e2eUsers.candidate);
  await expect(page.getByRole('link', { name: 'Configuración de IA' })).toHaveCount(0);
  await page.goto('/app/admin/ai-configuration');
  await expect(page).toHaveURL(/\/403/);
  const token = await apiToken(request, e2eUsers.candidate);
  expect((await request.get('/api/v1/admin/ai-provider', { headers: auth(token) })).status()).toBe(403);
  expect((await request.post('/api/v1/admin/ai-provider/test', { headers: auth(token) })).status()).toBe(403);
});
