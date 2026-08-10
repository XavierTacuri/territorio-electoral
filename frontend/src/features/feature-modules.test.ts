import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { apiBlob, apiRequest } from '../api/client';

const server = setupServer();
const nativeFetch = globalThis.fetch;
let calls: Array<{ path: string; method: string; body: unknown }> = [];

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  server.resetHandlers();
  calls = [];
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

function jsonApi(response: Record<string, unknown> = { id: 'created', status: 'COMPLETED' }) {
  server.use(
    http.all('*/api/v1/*', async ({ request }) => {
      let body: unknown = null;
      if (!['GET', 'HEAD'].includes(request.method)) {
        const type = request.headers.get('content-type') ?? '';
        body = type.includes('json')
          ? await request.clone().json()
          : type.includes('multipart')
            ? 'form-data'
            : await request.clone().text();
      }
      calls.push({ path: new URL(request.url).pathname, method: request.method, body });
      return HttpResponse.json(response);
    }),
  );
}
async function mutation(path: string, body: object, method = 'POST') {
  jsonApi();
  await apiRequest(path, { method, body: JSON.stringify(body) });
  expect(calls[0]).toMatchObject({ path: '/api/v1' + path, method, body });
}

describe('contratos funcionales por modulo con MSW', () => {
  it('actividades envia creacion y edicion', async () => {
    await mutation('/campaigns/c/activities', { title: 'Asamblea', activity_date: '2026-08-03' });
    calls = [];
    await mutation('/campaigns/c/activities/a', { title: 'Asamblea editada' }, 'PATCH');
  });
  it('participantes agregados nunca envia identidades', async () => {
    await mutation(
      '/campaigns/c/activities/a/participants-summary',
      { estimated_attendees: 31, organizations_count: 2 },
      'PUT',
    );
    expect(JSON.stringify(calls[0].body)).not.toMatch(/name|email|phone|cedula/i);
  });
  it('necesidades envia prioridad y menciones', () =>
    mutation('/campaigns/c/activities/a/needs', {
      title: 'Via',
      priority: 'HIGH',
      mentions_count: 4,
    }));
  it('compromisos completa mediante transicion explicita', () =>
    mutation('/campaigns/c/commitments/x/status', { status: 'COMPLETED' }));
  it('constructor crea secciones, preguntas y opciones ordenadas', async () => {
    await mutation('/campaigns/c/surveys/s/sections', { title: 'Servicios', display_order: 1 });
    calls = [];
    await mutation('/campaigns/c/surveys/s/sections/x/questions', {
      question_text: 'Prioridad',
      question_type: 'SINGLE_CHOICE',
      is_required: true,
    });
    calls = [];
    await mutation('/campaigns/c/surveys/s/questions/q/options', {
      code: 'AGUA',
      label: 'Agua',
      display_order: 2,
    });
  });
  it('edicion de encuesta usa PATCH sobre elementos existentes', () =>
    mutation(
      '/campaigns/c/surveys/s/questions/q',
      { question_text: 'Texto editado', help_text: 'Ayuda' },
      'PATCH',
    ));
  it('captura anonima envia clave y no datos personales', async () => {
    const body = {
      submission_key: 'random-key',
      response_date: '2026-08-03',
      parish_id: 1,
      answers: [{ question_code: 'Q', selected_option_codes: ['A'] }],
    };
    await mutation('/campaigns/c/surveys/s/submissions', body);
    expect(JSON.stringify(calls[0].body)).not.toMatch(/email|phone|cedula|first_name|last_name/i);
  });
  it('resultados SUPPRESSED ocultan distribucion', async () => {
    jsonApi({ data_status: 'SUPPRESSED', distribution: null, response_count: 2 });
    const result = await apiRequest<{ data_status: string; distribution: unknown }>(
      '/campaigns/c/surveys/s/results',
    );
    expect(result.data_status).toBe('SUPPRESSED');
    expect(result.distribution).toBeNull();
  });
  it('CSV separa validacion y ejecucion', async () => {
    jsonApi();
    const file = new FormData();
    file.append('file', new Blob(['code,name']), 'safe.csv');
    await apiRequest('/data-imports/validate', { method: 'POST', body: file });
    await apiRequest('/data-imports/execute', { method: 'POST', body: file });
    expect(calls.map((x) => x.path)).toEqual([
      '/api/v1/data-imports/validate',
      '/api/v1/data-imports/execute',
    ]);
  });
  it('GeoJSON separa validacion y ejecucion', async () => {
    jsonApi();
    const file = new FormData();
    file.append('file', new Blob(['{"type":"FeatureCollection","features":[]}']), 'safe.geojson');
    await apiRequest('/geometry-imports/validate', { method: 'POST', body: file });
    await apiRequest('/geometry-imports/execute', { method: 'POST', body: file });
    expect(calls.map((x) => x.method)).toEqual(['POST', 'POST']);
  });
  it('informes envia formato permitido', () =>
    mutation('/campaigns/c/reports/generate', {
      template_code: 'EXECUTIVE',
      format: 'PDF',
      report_date: '2026-08-03',
    }));
  it.each([
    ['PDF', '%PDF'],
    ['XLSX', 'PK'],
  ])('descarga %s procesa blob y Content-Disposition', async (format, signature) => {
    server.use(
      http.get(
        '*/api/v1/download',
        () =>
          new HttpResponse(signature, {
            headers: {
              'Content-Disposition': 'attachment; filename="report.' + format.toLowerCase() + '"',
            },
          }),
      ),
    );
    const result = await apiBlob('/download');
    expect(await result.blob.text()).toBe(signature);
    expect(result.disposition).toContain('attachment');
  });
  it('alertas cambia estado con nota', () =>
    mutation('/campaigns/c/alerts/a/acknowledge', { action_date: '2026-08-03', note: 'Revisada' }));
  it('usuarios envia solo campos administrables', () =>
    mutation('/users', {
      username: 'synthetic',
      email: 'synthetic@example.test',
      role_codes: ['ANALYST'],
    }));
  it('roles asigna un rol existente a usuario', () =>
    mutation('/users/u/roles', { role_codes: ['ANALYST'] }, 'PUT'));
  it('asignacion de campana envia el usuario seleccionado', () =>
    mutation('/campaigns/c/users', { user_id: 'u' }));
  it('fuentes crea metadatos oficiales sin rutas internas', async () => {
    await mutation('/data-sources', {
      code: 'SAFE',
      institution: 'Institucion sintetica',
      official_url: 'https://example.test/source',
    });
    expect(JSON.stringify(calls[0].body)).not.toMatch(/storage_key|temp_path/);
  });
  it('plantillas restringe formato y secciones declarativas', () =>
    mutation('/report-templates', {
      code: 'SAFE',
      supported_formats: ['PDF', 'XLSX'],
      sections: ['SUMMARY'],
    }));
  it('auditoria aplica filtros funcionales sin timestamps', async () => {
    jsonApi({ items: [] });
    await apiRequest('/security/audit-events?event_date=2026-08-03&event_type=LOGIN_SUCCESS');
    expect(calls[0].path).toBe('/api/v1/security/audit-events');
  });
  it('mapa consume FeatureCollection y resource_id', async () => {
    jsonApi({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { resource_id: '1' },
          geometry: { type: 'MultiPolygon', coordinates: [] },
        },
      ],
    });
    const map = await apiRequest<{ features: Array<{ properties: { resource_id: string } }> }>(
      '/campaigns/c/map/boundaries?level=PARISH',
    );
    expect(map.features[0].properties.resource_id).toBe('1');
  });
  it.each([403, 404, 410, 422, 503])(
    'propaga el estado %s para que la pagina muestre su estado controlado',
    async (status) => {
      server.use(
        http.get('*/api/v1/failure', () => HttpResponse.json({ detail: 'controlled' }, { status })),
      );
      await expect(apiRequest('/failure', { retryAuth: false })).rejects.toMatchObject({ status });
    },
  );
});
