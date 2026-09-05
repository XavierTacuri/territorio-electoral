import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { apiToken, browserLogin, e2eUsers } from './support/auth';

async function gualaceoCampaign(request: APIRequestContext, headers: Record<string, string>) {
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; slug: string; canton_id: number; organization_id: string }[];
  const campaign = campaigns.find((item) => item.slug === 'gualaceo-e2e-2027');
  if (!campaign) throw new Error('El fixture E2E requiere gualaceo-e2e-2027');
  return campaign;
}

async function syntheticCampaign(request: APIRequestContext, headers: Record<string, string>) {
  const campaigns = (
    await (await request.get('/api/v1/campaigns?page_size=100', { headers })).json()
  ).items as { id: string; slug: string }[];
  const campaign = campaigns.find((item) => item.slug === 'territorio-sintetico-e2e');
  if (!campaign) throw new Error('El fixture E2E requiere territorio-sintetico-e2e');
  return campaign;
}

async function pollingPlaces(request: APIRequestContext, headers: Record<string, string>, campaignId: string) {
  const body = (
    await (await request.get(`/api/v1/campaigns/${campaignId}/election-day/polling-places`, { headers })).json()
  ) as { items: { id: string; official_code: string; parish_id: number }[] };
  return body.items;
}

async function assignments(request: APIRequestContext, headers: Record<string, string>, campaignId: string) {
  const body = (
    await (await request.get(`/api/v1/campaigns/${campaignId}/election-day/assignments`, { headers })).json()
  ) as {
    items: {
      id: string;
      user_id: string;
      polling_place_id: string;
      board_id: string | null;
      status: string;
      checked_in_at: string | null;
      replaced_by_assignment_id: string | null;
    }[];
  };
  return body.items;
}

async function gotoElectionDay(page: Page, campaignId: string) {
  await page.goto(`/app/campaigns/${campaignId}/election-day`);
  await expect(page.getByRole('heading', { name: 'Jornada Electoral' })).toBeVisible();
}

test.describe('Modo Jornada Electoral', () => {
  test('CANDIDATE ve el Centro de Jornada con cobertura, mapa e incidencias recientes', async ({
    page,
    request,
  }) => {
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);

    await browserLogin(page, e2eUsers.candidate);
    await gotoElectionDay(page, campaign.id);
    await expect(page.getByText('Jornada activa')).toBeVisible();
    await expect(page.getByText('Recintos', { exact: true })).toBeVisible();
    await expect(page.getByText('Escuela Sintética Central', { exact: true })).toBeVisible();
    await expect(page.getByText('Colegio Sintético Norte', { exact: true })).toBeVisible();
    await expect(page.getByText('Casa Comunal Sintética', { exact: true })).toBeVisible();
    await expect(page.getByText('Incidencias recientes')).toBeVisible();
    await expect(
      page.getByText('cobertura, presencia, incidencias y documentación. No es un sistema de resultados.'),
    ).toBeVisible();
  });

  test('ANALYST ve la jornada en modo solo lectura, sin controles de gestión', async ({
    page,
    request,
  }) => {
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);

    await browserLogin(page, e2eUsers.analyst);
    await gotoElectionDay(page, campaign.id);
    await expect(page.getByRole('button', { name: 'Activar jornada' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Cerrar jornada' })).toHaveCount(0);

    const places = await pollingPlaces(request, headers, campaign.id);
    const place = places.find((p) => p.official_code === 'E2E-REC-01')!;
    await page.goto(`/app/campaigns/${campaign.id}/election-day/polling-places/${place.id}`);
    await expect(page.getByRole('button', { name: 'AGREGAR JUNTA' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'REPORTAR INCIDENCIA' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'ADJUNTAR DOCUMENTO' })).toHaveCount(0);
  });

  test('responsive: el Centro de Jornada no desborda horizontalmente en 375/768/1440', async ({
    page,
    request,
  }) => {
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    await browserLogin(page, e2eUsers.manager);
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await gotoElectionDay(page, campaign.id);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
        ),
        `no debe desbordar en ${width}px`,
      ).toBe(true);
    }
  });

  test('MANAGER resuelve una incidencia abierta desde el detalle del recinto', async ({
    page,
    request,
  }) => {
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    const places = await pollingPlaces(request, headers, campaign.id);
    const place = places.find((p) => p.official_code === 'E2E-REC-01')!;

    await browserLogin(page, e2eUsers.manager);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/polling-places/${place.id}`);
    await expect(page.getByText(/Falta material electoral sintético/)).toBeVisible();
    const resolveResponse = page.waitForResponse((r) => r.url().includes('/resolve'));
    await page.getByRole('button', { name: 'Resolver' }).click();
    expect((await resolveResponse).status()).toBe(200);
    await expect(page.getByText(/Logística — Resuelta/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Resolver' })).toHaveCount(0);
  });

  test('MANAGER reemplaza una asignación desde la UI conservando el check-in original', async ({
    page,
    request,
  }) => {
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    const places = await pollingPlaces(request, headers, campaign.id);
    const place1 = places.find((p) => p.official_code === 'E2E-REC-01')!;
    const place2 = places.find((p) => p.official_code === 'E2E-REC-02')!;
    const list = await assignments(request, headers, campaign.id);
    const delegateAAssignment = list.find(
      (a) => a.polling_place_id === place1.id && a.status === 'CHECKED_IN' && a.board_id,
    )!;
    expect(delegateAAssignment.checked_in_at).not.toBeNull();
    // delegate_e2e_b ya existe como personal de esta jornada (asignado en el
    // recinto 2 por el fixture): se reutiliza su usuario, no se crea uno nuevo.
    const delegateBId = list.find((a) => a.polling_place_id === place2.id)!.user_id;

    await browserLogin(page, e2eUsers.manager);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/polling-places/${place1.id}`);
    await expect(page.getByText(/Delegado de junta/)).toBeVisible();
    await page.getByRole('button', { name: 'REEMPLAZAR' }).first().click();
    await expect(page.getByRole('heading', { name: 'Reemplazar personal asignado' })).toBeVisible();
    await page.getByLabel('Nuevo usuario').click();
    const replaceResponse = page.waitForResponse((r) => r.url().includes('/replace'));
    await page.getByRole('option', { name: /delegate_e2e_b/ }).click();
    await page.getByRole('button', { name: 'Confirmar reemplazo' }).click();
    expect((await replaceResponse).status()).toBe(200);
    await expect(page.getByText('Personal reemplazado.')).toBeVisible();

    const after = await assignments(request, headers, campaign.id);
    const oldRow = after.find((a) => a.id === delegateAAssignment.id)!;
    expect(oldRow.status).toBe('REPLACED');
    // §52: el check-in original nunca se borra al reemplazar la asignación.
    expect(oldRow.checked_in_at).toBe(delegateAAssignment.checked_in_at);
    const newRow = after.find((a) => a.id === oldRow.replaced_by_assignment_id);
    expect(newRow?.user_id).toBe(delegateBId);
  });

  test('Coordinador confirma presencia, reporta incidencia y adjunta documento sin conexión; sincroniza una sola vez', async ({
    page,
    request,
    context,
  }) => {
    test.setTimeout(120000);
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);

    await browserLogin(page, e2eUsers.delegateB);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/my`);
    await expect(page.getByRole('heading', { name: 'Mi Jornada' })).toBeVisible();
    await expect(page.getByText(/Escuela Sintética Central|Colegio Sintético Norte/)).toBeVisible({
      timeout: 15000,
    });

    await context.setOffline(true);
    await expect(page.getByText('Sin conexión: los registros se guardan en el dispositivo')).toBeVisible();

    await page.getByRole('button', { name: 'CONFIRMAR PRESENCIA' }).click();
    await expect(
      page.getByText('Guardado en el dispositivo. Se sincronizará con el servidor.'),
    ).toBeVisible();

    await page.getByRole('button', { name: 'REPORTAR INCIDENCIA' }).click();
    await page.getByLabel('Descripción').fill('Sin conexión eléctrica en la junta (offline E2E).');
    await page.getByRole('button', { name: 'Guardar incidencia' }).click();
    await expect(
      page.getByText('Incidencia guardada en el dispositivo. Se sincronizará con el servidor.'),
    ).toBeVisible();

    await page.setInputFiles('input[type="file"][accept*="image"]', {
      name: 'acta-offline.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0]),
    });
    await expect(
      page.getByText('Documento guardado en el dispositivo. Se sincronizará con el servidor.'),
    ).toBeVisible();
    await expect(page.getByText('Pendientes de sincronización: 3')).toBeVisible();

    await context.setOffline(false);
    await page.getByRole('button', { name: 'Sincronizar ahora' }).click();
    await expect(page.getByText(/3 registro.*sincronizado/i)).toBeVisible({ timeout: 20000 });
    await expect(page.getByText('Pendientes de sincronización: 0')).toBeVisible();

    // Never a second, duplicate upload from a stray re-sync.
    await expect(page.getByRole('button', { name: 'Sincronizar ahora' })).toBeDisabled();

    const delegateBToken = await apiToken(request, e2eUsers.delegateB);
    const delegateBHeaders = { Authorization: 'Bearer ' + delegateBToken };
    const my = await (
      await request.get(`/api/v1/campaigns/${campaign.id}/election-day/my-assignment`, {
        headers: delegateBHeaders,
      })
    ).json();
    expect(my.status).toBe('CHECKED_IN');

    const incidents = (
      await (
        await request.get(`/api/v1/campaigns/${campaign.id}/election-day/incidents`, { headers })
      ).json()
    ).items as { description: string }[];
    expect(incidents.some((i) => i.description.includes('offline E2E'))).toBe(true);

    const documents = (
      await (
        await request.get(
          `/api/v1/campaigns/${campaign.id}/election-day/documents?polling_place_id=${my.polling_place_id}`,
          { headers },
        )
      ).json()
    ).items as { id: string; mime_type: string; document_type: string }[];
    const uploaded = documents.find((d) => d.mime_type === 'image/jpeg');
    expect(uploaded).toBeTruthy();
    // §2/§98: nunca un campo de votos/resultado — solo metadatos operativos del documento.
    expect(Object.keys(uploaded!)).not.toContain('votes');
    expect(Object.keys(uploaded!)).not.toContain('result');

    const download = await request.get(
      `/api/v1/campaigns/${campaign.id}/election-day/documents/${uploaded!.id}/download`,
      { headers },
    );
    expect(download.status()).toBe(200);
    const bytes = Buffer.from(await download.body());
    expect(bytes.subarray(0, 3).equals(Buffer.from([0xff, 0xd8, 0xff]))).toBe(true);
  });

  test('RBAC: el alcance territorial del Coordinator limita incidencias y juntas fuera de su parroquia asignada', async ({
    request,
  }) => {
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    const places = await pollingPlaces(request, headers, campaign.id);
    const place1 = places.find((p) => p.official_code === 'E2E-REC-01')!; // parroquia asignada a coordinator_e2e
    const place2 = places.find((p) => p.official_code === 'E2E-REC-02')!; // fuera de su alcance

    const coordinatorToken = await apiToken(request, e2eUsers.coordinator);
    const coordinatorHeaders = { Authorization: 'Bearer ' + coordinatorToken };

    const allowed = await request.get(
      `/api/v1/campaigns/${campaign.id}/election-day/polling-places/${place1.id}/boards`,
      { headers: coordinatorHeaders },
    );
    expect(allowed.status()).toBe(200);

    const denied = await request.get(
      `/api/v1/campaigns/${campaign.id}/election-day/polling-places/${place2.id}/boards`,
      { headers: coordinatorHeaders },
    );
    expect(denied.status()).toBe(403);

    const deniedIncident = await request.post(`/api/v1/campaigns/${campaign.id}/election-day/incidents`, {
      headers: coordinatorHeaders,
      data: { polling_place_id: place2.id, category: 'OTHER', description: 'Fuera de alcance E2E' },
    });
    expect(deniedIncident.status()).toBe(403);
  });

  test('RBAC: un usuario sin acceso a la organización no puede leer la jornada; otra campaña no ve esta jornada', async ({
    request,
  }) => {
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    const other = await syntheticCampaign(request, headers);

    const limitOwnerToken = await apiToken(request, 'limit_owner');
    const limitOwnerHeaders = { Authorization: 'Bearer ' + limitOwnerToken };
    const forbidden = await request.get(`/api/v1/campaigns/${campaign.id}/election-day/operation`, {
      headers: limitOwnerHeaders,
    });
    expect(forbidden.status()).toBe(403);

    const otherOperation = await request.get(
      `/api/v1/campaigns/${other.id}/election-day/operation`,
      { headers },
    );
    expect(otherOperation.status()).toBe(404);
  });

  test('Territorio IA responde preguntas factuales de jornada y bloquea preguntas sobre ventaja/resultados', async ({
    request,
  }) => {
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);

    const factual = await request.post(`/api/v1/campaigns/${campaign.id}/territory-ai/query`, {
      headers,
      data: { question: '¿Cuál es la cobertura y el estado operativo de la jornada electoral?' },
    });
    expect(factual.status()).toBe(200);
    const factualBody = await factual.json();
    expect(factualBody.intent).toBe('ELECTION_DAY_OPERATIONS');
    expect(factualBody.answer).toMatch(/Cobertura de recintos/);
    expect(factualBody.answer).not.toMatch(/gan(a|ó)|resultado final|proyección/i);

    const blocked = await request.post(`/api/v1/campaigns/${campaign.id}/territory-ai/query`, {
      headers,
      data: { question: '¿Qué actas muestran ventaja en los recintos de la jornada?' },
    });
    expect(blocked.status()).toBe(200);
    const blockedBody = await blocked.json();
    expect(blockedBody.status).toBe('BLOCKED');
    expect(blockedBody.answer).toMatch(/No realizo predicciones de ganador/);
  });

  test('ADMIN importa recintos y juntas desde el Data Hub y aparecen en Modo Jornada', async ({
    page,
    request,
  }) => {
    test.setTimeout(60000);
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    const canton = await (
      await request.get(`/api/v1/cantons/${campaign.canton_id}`, { headers })
    ).json();
    const provinces = (await (await request.get('/api/v1/provinces', { headers })).json()) as {
      id: number;
      code: string;
    }[];
    const province = provinces.find((p) => p.id === canton.province_id)!;
    const parishes = (await (
      await request.get(`/api/v1/parishes?canton_id=${campaign.canton_id}`, { headers })
    ).json()) as { dpa_code: string }[];
    const parish = parishes[0];
    const stamp = Date.now();
    const placeCode = `DH-E2E-${stamp}`;
    const boardCode = `${placeCode}-J01`;

    const placesSourceResponse = await request.post('/api/v1/data-sources', {
      headers,
      data: {
        code: `DH_PP_${stamp}`,
        institution: 'Consejo Nacional Electoral',
        dataset_name: 'Recintos Data Hub E2E',
        dataset_type: 'CNE_POLLING_PLACES',
      },
    });
    expect(placesSourceResponse.status()).toBe(201);
    const boardsSourceResponse = await request.post('/api/v1/data-sources', {
      headers,
      data: {
        code: `DH_BOARDS_${stamp}`,
        institution: 'Consejo Nacional Electoral',
        dataset_name: 'Juntas Data Hub E2E',
        dataset_type: 'CNE_ELECTORAL_BOARDS',
      },
    });
    expect(boardsSourceResponse.status()).toBe(201);

    await browserLogin(page, e2eUsers.admin);
    await page.goto('/app/admin/official-data/election-day/polling-places');
    await page.getByLabel('Fuente').click();
    await page.getByRole('option', { name: /Recintos Data Hub E2E/ }).click();
    await page.setInputFiles('input[type="file"]', {
      name: 'recintos.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(
        `process_code,province_dpa,canton_dpa,parish_dpa,polling_place_code,polling_place_name,polling_place_address,polling_place_latitude,polling_place_longitude\nE2E_ELECTION_DAY_2027,${province.code},${canton.dpa_code},${parish.dpa_code},${placeCode},Recinto Data Hub E2E,,,\n`,
      ),
    });
    await page.getByRole('button', { name: 'VALIDAR' }).click();
    await expect(page.getByText('VALIDATED')).toBeVisible();
    await page.getByRole('button', { name: 'EJECUTAR' }).click();
    await expect(page.getByText('Recintos importados correctamente.')).toBeVisible();

    await page.goto('/app/admin/official-data/election-day/boards');
    await page.getByLabel('Fuente').click();
    await page.getByRole('option', { name: /Juntas Data Hub E2E/ }).click();
    await page.setInputFiles('input[type="file"]', {
      name: 'juntas.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(
        `process_code,polling_place_code,board_code,board_number,sex_category,registered_voters\nE2E_ELECTION_DAY_2027,${placeCode},${boardCode},1,MIXED,300\n`,
      ),
    });
    await page.getByRole('button', { name: 'VALIDAR' }).click();
    await expect(page.getByText('VALIDATED')).toBeVisible();
    await page.getByRole('button', { name: 'EJECUTAR' }).click();
    await expect(page.getByText('Juntas importadas correctamente.')).toBeVisible();

    await page.goto(`/app/campaigns/${campaign.id}/election-day`);
    await expect(page.getByText('Recinto Data Hub E2E')).toBeVisible();

    const places = await pollingPlaces(request, headers, campaign.id);
    const imported = places.find((p) => p.official_code === placeCode);
    expect(imported).toBeTruthy();
    const boards = await (
      await request.get(
        `/api/v1/campaigns/${campaign.id}/election-day/polling-places/${imported!.id}/boards`,
        { headers },
      )
    ).json();
    expect(boards.some((b: { official_code: string }) => b.official_code === boardCode)).toBe(true);
  });

  test('un código de junta duplicado muestra un error visible en español sin perder los datos escritos', async ({
    page,
    request,
  }) => {
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);
    const places = await pollingPlaces(request, headers, campaign.id);
    const place1 = places.find((p) => p.official_code === 'E2E-REC-01')!;

    await browserLogin(page, e2eUsers.manager);
    await page.goto(`/app/campaigns/${campaign.id}/election-day/polling-places/${place1.id}`);
    await expect(page.getByText('E2E-REC-01-J01')).toBeVisible();
    await page.getByRole('button', { name: 'AGREGAR JUNTA' }).click();
    // Reutiliza deliberadamente un código de junta que ya existe en este recinto (§34/§92 del seed).
    await page.getByLabel('Código de junta').fill('E2E-REC-01-J01');
    await page.getByRole('button', { name: 'Guardar' }).click();
    await expect(page.getByText('No fue posible crear la junta.')).toBeVisible();
    // El diálogo permanece abierto y el texto escrito no se pierde.
    await expect(page.getByRole('heading', { name: 'Agregar junta' })).toBeVisible();
    await expect(page.getByLabel('Código de junta')).toHaveValue('E2E-REC-01-J01');
    // La página sigue operativa: no queda en una pantalla de error global.
    await page.getByRole('button', { name: 'Cancelar' }).click();
    await expect(page.getByRole('heading', { name: 'Agregar junta' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Escuela Sintética Central' })).toBeVisible();
  });

  test('MANAGER cierra la jornada y genera el Informe de Jornada Electoral', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const adminToken = await apiToken(request);
    const headers = { Authorization: 'Bearer ' + adminToken };
    const campaign = await gualaceoCampaign(request, headers);

    await browserLogin(page, e2eUsers.manager);
    await gotoElectionDay(page, campaign.id);
    await page.getByRole('button', { name: 'Cerrar jornada' }).click();
    await expect(page.getByRole('heading', { name: 'Cerrar jornada' })).toBeVisible();
    const closeResponse = page.waitForResponse((r) => r.url().endsWith('/operation/close'));
    await page.getByRole('button', { name: 'Confirmar cierre' }).click();
    expect((await closeResponse).status()).toBe(200);
    await expect(page.getByText('Jornada cerrada')).toBeVisible();

    await page.goto(`/app/campaigns/${campaign.id}/reports`);
    await page.getByLabel('Tipo de informe').click();
    await page.getByRole('option', { name: 'Informe de jornada electoral' }).click();
    const title = 'Informe de jornada E2E ' + Date.now();
    await page.getByLabel('Título del informe').fill(title);
    const generateResponse = page.waitForResponse(
      (r) => r.url().endsWith('/reports/generate') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Exportar PDF' }).click();
    expect((await generateResponse).status()).toBe(201);
    await expect(page.getByText(title)).toBeVisible();

    const row = page.getByRole('row').filter({ hasText: title });
    const downloadResponse = page.waitForResponse((r) => r.url().includes('/download'));
    const downloadPromise = page.waitForEvent('download');
    await row.getByRole('button', { name: 'Descargar' }).click();
    const [response, download] = await Promise.all([downloadResponse, downloadPromise]);
    expect(response.headers()['content-disposition']).toContain('attachment');
    const stream = await download.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream) chunks.push(Buffer.from(chunk));
    expect(Buffer.concat(chunks).subarray(0, 4).toString()).toBe('%PDF');
  });
});
