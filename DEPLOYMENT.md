# Despliegue

Requiere Docker Compose, HTTPS terminado delante del puerto 8080 y secretos aleatorios externos. Copie backend/.env.production.example como backend/.env.production, reemplace todos los valores replace_me, configure el dominio real y no versione ese archivo.

1. docker compose -f docker-compose.prod.yml build
2. docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
3. docker compose -f docker-compose.prod.yml up -d
4. Verifique /health y /api/v1/health.

PostgreSQL y FastAPI no publican puertos. Nginx aplica CSP, límites básicos, headers y proxy. Los informes (`report_artifacts`) y la evidencia/documentación de Jornada Electoral (`evidence_artifacts`, montado en `/app/generated-evidence`) usan volúmenes persistentes — ambos deben existir en `docker-compose.prod.yml`; un contenedor `api` sin el volumen de evidencia pierde fotos/actas al reiniciar. Una sola tarea de release ejecuta Alembic antes de escalar. Para rollback, restaure imagen y backup compatibles; nunca haga downgrade sin validar pérdida de datos.

Use TLS, cookies Secure, hosts/orígenes exactos y documentación API desactivada. Nginx en este repo asume que TLS se termina delante del puerto 8080 (load balancer/reverse proxy externo); ese terminador — no este `nginx.conf` — debe añadir `Strict-Transport-Security` (HSTS), ya que Nginx aquí nunca ve la conexión HTTPS directamente. Consulte logs con docker compose logs; los logs no contienen cuerpos, tokens ni encuestas. Dimensione CPU/memoria en el orquestador. En múltiples proxies sustituya los límites locales por un rate limiter distribuido.
