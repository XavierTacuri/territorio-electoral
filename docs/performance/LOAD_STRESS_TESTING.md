# Load / Stress Testing — Fase 4C.6

Suite reproducible de pruebas de carga para Territorio Electoral. Complementa [`docs/performance/PERFORMANCE_BASELINE.md`](./PERFORMANCE_BASELINE.md) (resultados, análisis, recomendaciones de dimensionamiento). **Ningún resultado de este documento mide AWS real** — todo corre contra `docker-compose.e2e.yml`/`docker-compose.multi-instance.yml` en localhost. Ver `PERFORMANCE_BASELINE.md`, sección "Incertidumbres", para la lista explícita de lo que solo puede confirmarse en AWS.

**Segunda pasada (resource-constrained benchmark)**: añadió `docker-compose.performance.yml`/`docker-compose.multi-instance.performance.yml` (límites explícitos de CPU/memoria, ver §"Resource limits" abajo) y `backend/scripts/scale_loadtest_dataset.py` (dataset sintético escalable S/M/L) — documentado en detalle en `PERFORMANCE_BASELINE.md`, sección "SEGUNDA PASADA".

## Herramienta elegida: k6

Se auditó el repositorio completo (`k6`, `locust`, `jmeter`, `vegeta`, `wrk`, `hey`, `artillery`, `loadtest`, `benchmark`, `stress`, `soak`) — no existía ninguna herramienta de load testing previa. Se eligió **k6** (`grafana/k6:0.54.0`, fijado por versión igual que `hashicorp/terraform:1.16.3` en fases anteriores):

- Ejecutable vía Docker sin instalar nada permanente en Windows (`docker run grafana/k6 ...`).
- Escenarios (`ramping-vus`/`constant-vus`), thresholds, y métricas custom (`Trend`/`Rate`/`Counter`) nativos — sin dependencias adicionales.
- `--summary-export` produce JSON machine-readable directamente, sin post-procesamiento.

## Estructura de archivos

```
loadtests/
  k6/
    main.js          Script unico parametrizable (todos los escenarios/mezclas)
    lib/auth.js       Login con cache por VU + alternancia de host (single/multi-instance)
    data/
      fixture.json     IDs reales del fixture E2E (docker-compose.e2e.yml)
      fixture_mi.json   IDs reales del fixture multi-instance (docker-compose.multi-instance.yml)
  run.sh              Wrapper: k6 + docker stats en paralelo + resultados con timestamp
  results/            Generado — ignorado por git salvo .gitignore (ver §"Resultados")
backend/scripts/export_loadtest_fixture.py   Exporta los IDs de arriba desde la DB real (solo lectura)
backend/scripts/scale_loadtest_dataset.py    Genera dataset sintetico escalable S/M/L (segunda pasada)
docker-compose.performance.yml               Override: limites CPU/memoria explicitos para `api`/`frontend` (segunda pasada)
docker-compose.multi-instance.performance.yml  Idem, mismo limite para api-a Y api-b (comparacion bajo limites iguales)
docs/performance/
  LOAD_STRESS_TESTING.md   Este documento
  PERFORMANCE_BASELINE.md  Resultados, análisis, recomendaciones
```

## Resource limits (segunda pasada)

La primera pasada corrió el backend **sin límite de CPU/memoria** — Docker Desktop dejó que usara hasta ~200% de CPU del host, una condición que no existe en una Fargate task real (`backend_task_cpu=256` = 0.25 vCPU). `docker-compose.performance.yml` aplica límites explícitos vía `deploy.resources.limits` (Compose v2 los aplica en `docker compose up` normal, sin Swarm):

```bash
PERF_CPU_LIMIT=0.25 PERF_MEM_LIMIT=512M docker compose -p territorio-e2e -f docker-compose.e2e.yml -f docker-compose.performance.yml up -d
docker inspect territorio-e2e-api-1 --format 'NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}}'  # verificar, no confiar solo en el YAML
```

Perfiles usados en `PERFORMANCE_BASELINE.md`:

| Perfil | `PERF_CPU_LIMIT` | `PERF_MEM_LIMIT` | Equivalente Fargate aproximado |
| --- | --- | --- | --- |
| A | `0.25` | `512M` | 256 CPU units / 512MB (config actual de Terraform) |
| B | `0.50` | `1024M` | 512 CPU units / 1024MB |
| C | `1.00` | `2048M` | 1024 CPU units / 2048MB |

`frontend` queda fijo en 0.25 CPU/128M en este override — no para medirlo, sino para que no compita por recursos del host mientras se mide `api` (nunca se sometió a carga).

`PERF_WEB_CONCURRENCY` (default `1`, opcional) parametriza el experimento aislado de `WEB_CONCURRENCY` (ver `PERFORMANCE_BASELINE.md`, §33) — nunca cambia el valor productivo de `config.py`.

Para la comparación single-vs-multi-instance bajo límites iguales, `docker-compose.multi-instance.performance.yml` aplica el mismo `PERF_CPU_LIMIT`/`PERF_MEM_LIMIT` a `api-a` y `api-b`:

```bash
PERF_CPU_LIMIT=0.50 PERF_MEM_LIMIT=1024M docker compose -p territorio-mi -f docker-compose.multi-instance.yml -f docker-compose.multi-instance.performance.yml up -d db api-a   # single
# luego, sin bajar nada:
docker compose -p territorio-mi -f docker-compose.multi-instance.yml -f docker-compose.multi-instance.performance.yml up -d api-b   # agrega la segunda instancia, mismo limite
```

## Dataset scaling (segunda pasada)

`backend/scripts/scale_loadtest_dataset.py` genera recintos/juntas sintéticos adicionales sobre el **mismo** `electoral_process` del fixture (parish/canton/province ya válidas del fixture base — nunca inventa una nueva, nunca rompe una FK). Multiplicadores **técnicos**, no una estimación de cuántos recintos tendrá una elección real:

```bash
docker compose -p territorio-e2e -f docker-compose.e2e.yml cp backend/scripts/scale_loadtest_dataset.py api:/app/scripts/scale_loadtest_dataset.py
docker compose -p territorio-e2e -f docker-compose.e2e.yml exec -T api python -m scripts.scale_loadtest_dataset --target-places 60    # ~M
docker compose -p territorio-e2e -f docker-compose.e2e.yml exec -T api python -m scripts.scale_loadtest_dataset --target-places 250   # ~L
docker compose -p territorio-e2e -f docker-compose.e2e.yml exec -T api python -m scripts.scale_loadtest_dataset --target-places 0 --reset   # vuelve a Dataset S
```

`--reset` elimina únicamente los recintos con prefijo `LOADTEST-` (y sus juntas) — nunca toca los datos de `seed_e2e.py`. Ver `PERFORMANCE_BASELINE.md`, §31, para los tamaños S/M/L reales usados y sus resultados.

Un único script (`main.js`) en vez de un archivo por escenario — evita duplicar los flujos de petición (lectura/mixto/escritura) seis veces. La forma de carga (smoke/baseline/load/stress/spike/soak) y la mezcla de tráfico (read/mixed/write/auth) son dos ejes independientes, ambos seleccionables por variable de entorno.

## Requisitos

- Docker Desktop (ya usado por el resto del proyecto).
- El stack `docker-compose.e2e.yml` (o `docker-compose.multi-instance.yml` para la comparación single/multi-instance) levantado, migrado y sembrado — ver `README.md` para las variables `E2E_*`/`TERRITORIO_MI_*` requeridas.
- `backend/scripts/export_loadtest_fixture.py` ejecutado una vez tras sembrar, para generar `loadtests/k6/data/fixture*.json` con los IDs reales (nunca inventados).

## Preparación

```bash
source "$HOME/.e2e_ci_vars.sh"   # o exporta E2E_DB_PASSWORD/E2E_SECRET_KEY/... manualmente
docker compose -p territorio-e2e -f docker-compose.e2e.yml up --build -d
docker compose -p territorio-e2e -f docker-compose.e2e.yml exec -T api alembic upgrade head
docker compose -p territorio-e2e -f docker-compose.e2e.yml exec -T api python -m app.scripts.seed_e2e

# Exportar los IDs reales del fixture (bucket, campaña, recinto, delegado con jornada ACTIVA)
docker compose -p territorio-e2e -f docker-compose.e2e.yml cp backend/scripts/export_loadtest_fixture.py api:/app/scripts/export_loadtest_fixture.py
docker compose -p territorio-e2e -f docker-compose.e2e.yml exec -T api python -m scripts.export_loadtest_fixture > loadtests/k6/data/fixture.json
```

`export_loadtest_fixture.py` es de solo lectura: consulta la campaña `gualaceo-e2e-2027` (la única con una `ElectionDayOperation` en estado `ACTIVE` y un delegado ya asignado/check-in en el fixture E2E — `app/scripts/seed_e2e.py::ensure_election_day_fixture`), nunca modifica filas.

## Dataset sintético utilizado

Todos los datos son fixtures/seeds ya existentes en el repo (`app.scripts.seed_e2e`) — ningún dato personal real, ninguna credencial real, ningún bucket S3 real (`ARTIFACT_STORAGE_PROVIDER=local` en ambos stacks de prueba). Volumen real observado en la corrida de esta revisión (`dataset_counts` de `fixture.json`):

| Entidad | Cantidad |
| --- | --- |
| Recintos electorales (`polling_places`) | 6 |
| Juntas receptoras del voto (`electoral_boards`) | 16 |
| Usuarios | 20 |

Deliberadamente pequeño (no se introdujeron millones de filas sin necesidad) — suficiente para que las lecturas agregadas (`dashboard/overview`, `election-day/control-center`) ejerciten agregaciones SQL reales sobre una tabla no vacía, sin inflar artificialmente el tiempo de seed.

## Endpoints seleccionados (todos reales, verificados contra `backend/app/api/routes/*.py`)

| Categoría | Endpoint | Método |
| --- | --- | --- |
| A. Lectura ligera | `/api/v1/auth/me` | GET |
| B. Lectura DB | `/api/v1/campaigns/{id}/election-day/coverage` | GET |
| B. Lectura DB | `/api/v1/campaigns/{id}/election-day/polling-places` | GET |
| C/F. Lectura agregada, crítica | `/api/v1/campaigns/{id}/election-day/control-center` | GET |
| C. Lectura agregada/pesada | `/api/v1/campaigns/{id}/dashboard/overview` | GET |
| D/F. Escritura, crítica | `/api/v1/campaigns/{id}/election-day/incidents` | POST |
| E. Autenticación | `/api/v1/auth/login` | POST |
| G. Health/readiness | `/api/v1/health`, `/api/v1/ready` | GET |
| H. Archivos/reportes | `/api/v1/campaigns/{id}/reports` (listado) | GET |

**Deliberadamente excluido**: `POST /api/v1/campaigns/{id}/reports/generate` (generación real de PDF/XLSX). Es una operación de costo desproporcionado (render + escritura a disco) frente al resto del tráfico de jornada electoral — incluirla en la mezcla de carga general mediría principalmente el costo de generar reportes, no el patrón de tráfico real. Queda fuera del alcance de esta primera pasada; candidato a un escenario dedicado propio si se decide medirlo.

## Flujos críticos representados

Derivados del código real (`election_day_service.py`, `election_day_access_service.py`), no inventados:

- **Consulta de cobertura/control center** (lectura agregada, crítica durante jornada): quién está reportando, qué recintos faltan.
- **Reporte de incidencias** (escritura crítica de campo): un delegado de recinto reporta una incidencia — único flujo de escritura de Jornada Electoral que no exige un rol de validador de actas (más simple de reproducir de forma sintética y repetible que el flujo de actas, que tiene locking optimista por junta+contienda).
- **Autenticación**: todo flujo empieza con login; medido tanto embebido (una vez por VU, cacheado) como en un escenario dedicado.
- **Dashboard ejecutivo**: la lectura agregada más pesada del sistema (múltiples agregaciones SQL).

**Hallazgo de acceso real, no asumido**: `admin_e2e` (superusuario `ADMIN`) **no** tiene acceso a `coverage`/`control-center`/`polling-places` por defecto — `ElectionDayAccessService.require_control_center_access` exige ser ejecutivo de campaña (`CANDIDATE`/`CAMPAIGN_MANAGER`) o un `ADMIN` con una `ElectionDayAdminSupportSession` activa. Confirmado con un 403 real durante el primer smoke test de esta revisión. El usuario de lectura de la suite es `manager_e2e` (`CAMPAIGN_MANAGER`), no `admin_e2e`.

## Variables de entorno (`K6_*`)

| Variable | Default | Descripción |
| --- | --- | --- |
| `K6_SCENARIO` | `smoke` | `smoke`\|`baseline`\|`load`\|`stress`\|`spike`\|`soak` |
| `K6_MIX` | `mixed` | `read`\|`mixed`\|`write`\|`auth` |
| `K6_MIX_WRITE_RATIO` | `0.15` | Proporción de escritura en `mixed` — ver hipótesis abajo |
| `K6_VUS` | según escenario | VUs para smoke/baseline/soak |
| `K6_DURATION` | según escenario | Duración para smoke/baseline/soak |
| `K6_RAMP` / `K6_HOLD` | `30s` / `2m` | Rampa/sostenido de `load` |
| `K6_STRESS_STEP1..5` | `25,50,100,150,200` | VUs de cada escalón de `stress` |
| `K6_SPIKE_BASELINE` / `K6_SPIKE_PEAK` | `10` / `150` | VUs base/pico de `spike` |
| `K6_SLEEP` | `0.5` | Pausa entre iteraciones (think-time) |
| `K6_BASE_URL` | `http://localhost:18000` | Host objetivo (dentro de la red Docker: `http://api:8000`) |
| `K6_BASE_URL_B` | _(vacío)_ | Segundo host — activa alternancia round-robin (comparación single/multi-instance) |
| `K6_FIXTURE_FILE` | `./data/fixture.json` | Fixture alternativo (p. ej. `./data/fixture_mi.json`) |
| `K6_ADMIN_USER` / `K6_DELEGATE_USER` | `manager_e2e` / `delegate_e2e_a` | Usuarios de fixture |
| `K6_USER_PASSWORD` | _(obligatorio)_ | Mismo valor que `E2E_USER_PASSWORD`/`TERRITORIO_MI_USER_PASSWORD` — nunca hardcodeado |
| `K6_THRESHOLD_ERROR_RATE` / `K6_THRESHOLD_TECH_ERROR_RATE` | `0.05` / `0.02` | Umbrales técnicos iniciales (ver `PERFORMANCE_BASELINE.md`) |

**Hipótesis del `mixed` (15% escritura)**: durante una jornada electoral, el personal de campo consulta cobertura/control-center con mucha más frecuencia de la que reporta incidencias — un delegado revisa el estado varias veces por cada incidencia real que reporta. 15% es un punto de partida razonado documentado aquí, no una medición de uso real (no existe todavía) ni un 50/50 arbitrario — ajustable vía `K6_MIX_WRITE_RATIO`.

## Autenticación en la suite

`lib/auth.js` cachea el token **por VU** (variable a nivel de módulo — k6 instancia el script una vez por VU) — login solo en la primera iteración de cada VU, reutilizado en las siguientes. El escenario `K6_MIX=auth` es la única mezcla donde se hace login en cada iteración, deliberadamente, para medir ese endpoint específico. Nunca se hardcodea un token: `K6_USER_PASSWORD` es obligatorio y el script falla explícitamente si falta.

**Hallazgo de seguridad corregido durante esta revisión**: la primera versión de `setup()` devolvía los tokens JWT reales dentro del objeto de retorno, que `--summary-export` serializa íntegro en `setup_data` — un secreto de corta duración pero real quedando en texto plano en un archivo potencialmente versionable. Corregido: `setup()` ya no retorna tokens (solo hace warm-up con un login local no expuesto); cada VU hace su propio primer login, cacheado igual que antes.

## Warm-up

`setup()` ejecuta 3 lecturas de `dashboard/overview` con un login propio antes de que empiece cualquier iteración medida — estabiliza el pool de conexiones DB/SQLAlchemy y el runtime antes de registrar métricas. k6 no incluye `setup()` en el resumen de métricas de las VUs, así que nunca se mezcla con los resultados principales.

## Idempotencia y escrituras concurrentes

`writeHeavy()` reenvía el mismo `client_generated_id` cada 5ª iteración (`territorio_idempotent_replay_total` cuenta estos casos) — prueba que `ElectionDayService.create_incident` devuelve el recurso existente en vez de duplicar o fallar (ver `election_day_service.py:396-399`). Se distingue explícitamente error de negocio (4xx esperado, contado en `territorio_business_error_rate`) de error técnico (5xx/timeout/conexión, contado en `territorio_technical_error_rate`) — nunca se cuentan juntos.

## Métricas recolectadas

HTTP estándar de k6 (`http_req_duration` con `p(50)/p(90)/p(95)/p(99)/max`, `http_reqs` para RPS, `http_req_failed` para tasa de error) más métricas custom: `territorio_read_duration`/`territorio_write_duration` (Trends separados), `territorio_business_error_rate`/`territorio_technical_error_rate` (Rates separadas), `territorio_idempotent_replay_total` (Counter). `summaryTrendStats` incluye explícitamente p50/p90/p95/p99 — nunca solo el promedio.

## Métricas de host/contenedores

`loadtests/run.sh` lanza un poller `docker stats --no-stream` en background (cada 2s) durante toda la corrida de k6, hacia un CSV con columnas `container,timestamp,cpu_perc,mem_usage,mem_perc,net_io,block_io,pids`. Sin stack de observabilidad adicional — es la herramienta que Docker ya trae. Contenedores capturados por defecto: `api` y `db`; configurable vía `K6_STATS_CONTAINERS`.

## Comandos de ejecución

```bash
# Smoke — confirma que scripts/auth/rutas/data-setup funcionan antes de cargas mayores
K6_SCENARIO=smoke K6_MIX=mixed K6_USER_PASSWORD=<mismo valor que E2E_USER_PASSWORD> bash loadtests/run.sh

# Baseline — referencia de baja concurrencia
K6_SCENARIO=baseline K6_MIX=mixed K6_VUS=10 K6_DURATION=1m K6_USER_PASSWORD=... bash loadtests/run.sh

# Load — carga sostenida
K6_SCENARIO=load K6_MIX=mixed K6_VUS=50 K6_RAMP=30s K6_HOLD=2m K6_USER_PASSWORD=... bash loadtests/run.sh

# Stress — escalonado hasta degradación
K6_SCENARIO=stress K6_MIX=mixed K6_USER_PASSWORD=... bash loadtests/run.sh

# Spike — subida brusca y recuperación
K6_SCENARIO=spike K6_MIX=mixed K6_SPIKE_BASELINE=10 K6_SPIKE_PEAK=120 K6_USER_PASSWORD=... bash loadtests/run.sh

# Soak corto (5 min, para CI/local) — ver "Soak largo" abajo para una corrida real
K6_SCENARIO=soak K6_MIX=mixed K6_VUS=15 K6_DURATION=5m K6_USER_PASSWORD=... bash loadtests/run.sh

# Escenarios dedicados de mezcla
K6_SCENARIO=baseline K6_MIX=read  K6_VUS=10 K6_DURATION=30s K6_USER_PASSWORD=... bash loadtests/run.sh
K6_SCENARIO=baseline K6_MIX=write K6_VUS=10 K6_DURATION=30s K6_USER_PASSWORD=... bash loadtests/run.sh
K6_SCENARIO=baseline K6_MIX=auth  K6_VUS=10 K6_DURATION=30s K6_USER_PASSWORD=... bash loadtests/run.sh
```

### Soak largo (ejecución manual posterior, no incluida en esta pasada)

```bash
K6_SCENARIO=soak K6_MIX=mixed K6_VUS=15 K6_DURATION=2h K6_USER_PASSWORD=... bash loadtests/run.sh
```

Esta revisión ejecutó únicamente un soak de **5 minutos** — suficiente para detectar una fuga grosera de memoria/conexiones, **no** para validar estabilidad de varias horas. Ver `PERFORMANCE_BASELINE.md`, "Soak", para el resultado real y esta limitación explícita.

### Comparación single vs multi-instance

```bash
source variables TERRITORIO_MI_* (ver docker-compose.multi-instance.yml)
docker compose -p territorio-mi -f docker-compose.multi-instance.yml up --build -d
docker compose -p territorio-mi -f docker-compose.multi-instance.yml exec -T api-a python -m app.scripts.seed_e2e
docker compose -p territorio-mi -f docker-compose.multi-instance.yml cp backend/scripts/export_loadtest_fixture.py api-a:/app/scripts/export_loadtest_fixture.py
docker compose -p territorio-mi -f docker-compose.multi-instance.yml exec -T api-a python -m scripts.export_loadtest_fixture > loadtests/k6/data/fixture_mi.json

# Single-instance (solo api-a)
K6_SCENARIO=baseline K6_MIX=mixed K6_VUS=10 K6_DURATION=1m K6_USER_PASSWORD=<TERRITORIO_MI_USER_PASSWORD> \
  K6_ADMIN_USER=manager_e2e K6_DELEGATE_USER=delegate_e2e_a K6_FIXTURE_FILE=./data/fixture_mi.json \
  K6_NETWORK=territorio_multi_instance_default K6_BASE_URL=http://api-a:8000 \
  K6_STATS_CONTAINERS="territorio-mi-api-a-1 territorio-mi-db-1" bash loadtests/run.sh

# Multi-instance (api-a + api-b, alternancia round-robin)
K6_SCENARIO=baseline K6_MIX=mixed K6_VUS=10 K6_DURATION=1m K6_USER_PASSWORD=<TERRITORIO_MI_USER_PASSWORD> \
  K6_ADMIN_USER=manager_e2e K6_DELEGATE_USER=delegate_e2e_a K6_FIXTURE_FILE=./data/fixture_mi.json \
  K6_NETWORK=territorio_multi_instance_default K6_BASE_URL=http://api-a:8000 K6_BASE_URL_B=http://api-b:8000 \
  K6_STATS_CONTAINERS="territorio-mi-api-a-1 territorio-mi-api-b-1 territorio-mi-db-1" bash loadtests/run.sh
```

**La alternancia `K6_BASE_URL_B` no es un ALB**: es una alternancia round-robin simple a nivel de cliente, sin health-check-aware routing, sin connection draining, sin distribución ponderada. Prueba que 2 procesos backend independientes compartiendo la misma base de datos pueden repartirse tráfico real — no reemplaza la validación de un ALB real en AWS.

## Resultados

`loadtests/results/` contiene el JSON (`--summary-export`) y el CSV de `docker stats` de cada corrida, con timestamp en el nombre — generado, **no versionado** (`.gitignore` local a esa carpeta). `PERFORMANCE_BASELINE.md` contiene el resumen pequeño, sí versionado, con las cifras que importan de cada corrida.

## Interpretación

- **RPS/latencia por sí solos no localizan el cuello de botella** — cruzar siempre con `docker stats` (CPU/memoria de `api` vs `db`) antes de concluir dónde está la saturación (ver `PERFORMANCE_BASELINE.md`, "Bottleneck analysis").
- **p95/p99 rondando el techo de timeout de k6 (60s por defecto)** es la señal de que el sistema dejó de responder dentro de un tiempo razonable, no que las respuestas tardan literalmente 60s cada una.
- **`territorio_technical_error_rate` vs `territorio_business_error_rate`**: solo el primero indica un problema real de capacidad/infraestructura; el segundo son reglas de negocio funcionando como se espera (p. ej. una jornada no activa).

## Limitaciones del entorno local

- Un solo host Docker Desktop (Windows) sirve simultáneamente el generador de carga (k6), el backend, PostgreSQL y el motor Docker — el generador de carga y el sistema bajo prueba **compiten por los mismos núcleos/memoria**, algo que nunca ocurre contra AWS real (§16/§20 más abajo distingue explícitamente "host Docker saturado" de "limitación intrínseca de la aplicación").
- Sin ALB, sin WAF, sin RDS Proxy reales — ver `PERFORMANCE_BASELINE.md` para qué de esto queda marcado como "pendiente de validar en AWS".
- `WEB_CONCURRENCY=1` (un único worker Uvicorn) en ambos stacks de prueba — igual que el valor por defecto de `backend/app/core/config.py`, no un valor productivo ya decidido.

## Cleanup

```bash
docker compose -p territorio-e2e -f docker-compose.e2e.yml down -v
docker compose -p territorio-mi -f docker-compose.multi-instance.yml down -v   # si se ejecutó la comparación
```

`down -v` elimina también los volúmenes (datos sintéticos) — nunca hay estado real que preservar en estos stacks.

## Backend regression tests después de los benchmarks

Después de cada batería de pruebas se re-ejecuta `pytest` completo contra el stack de desarrollo — nunca contra `docker-compose.e2e.yml`, que queda dedicado a k6. Ver `PERFORMANCE_BASELINE.md`, "Validación final", para el resultado real de esta revisión.

## Estrategia futura de performance CI

Esta primera pasada **no** agrega stress/soak pesados al pipeline de CI normal — solo se ejecutan manualmente o en infraestructura dedicada. Un smoke performance rápido (VUs bajos, duración corta, el mismo `K6_SCENARIO=smoke`) podría incorporarse a CI en una fase futura como chequeo de regresión básico (¿sigue respondiendo el flujo crítico dentro de un umbral amplio?) — no decidido ni implementado en esta fase.
