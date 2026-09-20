import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers, logout } from './support/auth';
import { uniqueE2eValue } from './support/run-data';

// Navega directo por URL a partir del API, igual que candidate-navigation.spec.ts —
// el selector de campaña de la topbar filtra por la organización activa, y
// "Gualaceo E2E 2027" no siempre está bajo la organización seleccionada por
// defecto para cada cuenta E2E, así que depender del dropdown es frágil.
async function openGualaceoElectionDay(
  page: Page,
  request: APIRequestContext,
  username: string,
): Promise<string> {
  const token = await apiToken(request, username);
  const response = await request.get('/api/v1/campaigns?page_size=100', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status()).toBe(200);
  const campaigns = (await response.json()) as { items: { id: string; name: string }[] };
  const campaign = campaigns.items.find((item) => item.name === 'Gualaceo E2E 2027');
  expect(campaign).toBeTruthy();
  await page.goto(`/app/campaigns/${campaign!.id}/election-day`);
  await expect(page.getByRole('heading', { name: 'Jornada Electoral' })).toBeVisible();
  return campaign!.id;
}

// invite_url ahora lleva el token en el fragment (#token=...), nunca en el
// path: el fragment nunca sale del navegador hacia el servidor HTTP.
async function readInviteUrl(page: Page): Promise<string> {
  await expect(page.getByRole('heading', { name: 'Invitación creada' })).toBeVisible();
  const url = await page.locator('input[readonly]').first().inputValue();
  await page.getByRole('button', { name: 'Cerrar' }).click();
  expect(url).toContain('#token=');
  return url;
}

function tokenFromInviteUrl(inviteUrl: string): string {
  return inviteUrl.split('#token=')[1];
}

async function fillNewAccountForm(page: Page, password: string) {
  await page.getByLabel('Nueva contraseña', { exact: false }).fill(password);
  await page.getByLabel('Confirmar contraseña', { exact: false }).fill(password);
  await page.getByRole('button', { name: 'ACTIVAR MI ACCESO' }).click();
}

// Login EN LA MISMA página de invitación (nunca navega a /login): así el
// flujo de "cuenta existente" nunca puede terminar en /403 por perder el
// contexto de la invitación al cambiar de ruta.
async function fillInlineLogin(page: Page, password: string) {
  await page.getByLabel('Contraseña', { exact: false }).fill(password);
  await page.getByRole('button', { name: 'INICIAR SESIÓN Y ACEPTAR' }).click();
}

test('CANDIDATE invita a un Delegado de recinto: token en fragment, cuenta nueva con login automático, Mi Jornada y accesos bloqueados', async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const email = uniqueE2eValue('delegate-invite') + '@example.com';
  const staffPassword = 'DelegadaPass123';

  await browserLogin(page, e2eUsers.candidate);
  const campaignId = await openGualaceoElectionDay(page, request, e2eUsers.candidate);

  await page.getByRole('button', { name: 'AGREGAR PERSONAL' }).click();
  await page.getByLabel('Nombre').fill('Delegada');
  await page.getByLabel('Apellido').fill('Invitada E2E');
  await page.getByLabel('Correo').fill(email);
  await page.getByRole('combobox', { name: 'Recintos' }).click();
  await page.getByRole('option', { name: 'Casa Comunal Sintética' }).click();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Crear invitación' }).click();

  const inviteUrl = await readInviteUrl(page);
  const token = tokenFromInviteUrl(inviteUrl);
  await logout(page);

  await page.goto(inviteUrl);
  // El fragment se limpia de inmediato: la URL nunca debe seguir mostrando el token.
  await expect(page.getByText('Delegado de recinto')).toBeVisible();
  expect(page.url()).not.toContain(token);
  expect(page.url()).not.toContain('#token=');

  await expect(page.getByText('Casa Comunal Sintética')).toBeVisible();
  await fillNewAccountForm(page, staffPassword);
  await expect(page.getByText('Tu acceso a la Jornada Electoral está listo.')).toBeVisible();

  // La cuenta nueva queda autenticada de inmediato: "IR A MI JORNADA" va
  // directo a /app/election-day, sin pasar por /login.
  await page.getByRole('button', { name: 'IR A MI JORNADA' }).click();
  await expect(page).toHaveURL(/\/app\/election-day$/);
  await expect(page.getByRole('heading', { name: 'Mis jornadas electorales' })).toBeVisible();
  await expect(page.getByText('Gualaceo E2E 2027')).toBeVisible();

  // Selector de campaña general reemplazado por el contexto de Jornada (§4).
  await expect(page.getByText('Jornada Electoral').first()).toBeVisible();
  await expect(page.getByText('No existen campañas')).toHaveCount(0);

  // Navegación reducida (§22): solo Jornada Electoral, nunca Panorama/Dashboard.
  await expect(page.getByRole('link', { name: 'Panorama electoral' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Dashboard' })).toHaveCount(0);

  await page.getByRole('link', { name: 'MI JORNADA', exact: true }).click();
  await expect(page.getByText('Casa Comunal Sintética')).toBeVisible();

  // Bloqueo server-side de URLs directas (§22).
  await page.goto(`/app/campaigns/${campaignId}/panorama`);
  await expect(
    page.getByText('Parte de la información no está disponible en este momento.'),
  ).toBeVisible();

  await page.goto(`/app/campaigns/${campaignId}/election-day`);
  await expect(page).toHaveURL('/403');
  await expect(page.getByText('No tienes permisos para acceder a esta página.')).toBeVisible();
});

test('cuenta existente: segunda invitación a la misma persona se acepta con login en la propia página, sin CampaignUser y sin terminar en /403', async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const email = uniqueE2eValue('existing-user') + '@example.com';
  const password = 'ExistingUserPass123';

  // 1) Se crea la cuenta por primera vez, como Delegado de otro recinto.
  await browserLogin(page, e2eUsers.candidate);
  const campaignId = await openGualaceoElectionDay(page, request, e2eUsers.candidate);
  await page.getByRole('button', { name: 'AGREGAR PERSONAL' }).click();
  await page.getByLabel('Nombre').fill('Existente');
  await page.getByLabel('Apellido').fill('E2E');
  await page.getByLabel('Correo').fill(email);
  await page.getByRole('combobox', { name: 'Recintos' }).click();
  await page.getByRole('option', { name: 'Casa Comunal Sintética' }).click();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Crear invitación' }).click();
  const firstInviteUrl = await readInviteUrl(page);
  await logout(page);
  await page.goto(firstInviteUrl);
  await fillNewAccountForm(page, password);
  await expect(page.getByText('Tu acceso a la Jornada Electoral está listo.')).toBeVisible();
  // La cuenta nueva ya quedó autenticada in-page; hay que entrar a la app
  // (AppShell) antes de poder usar el menú de usuario para cerrar sesión.
  await page.getByRole('button', { name: 'IR A MI JORNADA' }).click();
  await expect(page).toHaveURL(/\/app\/election-day$/);
  await logout(page);

  // 2) La misma persona recibe una SEGUNDA invitación, ahora como Validador.
  await browserLogin(page, e2eUsers.manager);
  await openGualaceoElectionDay(page, request, e2eUsers.manager);
  await page.getByRole('button', { name: 'AGREGAR PERSONAL' }).click();
  await page.getByLabel('Nombre').fill('Existente');
  await page.getByLabel('Apellido').fill('E2E');
  await page.getByLabel('Correo').fill(email);
  await page.getByLabel('Perfil').click();
  await page.getByRole('option', { name: 'Validador de actas' }).click();
  await page.getByRole('button', { name: 'Crear invitación' }).click();
  const secondInviteUrl = await readInviteUrl(page);
  await logout(page);

  // 3) Abre la segunda invitación: detecta cuenta existente, inicia sesión
  // EN LA MISMA página (nunca navega a /login) y acepta.
  await page.goto(secondInviteUrl);
  await expect(page.getByText('Ya tienes una cuenta en Territorio Electoral.')).toBeVisible();
  await expect(page.getByText('Validador de actas')).toBeVisible();
  await fillInlineLogin(page, password);
  await expect(page.getByText('Tu acceso a la Jornada Electoral está listo.')).toBeVisible();

  await page.getByRole('button', { name: 'IR A MI JORNADA' }).click();
  await expect(page).toHaveURL(/\/app\/election-day$/);
  await expect(page).not.toHaveURL('/403');

  // Ambos perfiles conviven en la misma cuenta operativa, sin CampaignUser.
  await expect(page.getByRole('link', { name: 'MI JORNADA', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'VALIDACIÓN DE ACTAS', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Validación de actas' })).toBeVisible();

  await page.goto(`/app/campaigns/${campaignId}/election-day`);
  await expect(page).toHaveURL('/403');

  // Verificación server-side: un único User, sin CampaignUser, un único
  // ElectionDayAssignment por perfil.
  const adminToken = await apiToken(request, e2eUsers.admin);
  const usersResp = await request.get(`/api/v1/users?search=${encodeURIComponent(email)}`, {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
  expect(usersResp.status()).toBe(200);
  const users = (await usersResp.json()).items as { id: string }[];
  expect(users).toHaveLength(1);
});

test('CAMPAIGN_MANAGER invita a un Validador de actas: aceptación y Control Center bloqueado', async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const email = uniqueE2eValue('validator-invite') + '@example.com';
  const staffPassword = 'ValidadorPass123';

  await browserLogin(page, e2eUsers.manager);
  const campaignId = await openGualaceoElectionDay(page, request, e2eUsers.manager);

  await page.getByRole('button', { name: 'AGREGAR PERSONAL' }).click();
  await page.getByLabel('Nombre').fill('Validador');
  await page.getByLabel('Apellido').fill('Invitado E2E');
  await page.getByLabel('Correo').fill(email);
  await page.getByLabel('Perfil').click();
  await page.getByRole('option', { name: 'Validador de actas' }).click();
  await page.getByRole('button', { name: 'Crear invitación' }).click();

  const inviteUrl = await readInviteUrl(page);
  await logout(page);

  await page.goto(inviteUrl);
  await expect(page.getByText('Validador de actas')).toBeVisible();
  await fillNewAccountForm(page, staffPassword);
  await expect(page.getByText('Tu acceso a la Jornada Electoral está listo.')).toBeVisible();

  await page.getByRole('button', { name: 'IR A MI JORNADA' }).click();
  await expect(page).toHaveURL(/\/app\/election-day$/);

  await page.getByRole('link', { name: 'VALIDACIÓN DE ACTAS', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Validación de actas' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'MI JORNADA', exact: true })).toHaveCount(0);

  await page.goto(`/app/campaigns/${campaignId}/election-day`);
  await expect(page).toHaveURL('/403');
});

test('el token de invitación nunca se expone por la API de listado/consulta ni en la URL', async ({
  page,
  request,
}) => {
  await browserLogin(page, e2eUsers.candidate);
  const campaignId = await openGualaceoElectionDay(page, request, e2eUsers.candidate);
  await page.getByRole('button', { name: 'AGREGAR PERSONAL' }).click();
  await page.getByLabel('Nombre').fill('Token');
  await page.getByLabel('Apellido').fill('Check E2E');
  await page.getByLabel('Correo').fill(uniqueE2eValue('token-check') + '@example.com');
  await page.getByRole('combobox', { name: 'Recintos' }).click();
  await page.getByRole('option', { name: 'Casa Comunal Sintética' }).click();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Crear invitación' }).click();
  const inviteUrl = await readInviteUrl(page);
  const token = tokenFromInviteUrl(inviteUrl);

  const candidateToken = await apiToken(request, e2eUsers.candidate);
  const listResponse = await request.get(
    `/api/v1/campaigns/${campaignId}/election-day/staff/invitations`,
    { headers: { Authorization: `Bearer ${candidateToken}` } },
  );
  const body = await listResponse.text();
  expect(body).not.toContain(token);
  expect(body).not.toContain('token_hash');

  // No debe existir ninguna ruta {token} en el OpenAPI servido por el propio backend
  // (fetch directo al backend: /openapi.json no pasa por el proxy del frontend).
  const openapiResp = await request.get('http://localhost:18000/openapi.json');
  const openapi = await openapiResp.json();
  const tokenPaths = Object.keys(openapi.paths).filter(
    (p: string) => p.includes('invitation') && p.includes('{token}'),
  );
  expect(tokenPaths).toEqual([]);

  // El preview real nunca acepta el token como query param.
  await page.goto(inviteUrl);
  await expect(page.getByText('Casa Comunal Sintética')).toBeVisible();
  expect(page.url()).not.toContain(token);
});
