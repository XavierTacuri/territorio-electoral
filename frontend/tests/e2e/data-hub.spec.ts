import { test, expect } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';
import { e2eRunId, uniqueE2eValue } from './support/run-data';

function rollCsv(processCode: string, snapshotDate: string, registeredVoters: number) {
  const header =
    'snapshot_date,process_code,geography_level,province_dpa,canton_dpa,parish_dpa,registered_voters,male_voters,female_voters,electoral_zones,juntas\n';
  const row = `${snapshotDate},${processCode},PARISH,01,0103,010350,${registeredVoters},${Math.floor(registeredVoters / 2)},${Math.ceil(registeredVoters / 2)},,\n`;
  return header + row;
}

// Derives a snapshot date unique to this run (not just today's date) so the shared,
// persistent E2E database never accumulates two versions with the same "Corte …" label
// across repeated executions.
function runUniqueDate(seed: string, offsetDays: number) {
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) % 100000;
  const date = new Date(Date.UTC(2031, 0, 1));
  date.setUTCDate(date.getUTCDate() + (hash % 3000) + offsetDays);
  return date.toISOString().slice(0, 10);
}

test('Centro de datos: catálogo, versión, activación y RBAC', async ({ page, request }) => {
  test.setTimeout(120000);
  const runId = e2eRunId;
  const sourceCode = uniqueE2eValue('DH_E2E_SOURCE').toUpperCase().replace(/-/g, '_');
  const processCode = uniqueE2eValue('DH_E2E_PROCESS').toUpperCase().replace(/-/g, '_');
  const sourceInstitution = `CNE Data Hub E2E ${runId}`;
  const sourceDatasetName = `Registro sintético Data Hub ${runId}`;
  const v1Date = runUniqueDate(runId, 0);
  const v2Date = runUniqueDate(runId, 10);
  const v1Label = `Corte ${v1Date}`;
  const v2Label = `Corte ${v2Date}`;
  const v1ElectionDate = `01/${v1Date.slice(5, 7)}/${v1Date.slice(0, 4)}`;

  const token = await apiToken(request);
  const headers = { Authorization: 'Bearer ' + token };
  const createSource = await request.post('/api/v1/data-sources', {
    headers,
    data: {
      code: sourceCode,
      institution: sourceInstitution,
      dataset_name: sourceDatasetName,
      dataset_type: 'CNE_ELECTORAL_ROLL_SNAPSHOT',
      is_official: true,
    },
  });
  expect(createSource.status()).toBe(201);

  await browserLogin(page);

  await test.step('catálogo del Centro de datos', async () => {
    await page.goto('/app/admin/data-hub');
    await expect(page.getByRole('heading', { name: 'Centro de datos de Ecuador' })).toBeVisible();
    await page.getByRole('link', { name: 'CNE · Registro electoral preelectoral' }).click();
    await expect(page.getByRole('heading', { name: 'CNE · Registro electoral preelectoral' })).toBeVisible();
  });

  await test.step('nueva importación V1 y creación de proceso electoral', async () => {
    await page.getByRole('link', { name: 'Nueva importación' }).click();
    await expect(page).toHaveURL(/official-data\/cne\/roll/);
    await page.getByLabel('Fuente CNE').click();
    await page.getByRole('option', { name: `${sourceInstitution} · ${sourceDatasetName}` }).click();
    await page.locator('input[type=file]').setInputFiles({
      name: 'roll-v1.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(rollCsv(processCode, v1Date, 1000)),
    });
    await expect(page.getByText('Este archivo requiere un proceso electoral que todavía no existe.')).toBeVisible();
    await page.getByLabel('Nombre').fill(`Proceso sintético Data Hub ${runId}`);
    await page.getByLabel('Fecha electoral (DD/MM/AAAA)').fill(v1ElectionDate);
    await page.getByRole('button', { name: 'CREAR PROCESO ELECTORAL' }).last().click();
    await expect(page.getByText('Existente ✅. Se reutilizará.')).toBeVisible();
    let response = page.waitForResponse((r) => r.url().endsWith('/data-imports/validate'));
    await page.getByRole('button', { name: 'VALIDAR SNAPSHOT' }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByText('Estado: VALIDATED')).toBeVisible();
    response = page.waitForResponse((r) => r.url().endsWith('/data-imports/execute'));
    await page.getByRole('button', { name: 'EJECUTAR' }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByText('Snapshot importado correctamente.')).toBeVisible();
  });

  await test.step('nueva importación V2 (segundo corte)', async () => {
    await page.getByLabel('Fuente CNE').click();
    await page.getByRole('option', { name: `${sourceInstitution} · ${sourceDatasetName}` }).click();
    await page.locator('input[type=file]').setInputFiles({
      name: 'roll-v2.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(rollCsv(processCode, v2Date, 900)),
    });
    await expect(page.getByText('Existente ✅. Se reutilizará.')).toBeVisible();
    let response = page.waitForResponse((r) => r.url().endsWith('/data-imports/validate'));
    await page.getByRole('button', { name: 'VALIDAR SNAPSHOT' }).click();
    expect((await response).status()).toBe(200);
    response = page.waitForResponse((r) => r.url().endsWith('/data-imports/execute'));
    await page.getByRole('button', { name: 'EJECUTAR' }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByText('Snapshot importado correctamente.')).toBeVisible();
  });

  await test.step('versionado: activar V1, luego V2 lo reemplaza sin perder V1', async () => {
    await page.goto('/app/admin/data-hub/CNE_ELECTORAL_ROLL_SNAPSHOT');
    const rowV1 = page.getByRole('row').filter({ hasText: v1Label });
    const rowV2 = page.getByRole('row').filter({ hasText: v2Label });
    await expect(rowV1).toBeVisible();
    await expect(rowV2).toBeVisible();
    await rowV1.getByRole('button', { name: 'Activar' }).click();
    let response = page.waitForResponse((r) => r.url().includes('/data-hub/versions/') && r.url().endsWith('/activate'));
    await page.getByRole('button', { name: 'Confirmar' }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByText(`Versión vigente: ${v1Label}`)).toBeVisible();
    await rowV2.getByRole('button', { name: 'Activar' }).click();
    response = page.waitForResponse((r) => r.url().includes('/data-hub/versions/') && r.url().endsWith('/activate'));
    await page.getByRole('button', { name: 'Confirmar' }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByText(`Versión vigente: ${v2Label}`)).toBeVisible();
    await expect(rowV1.getByText('Reemplazada')).toBeVisible();
    await expect(rowV1).toBeVisible();
    await expect(rowV2.getByText('Activa')).toBeVisible();
  });

  await test.step('ANALYST tiene visibilidad de solo lectura', async () => {
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await browserLogin(page, e2eUsers.analyst);
    await page.goto('/app/admin/data-hub/CNE_ELECTORAL_ROLL_SNAPSHOT');
    await expect(page.getByRole('heading', { name: 'CNE · Registro electoral preelectoral' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Nueva importación' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Activar' })).toHaveCount(0);
  });

  await test.step('rol sin acceso global (ej. administrador de organización) es rechazado', async () => {
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await browserLogin(page, e2eUsers.alphaManager);
    await page.goto('/app/admin/data-hub');
    await expect(page).toHaveURL(/\/403/);
  });
});
