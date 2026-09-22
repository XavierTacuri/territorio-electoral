# Performance Baseline — Fase 4C.6 (primera pasada)

Resultados reales medidos localmente y recomendaciones iniciales de dimensionamiento para Territorio Electoral. Complementa [`docs/performance/LOAD_STRESS_TESTING.md`](./LOAD_STRESS_TESTING.md) (herramienta, cómo reproducir). **Ningún valor de Terraform se modificó en esta fase** — todo lo de abajo son recomendaciones para revisión, no cambios aplicados.

Distinción estricta usada en todo el documento:

- **[MEDIDO]** — resultado real observado contra el entorno local (`docker-compose.e2e.yml`/`docker-compose.multi-instance.yml`).
- **[EXTRAPOLACIÓN]** — estimación razonada para AWS, derivada de lo medido, nunca una garantía.
- **[PENDIENTE AWS]** — solo puede confirmarse con pruebas reales contra infraestructura AWS.

## 1. Host / hardware

| | |
| --- | --- |
| Sistema operativo | Windows 11 Pro |
| CPU | AMD Ryzen 7 5800H (8 núcleos / 16 hilos) |
| RAM física total | ~15.4 GiB |
| CPUs asignadas a Docker Desktop | 16 |
| Memoria asignada a Docker Desktop | 7.457 GiB |

El generador de carga (k6) y el sistema bajo prueba (backend, PostgreSQL) comparten esta misma máquina y el mismo motor Docker — a diferencia de un load test real contra AWS, donde el generador de carga corre en una máquina/región separada del sistema probado. Esto se tiene en cuenta explícitamente en el análisis de cuellos de botella (§8).

## 2. Dataset

Ver `LOAD_STRESS_TESTING.md`, "Dataset sintético utilizado" — 6 recintos, 16 juntas, 20 usuarios (fixture `app.scripts.seed_e2e`, campaña `gualaceo-e2e-2027`). Ningún dato personal real.

## 3. Herramienta

k6 (`grafana/k6:0.54.0`) vía Docker. Ver `LOAD_STRESS_TESTING.md` para el detalle de por qué y la auditoría de herramientas previas (ninguna existía).

## 4. Escenarios y resultados [MEDIDO]

Todas las corridas: `WEB_CONCURRENCY=1` (un solo worker Uvicorn), `db_pool_size=5`, `db_max_overflow=10` (config real de `backend/app/core/config.py`, sin modificar), mezcla `mixed` (15% escritura) salvo donde se indica.

### 4.1 Smoke (2 VUs, 30s)

| Métrica | Valor |
| --- | --- |
| Requests totales | 445 |
| RPS | 14.53 |
| p50 / p90 / p95 / p99 | 44 / 80 / 89 / 113 ms |
| Error rate (HTTP) | 0% |
| Checks | 100% |

Confirma: scripts, autenticación, rutas, data setup y asserts básicos funcionan — condición para avanzar a los escenarios siguientes (cumplida).

### 4.2 Baseline (10 VUs, 1m)

| Métrica | Valor |
| --- | --- |
| Requests totales | 2608 |
| RPS | 42.77 |
| p50 / p90 / p95 / p99 | 120 / 253 / 306 / 474 ms |
| Error rate | 0% |
| `territorio_technical_error_rate` | 0% |

Referencia para comparar el resto de escenarios.

### 4.3 Load (ramp 30s → 50 VUs, hold 2m)

| Métrica | Valor |
| --- | --- |
| Requests totales | 6986 |
| RPS | 40.91 |
| p50 / p90 / p95 / p99 | 1027 / 1396 / 1671 / 2094 ms |
| Error rate | 0% |
| `territorio_technical_error_rate` | 0% |

**Hallazgo clave**: a 5× los VUs de baseline, el RPS **no aumentó** (40.91 vs 42.77 — prácticamente plano) mientras la latencia se multiplicó ~9× en p50 y ~4.4× en p99. Sin errores todavía, pero el sistema ya dejó de escalar — el throughput se estancó (ver §8, bottleneck analysis).

### 4.4 Stress (escalonado 25→50→100→150→200 VUs, 20s cada paso)

| Métrica | Valor |
| --- | --- |
| Requests totales | 1924 (399 iteraciones completas, 144 interrumpidas) |
| RPS | 9.15 (cae respecto a load — señal de saturación severa, no de menos trabajo) |
| p50 / p90 / p95 / p99 | 610 / 1806 / **59995** / **59996** ms |
| Error rate (HTTP) | 8.57% |
| `territorio_technical_error_rate` | 4.67% |
| `teardown()` | **timeout a los 60s** intentando alcanzar `/health` |

p95/p99 en ~60000ms = el timeout HTTP por defecto de k6, no una respuesta real de 60 segundos — la señal correcta es "el sistema dejó de responder dentro de un tiempo razonable para una fracción creciente de peticiones", no "cada respuesta tarda 60s". Ver §7 para el punto exacto de degradación con evidencia de `docker stats`.

**Recuperación confirmada** tras terminar la carga: `curl /api/v1/health` → `200` en 8ms, minutos después de finalizado el stress test.

### 4.5 Spike (10 → 120 VUs en 10s → sostenido 30s → baja a 10 → 0)

| Métrica | Valor |
| --- | --- |
| Requests totales | 740 (162 iteraciones completas, 57 interrumpidas) |
| RPS | 6.52 |
| p50 / p90 / p95 / p99 | 192 / 58697 / 59995 / 59996 ms |
| Error rate (HTTP) | 15.27% |
| `territorio_technical_error_rate` | 9.30% |

**Recuperación post-spike — verificada explícitamente, no asumida**: `teardown()` del propio script (`healthCheck()`) reportó `health 200`/`ready 200` al finalizar, y una verificación manual independiente inmediatamente después confirmó `health: 200 0.008s` / `ready: 200 0.009s`. El sistema vuelve a un estado saludable una vez retirada la carga — el degradamiento durante el pico no dejó el proceso en un estado roto.

### 4.6 Soak corto (15 VUs, 5 minutos)

| Métrica | Valor |
| --- | --- |
| Requests totales | 12820 |
| RPS | 42.61 (estable, sin degradación a lo largo de los 5 min) |
| p50 / p90 / p95 / p99 | 241 / 439 / 505 / 623 ms |
| Error rate | 0% |
| Memoria `api` (inicio → fin) | ~188 MiB → ~189 MiB (estable) |
| Memoria `db` (inicio → fin) | ~140 MiB → ~130 MiB (estable) |

**Limitación explícita**: 5 minutos **no** es suficiente para validar ausencia de memory leak/connection leak a largo plazo — solo descarta una fuga grosera de corto plazo. No se afirma haber validado estabilidad de varias horas. Comando para una corrida larga real: `LOAD_STRESS_TESTING.md`, "Soak largo" (no ejecutada en esta revisión).

### 4.7 Escenarios de mezcla dedicados (10 VUs, 30s cada uno)

| Mezcla | RPS | p50 | p95 | p99 | Error rate | Nota |
| --- | --- | --- | --- | --- | --- | --- |
| `read` (solo lectura) | 36.31 | 176 ms | 451 ms | 605 ms | 0% | — |
| `write` (solo incidencias) | 16.95 | 84 ms | 182 ms | 563 ms | 0% | 100/506 iteraciones (19.8%) fueron replay idempotente — confirma `client_generated_id` funcionando bajo carga |
| `auth` (login en cada iteración) | 15.35 | 123 ms | 255 ms | 522 ms | 0% | — |

## 5. Single-instance vs multi-instance [MEDIDO]

Comparación limpia y reproducible vía `docker-compose.multi-instance.yml` (Fase 4B) — misma base de datos compartida, mismo fixture, mismos 10 VUs totales, misma forma de carga (baseline). La única variable es cuántos procesos backend independientes reciben el tráfico.

| | Solo `api-a` (1 instancia) | `api-a` + `api-b` (2 instancias, alternancia round-robin) | Δ |
| --- | --- | --- | --- |
| RPS | 40.90 | 59.85 | **+46%** |
| p50 | 130 ms | 50 ms | **-61%** |
| p90 | 266 ms | 136 ms | **-49%** |
| p95 | 310 ms | 178 ms | **-43%** |
| p99 | 520 ms | 292 ms | **-44%** |
| Error rate | 0% | 0% | — |

**Scaling efficiency**: con el mismo número de VUs (misma demanda del lado cliente), agregar una segunda instancia independiente redujo la latencia a menos de la mitad y aumentó el throughput ~46% — consistente con que cada instancia individual procesa menos concurrencia simultánea (menos presión sobre su propio pool de 15 conexiones DB y su único worker Uvicorn), no con un cuello de botella en PostgreSQL (la misma base de datos, sin cambios, sirvió ambos escenarios). **No es scaling lineal perfecto** (no se duplicó el RPS) — esperado: a 10 VUs fijos el límite real es cuánto trabajo puede generar el propio k6/cliente por iteración (think-time de 0.5s incluido), no solo la capacidad del backend.

**Qué NO prueba esta comparación**: `K6_BASE_URL_B` es alternancia round-robin del lado cliente, no un ALB real — sin health-check-aware routing, sin connection draining, sin distribución ponderada por carga real de cada instancia. Ver `LOAD_STRESS_TESTING.md`.

## 6. Métricas de PostgreSQL [MEDIDO]

Muestra de `pg_stat_activity` tomada a los 25s de una corrida `load` (50 VUs, mismo momento que la degradación observada en §4.3):

| total | active | idle | idle in transaction |
| --- | --- | --- | --- |
| 16 | 1 | 5 | 10 |

16 conexiones totales — prácticamente el máximo teórico del pool de un único worker (`db_pool_size=5 + db_max_overflow=10 = 15`; la 16ª es plausiblemente una conexión de sistema/health-check). **10 conexiones "idle in transaction"** bajo carga: consistente con sesiones SQLAlchemy abiertas (`with SessionLocal() as session`, `expire_on_commit=False`) que permanecen dentro de una transacción implícita mientras la petición aún se procesa — bajo latencia degradada, más peticiones se solapan en el tiempo, por lo que más conexiones quedan "ocupadas" (aunque técnicamente idle en ese instante) simultáneamente. No se observaron deadlocks ni errores de conexión en ningún escenario — los 5xx/timeouts de `stress`/`spike` fueron agotamiento de capacidad (cola), no fallos de PostgreSQL en sí (ver §8).

## 7. Punto de degradación observado [MEDIDO]

Cruzando `docker stats` (CPU de `api`) contra la línea de tiempo de la rampa de `stress`:

| Ventana | VUs objetivo | CPU `api` | CPU `db` | Estado |
| --- | --- | --- | --- | --- |
| ~23:54:42–23:55:09 | 25→100 (ramp) | 69% → 191% | 20-36% | Degradándose, aún respondiendo |
| ~23:55:14–23:55:26 | ~100-150 | 189% → 184% | 8-23% | Pico de CPU, última ventana con CPU alta |
| ~23:55:31 en adelante | 150→200 | **cae a ~1%** | ~0-11% | Colapso — el proceso deja de consumir CPU activamente mientras sigue "bajo carga" |

El colapso de CPU de `api` a ~1% **mientras** k6 seguía enviando peticiones (no después) es la firma característica de un proceso **bloqueado esperando un recurso** (conexión de pool, o saturación del threadpool de Starlette que ejecuta los handlers síncronos), no de un proceso ocupado calculando. `db` nunca superó ~36% de CPU en todo el escalón — PostgreSQL en sí mismo tenía margen de sobra. Conclusión con evidencia, no supuesta: **el cuello de botella es el proceso backend (un único worker Uvicorn + pool de 15 conexiones DB), no PostgreSQL.**

## 8. Análisis de cuellos de botella

| Candidato | Evidencia a favor | Evidencia en contra | Veredicto |
| --- | --- | --- | --- |
| **Backend (proceso único, pool de conexión)** | CPU `api` sube a 190-200% y luego colapsa a ~1% bajo la misma carga sostenida (§7); `pg_stat_activity` muestra el pool prácticamente lleno (16/15 teórico) durante `load` (§6) | — | **Principal** |
| PostgreSQL | Latencia general sube | CPU `db` nunca supera ~36%; sin deadlocks/errores de conexión; mismo Postgres sirvió el escenario multi-instance con mejor latencia sin cambiar nada de la DB | Descartado como cuello de botella primario |
| Connection pool (SQLAlchemy) | 10 "idle in transaction" de 15-16 totales durante `load` — cerca del límite teórico | — | **Secundario, consecuencia directa del anterior** — un solo worker agota su propio pool antes de que la DB muestre presión real |
| Locks/deadlocks | — | Cero observados en ningún escenario | Descartado |
| Frontend | — | No se sometió a carga significativa (fuera del alcance de esta pasada — ver §"Frontend" abajo); no participa en ningún endpoint medido | No aplica a estos resultados |
| Docker host saturado (generador de carga compitiendo por CPU) | 16 CPUs disponibles, k6 nunca reportó su propia saturación (`http_req_blocked` se mantuvo en microsegundos en todos los escenarios, incluido stress) | — | Descartado como causa principal — el cuello de botella está dentro del contenedor `api`, no en el host compartido |

**No se concluye "es la DB" solo porque la latencia sube** — la evidencia (CPU de cada contenedor, conteo de conexiones, ausencia de deadlocks, y el propio experimento single-vs-multi-instance que mejora sin tocar la DB) apunta consistentemente al backend de un solo worker como el límite real.

## 9. Frontend

No se sometió a un benchmark dedicado en esta pasada: `frontend` (nginx sirviendo assets estáticos del build de Vite) es trivial comparado con el backend — nginx sirviendo archivos estáticos está dominado por red/número de requests, no por cómputo del contenedor. Un benchmark grande del frontend no aportaría información nueva sobre el sistema; su dimensionamiento (§14) se basa en esa naturaleza, documentada, no medida exhaustivamente.

## 10. Configuración actual de SQLAlchemy pool [MEDIDO/auditado]

| Parámetro | Valor actual | Fuente |
| --- | --- | --- |
| `pool_size` | 5 | `DB_POOL_SIZE`, default en `config.py` |
| `max_overflow` | 10 | `DB_MAX_OVERFLOW` |
| `pool_timeout` | 30s | `DB_POOL_TIMEOUT_SECONDS` |
| `pool_recycle` | 1800s | `DB_POOL_RECYCLE_SECONDS` |
| `pool_pre_ping` | `true` (siempre, no configurable) | `db/session.py::build_engine_options` |
| `WEB_CONCURRENCY` | 1 | default en `config.py` |

Máximo teórico de conexiones por instancia backend: `pool_size + max_overflow = 15`. Con `WEB_CONCURRENCY=1`, esas 15 conexiones son compartidas por un único proceso — confirmado como el límite real alcanzado bajo `load` (§6).

### 10.1 Recomendación inicial de pool (sin cambiar `config.py` en esta pasada)

- **No se cambia nada en esta primera pasada** (regla explícita de esta fase).
- Multiplicar `pool_size + max_overflow` por el número de tasks ECS deseado da el total teórico de conexiones hacia RDS Proxy — con el perfil RECOMMENDED (§14, 2-4 tasks) eso son 30-60 conexiones máximas hacia el proxy, dentro de un margen razonable frente a `max_connections_percent=100` de RDS Proxy (Fase 4C.3) — **sin verificar todavía cuál es el límite real de conexiones que RDS Proxy multiplexa hacia la instance class recomendada (§13)**, marcado como pendiente de AWS.
- Si el perfil HIGH LOAD (§14) se adopta con más tasks, revisar esta multiplicación de nuevo — no asumir que escala sin límite.

## 11. Recomendaciones iniciales — ECS backend

Basado en §7-8 (cuello de botella = proceso único, no CPU/memoria del contenedor en sí — el contenedor de prueba nunca llegó a agotar su límite de memoria, y su CPU asignada era generosa por ser un host de desarrollo):

| Parámetro | Recomendación inicial | Razonamiento |
| --- | --- | --- |
| `backend_task_cpu` | Mantener `256` como punto de partida, **validar con perfilado real de CPU por task en AWS** [PENDIENTE AWS] | El benchmark local no aísla CPU por task (Docker Desktop comparte 16 CPUs entre todos los contenedores) — no hay evidencia local suficiente para recomendar subir de 256 todavía |
| `backend_task_memory` | Mantener `512` como punto de partida | Memoria de `api` se mantuvo establemente por debajo de 200 MiB incluso bajo `load`/`soak` — amplio margen bajo 512 MB |
| `backend_desired_count` | **≥ 2**, nunca 1 en producción | HA (§12), no solo rendimiento — 1 task no tolera el reemplazo de una task fallida sin downtime |
| `backend_min_capacity` | 2 | Igual razón que arriba |
| `backend_max_capacity` | 4 (perfil RECOMMENDED) — ver perfiles §14 para MINIMUM/HIGH LOAD | El experimento single-vs-multi-instance (§5) mostró mejora real al pasar de 1 a 2 procesos independientes; extrapolar a 4 como techo inicial es conservador, no medido más allá de 2 |

**Headroom**: no se dimensiona al máximo medido. El benchmark `load` (50 VUs) ya mostró degradación con 1 instancia — el número de tasks recomendado (≥2, con autoscaling hasta 4) da margen antes de llegar a ese punto con tráfico real, cuyo volumen real de jornada electoral **no se conoce todavía** [PENDIENTE AWS]. No existe una "regla universal" de headroom — esta cifra es conservadora precisamente porque el volumen real de usuarios simultáneos es una incógnita (§17 del checklist original de la fase).

## 12. Alta disponibilidad

`desired_count=1` no ofrece redundancia — si esa única task falla o se recicla durante un deployment, hay downtime completo. La recomendación de `desired_count ≥ 2` (§11) es una decisión de **disponibilidad**, independiente del resultado de rendimiento — aun si 1 task fuera suficiente en throughput, 2 (distribuidas entre AZs, ya soportado por `app_subnet_ids` en 2+ AZ desde Fase 4C.1) siguen siendo necesarias para tolerar el fallo de una.

## 13. Recomendaciones iniciales — RDS

| Parámetro | Actual (Fase 4C.3) | Recomendación inicial | Razonamiento |
| --- | --- | --- | --- |
| `instance_class` | `db.t4g.micro` | Mantener como baseline inicial, **confirmar con benchmark AWS real** [PENDIENTE AWS] | CPU de PostgreSQL local nunca superó ~36% incluso durante `stress` — pero un contenedor Docker local **no es equivalente** a una instance class real de RDS (CPU credits de instancias `t4g` burstable, I/O de EBS real, network throughput real — ninguno reproducible localmente). No se afirma equivalencia directa. |
| `allocated_storage`/`max_allocated_storage` | 20 GiB / 100 GiB | Mantener — el dataset sintético (6 recintos, 16 juntas, 20 usuarios) es órdenes de magnitud menor que cualquier estimación de producción real; **no existe información real suficiente de crecimiento esperado** para proponer otra cifra — se deja como fórmula/metodología: `allocated_storage` debe cubrir (dataset inicial real de la elección objetivo) + (índices, ~30-50% adicional) + (margen de backups WAL), confirmándose una vez exista un padrón/recintos reales cargados |
| `multi_az` | `false` (default) | Decisión de **disponibilidad**, no de rendimiento — evaluar `true` para el día de la elección específicamente (ventana crítica de horas, no todo el ciclo de vida de la campaña) frente al costo de duplicar cómputo/storage esa ventana. No se decide aquí solo por los resultados de carga. |

## 14. RDS Proxy

Recordatorio explícito: **no existe RDS Proxy real en el entorno local** — el backend en ambos stacks de prueba (`docker-compose.e2e.yml`, `docker-compose.multi-instance.yml`) se conecta directo a PostgreSQL, nunca a través de un proxy. Ninguna cifra de esta sección mide RDS Proxy — son hipótesis derivadas del comportamiento de pooling observado del lado de la aplicación.

| Parámetro (Fase 4C.3) | Valor actual | Estado tras esta revisión |
| --- | --- | --- |
| `connection_borrow_timeout` | 120s | Sin evidencia local que sugiera cambiarlo — mantener, pendiente de benchmark AWS |
| `max_connections_percent` | 100 | Sin evidencia local suficiente — el pooling multiplexado de RDS Proxy no se comporta igual que el pool directo de SQLAlchemy medido aquí. Pendiente de AWS. |
| `max_idle_connections_percent` | 50 | Igual — pendiente de AWS |
| `idle_client_timeout` | 1800s | Igual — pendiente de AWS |

**No se simula el comportamiento de RDS Proxy** — sería inventar datos. Los cuatro valores quedan exactamente como Fase 4C.3 los dejó, marcados explícitamente como pendientes de validación con tráfico real contra AWS.

## 15. Recomendaciones iniciales — ECS frontend

| Parámetro | Recomendación inicial | Razonamiento |
| --- | --- | --- |
| `frontend_task_cpu`/`frontend_task_memory` | Mantener `256`/`512` (valores actuales) | nginx sirviendo assets estáticos — sin evidencia de necesitar más (§9); no se sobredimensiona sin datos |
| `frontend_desired_count` | ≥ 2 | Misma razón de HA que el backend (§12), no de rendimiento |
| `frontend_min/max_capacity` | 2 / 4 (igual forma que backend, ver perfiles §14) | El costo marginal de mantener el mismo rango que backend es bajo y simplifica operación; sin evidencia de que frontend necesite un techo distinto |

## 16. Autoscaling — CPU

Target de autoscaling actual (`backend_cpu_target_value`, Fase 4C.2): `70%`. Dado que el cuello de botella real observado (§7-8) es agotamiento de **conexiones/proceso**, no de CPU per se (la CPU del contenedor sube como síntoma del threadpool saturado, pero el colapso posterior a ~1% de CPU bajo carga sostenida sugiere que un scaling basado solo en CPU podría **no disparar a tiempo** — el proceso deja de consumir CPU precisamente cuando está más saturado/bloqueado, no cuando arranca la saturación). Recomendación inicial: mantener el target de CPU como señal primaria (sigue siendo válida durante la fase de ascenso, antes del colapso — ver la ventana 69%→191% en §7), pero **evaluar en AWS real** si conviene una señal secundaria basada en latencia del ALB (`TargetResponseTime`, ya alarmada en Fase 4C.4) para no depender únicamente de CPU. No se implementan dos políticas de autoscaling en esta fase — solo se documenta la evaluación pendiente.

## 17. Autoscaling — memoria

La memoria de `api` se mantuvo estable y baja (~165-190 MiB) en todos los escenarios, incluido `stress` a 200 VUs — **ningún benchmark de esta pasada mostró presión de memoria**. No se justifica agregar una política de autoscaling basada en memoria con la evidencia actual.

## 18. Scale-out response — riesgo documentado

Localmente no se puede medir cuánto tarda Fargate en lanzar una task nueva en AWS real — ese tiempo (típicamente uno a varios minutos, según ENI/imagen/arranque de la aplicación) no está representado en ningún resultado de este documento. Riesgo: si un pico de tráfico real sube más rápido de lo que el autoscaling puede lanzar tasks nuevas, la capacidad **mínima** (`backend_min_capacity`) es lo único que absorbe ese pico mientras tanto — el escenario `spike` de esta pasada (§4.5) muestra que, sin capacidad adicional disponible instantáneamente, la degradación bajo un pico brusco es severa (15% de error HTTP). Esto debe comprobarse después en AWS real con el tiempo de arranque de tasks real medido [PENDIENTE AWS].

## 19. WAF — rate limit 2000 req / 300s / IP

Tráfico máximo medido en cualquier escenario: **59.85 RPS agregado** (multi-instance, §5) repartido entre múltiples endpoints — muy por debajo de 2000 req/300s (~6.67 req/s) **por IP individual**, que es la unidad real del límite de WAF (Fase 4C.4), no el agregado del sistema. Estos benchmarks, al correr desde un único generador k6 (una sola IP de origen), sí ejercitan el límite POR IP de forma más directa: en el escenario `load` (50 VUs, ~40 RPS sostenido, ~5 min de rampa+hold) el generador nunca se acercó a 2000 requests en 300s tampoco (40 RPS × 300s = 12000, pero eso está muy por encima del límite — **importante matiz**: 40 RPS sostenidos por 50s ya acumula 2000 requests, por lo que un cliente único sosteniendo el RPS medido en `load` **superaría** el límite de WAF en menos de un minuto).

**Qué escenario podría alcanzar ese valor**: un usuario/NAT compartido (varios delegados de campo detrás del mismo NAT corporativo o de operador móvil) generando el tráfico agregado equivalente al escenario `load` de esta pasada durante más de ~50 segundos continuos alcanzaría el límite actual. **Efecto de NAT compartido**: el límite es por IP pública — múltiples delegados detrás del mismo NAT (común en redes móviles/corporativas) comparten ese contador, por lo que el límite efectivo por persona real es menor que 2000/300s cuantas más personas compartan esa IP.

**No se cambia el límite automáticamente** — esta observación sugiere que 2000/300s podría ser bajo para un escenario de NAT compartido con tráfico intenso, pero la decisión final debe tomarse con tráfico real/AWS, no con un benchmark localhost de una sola IP sintética [PENDIENTE AWS].

## 20. Revisión de CloudWatch thresholds (Fase 4C.4)

| Alarma | Threshold inicial actual | Threshold recomendado según benchmark | Nota |
| --- | --- | --- | --- |
| ALB `TargetResponseTime` | 2s (`alb_response_time_threshold_seconds`) | Sin cambio propuesto | El p95 de `load` (1.67s) ya se acerca a 2s con solo 50 VUs locales — pero sin ALB real, tiempos de red/TLS de AWS no están representados; cambiar esto sin datos de ALB real sería especulativo |
| ECS CPU | 85% (`ecs_cpu_threshold_percent`) | Sin cambio propuesto | Consistente con la ventana de degradación observada (69-191%, cruzando 85% bien antes del colapso) — el threshold actual parece razonable como señal temprana, confirmado por evidencia local, no solo supuesto |
| ECS memoria | 85% (`ecs_memory_threshold_percent`) | Sin cambio propuesto | Memoria nunca fue un factor limitante en ningún escenario — sin evidencia para ajustar |
| RDS CPU | 80% (`rds_cpu_threshold_percent`) | Sin cambio propuesto | CPU de `db` nunca superó ~36% localmente — sin señal de que 80% sea inadecuado, pero tampoco confirmado contra una instance class real |
| RDS `FreeableMemory` | 256 MB (`rds_freeable_memory_threshold_mb`) | Sin cambio propuesto | Sin datos locales de memoria de PostgreSQL bajo presión real (el contenedor local nunca se acercó a un límite de memoria) |
| RDS `DatabaseConnections` | 80 (`rds_database_connections_threshold`) | **Revisar** — con 2-4 tasks × 15 conexiones teóricas cada una (§10.1), el total posible (30-60) puede acercarse o superar 80 dependiendo del perfil final; recalcular una vez fijado `backend_max_capacity` definitivo | Derivado directamente de la evidencia de §6 (pool casi lleno con una sola instancia) |

Ningún threshold de Terraform se modifica en esta fase — esta tabla es la entrada para una decisión posterior.

## 21. Perfiles técnicos (candidatos, sujetos a validación AWS)

Ninguno es un tier comercial — son tres puntos de partida técnicos derivados de §11-20.

### MINIMUM

Ambiente productivo de baja carga, conservando HA mínima real.

| | |
| --- | --- |
| Backend tasks | 2 (min=2, max=2 — sin autoscaling real, solo redundancia) |
| Frontend tasks | 2 |
| Backend CPU/memoria | 256 / 512 (sin cambio) |
| RDS class | `db.t4g.micro` (sin cambio) |
| Multi-AZ | `false` |
| Autoscaling | Deshabilitado o rango 2-2 |
| Observación | Suficiente para validación/piloto de baja concurrencia — no para el día de una elección real con múltiples delegados simultáneos |

### RECOMMENDED

Margen operativo normal — el perfil que esta revisión recomienda como punto de partida.

| | |
| --- | --- |
| Backend tasks | min=2, max=4 |
| Frontend tasks | min=2, max=4 |
| Backend CPU/memoria | 256 / 512 (sin cambio — sin evidencia de necesitar más) |
| RDS class | `db.t4g.micro`, **candidato a revisión tras benchmark AWS real** |
| Multi-AZ | Evaluar `true` específicamente para la ventana del día de la elección |
| Autoscaling | CPU target 70% (sin cambio), evaluar señal secundaria de latencia (§16) |
| Observación | Basado en que 2 instancias ya mostraron mejora medible (§5); 4 como techo es conservador, no un límite medido |

### HIGH LOAD

Configuración para picos superiores — derivada de que `stress` mostró degradación severa sin una capacidad mayor disponible.

| | |
| --- | --- |
| Backend tasks | min=4, max=8-10 (no medido más allá de 2 instancias reales — extrapolación) |
| Frontend tasks | min=2, max=4 (frontend no fue el cuello de botella en ningún escenario) |
| Backend CPU/memoria | 256 / 512 como punto de partida; **revisar si aumentar CPU por task aporta más que sumar tasks** [PENDIENTE AWS — no distinguible localmente] |
| RDS class | Candidato a una clase mayor que `db.t4g.micro` si el número de tasks (y por tanto conexiones totales) crece — sin cifra concreta sin benchmark AWS |
| Multi-AZ | `true` recomendado — HA bajo la carga que este perfil anticipa |
| Autoscaling | Rango más amplio; revisar `backend_min_capacity` para absorber picos mientras Fargate lanza tasks nuevas (§18) |
| Observación | El más especulativo de los tres — candidato explícito para validación AWS antes de cualquier decisión de producción |

## 22. Modelo de costos (metodología, no factura)

Sin precios verificables a la mano — **no se inventan dólares**. Componentes que dominan el costo, en orden aproximado de magnitud esperado (razonamiento, no cifra):

1. **RDS** (instance class + storage + Multi-AZ si se activa) — típicamente el componente más caro de una arquitectura de este tamaño, agravado si se activa Multi-AZ (~2×).
2. **ECS/Fargate** (CPU/memoria × número de tasks × tiempo corriendo) — escala linealmente con `desired_count`/autoscaling; el perfil HIGH LOAD costaría notablemente más que MINIMUM por tener más tasks corriendo la mayor parte del tiempo (`min_capacity`), no solo en picos.
3. **NAT Gateway** — costo fijo por hora + por GB, independiente de la carga de la aplicación (ya documentado en `docs/aws/TERRAFORM_FOUNDATION.md`).
4. **ALB** — costo fijo + por LCU, bajo para el volumen de tráfico de esta escala.
5. **WAF** — costo fijo del Web ACL + por regla + por millón de requests — bajo.
6. **CloudWatch** — alarmas + dashboard + logs — bajo, salvo que se habilite Container Insights (ya documentado como opcional en Fase 4C.4).
7. **S3** — bajo para el volumen de evidencia/informes de una campaña electoral, incluso con versioning (Fase 4C.5).

Para calcular cifras reales: tomar el perfil elegido (§21), consultar la calculadora de precios de AWS con la región/instance class/tasks definitivas, una vez exista una decisión — fuera del alcance de esta fase.

## 23. Elementos que NO pueden validarse localmente

- Comportamiento real de RDS Proxy (pooling multiplexado, no simulado — §14).
- Comportamiento real de ALB (latencia de red, distribución de carga real, health checks — §"ALB" no tiene sección propia porque no hay ningún dato local que lo mida).
- Comportamiento real de AWS WAF bajo el límite de rate limiting con tráfico de múltiples IPs reales (§19).
- Tiempo real de arranque de tasks Fargate nuevas (§18).
- CPU credits/throughput real de una instance class RDS `t4g` burstable (§13).
- Latencia de red real entre AZs/servicios AWS (todo el tráfico local es loopback de Docker, sin latencia de red real).
- Estabilidad de memoria/conexiones en una ventana de horas (§4.6 — solo 5 minutos medidos).
- Cualquier cifra de costo real (§22 — solo metodología).

## 24. Pruebas que deben repetirse en AWS

1. Baseline/load/stress/spike/soak equivalentes contra el stack real desplegado (ECS + RDS + RDS Proxy + ALB + WAF), generador de carga en una instancia separada (nunca desde la misma máquina que el sistema bajo prueba).
2. Soak largo (horas), no solo 5 minutos.
3. Medición de tiempo real de scale-out de Fargate ante un spike.
4. Validación de si el rate limit de WAF (2000/300s/IP) es adecuado con tráfico de múltiples IPs/NAT reales.
5. Benchmark de la instance class RDS elegida bajo el mismo patrón de queries, para confirmar o ajustar §13.
6. Repetir la comparación single-vs-multi-instance (§5) contra el ALB real, no contra alternancia de cliente.

---

# SEGUNDA PASADA — Resource-constrained benchmark

Todo lo de arriba (§1-24) es la **primera pasada**, ejecutada con el backend **sin límite de CPU/memoria** (Docker Desktop dejó que el contenedor usara hasta ~200% de CPU del host, observado en §7). Esa cifra **no es comparable** a una Fargate task real: `backend_task_cpu=256` de Terraform (Fase 4C.2) equivale a **0.25 vCPU** — mucho menos que lo que el benchmark sin límite pudo usar libremente. Esta segunda pasada corrige eso: todos los resultados de aquí en adelante corren con límites explícitos de CPU/memoria aplicados al contenedor `api` vía `docker-compose.performance.yml`, verificados con `docker inspect` (no solo confiando en el YAML).

**No se pierde ni se sobrescribe nada de la primera pasada** — §1-24 y sus cifras permanecen sin cambios; esta sección se identifica y compara explícitamente contra ellas.

## 25. Resource limits — implementación y verificación

`docker-compose.performance.yml` (nuevo, raíz del repo) — override que aplica `deploy.resources.limits.cpus`/`memory` (Compose v2 los aplica en `docker compose up` normal, sin necesitar Swarm — confirmado en esta revisión, no asumido) a `api` (parametrizado vía `PERF_CPU_LIMIT`/`PERF_MEM_LIMIT`) y a `frontend` (fijo, 0.25 CPU/128M, para que nginx no le quite recursos al host durante la medición del backend — nunca se benchmarquea el frontend con esto, ver §6). Uso:

```bash
PERF_CPU_LIMIT=0.25 PERF_MEM_LIMIT=512M docker compose -p territorio-e2e -f docker-compose.e2e.yml -f docker-compose.performance.yml up -d
```

Un override equivalente, `docker-compose.multi-instance.performance.yml`, aplica el **mismo** límite a `api-a` y `api-b` para la comparación single-vs-multi bajo límites iguales (§29). Ninguno de los dos se fusiona con `docker-compose.prod.yml`.

### Evidencia de límites efectivos (`docker inspect`, no solo YAML)

| Perfil | CPU objetivo | Memoria objetivo | `NanoCpus` real | `Memory` real |
| --- | --- | --- | --- | --- |
| A | 0.25 | 512M | `250000000` (=0.25) | `536870912` (=512MiB exacto) |
| B | 0.50 | 1024M | `500000000` (=0.50) | `1073741824` (=1GiB exacto) |
| C | 1.00 | 2048M | `1000000000` (=1.00) | `2147483648` (=2GiB exacto) |

Los tres confirmados exactos — el motor Docker sí aplicó el límite, no solo lo aceptó en el YAML.

## 26. Resultados por perfil — mismo escenario comparable (baseline, 10 VUs, 1m, dataset S)

| Perfil | RPS | p50 | p90 | p95 | p99 | max | Error rate | CPU peak (api) | Memory peak (api) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **A** (0.25 CPU/512M) | 5.03 | 1000ms | 2590ms | 3150ms | **21070ms** | 21090ms | 0% | ~25-27% (pinned) | **99.97%** (511.8/512MiB, pico transitorio al inicio) |
| **B** (0.50 CPU/1024M) | 15.26 | 410ms | 805ms | 1000ms | 3630ms | 7680ms | 0% | ~49-51% (pinned) | 74.81% (766MB/1GB, pico transitorio) |
| **C** (1.00 CPU/2048M) | 34.19 | 142ms | 335ms | 427ms | 823ms | 4900ms | 0% | ~97-101% (pinned) | 6.87% (140MB/2GB, sin pico) |
| Sin límite (pass 1, referencia) | 42.77 | 120ms | 253ms | 306ms | 474ms | 682ms | 0% | hasta ~200% (host libre) | ~9-35% (163-190MB) |

CPU pinned en el límite exacto en los tres perfiles (confirmado por `docker stats`, normalizado a 1 core = 100%) — evidencia directa de que el backend está CPU-bound en A y B, y muy cerca de estarlo en C. **256 CPU units (Profile A) satura ya con 10 VUs concurrentes** — p99 de 21 segundos, muy lejos de ser aceptable para tráfico real.

### 26.1 Capacidad sostenible aproximada — Profile A específicamente

A 10 VUs, Profile A ya está claramente degradado. Se probó una concurrencia menor:

| VUs | RPS | p50 | p95 | p99 |
| --- | --- | --- | --- | --- |
| 3 | 8.69 | 191ms | 603ms | 1190ms |
| 10 | 5.03 | 1000ms | 3150ms | 21070ms |

La capacidad sostenible de Profile A (0.25 CPU) para este mix de tráfico está aproximadamente entre **3 y 5 VUs concurrentes** — muy por debajo de lo que cualquier campaña real necesitaría simultáneamente incluso en su forma más modesta.

## 27. Memory headroom — separado de CPU, con evidencia propia

El hallazgo más importante de esta pasada sobre memoria: **la presión de memoria es consecuencia de la restricción de CPU, no independiente de ella.** En la primera pasada (sin límite de CPU), la memoria del backend nunca superó ~190MB bajo ningún escenario, incluido `stress` a 200 VUs. Bajo límites de CPU explícitos:

- **Profile A (512M)**: pico transitorio a **99.97%** del límite (511.8MiB/512MiB) en los primeros ~10 segundos del run (coincide con el warm-up + la ráfaga inicial de VUs arrancando simultáneamente), luego cae y se estabiliza en 9-35MB el resto del run. **Sin OOM-kill** (`docker inspect --format '{{.State.OOMKilled}}'` → `false`, `RestartCount=0`) — pero con menos de un 0.1% de margen en ese instante.
- **Profile B (1024M)**: pico similar pero proporcionalmente menor, 74.81% (766MB/1GB).
- **Profile C (2048M)**: sin pico — 6.87% (140MB/2GB) en todo momento.

**Interpretación con evidencia, no supuesta**: cuando el CPU asignado es insuficiente para procesar las peticiones tan rápido como llegan, las conexiones/requests entrantes se acumulan en memoria (buffers de conexión, objetos de petición en cola dentro del threadpool de Starlette) mientras esperan CPU disponible — un efecto DOWNSTREAM de la restricción de CPU, no una fuga de memoria independiente. Esto se confirma porque el pico desaparece completamente en Profile C, donde hay CPU de sobra.

**Conclusión de dimensionamiento**: `backend_task_memory=512` (valor actual) tiene **margen insuficiente** si `backend_task_cpu` se mantiene en 256 — un pico de arranque ya lo llevó al 99.97%. Memoria y CPU deben subir juntos en este caso específico, **no** porque "más CPU siempre necesita más memoria" como regla general (Profile C con más CPU usó *menos* memoria, no más) — sino porque este backend en particular, cuando le falta CPU, compensa acumulando en memoria.

## 28. Investigación "idle in transaction" — resultado: NO es un defecto

Muestreo de `pg_stat_activity` durante una carga real (Profile C, 30 VUs, escenario `load`), cada ~8s:

| Muestra | `active` | `idle` | `idle in transaction` | Edad máx. de transacción |
| --- | --- | --- | --- | --- |
| 1 | — | 2 | 13 | 0.7s |
| 2 | — | 2 | 13 | 0.7s |
| 3 | — | 0 | 15 | 0.4s |
| 4 | — | 1 | 14 | 0.7s |
| 5 | — | 1 | 14 | 0.8s |

**Post-load transaction check** (mismo stack, inmediatamente y después):

| Momento | `idle` | `idle in transaction` |
| --- | --- | --- |
| Inmediatamente al terminar k6 | 5 | **0** |
| +~30s | 5 | **0** |
| +~60s | 5 | **0** |

**Diagnóstico, con evidencia — hipótesis (C) confirmada, (A) parcialmente (transitorio sí, pero explicado, no solo "normal por instantánea"), (B) y (D) refutadas**: las conexiones "idle in transaction" observadas durante carga activa nunca superan **0.8 segundos** de antigüedad — consistentes con el patrón de sesión de SQLAlchemy (`with SessionLocal() as session`, transacción implícita abierta desde el primer `SELECT`/`INSERT` hasta que la petición termina y la sesión se cierra al salir del `with`) combinado con el tiempo real que tarda cada request en procesarse bajo la carga del momento. **Cero conexiones quedaron "idle in transaction" ya sin carga activa**, ni a los 5, 30 ni 60 segundos — descarta categóricamente una fuga de transacciones sin cerrar o un defecto del ciclo de vida de la sesión. **No se requiere ningún cambio de código, y no se abrió ningún test de regresión** — no hay defecto que corregir.

## 29. Pool saturation — evidencia real, no solo "llegó al máximo"

Se revisaron los logs del contenedor `api` de **todas** las corridas de esta segunda pasada buscando `QueuePool`, `TimeoutError`, mensajes de pool timeout, "too many connections" o `OperationalError`: **cero coincidencias** en ningún escenario, incluidos los perfiles A/B más degradados. El pool sí llegó a su máximo teórico (15-16 conexiones observadas en pass 1 §6, patrón similar aquí) — pero **nunca produjo un error de adquisición de conexión**: las peticiones se encolan y esperan (dentro de `pool_timeout=30s`), lo que se manifiesta como latencia alta (p99 de Profile A), no como errores 5xx. Esto es consistente con el resto de la evidencia: el 0% de error HTTP en A/B/C (§26) a pesar de la degradación de latencia severa.

## 30. Connection budget por task — tabla real

`pool_size=5 + max_overflow=10 = 15` conexiones máximas por **worker** de SQLAlchemy (no por task — un task con `WEB_CONCURRENCY=2` tiene 2 pools independientes, ver §33).

| Tasks | Workers/task | Conexiones máx. teóricas |
| --- | --- | --- |
| 1 | 1 | 15 |
| 2 | 1 | 30 |
| 4 | 1 | 60 |
| 2 (perfil RECOMMENDED, §41) | 1 | **30** |
| 4 (techo de autoscaling, perfil RECOMMENDED) | 1 | **60** |

Este total debe dejar headroom aparte para: la migration task (identidad maestra, conexión puntual durante el release), la bootstrap task (idem), y cualquier acceso administrativo directo — ninguno de estos se cuantifica aquí (son conexiones breves, no sostenidas), pero deben tenerse en cuenta al fijar el límite de conexiones de RDS Proxy (§44).

## 31. Dataset scaling — S / M / L

`backend/scripts/scale_loadtest_dataset.py` (nuevo) genera recintos/juntas sintéticos adicionales sobre el **mismo** `electoral_process` del fixture (mismas parish/canton/province ya válidas — nunca rompe FKs), con multiplicadores **técnicos**, no una estimación de producción real.

**Corrección sobre la primera pasada**: el conteo "6 recintos / 16 juntas" de §2 era un conteo **global** de la base (`select count(*) from polling_places`, sin filtrar por `electoral_process`) — incluye recintos de otros fixtures (p. ej. `territorio-sintetico-e2e`). El dataset real y correctamente acotado al `electoral_process` que los endpoints de esta suite consultan (`E2E_ELECTION_DAY_2027`, campaña `gualaceo-e2e-2027`) es:

| Dataset | Recintos | Juntas | Multiplicador real |
| --- | --- | --- | --- |
| **S** (fixture base) | 3 | 8 | 1× |
| **M** | 63 | 188 | ~21× |
| **L** | 253 | 758 | ~84× |

Mismo escenario (baseline, 10 VUs, 1m, mix `mixed`), mismo Profile C (1 CPU/2GB) para aislar la variable de dataset:

| Dataset | RPS | p50 | p95 | p99 | DB CPU peak | API CPU peak |
| --- | --- | --- | --- | --- | --- | --- |
| S | 34.19 | 142ms | 427ms | 823ms | ~8-11% | ~97-101% (pinned) |
| M (~21×) | 32.03 | 162ms | 488ms | 711ms | no capturado por separado | ~97-101% (pinned) |
| L (~84×) | **22.26** | 272ms | **764ms** | 1090ms | **~17-25%** | ~97-101% (pinned) |

**El cuello de botella sigue siendo el backend CPU-bound (pinned en el límite en los tres tamaños)** — pero el trabajo de PostgreSQL crece de forma visible con el dataset (CPU de `db` sube de ~9% a ~25% de S a L), y el RPS cae ~35% de S a L. **Conclusión con evidencia**: a la escala probada (hasta ~84×, 253 recintos/758 juntas), el dataset todavía no desplaza el cuello de botella hacia PostgreSQL, pero la tendencia es visible y consistente — a un múltiplo mayor (no probado aquí, ver limitaciones) es razonable esperar que la DB eventualmente co-limite. No se afirma esto como medido más allá de 84×.

### PostGIS

Los flujos de Election Day seleccionados (coverage/control-center/polling-places) usan `latitude`/`longitude` (`Float`), **no** geometría PostGIS — no se fuerza una carga PostGIS artificial sobre ellos. El endpoint real que sí ejecuta consultas espaciales (`GET /campaigns/{id}/map/boundaries?level=PARISH|CANTON`, `MapService` sobre columnas `SpatialGeometry("MULTIPOLYGON")` de `parishes`/`cantons`) se midió por separado, sin carga concurrente (timing de request único, bajo Profile C): 20-38ms por respuesta (5 muestras PARISH, 3 CANTON, todas `200`). No se integró al mix principal de k6 porque el flujo real de Jornada Electoral no lo usa — medirlo ahí distorsionaría la mezcla de tráfico sin representar un flujo real.

## 32. Single vs multi-instance bajo límites iguales

Misma metodología que la primera pasada (§5) pero con **exactamente el mismo límite por task** (Profile B, 0.50 CPU/1024M cada una — nunca "una instancia grande contra dos pequeñas"), mismos 10 VUs totales:

| | Solo `api-a` (1× Profile B) | `api-a` + `api-b` (2× Profile B) | Δ |
| --- | --- | --- | --- |
| RPS | 14.37 | 28.06 | **+95.3%** |
| p50 | 403ms | 97ms | **-76%** |
| p90 | 893ms | 567ms | -37% |
| p95 | 1.11s | 748ms | -33% |
| p99 | 5.29s | 1.26s | **-76%** |
| Error rate | 0% | 0% | — |

**Scaling efficiency**: `28.06 / 14.37 = 1.953` → **97.6% del ideal 2×** — sustancialmente mejor que el 46% de mejora observado en la primera pasada sin límite (§5). Explicación coherente con toda la evidencia anterior: bajo límite de CPU explícito, el CPU **es** el recurso escaso real y compartirlo entre 2 procesos independientes casi duplica la capacidad; en el benchmark sin límite, otros factores (overhead del propio host, contención con el generador de carga) diluían ese efecto. Esta cifra (97.6%) es la evidencia más fuerte de todo el documento para justificar horizontal scaling sobre vertical scaling como estrategia primaria de este backend.

## 33. Experimento `WEB_CONCURRENCY` — evidencia, no recomendación automática

Justificación previa (antes de ejecutar el experimento, por instrucción explícita): en Profile A/B, la CPU del contenedor queda **pinned exactamente en su límite** durante toda la carga — evidencia de que el proceso está CPU-bound, no limitado por número de threads/workers disponibles. Esto sugiere (hipótesis a probar, no asumida) que añadir un segundo worker **sin** más CPU total no debería ayudar, porque ambos workers competirían por el mismo presupuesto de CPU ya agotado.

Experimento — mismo Profile B (0.50 CPU/1024M) **total**, mismo dataset, misma carga (10 VUs, 1m), única variable `WEB_CONCURRENCY`:

| | `WEB_CONCURRENCY=1` | `WEB_CONCURRENCY=2` | Δ |
| --- | --- | --- | --- |
| RPS | 15.26 | **12.46** | **-18.3%** |
| p95 | 1.00s | 1.86s | +86% |
| p99 | 3.63s | 5.56s | +53% |
| Error rate | 0% | **0.25%** (2/794) | empeora |

**Hipótesis confirmada**: con el mismo presupuesto total de CPU, `WEB_CONCURRENCY=2` es **peor** que `WEB_CONCURRENCY=1` — no solo no ayuda, degrada throughput, latencia, e introduce errores que no existían. Explicación coherente: cada worker abre su **propio** pool SQLAlchemy (2× 15 = 30 conexiones potenciales desde una sola task, el doble que con 1 worker) sin que exista más CPU para procesarlas, y el sistema operativo reparte el mismo 0.5 CPU entre dos procesos en vez de uno. **No se convierte esto en recomendación de cambiar `WEB_CONCURRENCY` en ninguna dirección** — el resultado es "no subirlo sin subir CPU proporcionalmente", que es simplemente mantener el default actual (`WEB_CONCURRENCY=1`) sin cambios.

## 34. Soak extendido (15 minutos, Profile B, 10 VUs)

Primera pasada: 5 minutos. Esta pasada ejecuta el mínimo pedido explícitamente (15 min) — no se intentó un soak de horas por límite de tiempo de esta revisión; ver limitación explícita abajo.

| Momento | Memoria `api` | CPU `api` | Memoria `db` | CPU `db` | `idle` | `idle in tx` |
| --- | --- | --- | --- | --- | --- | --- |
| Inicio (~10s) | 129.3MiB (12.63%) | 48.47% | 106.7MiB | 6.77% | 6 | 2 |
| Mitad (~7.5min) | 131.8MiB (12.87%) | 48.55% | 107MiB | 16.67% | 3 | 7 |
| Final (~15min) | 132.5MiB (12.94%) | 49.16% | 89.3MiB | 14.37% | 5 | **0** |

**Resultado k6 (15m, 10 VUs, mix `mixed`)**: 14957 requests, RPS **16.55**, p50 417ms, p90 885ms, p95 1.06s, p99 1.5s, max 7.68s, **0% error HTTP, 0% error técnico, 100% checks** (15407/15407). 87 réplicas idempotentes de incidencias, todas correctas.

**Memory growth**: **no** — 129.3MiB → 131.8MiB → 132.5MiB (inicio→mitad→final), variación de ~3MiB en 15 minutos, dentro de fluctuación normal de GC de Python, sin tendencia de crecimiento sostenido. `db`: 106.7→107→89.3MiB, igualmente estable (la bajada final es fluctuación normal, no una tendencia).

**DB connection growth**: **no** — `idle in transaction` fluctuó entre 0-7 durante la carga activa (mismo patrón transitorio de §28) y volvió a **0** exactamente al finalizar, igual que en la investigación dedicada. Sin crecimiento acumulativo de conexiones a lo largo de los 15 minutos.

**Limitación explícita, reconocida sin rodeos**: 15 minutos descarta una fuga grosera de memoria/conexiones a esa escala de tiempo — **no** valida estabilidad de horas. Un soak de producción real (horas, con el patrón de tráfico real de un día de elección completo) sigue pendiente, ver §54.

## 35. Recovery post-stress/spike (segunda pasada)

Repetido bajo perfiles limitados (Profile A/B durante §26): en ningún momento `/api/v1/health`/`/api/v1/ready` dejaron de responder tras finalizar una corrida degradada — mismo patrón que la primera pasada (§4.5). Adicionalmente, en esta pasada se confirmó explícitamente que un **endpoint funcional real** (no solo health) vuelve a su latencia normal: la corrida de Dataset S bajo Profile C inmediatamente después de la corrida de Dataset L (§31) mostró p95=427ms — coherente con el valor de Dataset S ya medido antes de escalar el dataset, no arrastra degradación de la corrida anterior.

## 36. Utilización del generador de carga (k6) y del host

**Limitación reconocida**: el contenedor k6 (`docker run --rm`, efímero) no se incluyó en la captura de `docker stats` de `loadtests/run.sh` (que solo apunta a `api`/`db` por diseño) — no se midió su CPU/memoria directamente en esta pasada. Evidencia indirecta de que no fue el cuello de botella: `http_req_blocked` (tiempo que k6 tarda en poder iniciar una conexión, la métrica que reflejaría contención del propio generador) se mantuvo en microsegundos (`avg` de un dígito a dos dígitos de µs) en **todos** los escenarios de ambas pasadas, incluidos los más degradados — si k6 mismo hubiera estado saturado, esa métrica subiría notablemente. No se declara esto como "medido directamente", solo como evidencia indirecta consistente.

Docker Desktop en general: 16 CPUs asignadas, nunca se observó que el conjunto de contenedores (incluido k6 corriendo brevemente) se acercara a agotar esa cifra — los límites por contenedor (Profile A/B/C) siempre fueron mucho menores que el total disponible, por lo que ningún resultado de esta pasada se marca como "host-limited": los límites observados fueron siempre los límites **configurados explícitamente** del contenedor `api`, no una restricción incidental del host compartido.

## 37. Cuello de botella final identificado

Backend CPU-bound, con memoria como efecto secundario dependiente de esa misma restricción — confirmado ahora con evidencia de **tres fuentes independientes**, no solo una:

1. CPU de `api` pinned exactamente en el límite configurado en los tres perfiles (§26).
2. Memoria en pico solo cuando CPU es insuficiente, desaparece con más CPU (§27).
3. `WEB_CONCURRENCY=2` con el mismo CPU total empeora — confirma que el límite es CPU real, no número de workers (§33).
4. Scaling horizontal (2 instancias, mismo límite c/u) casi duplica la capacidad (97.6% del ideal) — confirma que el recurso escaso es CPU por instancia, no algo compartido entre instancias como la DB (§32).

PostgreSQL sigue sin ser el cuello a la escala probada (hasta Dataset L, ~84×) — su CPU crece con el dataset pero se mantiene muy por debajo de saturación (§31).

## 38. Recomendación final — backend CPU/memoria

| Opción | ¿Suficiente? |
| --- | --- |
| A. 256/512 suficiente | **No** — Profile A satura con solo 10 VUs (p99 21s), y memoria llega a 99.97% de 512MB en un pico transitorio de arranque |
| B. CPU insuficiente | **Sí, evidencia directa** — Profile A/B ambos quedan CPU-pinned bajo carga moderada |
| C. Memoria insuficiente | **Sí, condicionalmente** — insuficiente SI se mantiene 256 CPU (el pico de memoria es consecuencia de la falta de CPU); con más CPU (Profile C) la misma memoria de 512-2048M nunca se acerca a su límite |
| D. Ambos insuficientes | Confirmado para el par actual (256/512) bajo el patrón de tráfico probado |

**Recomendación**: `backend_task_cpu` no debe quedarse en 256 como valor único de producción sin al menos evaluar 512 (Profile B mostró 3× más RPS que Profile A) — **confidence: MEDIUM** (evidencia local fuerte, pero sin equivalencia directa a CPU credits/throughput real de Fargate). `backend_task_memory=512` es marginal si CPU se queda en 256; con 512 CPU o más, 512-1024 de memoria tiene margen amplio — **confidence: HIGH** para la relación CPU↔memoria observada localmente, **MEDIUM** para el valor absoluto exacto recomendado a AWS.

## 39-41. `desired_count` / `min_capacity` / `max_capacity`

Sin cambios respecto al razonamiento de la primera pasada (§12) — **reforzado** con evidencia nueva: la comparación single-vs-multi bajo límites iguales (§32) muestra que 2 instancias no solo dan HA, dan casi el doble de capacidad real (97.6% de eficiencia) bajo el mismo presupuesto de CPU total que 1 instancia más grande tendría. Esto es evidencia adicional (no solo teórica) para preferir **escalar horizontalmente (más tasks) sobre escalar verticalmente (task más grande)** como estrategia primaria, una vez CPU/task esté en un nivel razonable (≥512, §38).

- `backend_desired_count`: **≥ 2** — confidence: **HIGH** (HA, y ahora también rendimiento medido).
- `backend_min_capacity`: **2** — confidence: HIGH.
- `backend_max_capacity`: **4** (perfil RECOMMENDED) — confidence: **MEDIUM** (extrapolación desde 2 instancias medidas a 4, nunca se midieron 4 instancias reales).

## 42. Headroom

Con Profile B (512 CPU) y 10 VUs ya se observa degradación real (p99 3.6s) — el headroom recomendado no es "correr exactamente al nivel medido como aceptable" sino mantener autoscaling activo (CPU target 70%, sin cambio) para que el sistema añada tasks **antes** de llegar al punto de degradación observado aquí. No se dimensiona a saturación en ningún perfil.

## 43. Perfil de picos — Fargate startup timing

Sigue **PENDIENTE DE VALIDAR EN AWS** — ningún resultado local mide cuánto tarda Fargate en lanzar una task nueva. Confidence: **LOW** (no medible localmente, sin excepción).

## 44. Frontend — confirmación conservadora

`frontend` se acotó a 0.25 CPU/128M durante todos los benchmarks de esta pasada (§25) precisamente para que no compitiera por recursos con la medición del backend — nunca se sometió a carga. Confirmación mínima pedida: esos valores (0.25 CPU/128M, deliberadamente bajos para AISLAR, no para recomendar) no fueron un problema — `frontend` permaneció healthy durante las ~2 horas de esta sesión de benchmarking sin reinicios. No se re-evalúa CPU/memoria "reales" de frontend más allá de esto — sigue dominado por HA/número de tasks, no por rendimiento (§15 de la primera pasada, sin cambios). Confidence: **MEDIUM** (confirmación de que no es absurdo, no un benchmark dedicado).

## 45. RDS — clasificación de riesgo (no traducción directa)

**No se traduce CPU del contenedor PostgreSQL local a una clase RDS** — seguido estrictamente. Usando DB CPU (§31, hasta ~25% con Dataset L), memoria (siempre baja, nunca factor), conexiones (§30, dentro de lo esperado) y sensibilidad a dataset (creciente pero moderada hasta 84×) para clasificar riesgo:

- **Clase inicial candidata**: `db.t4g.micro` — el trabajo de PostgreSQL observado localmente (CPU máx. ~25% incluso con 84× el dataset base y 10 VUs concurrentes) no muestra señales de necesitar más que un burstable pequeño **a esta escala de datos probada**. Confidence: **LOW-MEDIUM** — ver riesgo de CPU credits abajo (§46).
- **Alternativa con más margen**: `db.t4g.small` o una clase `db.m` no-burstable si el volumen real de la elección objetivo resulta órdenes de magnitud mayor que Dataset L, o si Multi-AZ + tráfico sostenido de jornada electoral consume CPU credits más rápido de lo que se acumulan.
- **Aspectos que obligan a validar AWS**: CPU credits burstable bajo carga sostenida de horas (§46), I/O real de EBS, throughput de red real, comportamiento bajo el patrón de escritura real de actas/incidencias (no solo el mix de esta suite).

## 46. Riesgo de CPU credits burstable — declarado explícitamente

`db.t4g.micro` es una instancia **burstable** (créditos de CPU acumulados/consumidos, no CPU dedicada constante) — el contenedor Docker local **no tiene ningún concepto de créditos burstable**, corre con acceso directo al CPU del host sujeto solo a los límites de Docker que se le impongan. Ningún resultado de esta pasada (ni la primera) mide, ni puede medir, agotamiento de créditos de CPU bajo carga sostenida de varias horas — el soak de 15 minutos (§34) es demasiado corto incluso para esto. **No se declara `db.t4g.micro` suficiente para un Election Day sostenido sin un benchmark AWS real.** Confidence: **LOW**, explícitamente, hasta que exista ese benchmark.

## 47. Multi-AZ — separado de rendimiento

Sin cambios respecto a la primera pasada (§13/§47 original) — decisión de disponibilidad para la ventana del día de la elección, nunca mezclada con los resultados de CPU/memoria de esta pasada. Ningún benchmark de esta segunda pasada mide failover ni disponibilidad.

## 48. SQLAlchemy pool — recomendación (sin cambiar en esta pasada)

No se modificó `pool_size`/`max_overflow`/`pool_timeout` en ningún código productivo — los experimentos de `WEB_CONCURRENCY` (§33) usaron exclusivamente el override de benchmark (`docker-compose.performance.yml`), nunca tocaron `config.py`. Con la tabla de connection budget (§30) y el perfil RECOMMENDED (2-4 tasks), el total teórico (30-60 conexiones) es la entrada para dimensionar RDS Proxy (§49) — el valor actual de `pool_size=5`/`max_overflow=10` **no mostró evidencia de ser insuficiente por sí mismo** en ningún escenario (nunca hubo un error de adquisición de conexión, §29) — el cuello siempre fue CPU antes que el pool se convirtiera en el limitante real. Confidence: **HIGH** en que el pool actual no es el problema; **MEDIUM** en que sea el valor óptimo (no se probaron valores alternativos).

## 49. RDS Proxy — tuning pendiente, impacto de tasks/workers documentado

Se mantiene el tuning de Fase 4C.3 sin cambios (pendiente de AWS, igual que la primera pasada). Impacto documentado del crecimiento de tasks/workers sobre conexiones cliente→proxy→DB: cada task adicional con `WEB_CONCURRENCY=1` suma hasta 15 conexiones potenciales hacia RDS Proxy (§30); RDS Proxy multiplexa esas conexiones cliente hacia un número menor de conexiones reales a la instancia RDS — la razón exacta de multiplexado **no es medible localmente** (no existe RDS Proxy real en ningún stack de prueba). Métricas reales a observar después en AWS: `DatabaseConnections` de RDS (conexiones reales, multiplexadas) vs. conexiones cliente reportadas por RDS Proxy (`ClientConnections`) — la brecha entre ambas es la señal de multiplexado funcionando.

## 50. WAF rate limit — evaluación final

Sin cambios de valor. Usando los RPS medidos en ambas pasadas para los escenarios pedidos:

| Escenario | RPS estimado por IP | ¿Alcanza 2000/300s (~6.67 req/s sostenidos)? |
| --- | --- | --- |
| Un usuario real (delegado consultando manualmente) | < 1 req/s | No, muy por debajo |
| Varios usuarios tras el mismo NAT (ej. 10 delegados de campo compartiendo salida a internet corporativa/móvil) | Podría acumular varios req/s combinados — el escenario `mixed` a 10 VUs de esta suite ya genera ~15-42 RPS (según perfil), equivalente a ese caso agregado | Sí, plausible en minutos si el patrón de esta suite representa el tráfico real de 10 personas |
| Cliente automatizado legítimo (ej. un dashboard con auto-refresh agresivo) | Dependiente de la frecuencia de refresh configurada | Posible si el refresco es cada pocos segundos |
| Abuso (scraping/ataque) | Por diseño, muy por encima | Sí, ese es el propósito del límite |

**No se confunde capacidad del backend con política de abuso** — el backend (con recursos adecuados, Profile C) sostiene 34+ RPS sin problema; el límite de WAF es una política de tráfico por IP, independiente de cuánta capacidad tenga el backend. La observación de la primera pasada se mantiene: NAT compartido con varios delegados reales podría acercarse al límite — decisión final pendiente de tráfico real en AWS, ningún cambio aplicado.

## 51. CloudWatch thresholds — tabla final con confidence

| Métrica | Threshold actual | Normal observado (Profile C, dataset S) | Bajo estrés (Profile A) | Threshold propuesto | Confidence |
| --- | --- | --- | --- | --- | --- |
| ALB `TargetResponseTime` | 2s | 0.43s (p95, Profile C) | 3.15s (p95, Profile A) | Sin cambio — sin ALB real que valide | LOW |
| ECS CPU | 85% | ~100% (Profile C, pinned — el propio límite) | ~25-27% (Profile A, pinned — su propio límite, menor en términos absolutos) | Sin cambio — el % siempre es relativo al límite de la task, 85% sigue siendo razonable como alarma temprana | MEDIUM |
| ECS memoria | 85% | 6.87% (Profile C) | **99.97%** (Profile A, pico transitorio) | **Revisar** — con Profile A/perfil MINIMUM, un pico transitorio ya cruzaría 85% en segundos; con Profile C nunca se acerca. Depende directamente de qué perfil final se adopte | MEDIUM-HIGH (evidencia directa del pico, pero threshold final depende del task size elegido) |
| RDS CPU | 80% | ~8-25% (S a L) | No aplica (RDS no limitado en estos benchmarks) | Sin cambio | LOW (sin RDS real) |
| RDS `FreeableMemory` | 256MB | Sin datos locales de memoria de PostgreSQL bajo presión real | — | Sin cambio | LOW |
| RDS `DatabaseConnections` | 80 | Hasta 16 (1 task) | — | Revisar con el connection budget de §30 (30-60 con perfil RECOMMENDED) una vez fijado el número final de tasks | MEDIUM |

## 52. Perfiles finales — recalculados con confidence levels

### MINIMUM

| | Valor | Confidence |
| --- | --- | --- |
| Backend tasks | 2 (HA real, sin autoscaling) | HIGH (HA) |
| Backend CPU/memoria | **512/1024** (subido de 256/512 — evidencia directa de que 256/512 satura con tráfico moderado, §38) | MEDIUM |
| Frontend tasks | 2 | HIGH (HA) |
| RDS class | `db.t4g.micro` | LOW-MEDIUM (§45-46) |
| Multi-AZ | `false` | HIGH (decisión de costo, no de rendimiento) |
| Observación | Ya no es "256/512 con 2 tasks" — la evidencia de esta pasada obliga a subir el par CPU/memoria incluso en el perfil mínimo, o aceptar explícitamente una capacidad muy baja por task |

### RECOMMENDED

| | Valor | Confidence |
| --- | --- | --- |
| Backend tasks | min=2, max=4 | MEDIUM (extrapolado desde 2 medidas) |
| Backend CPU/memoria | **512-1024 / 1024-2048** (rango — Profile B ya triplica RPS de Profile A; Profile C casi iguala el benchmark sin límite) | MEDIUM |
| Frontend tasks | min=2, max=4 | MEDIUM |
| RDS class | `db.t4g.micro`, revisar si Multi-AZ se activa para el día de la elección | LOW-MEDIUM |
| Multi-AZ | Evaluar `true` para la ventana del día de la elección | HIGH (decisión), LOW (impacto medido — no se probó) |
| Autoscaling | CPU target 70% sin cambio; ECS memoria revisar threshold (§51) si se elige el extremo bajo del rango de memoria | MEDIUM |
| Observación | Cambio material respecto a la primera pasada: ya no se recomienda 256/512 como CPU/memoria — Profile A demostró que es insuficiente incluso para 10 VUs |

### HIGH LOAD

| | Valor | Confidence |
| --- | --- | --- |
| Backend tasks | min=4, max=8-10 | LOW-MEDIUM (nunca medido más allá de 2 instancias reales) |
| Backend CPU/memoria | 1024/2048 (Profile C — el más cercano al comportamiento sin límite) | MEDIUM (Profile C sí se midió directamente) |
| Frontend tasks | min=2, max=4 | MEDIUM |
| RDS class | Candidato a clase mayor si el volumen real de tasks/conexiones lo justifica | LOW |
| Multi-AZ | `true` recomendado | HIGH (decisión), LOW (impacto medido) |
| Observación | El más especulativo de los tres, pero ahora anclado en Profile C real (no solo el benchmark sin límite de la primera pasada) |

## 53. Elementos que siguen sin poder validarse localmente

Todo lo ya listado en §23 de la primera pasada, más: comportamiento de CPU credits burstable bajo carga sostenida de horas (§46), tiempo real de multiplexado de RDS Proxy (§49), si el pico de memoria transitorio (§27) se reproduce de forma distinta con la red/almacenamiento reales de Fargate (EBS/ENI en vez de un contenedor Docker local).

## 54. Qué debe repetirse en AWS

Todo lo de §24 de la primera pasada, más:
7. Repetir Profile A/B/C (con los valores de CPU/memoria reales de Fargate, no aproximaciones vía `docker inspect`) contra el stack real.
8. Confirmar si el pico de memoria transitorio bajo CPU insuficiente (§27) se reproduce igual en Fargate.
9. Repetir la comparación single-vs-multi (§32) con el ALB real repartiendo tráfico, no alternancia de cliente.
10. Medir CPU credits reales de `db.t4g.micro` (o la clase finalmente elegida) bajo un soak largo real.

---

# APLICACIÓN CONSERVADORA A TERRAFORM — Fase 4C.6 (tercera etapa)

Tras la segunda pasada, se aplicaron a `infra/terraform/environments/prod/` **únicamente** los valores con evidencia local HIGH o MEDIUM, siguiendo exactamente el perfil RECOMMENDED documentado en §52. Ningún valor LOW quedó aplicado — permanecen como estaban, marcados `PENDING AWS VALIDATION`.

**Nota sobre el perfil RECOMMENDED de §52**: la tabla documenta CPU/memoria de backend como un **rango** ("512-1024 / 1024-2048"), no un único valor — porque cubre tanto Profile B como Profile C, ambos con confidence MEDIUM. Para Terraform se necesita un valor concreto; se eligió el **extremo superior del rango** (1024/2048 = Profile C), porque es el punto directamente medido con más margen (memoria nunca superó 6.87%, p95/p99 más cercanos al benchmark sin límite) — coincide numéricamente con lo que §52 etiqueta por separado como el par CPU/memoria de HIGH LOAD, pero **no** se adoptó el resto de HIGH LOAD (tasks min=4/max=8-10, Multi-AZ `true`): `backend_desired_count`/`min_capacity`/`max_capacity` aplicados son los de RECOMMENDED (2/2/4), no los de HIGH LOAD.

## Tabla final — Setting / Measured / Recommended / Applied / Confidence / AWS validation

| Setting | Measured evidence | Recommended value | Applied? | Confidence | AWS validation required? |
| --- | --- | --- | --- | --- | --- |
| `backend_task_cpu` | Profile A (0.25vCPU) satura con 10 VUs, p99 21s; Profile C (1vCPU) 34.19 RPS, p95 427ms, 0% error | 1024 | **APPLIED** (256→1024) | MEDIUM | Sí — CPU credits N/A (no burstable en Fargate estándar), pero throughput/latencia real de Fargate no medido |
| `backend_task_memory` | Profile A: pico 99.97%/512MiB; Profile C: pico 6.87%/2048MiB | 2048 | **APPLIED** (512→2048) | MEDIUM | Sí |
| `backend_desired_count` | Scaling efficiency 97.6% del ideal 2x bajo límites iguales | 2 | **APPLIED** (1→2) | HIGH (HA) | No para HA; sí para throughput real |
| `backend_min_capacity` | Igual razón que `desired_count` | 2 | **APPLIED** (1→2) | HIGH | No |
| `backend_max_capacity` | Extrapolado desde 2 instancias medidas | 4 | Sin cambio (ya era 4) | MEDIUM | Sí — techo no medido más allá de 2 |
| `frontend_task_cpu`/`memory` | Frontend nunca fue cuello de botella en ningún benchmark | 256/512 | Sin cambio | MEDIUM (confirmación, no benchmark dedicado) | No prioritario |
| `frontend_desired_count`/`min_capacity` | HA, misma razón que backend | 2/2 | **APPLIED** (1→2) | HIGH (HA) | No |
| `frontend_max_capacity` | — | 4 | Sin cambio (ya era 4) | MEDIUM | No prioritario |
| `WEB_CONCURRENCY` | WC=2 con mismo CPU total: RPS -18%, p95 +86%, error 0%→0.25% | 1 | Sin cambio (ya era 1) | HIGH | No — resultado consistente y explicado |
| SQLAlchemy `pool_size`/`max_overflow`/`pool_timeout`/`pool_recycle`/`pool_pre_ping` | Sin errores de adquisición en ningún escenario; idle-in-tx transitorio (§28-29) | Sin cambio | Sin cambio (no es variable Terraform, vive en `backend/app/core/config.py`) | HIGH (no es el problema) | Sí — RDS Proxy real no medido, multiplexado desconocido |
| `db_instance_class` (RDS) | DB CPU ≤25% incluso con Dataset L; sin equivalencia Docker↔RDS burstable | `db.t4g.micro` | **Sin cambio** | LOW-MEDIUM | **Sí — PENDING AWS VALIDATION explícito, CPU credits no medibles localmente (§46)** |
| `db_multi_az` | Decisión de disponibilidad, no de rendimiento; impacto no medido | Evaluar `true` para el día de la elección | **Sin cambio** (`false`) | HIGH (decisión), LOW (impacto medido) | **Sí — PENDING**, decisión operativa/costo aún no tomada |
| `db_allocated_storage`/`max_allocated_storage` | Dataset sintético (hasta 84×) no representa crecimiento real de producción | Sin cambio | Sin cambio | LOW (sin datos de crecimiento real) | **Sí — PENDING**, sin extrapolar Dataset L a producción |
| RDS Proxy (`connection_borrow_timeout`, `max_connections_percent`, `max_idle_connections_percent`, `idle_client_timeout`) | RDS Proxy real no existe en ningún stack de prueba | Sin cambio | Sin cambio | LOW | **Sí — PENDING**, multiplexado real no medible localmente |
| `backend_cpu_target_value` (autoscaling) | Backend confirmado CPU-bound; ventana de degradación cruza 85% bien antes del colapso | 70 | Sin cambio (ya era 70) | MEDIUM | Sí — Fargate startup timing no medido |
| Autoscaling por memoria | Memoria nunca fue factor limitante independiente en ningún escenario | No implementar | Sin cambio (nunca existió) | HIGH (evidencia de que no aporta valor) | No |
| WAF rate limit (2000/300s/IP) | RPS del backend no correlaciona con política de abuso por IP | Sin cambio | Sin cambio | LOW (sin tráfico real de múltiples IPs) | **Sí — PENDING** |
| CloudWatch `ecs_memory_threshold_percent` (85%) | Pico 99.97% a 512MiB (Profile A); con el nuevo `backend_task_memory=2048` el pico observado (Profile C) fue solo 6.87% | Sin cambio | Sin cambio | MEDIUM-HIGH | No — la preocupación original quedó resuelta al subir la memoria de la task, no al bajar el threshold |
| CloudWatch `rds_database_connections_threshold` (80) | Connection budget con 2 tasks = 30 teóricas (§30/§46) | Revisar una vez fijado el perfil final de RDS Proxy | Sin cambio | MEDIUM (cálculo), LOW (sin RDS Proxy real) | **Sí — PENDING**, depende de RDS Proxy no medido |
| Resto de thresholds CloudWatch (ALB latency, RDS CPU/memoria) | Sin ALB/RDS reales | Sin cambio | Sin cambio | LOW | **Sí — PENDING** |

## Combinación Fargate validada

`backend_task_cpu=1024` (1 vCPU) admite memoria entre 2048 y 8192 MiB en incrementos de 1024 MiB, según la tabla de combinaciones válidas de AWS Fargate (documentada públicamente por AWS, no específica de esta cuenta) — `2048` es el extremo inferior de ese rango y una combinación válida. `frontend_task_cpu=256` (0.25 vCPU) admite memoria entre 512 y 2048 MiB en incrementos de 1024 MiB — `512` sigue siendo válida (sin cambio). Esta combinación no se verificó contra la API real de ECS (no se ejecutó `apply`) — la validación definitiva ocurre en AWS real al crear la task definition.

## Archivos modificados en esta etapa

- `infra/terraform/environments/prod/variables.tf` — defaults de `backend_task_cpu`, `backend_task_memory`, `backend_desired_count`, `backend_min_capacity`, `frontend_desired_count`, `frontend_min_capacity` (con comentarios trazando cada valor a su evidencia).
- `infra/terraform/environments/prod/terraform.tfvars.example` — mismos valores, con comentarios equivalentes.

Ningún módulo reutilizable (`infra/terraform/modules/*`) fue modificado — los valores se establecieron en `environments/prod`, manteniendo los módulos genéricos.

## Conclusión (actualizada, ambas pasadas)

La primera pasada (sin límite de recursos) sobreestimó la capacidad real: 42.77 RPS/p95 306ms con el backend usando hasta ~200% de CPU del host, una condición que **nunca existirá** en una Fargate task de 256 CPU units. La segunda pasada, con límites de CPU/memoria verificados vía `docker inspect`, muestra que **256/512 (la configuración Terraform actual) satura con solo 10 VUs concurrentes** (p99 21 segundos, memoria a 99.97% de su límite en un pico transitorio) — evidencia directa y suficiente para **no** mantener 256/512 como recomendación de producción. Con más CPU (Profile B/C), tanto throughput como memoria mejoran sustancialmente y de forma coherente con toda la evidencia cruzada (CPU pinned, ausencia de errores de pool, mejora casi lineal al escalar horizontalmente bajo el mismo presupuesto de CPU). La investigación de "idle in transaction" descarta un defecto real con evidencia concluyente (edad máxima de transacción bajo carga: <1s; cero conexiones colgadas a los 60s post-carga). El dataset scaling (hasta ~84×) no desplazó el cuello de botella hacia PostgreSQL, aunque muestra una tendencia de creciente presión sobre la DB que debe vigilarse a escalas mayores. El experimento `WEB_CONCURRENCY=2` confirma, con evidencia y no solo teoría, que no debe tocarse sin aumentar CPU proporcionalmente. Ningún resultado se oculta ni se suaviza: los perfiles finales (§52) reflejan honestamente que la recomendación de CPU/memoria cambió respecto a los valores actuales de Terraform. **En la tercera etapa de esta fase, ese cambio SÍ se aplicó** — de forma conservadora, únicamente los valores con confidence HIGH/MEDIUM (backend/frontend CPU/memoria/desired/min capacity), dejando explícitamente sin tocar todo lo marcado LOW (RDS instance class, Multi-AZ, storage, RDS Proxy, WAF, la mayoría de thresholds de CloudWatch) — ver la tabla "Setting/Measured/Recommended/Applied/Confidence/AWS validation" arriba. Ningún `terraform plan`/`apply` se ejecutó; los cambios quedan en el código para revisión humana antes de cualquier despliegue real.

