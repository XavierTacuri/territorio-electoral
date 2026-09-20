# Checklist de release — Territorio Electoral

Marque cada punto contra el entorno de destino real antes de promover un despliegue. Ver DEPLOYMENT.md, OPERATIONS.md y SECURITY.md para el detalle de cada paso.

## Seguridad

- [ ] `backend/.env.production` creado a partir de `.env.production.example`, sin ningún valor `replace_me`/`change-me`.
- [ ] `SECRET_KEY`, `BROWSER_REFRESH_TOKEN_HMAC_SECRET`, `SURVEY_SUBMISSION_HMAC_SECRET` distintos entre sí, ≥32 caracteres, generados aleatoriamente.
- [ ] `APP_DEBUG=false`, `ENABLE_API_DOCS=false`, `PUBLIC_FETCH_ALLOW_PRIVATE_HOSTS=false`.
- [ ] `FRONTEND_ORIGINS`/`BROWSER_ALLOWED_ORIGINS`/`TRUSTED_HOSTS` explícitos, sin `*` ni `localhost`.
- [ ] `TERRITORY_AI_PROVIDER` no es `fake`; si es `openai`, `OPENAI_API_KEY` y `TERRITORY_AI_MODEL` configurados.
- [ ] `METRICS_TOKEN` configurado (≥24 caracteres) si `METRICS_ENABLED=true`.
- [ ] Todas las validaciones anteriores ya se auto-verifican al arrancar (`Settings.__init__` falla rápido) — confirmar que el arranque real en el entorno de destino no fue forzado a saltarse ninguna.

## Secretos

- [ ] Ningún secreto en el bundle del frontend, OpenAPI, logs, respuestas de API o git (verificado por grep en este ciclo; repetir tras cada build de producción).
- [ ] Credenciales de DB y storage fuera del control de versiones, inyectadas por el orquestador/secret manager.

## Base de datos

- [ ] `alembic upgrade head` desde una base vacía completa sin error.
- [ ] `alembic check` limpio contra el head real.
- [ ] Cabeza de migración única (sin ramas divergentes).
- [ ] Backup pre-despliegue tomado y verificado (`pg_restore --list`).

## Storage persistente

- [ ] `ARTIFACT_STORAGE_PROVIDER` corresponde a la topología real: `local` **solo** si exactamente una réplica de `api` comparte filesystem (Render staging, `docker-compose.prod.yml` de hoy); `s3` obligatorio para cualquier topología con ≥2 instancias independientes (ECS/Fargate, Fase 4B).
- [ ] Si `provider=local`: volumen de `report_artifacts` (`/app/generated-reports`) montado.
- [ ] Si `provider=local`: volumen de `evidence_artifacts` (`/app/generated-evidence`) montado — **corregido en un ciclo anterior**: `docker-compose.prod.yml` no lo incluía; evidencia y documentos de Jornada Electoral se perdían al reiniciar el contenedor `api`.
- [ ] Si `provider=local`: estrategia de respaldo de ambos volúmenes (no solo la base de datos) documentada y probada.
- [ ] Si `provider=s3`: `AWS_REGION`, `S3_ARTIFACT_BUCKET` configurados; bucket privado con Block Public Access, versioning y encryption activados (ver `docs/aws/PRODUCTION_ARCHITECTURE.md`).
- [ ] Si `provider=s3`: ninguna access key de AWS en `.env.production` — el proceso asume IAM Task Role; `Settings` no tiene (ni debe tener) un campo para credenciales estáticas.
- [ ] Si `provider=s3` y `S3_SSE_MODE=aws:kms`: `S3_KMS_KEY_ID` configurado y la IAM role del task tiene permiso `kms:GenerateDataKey`/`kms:Decrypt` sobre esa key.
- [ ] `APP_ENV=production` con `ARTIFACT_STORAGE_PROVIDER=local` emite el warning estructurado `artifact_storage_local_in_production` al arrancar — confirmar que aparece si esa combinación es intencional (Render), o corregirla si no lo es (AWS).

## Migraciones y pruebas

- [ ] Backend: 100 % (`docker compose exec api pytest`).
- [ ] Frontend: 100 % (`npm run -s test -- --run`).
- [ ] TypeScript: `npm run -s typecheck` limpio.
- [ ] ESLint: `npm run -s lint` limpio.
- [ ] Build: `npm run -s build` sin errores.
- [ ] OpenAPI: `frontend/openapi.json` sin drift contra el esquema en vivo.
- [ ] Playwright: 100 % en una corrida completa real, sin flakes conocidos (ver §"Flakes" abajo).

## Dominio / HTTPS

- [ ] Dominio real configurado (nunca `localhost` en producción — bloqueado explícitamente por `Settings`).
- [ ] TLS terminado delante del puerto 8080 del contenedor `frontend`.
- [ ] El terminador TLS (load balancer/reverse proxy externo a este repo) añade `Strict-Transport-Security`; `frontend/nginx.conf` no lo hace porque nunca ve la conexión HTTPS directamente.
- [ ] Cookies `Secure` habilitadas (ya forzado por `Settings` en producción).

## Monitoreo

- [ ] `GET /health` y `GET /api/v1/ready` verificados tras el despliegue.
- [ ] `GET /api/v1/metrics` accesible solo con el `METRICS_TOKEN` correcto.
- [ ] Logs estructurados con `request_id` llegando al agregador elegido.
- [ ] Alertas de espacio en disco (DB + ambos volúmenes de storage), expiración de TLS, tasa de 5xx y latencia configuradas en el orquestador/observabilidad externa (este repo no incluye un stack de métricas externo).

## Flakes / CI

- [ ] Los dos flakes históricos de Playwright (paginación de alertas y hito oficial) permanecieron en 0/86 en la corrida completa más reciente de este ciclo.
- [ ] CI ejecuta, como obligatorios antes de merge/deploy: backend, frontend, TypeScript, ESLint, build, drift de OpenAPI, `alembic check`, Playwright completo.
- [ ] Ningún test se dejó en modo "retry hasta que pase"; un test consistentemente inestable se trata como bug, no se enmascara con reintentos.

## Datos de demostración

- [ ] `seed_demo_data`/`seed_e2e` nunca se ejecutan contra la base de producción.
- [ ] Todo dato sintético visible en el producto lleva el prefijo/badge `[DEMO]` o equivalente; ningún fixture E2E se presenta como oficial.

## Documentación

- [ ] README, DEPLOYMENT.md, OPERATIONS.md, SECURITY.md reflejan el estado real del sistema (incluye Jornada Electoral y Data Hub de recintos/juntas, agregados en este ciclo).
- [ ] Guía de roles y mapa de producto vigentes (README § Guía de roles / Mapa de producto).

## Versión candidata

Propuesta para este ciclo: `v3.0.0-rc.1` (línea V2.x ya taggeada como v1.0.0 en el historial de commits; esta consolidación cierra Jornada Electoral V1 + Data Hub de recintos/juntas + estabilización). No se modificó `package.json` ni se creó el tag — pendiente de aprobación explícita.
