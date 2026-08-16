import { expect, type APIRequestContext, type Page } from '@playwright/test';

const configuredPassword = process.env.E2E_USER_PASSWORD;
if (!configuredPassword) throw new Error('E2E_USER_PASSWORD es obligatorio');
const password: string = configuredPassword;

export const e2eUsers = {
  admin: process.env.E2E_USER_NAME || 'admin_e2e',
  manager: 'manager_e2e',
  coordinator: 'coordinator_e2e',
  analyst: 'analyst_e2e',
  candidate: 'candidate_e2e',
  delegateA: 'delegate_e2e_a',
  delegateB: 'delegate_e2e_b',
  platformAdmin: 'platform_admin',
  alphaOwner: 'alpha_owner',
  alphaManager: 'alpha_manager',
  betaOwner: 'beta_owner',
  crossOrganization: 'cross_org_user',
} as const;

export async function apiToken(request: APIRequestContext, username = e2eUsers.admin) {
  const response = await request.post('/api/v1/auth/login', {
    form: { username, password },
  });
  expect(response.status(), `El usuario E2E ${username} debe poder autenticarse`).toBe(200);
  return (await response.json()).access_token as string;
}

export async function browserLogin(page: Page, username = e2eUsers.admin) {
  await page.goto('/login');
  await page.getByLabel('Correo o nombre de usuario').fill(username);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole('button', { name: /Iniciar sesi/ }).click();
  await expect(page).toHaveURL(/\/app/);
}
