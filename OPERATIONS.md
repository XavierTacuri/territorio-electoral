# Operaciones

- Salud: docker compose ps, GET /health, GET /api/v1/health.
- Migraciones: docker compose exec api alembic current y alembic check.
- Sesiones: python -m app.scripts.cleanup_auth_sessions --dry-run; quite la opción tras revisar.
- Seeds: solo scripts explícitos; E2E exige APP_ENV=e2e y base separada.
- Informes/alertas/importaciones: use sus comandos en backend/app/scripts; nunca exponga rutas internas.
- Backup: configure DATABASE_URL y ejecute scripts/backup_database.sh DESTINO; archive informes con backup_reports.sh.
- Restore: restore_database.sh ARCHIVO valida; agregue --confirm en ventana de mantenimiento.

Guarde backups fuera del servidor, cifrados, con control de acceso y pruebas periódicas. Retención sugerida: diarios 14 días, semanales 8 semanas y mensuales 12 meses, ajustada a política local. Monitoree espacio de PostgreSQL/informes, expiración de TLS, 5xx y latencia. No imprima secretos al diagnosticar.
