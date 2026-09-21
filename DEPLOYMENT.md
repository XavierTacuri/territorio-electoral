# Despliegue

Requiere Docker Compose, HTTPS terminado delante del puerto 8080 y secretos aleatorios externos. Copie backend/.env.production.example como backend/.env.production, reemplace todos los valores replace_me, configure el dominio real y no versione ese archivo.

1. docker compose -f docker-compose.prod.yml build
2. docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
3. docker compose -f docker-compose.prod.yml up -d
4. Verifique /health y /api/v1/health.

PostgreSQL y FastAPI no publican puertos. Nginx aplica CSP, límites básicos, headers y proxy. Los informes (`report_artifacts`) y la evidencia/documentación de Jornada Electoral (`evidence_artifacts`, montado en `/app/generated-evidence`) usan volúmenes persistentes — ambos deben existir en `docker-compose.prod.yml`; un contenedor `api` sin el volumen de evidencia pierde fotos/actas al reiniciar. Una sola tarea de release ejecuta Alembic antes de escalar. Para rollback, restaure imagen y backup compatibles; nunca haga downgrade sin validar pérdida de datos.

Esta topología (`docker-compose.prod.yml`, `ARTIFACT_STORAGE_PROVIDER=local` implícito) solo es correcta con **una** réplica de `api` compartiendo filesystem — el caso actual de Render staging. Para AWS con ECS/Fargate y más de una tarea `api` (Fase 4C), la aplicación ya soporta `ARTIFACT_STORAGE_PROVIDER=s3` (ver `backend/.env.production.example` y `docs/aws/PRODUCTION_ARCHITECTURE.md`): reportes y evidencia/actas se persisten en un bucket S3 privado en vez del filesystem del contenedor, y las actas usan subida directa navegador→S3 vía presigned POST. El Dockerfile actual ejecuta `alembic upgrade head && uvicorn ...` en el propio arranque de cada réplica — correcto con una sola instancia, pero en ECS con ≥2 tasks cada réplica migraría en paralelo; esto no es una hipótesis, Fase 4B lo reprodujo en `docker-compose.multi-instance.yml` (ambas réplicas de prueba compitieron por crear `alembic_version`). Fase 4C separa esto en una release task ECS dedicada que corre antes que el servicio escale, sin cambiar el comportamiento actual de Render/Docker Compose.

Use TLS, cookies Secure, hosts/orígenes exactos y documentación API desactivada. Nginx en este repo asume que TLS se termina delante del puerto 8080 (load balancer/reverse proxy externo); ese terminador — no este `nginx.conf` — debe añadir `Strict-Transport-Security` (HSTS), ya que Nginx aquí nunca ve la conexión HTTPS directamente. Consulte logs con docker compose logs; los logs no contienen cuerpos, tokens ni encuestas. Dimensione CPU/memoria en el orquestador. En múltiples proxies sustituya los límites locales por un rate limiter distribuido.
