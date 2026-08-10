import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { apiRequest, tokenStore } from './client';
import { ApiError } from './errors';
let refreshes = 0;
const server = setupServer();
const nativeFetch = globalThis.fetch;
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
  tokenStore.set(null);
  refreshes = 0;
});
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});
describe('cliente API con MSW', () => {
  it('decodifica JSON 200', async () => {
    server.use(http.get('*/api/v1/value', () => HttpResponse.json({ ok: true })));
    await expect(apiRequest('/value')).resolves.toEqual({ ok: true });
  });
  it('maneja 204', async () => {
    server.use(http.delete('*/api/v1/value', () => new HttpResponse(null, { status: 204 })));
    await expect(apiRequest('/value', { method: 'DELETE' })).resolves.toBeUndefined();
  });
  it('normaliza 403', async () => {
    server.use(
      http.get('*/api/v1/denied', () => HttpResponse.json({ detail: 'no' }, { status: 403 })),
    );
    await expect(apiRequest('/denied', { retryAuth: false })).rejects.toMatchObject({
      status: 403,
    });
  });
  it('normaliza 422 y conserva detalle', async () => {
    server.use(
      http.post('*/api/v1/form', () =>
        HttpResponse.json({ detail: [{ loc: ['body', 'title'] }] }, { status: 422 }),
      ),
    );
    try {
      await apiRequest('/form', { method: 'POST', body: '{}', retryAuth: false });
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).detail).toBeTruthy();
    }
  });
  it('coordina solicitudes simultáneas con un refresh', async () => {
    server.use(
      http.post('*/api/v1/auth/browser/refresh', () => {
        refreshes++;
        return HttpResponse.json({ access_token: 'renewed' });
      }),
      http.get('*/api/v1/protected', ({ request }) =>
        request.headers.get('authorization') === 'Bearer renewed'
          ? HttpResponse.json({ ok: true })
          : new HttpResponse(null, { status: 401 }),
      ),
    );
    const result = await Promise.all([
      apiRequest('/protected'),
      apiRequest('/protected'),
      apiRequest('/protected'),
    ]);
    expect(result).toHaveLength(3);
    expect(refreshes).toBe(1);
  });
  it('no repite refresh fallido', async () => {
    server.use(
      http.post('*/api/v1/auth/browser/refresh', () => new HttpResponse(null, { status: 401 })),
      http.get('*/api/v1/protected', () => new HttpResponse(null, { status: 401 })),
    );
    await expect(apiRequest('/protected')).rejects.toMatchObject({ status: 401 });
    expect(refreshes).toBe(0);
  });
  it('agrega bearer solo desde memoria', async () => {
    tokenStore.set('memory-token');
    server.use(
      http.get('*/api/v1/header', ({ request }) =>
        HttpResponse.json({ value: request.headers.get('authorization') }),
      ),
    );
    await expect(apiRequest<{ value: string }>('/header')).resolves.toEqual({
      value: 'Bearer memory-token',
    });
  });
  it('acepta AbortSignal', async () => {
    const controller = new AbortController();
    controller.abort();
    server.use(http.get('*/api/v1/slow', () => HttpResponse.json({})));
    await expect(apiRequest('/slow', { signal: controller.signal })).rejects.toBeTruthy();
  });
});
