import { ApiError, statusMessage } from './errors';
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;
let onSessionExpired: (() => void) | null = null;
export const tokenStore = {
  get: () => accessToken,
  set: (token: string | null) => {
    accessToken = token;
  },
  onExpired: (callback: () => void) => {
    onSessionExpired = callback;
  },
};
const csrfToken = () =>
  document.cookie
    .split('; ')
    .find((row) => row.startsWith('te_csrf='))
    ?.split('=')[1] ?? '';
async function renew(): Promise<boolean> {
  if (!refreshPromise)
    refreshPromise = fetch(BASE_URL + '/auth/browser/refresh', {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRF-Token': decodeURIComponent(csrfToken()) },
    })
      .then(async (response) => {
        if (!response.ok) return false;
        const data = (await response.json()) as { access_token: string };
        accessToken = data.access_token;
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  return refreshPromise;
}
export async function apiRequest<T>(
  path: string,
  init: RequestInit & { retryAuth?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', 'Bearer ' + accessToken);
  const response = await fetch(BASE_URL + path, { ...init, headers, credentials: 'include' });
  if (response.status === 401 && init.retryAuth !== false && !path.startsWith('/auth/browser/')) {
    if (await renew()) return apiRequest<T>(path, { ...init, retryAuth: false });
    accessToken = null;
    onSessionExpired?.();
  }
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, statusMessage(response.status), detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export async function apiBlob(path: string): Promise<{ blob: Blob; disposition: string | null }> {
  const headers = new Headers();
  if (accessToken) headers.set('Authorization', 'Bearer ' + accessToken);
  const response = await fetch(BASE_URL + path, {
    headers,
    credentials: 'include',
    cache: 'no-store',
  });
  if (!response.ok) throw new ApiError(response.status, statusMessage(response.status));
  return { blob: await response.blob(), disposition: response.headers.get('Content-Disposition') };
}
export { BASE_URL };
