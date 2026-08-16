# Operacion V2.9

## Configuracion y secretos

Partir de `backend/.env.production.example` y suministrar los valores mediante el gestor de secretos de la plataforma. Son obligatorios `DATABASE_URL` o todas las credenciales PostgreSQL separadas, `SECRET_KEY`, `BROWSER_REFRESH_TOKEN_HMAC_SECRET`, `SURVEY_SUBMISSION_HMAC_SECRET`, origenes HTTPS y hosts publicos. No almacenar el archivo resultante en Git. `TERRITORY_AI_PROVIDER=fake`, debug, documentacion API, origenes comodin, hosts comodin y acceso SSRF a redes privadas impiden el arranque productivo.

La aplicacion escribe logs JSON a stdout/stderr. La plataforma debe recolectarlos y aplicar rotacion/retencion; no se guardan indefinidamente en el contenedor. Si se habilita `/api/v1/metrics`, debe configurarse un token y restringirse adicionalmente en la red/reverse proxy.

## Despliegue

1. Verificar imagenes, variables, espacio y estado de la DB. Ejecutar `scripts/backup_database.sh DIRECTORIO` desde un entorno con herramientas PostgreSQL; la contrasena se entrega mediante `PGPASSFILE` o secret del entorno, nunca en el comando.
2. Verificar el dump con `pg_restore --list ARCHIVO` y conservarlo fuera del host de aplicacion.
3. Ejecutar una sola vez `scripts/release_migrate.sh` como release job. Nunca ejecutar Alembic concurrentemente desde cada replica.
4. Desplegar `docker compose -f docker-compose.prod.yml up -d`; PostgreSQL no publica el puerto 5432 y el codigo fuente no se monta.
5. Comprobar `/health`, `/api/v1/health`, `/api/v1/ready`, login con una cuenta de smoke previamente autorizada y las rutas principales. `scripts/production_smoke.sh URL` no crea datos ni usuarios.

El reverse proxy exterior termina TLS, conserva el host publico configurado y envia `X-Forwarded-Proto`. No se incluyen certificados ni configuracion dependiente de cloud.

## Restore y prueba

Nunca se restaura automaticamente ni con `APP_ENV=production`. Validar primero con `scripts/restore_database.sh ARCHIVO`; para ejecutar, usar `scripts/restore_database.sh ARCHIVO --confirm URL_DESTINO_NO_PRODUCTIVO`. El destino debe ser explicito, disposable y distinto de la fuente.

El drill usa una DB sintetica con migraciones y datos ficticios: definir `SOURCE_DATABASE_URL` y `RESTORE_DATABASE_URL`, ejecutar `scripts/restore_drill.sh` y comprobar Alembic, organizacion, campana y geografia. Nunca usar la base o volumen de Gualaceo como destino. El RPO, RTO, frecuencia, cifrado y retencion deben acordarse antes de produccion definitiva; este repositorio no inventa esos compromisos.

## Rollback

El rollback de aplicacion consiste en volver a la imagen anterior y repetir smoke. El rollback de DB es independiente: no ejecutar `alembic downgrade` automaticamente. Si una migracion no es compatible hacia atras, mantener la aplicacion anterior detenida y restaurar un backup verificado siguiendo el procedimiento de incidente. Antes de cada cambio de esquema debe revisarse su compatibilidad con ambas versiones.

## Fallos

`/health` prueba que el proceso responde; `/ready` devuelve 503 si la DB no esta disponible y retira la replica del trafico. Una caida del proveedor opcional de Territorio IA no afecta readiness y produce un error controlado solo en esa funcion. Los errores de fuentes publicas y reportes quedan aislados en sus ejecuciones; correlacionar incidentes mediante `X-Request-ID` sin copiar tokens, cookies, prompts ni datos personales a tickets.
