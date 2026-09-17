import { test, expect } from '@playwright/test';
import { browserLogin } from './support/auth';

test('evaluación, reconocimiento, resolución y deduplicación reales de alerta', async ({
  page,
}) => {
  await browserLogin(page);
  await page.getByLabel('Campaña').click();
  await page.getByRole('option', { name: 'Gualaceo E2E 2027' }).click();
  await page.getByRole('link', { name: 'Centro de alertas' }).click();
  let response = page.waitForResponse((r) => r.url().endsWith('/evaluate'));
  await page.getByRole('button', { name: 'Evaluar reglas' }).click();
  expect((await response).status()).toBe(200);
  // El Centro de alertas ahora abre en Activas por defecto (§2.3); se
  // selecciona explícitamente para no depender de ese valor inicial.
  const activeResponse = page.waitForResponse((r) => r.url().includes('state=ACTIVE'));
  await page.getByRole('combobox', { name: /Estado/ }).click();
  await page.getByRole('option', { name: 'Activas' }).click();
  expect((await activeResponse).status()).toBe(200);
  const rowsBefore = await page.getByRole('row').count();
  const row = page
    .getByRole('row')
    .filter({ has: page.getByRole('cell', { name: 'Pendiente', exact: true }) })
    .first();
  const title = (await row.getByRole('cell').first().textContent())!;
  await row.getByRole('button', { name: 'Gestionar' }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Nota').fill('Revisión operativa E2E');
  response = page.waitForResponse((r) => r.url().endsWith('/acknowledge'));
  await dialog.getByRole('button', { name: 'Confirmar' }).click();
  expect((await response).status()).toBe(200);
  // Revisada (ACKNOWLEDGED) sigue agrupada bajo Activas: la fila conserva
  // su insignia de estado "Revisada" en la celda, solo cambia el filtro.
  await page.getByRole('combobox', { name: /Estado/ }).click();
  await page.getByRole('option', { name: 'Activas' }).click();
  await page
    .getByRole('row')
    .filter({ hasText: title })
    .getByRole('button', { name: 'Gestionar' })
    .first()
    .click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Acción').click();
  await page.getByRole('option', { name: 'Resolver' }).click();
  response = page.waitForResponse((r) => r.url().endsWith('/resolve'));
  await dialog.getByRole('button', { name: 'Confirmar' }).click();
  expect((await response).status()).toBe(200);
  await page.getByRole('combobox', { name: /Estado/ }).click();
  await page.getByRole('option', { name: 'Resueltas' }).click();
  await expect(page.getByRole('row').filter({ hasText: title }).first()).toBeVisible();
  await page.getByRole('combobox', { name: /Estado/ }).click();
  await page.getByRole('option', { name: 'Activas' }).click();
  response = page.waitForResponse((r) => r.url().endsWith('/evaluate'));
  await page.getByRole('button', { name: 'Evaluar reglas' }).click();
  expect((await response).status()).toBe(200);
  await expect.poll(() => page.getByRole('row').count()).toBe(rowsBefore);
});
