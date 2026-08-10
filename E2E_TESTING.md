# Pruebas E2E

Use una base separada, APP_ENV=e2e y credenciales sintéticas suministradas por variables. Aplique migraciones, ejecute python -m app.scripts.seed_e2e, levante el perfil frontend y corra npm run e2e. Nunca apunte Playwright a desarrollo o producción.

Los artefactos (trace y screenshot) se conservan solo al fallar. Los selectores son accesibles y no se usan esperas fijas. La suite incluye login, accesibilidad y viewport 320 px; los flujos operativos se amplían contra contratos reales sin backend falso.
# Pruebas end-to-end

El stack E2E usa `docker-compose.e2e.yml`, una base y volúmenes exclusivos. El seed rechaza cualquier entorno distinto de `APP_ENV=e2e`.

Defina externamente `E2E_DB_PASSWORD`, `E2E_SECRET_KEY`, `E2E_REFRESH_SECRET`, `E2E_SURVEY_SECRET` y `E2E_USER_PASSWORD`. Ninguno se versiona. Después ejecute:

```bash
docker compose -p territorio-e2e -f docker-compose.e2e.yml up --build -d
docker compose -p territorio-e2e -f docker-compose.e2e.yml exec api alembic upgrade head
docker compose -p territorio-e2e -f docker-compose.e2e.yml exec api python -m app.scripts.seed_e2e
cd frontend
E2E_EXTERNAL_SERVER=1 E2E_BASE_URL=http://localhost:15173 npm run e2e
docker compose -p territorio-e2e -f docker-compose.e2e.yml down -v
```

Las cuentas son sintéticas (`admin_e2e`, `manager_e2e`, `coordinator_e2e`, `analyst_e2e`, `candidate_e2e`) y comparten únicamente la contraseña inyectada en `E2E_USER_PASSWORD`.
