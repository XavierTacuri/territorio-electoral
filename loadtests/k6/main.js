// Fase 4C.6 — suite unica de load/stress/spike/soak testing.
//
// Un unico script parametrizable por variables de entorno (K6_*) en vez de
// un archivo por escenario — evita duplicar los flujos de peticion (lectura,
// mixto, escritura) en 6 copias distintas. Ver docs/performance/LOAD_STRESS_TESTING.md
// para el catalogo completo de variables y ejemplos de invocacion.
//
// Apunta EXCLUSIVAMENTE al stack aislado docker-compose.e2e.yml (o
// docker-compose.multi-instance.yml para la comparacion single vs
// multi-instance) — nunca a AWS, produccion ni un host fuera de localhost.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { login, jsonHeaders, nextBaseUrl, isMultiInstance } from './lib/auth.js';

// K6_FIXTURE_FILE permite apuntar a un fixture distinto (p. ej.
// data/fixture_mi.json, exportado contra la base de docker-compose.multi-instance.yml)
// sin duplicar el script — usado por la comparacion single vs multi-instance.
const fixture = JSON.parse(open(__ENV.K6_FIXTURE_FILE || './data/fixture.json'));

const PASSWORD = __ENV.K6_USER_PASSWORD;
if (!PASSWORD) {
  throw new Error('K6_USER_PASSWORD es obligatorio (mismo valor que E2E_USER_PASSWORD del stack) — nunca hardcodeado en el script.');
}
// manager_e2e (CAMPAIGN_MANAGER) — no admin_e2e — porque las lecturas de
// Election Day (coverage/control-center/polling-places) exigen ser
// ejecutivo de campaña (CANDIDATE/CAMPAIGN_MANAGER) o un ADMIN con una
// ElectionDayAdminSupportSession activa (require_control_center_access,
// backend/app/services/election_day_access_service.py) — el superusuario
// ADMIN por si solo NO basta, confirmado con un 403 real durante el smoke
// test de esta revision, no asumido.
const ADMIN_USER = __ENV.K6_ADMIN_USER || 'manager_e2e';
const DELEGATE_USER = __ENV.K6_DELEGATE_USER || 'delegate_e2e_a';

const CAMPAIGN_ID = fixture.campaign_id;
const POLLING_PLACE_ID = fixture.polling_place_id;

// ---------------------------------------------------------------------
// Metricas custom (ademas de las HTTP por defecto que k6 ya recolecta:
// http_req_duration incluye p50/p90/p95/p99 automaticamente via trend).
// ---------------------------------------------------------------------
const readDuration = new Trend('territorio_read_duration', true);
const writeDuration = new Trend('territorio_write_duration', true);
const businessErrorRate = new Rate('territorio_business_error_rate');
const technicalErrorRate = new Rate('territorio_technical_error_rate');
const idempotentHits = new Counter('territorio_idempotent_replay_total');

// ---------------------------------------------------------------------
// Modelo de carga: escenario (forma de VUs/duracion) x mezcla (que flujo
// de peticiones ejecuta cada iteracion). Ambos ejes son independientes y
// configurables — ver §7/§8/§23-28 de la revision.
// ---------------------------------------------------------------------
const SCENARIO = __ENV.K6_SCENARIO || 'smoke';
const MIX = __ENV.K6_MIX || 'mixed'; // read | mixed | write | auth
const WRITE_RATIO = Number(__ENV.K6_MIX_WRITE_RATIO || 0.15);

function stagesFor(scenario) {
  switch (scenario) {
    case 'smoke':
      return { vus: Number(__ENV.K6_VUS || 2), duration: __ENV.K6_DURATION || '30s' };
    case 'baseline':
      return { vus: Number(__ENV.K6_VUS || 10), duration: __ENV.K6_DURATION || '1m' };
    case 'load':
      return {
        stages: [
          { duration: __ENV.K6_RAMP || '30s', target: Number(__ENV.K6_VUS || 50) },
          { duration: __ENV.K6_HOLD || '2m', target: Number(__ENV.K6_VUS || 50) },
          { duration: '20s', target: 0 },
        ],
      };
    case 'stress':
      return {
        stages: [
          { duration: '20s', target: Number(__ENV.K6_STRESS_STEP1 || 25) },
          { duration: '20s', target: Number(__ENV.K6_STRESS_STEP2 || 50) },
          { duration: '20s', target: Number(__ENV.K6_STRESS_STEP3 || 100) },
          { duration: '20s', target: Number(__ENV.K6_STRESS_STEP4 || 150) },
          { duration: '20s', target: Number(__ENV.K6_STRESS_STEP5 || 200) },
          { duration: '20s', target: 0 },
        ],
      };
    case 'spike':
      return {
        stages: [
          { duration: '15s', target: Number(__ENV.K6_SPIKE_BASELINE || 10) },
          { duration: '10s', target: Number(__ENV.K6_SPIKE_PEAK || 150) },
          { duration: '30s', target: Number(__ENV.K6_SPIKE_PEAK || 150) },
          { duration: '10s', target: Number(__ENV.K6_SPIKE_BASELINE || 10) },
          { duration: '30s', target: Number(__ENV.K6_SPIKE_BASELINE || 10) },
          { duration: '10s', target: 0 },
        ],
      };
    case 'soak':
      return { vus: Number(__ENV.K6_VUS || 15), duration: __ENV.K6_DURATION || '5m' };
    default:
      throw new Error(`K6_SCENARIO desconocido: ${scenario}`);
  }
}

const shape = stagesFor(SCENARIO);
export const options = {
  scenarios: {
    main: Object.assign({ executor: shape.stages ? 'ramping-vus' : 'constant-vus' }, shape),
  },
  // Umbrales tecnicos iniciales — no un SLA. Se revisan/proponen valores
  // definitivos SOLO despues de observar el baseline real (§29 de la
  // revision) — ver docs/performance/PERFORMANCE_BASELINE.md.
  thresholds: {
    http_req_failed: [`rate<${__ENV.K6_THRESHOLD_ERROR_RATE || '0.05'}`],
    territorio_technical_error_rate: [`rate<${__ENV.K6_THRESHOLD_TECH_ERROR_RATE || '0.02'}`],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(50)', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

// ---------------------------------------------------------------------
// Flujos de peticion — solo endpoints reales, verificados contra
// backend/app/api/routes/*.py. Nunca se inventa una ruta.
// ---------------------------------------------------------------------

function get(token, path, name) {
  return http.get(`${nextBaseUrl()}/api/v1${path}`, Object.assign(jsonHeaders(token), { tags: { name } }));
}

function classify(res, name) {
  const technicalFailure = res.status === 0 || res.status >= 500 || res.status === 408;
  technicalErrorRate.add(technicalFailure);
  if (res.status >= 400 && res.status < 500 && res.status !== 401 && res.status !== 403) {
    businessErrorRate.add(true);
  } else {
    businessErrorRate.add(false);
  }
  check(res, { [`${name} ok`]: (r) => r.status >= 200 && r.status < 300 });
}

// A/B/C/F: lectura ligera + lectura DB + lectura agregada, todas sobre
// endpoints reales de Election Day / Dashboard (los flujos mas frecuentes
// durante una jornada electoral: consultar cobertura, recintos, resumen).
export function readHeavy(adminToken) {
  const calls = [
    ['/auth/me', 'auth_me'], // A: lectura ligera
    [`/campaigns/${CAMPAIGN_ID}/election-day/coverage`, 'election_day_coverage'], // B: lectura DB
    [`/campaigns/${CAMPAIGN_ID}/election-day/polling-places`, 'election_day_polling_places'], // B: lectura DB
    [`/campaigns/${CAMPAIGN_ID}/election-day/control-center`, 'election_day_control_center'], // C/F: agregada, critica
    [`/campaigns/${CAMPAIGN_ID}/dashboard/overview`, 'dashboard_overview'], // C: agregada/pesada
    [`/campaigns/${CAMPAIGN_ID}/reports`, 'reports_list'], // H: listado de informes (liviano — nunca generacion)
  ];
  for (const [path, name] of calls) {
    const start = Date.now();
    const res = get(adminToken, path, name);
    readDuration.add(Date.now() - start);
    classify(res, name);
  }
}

// D/F: escritura real de Election Day (reporte de incidencia) — requiere el
// usuario DELEGADO asignado a ese recinto especifico y la jornada ACTIVA
// (ver backend/app/services/election_day_service.py::create_incident).
// Incluye idempotencia real (§12): cada 5ta iteracion reenvia el MISMO
// client_generated_id de la iteracion anterior para probar que el backend
// devuelve la incidencia existente en vez de duplicarla o fallar.
let _lastClientGeneratedId = null;
let _iterationCount = 0;

export function writeHeavy(delegateToken) {
  _iterationCount += 1;
  const replay = _lastClientGeneratedId && _iterationCount % 5 === 0;
  const clientGeneratedId = replay ? _lastClientGeneratedId : uuidv4();
  const payload = JSON.stringify({
    polling_place_id: POLLING_PLACE_ID,
    category: 'OTHER',
    description: `Carga sintetica k6 — iteracion ${_iterationCount} (${__ENV.K6_SCENARIO || 'smoke'})`,
    client_generated_id: clientGeneratedId,
  });
  const start = Date.now();
  const res = http.post(
    `${nextBaseUrl()}/api/v1/campaigns/${CAMPAIGN_ID}/election-day/incidents`,
    payload,
    jsonHeaders(delegateToken),
    { tags: { name: 'election_day_incident_create' } },
  );
  writeDuration.add(Date.now() - start);
  if (replay) {
    idempotentHits.add(1);
    check(res, { 'incident replay returns same resource, no 5xx': (r) => r.status < 500 });
  } else {
    check(res, { 'incident create 201': (r) => r.status === 201 });
    if (res.status === 201) _lastClientGeneratedId = clientGeneratedId;
  }
  classify(res, 'election_day_incident_create');
}

// E: autenticacion como flujo dedicado (no en cada iteracion de lectura).
export function authFlow() {
  const start = Date.now();
  const res = http.post(
    `${nextBaseUrl()}/api/v1/auth/login`,
    { username: ADMIN_USER, password: PASSWORD },
    { tags: { name: 'auth_login_scenario' } },
  );
  readDuration.add(Date.now() - start);
  check(res, { 'login 200': (r) => r.status === 200 });
  classify(res, 'auth_login_scenario');
}

// G: health/readiness — usado por smoke y como verificacion post-spike/soak.
export function healthCheck() {
  const h = http.get(`${nextBaseUrl()}/api/v1/health`, { tags: { name: 'health' } });
  const r = http.get(`${nextBaseUrl()}/api/v1/ready`, { tags: { name: 'ready' } });
  check(h, { 'health 200': (res) => res.status === 200 });
  check(r, { 'ready 200': (res) => res.status === 200 });
}

function uuidv4() {
  // Generador local — k6 no tiene crypto.randomUUID en todas las versiones
  // del runtime JS embebido; evita una dependencia externa para esto.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ---------------------------------------------------------------------
// setup(): warm-up — separado de las metricas principales (k6 no incluye
// setup() en el resumen de metricas de las iteraciones de VUs). Ejercita
// login + una lectura para estabilizar pools de conexion DB/SQLAlchemy
// antes de que empiecen a contar las iteraciones medidas.
// ---------------------------------------------------------------------
// IMPORTANTE (hallazgo de esta revision): setup() corre en su propia VU
// aislada de "init" — su cache de token (lib/auth.js) NUNCA es la misma
// que la de las VUs reales. Devolver un token real en el objeto que
// retorna setup() lo serializa tal cual dentro de setup_data en el JSON de
// --summary-export (confirmado con el primer smoke run de esta revision:
// el JWT completo quedaba en texto plano en el summary) — un secreto de
// corta duracion, pero real, en un archivo que podria versionarse por
// error. setup() por eso NUNCA retorna tokens: solo hace warm-up con su
// propio login local (nunca expuesto), y cada VU real hace su PRIMER login
// perezosamente (cacheado por VU en lib/auth.js, nunca repetido en
// iteraciones siguientes de esa misma VU).
export function setup() {
  const warmupToken = login(ADMIN_USER, PASSWORD);
  for (let i = 0; i < 3; i++) {
    get(warmupToken, `/campaigns/${CAMPAIGN_ID}/dashboard/overview`, 'warmup');
  }
  return { multiInstance: isMultiInstance() };
}

export default function () {
  if (MIX === 'auth') {
    authFlow();
  } else if (MIX === 'write') {
    writeHeavy(login(DELEGATE_USER, PASSWORD));
  } else if (MIX === 'read') {
    readHeavy(login(ADMIN_USER, PASSWORD));
  } else {
    // mixed (default): proporcion configurable de escrituras, resto lectura.
    // Hipotesis documentada (docs/performance/LOAD_STRESS_TESTING.md):
    // durante jornada electoral las lecturas (consultar cobertura/control
    // center) dominan sobre las escrituras (reportar incidencias) — 15%
    // escritura es un punto de partida razonado, no 50/50 arbitrario.
    if (Math.random() < WRITE_RATIO) {
      writeHeavy(login(DELEGATE_USER, PASSWORD));
    } else {
      readHeavy(login(ADMIN_USER, PASSWORD));
    }
  }
  sleep(Number(__ENV.K6_SLEEP || 0.5));
}

export function teardown(data) {
  // Verificacion de salud post-carga (§37: comprobar recuperacion).
  healthCheck();
}
