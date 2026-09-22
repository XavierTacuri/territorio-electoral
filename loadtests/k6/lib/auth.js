// Fase 4C.6 — helpers compartidos: login con reutilizacion de token por VU
// (nunca login en cada request, salvo el escenario de autenticacion
// dedicado) y alternancia de host cuando K6_BASE_URL_B esta definido
// (comparacion single-instance vs multi-instance, Fase 4B
// docker-compose.multi-instance.yml).
import http from 'k6/http';
import { check } from 'k6';

const URL_A = __ENV.K6_BASE_URL || 'http://localhost:18000';
const URL_B = __ENV.K6_BASE_URL_B || '';
const BASE_URLS = URL_B ? [URL_A, URL_B] : [URL_A];

// Estado a nivel de modulo: k6 instancia el script una vez por VU, asi que
// esto es efectivamente "por VU", nunca compartido entre VUs.
let _rrIndex = 0;
const _tokens = {};

export function nextBaseUrl() {
  const url = BASE_URLS[_rrIndex % BASE_URLS.length];
  _rrIndex += 1;
  return url;
}

export function isMultiInstance() {
  return BASE_URLS.length > 1;
}

export function login(username, password) {
  if (_tokens[username]) return _tokens[username];
  const url = `${nextBaseUrl()}/api/v1/auth/login`;
  const res = http.post(url, { username, password }, { tags: { name: 'auth_login' } });
  const ok = check(res, { 'login 200': (r) => r.status === 200 });
  if (!ok) {
    throw new Error(`login failed for ${username}: ${res.status} ${res.body}`);
  }
  const token = res.json('access_token');
  _tokens[username] = token;
  return token;
}

export function authHeaders(token, extra) {
  return Object.assign(
    { headers: Object.assign({ Authorization: `Bearer ${token}` }, extra || {}) },
  );
}

export function jsonHeaders(token) {
  return authHeaders(token, { 'Content-Type': 'application/json' });
}
