# Resumen versionable de resultados — Fase 4C.6

Pequeño y versionable a propósito — los JSON/CSV completos de cada corrida (`--summary-export` de k6 + `docker stats`) se generan en esta misma carpeta pero están ignorados por `.gitignore` (grandes, no deterministas, un archivo por corrida). El análisis completo está en [`docs/performance/PERFORMANCE_BASELINE.md`](../../docs/performance/PERFORMANCE_BASELINE.md). "not executed" = escenario no corrido, nunca una celda inventada.

## Primera pasada — SIN límite de CPU/memoria (no comparable a Fargate real)

| Escenario | Mezcla | VUs | RPS | p50 | p95 | p99 | Error rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| smoke | mixed | 2 | 14.53 | 44ms | 89ms | 113ms | 0% |
| baseline | mixed | 10 | 42.77 | 120ms | 306ms | 474ms | 0% |
| baseline | read | 10 | 36.31 | 176ms | 451ms | 605ms | 0% |
| baseline | write | 10 | 16.95 | 84ms | 182ms | 563ms | 0% |
| baseline | auth | 10 | 15.35 | 123ms | 255ms | 522ms | 0% |
| load | mixed | 50 (ramp) | 40.91 | 1027ms | 1671ms | 2094ms | 0% |
| stress | mixed | 25→200 (escalonado) | 9.15 | 610ms | ~60s (timeout) | ~60s (timeout) | 8.57% |
| spike | mixed | 10→120→10 | 6.52 | 192ms | ~60s (timeout) | ~60s (timeout) | 15.27% |
| soak (corto, 5min) | mixed | 15 | 42.61 | 241ms | 505ms | 623ms | 0% |
| single-instance | mixed | 10 | 40.90 | 130ms | 310ms | 520ms | 0% |
| multi-instance (2×) | mixed | 10 (repartidos) | 59.85 | 50ms | 178ms | 292ms | 0% |

## Segunda pasada — resource-constrained (límites verificados con `docker inspect`)

Mismo escenario baseline (10 VUs, 1m, dataset S salvo donde se indica) en todas las filas, salvo donde se anota.

| Perfil/variante | CPU limit | Mem limit | RPS | p50 | p95 | p99 | Error rate | Mem peak (api) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Profile A | 0.25 | 512M | 5.03 | 1000ms | 3150ms | 21070ms | 0% | 99.97% |
| Profile A (3 VUs, capacidad sostenible) | 0.25 | 512M | 8.69 | 191ms | 603ms | 1190ms | 0% | — |
| Profile B | 0.50 | 1024M | 15.26 | 410ms | 1000ms | 3630ms | 0% | 74.81% |
| Profile C | 1.00 | 2048M | 34.19 | 142ms | 427ms | 823ms | 0% | 6.87% |
| Profile C, Dataset M (~21×) | 1.00 | 2048M | 32.03 | 162ms | 488ms | 711ms | 0% | — |
| Profile C, Dataset L (~84×) | 1.00 | 2048M | 22.26 | 272ms | 764ms | 1090ms | 0% | — |
| Single-instance (mi, api-a) | 0.50 | 1024M | 14.37 | 403ms | 1110ms | 5290ms | 0% | — |
| Multi-instance (mi, api-a+api-b) | 0.50 c/u | 1024M c/u | 28.06 | 97ms | 748ms | 1260ms | 0% | — |
| Profile B, `WEB_CONCURRENCY=2` (experimental) | 0.50 | 1024M | 12.46 | 445ms | 1860ms | 4880ms | 0.25% | — |
| Soak extendido (15min, Profile B) | 0.50 | 1024M | 16.55 | 417ms | 1060ms | 1500ms | 0% | estable, sin crecimiento (129→132MiB) |

**256/512 (config Terraform actual) = Profile A** — satura con solo 10 VUs (p99 21s, memoria al 99.97%). Scaling horizontal bajo límites iguales (single→multi) da 97.6% del ideal 2× (vs. 46% sin límite en la primera pasada) — el CPU por instancia es el recurso escaso real. `WEB_CONCURRENCY=2` con el mismo CPU total empeora todo. Idle-in-transaction: 0 conexiones colgadas a los 5/30/60s post-carga — no es un defecto. Ver `PERFORMANCE_BASELINE.md` para el análisis completo, recomendaciones finales con confidence levels, y las incertidumbres pendientes de validar en AWS.
