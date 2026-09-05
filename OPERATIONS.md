# Operaciones

- Salud: docker compose ps, GET /health, GET /api/v1/health.
- Migraciones: docker compose exec api alembic current y alembic check.
- Sesiones: python -m app.scripts.cleanup_auth_sessions --dry-run; quite la opción tras revisar.
- Seeds: solo scripts explícitos; E2E exige APP_ENV=e2e y base separada.
- Informes/alertas/importaciones: use sus comandos en backend/app/scripts; nunca exponga rutas internas.
- Backup: configure DATABASE_URL y ejecute scripts/backup_database.sh DESTINO; archive informes con backup_reports.sh.
- Restore: restore_database.sh ARCHIVO valida; agregue --confirm en ventana de mantenimiento.
- Evidencia y documentos de Jornada Electoral viven en el volumen `evidence_artifacts` (`/app/generated-evidence`), separado de la base de datos: un backup de solo la DB no los incluye. Respáldelo aparte (`docker run --rm -v evidence_artifacts:/data -v $(pwd):/backup alpine tar czf /backup/evidence_$(date -u +%Y%m%dT%H%M%SZ).tgz -C /data .` o equivalente del orquestador) con la misma cadencia que la base de datos.
- Simulacro backup/restore verificado (base sintética de desarrollo): `pg_dump --format=custom` → `pg_restore --list` → restaurar en una base descartable (`createdb`/`pg_restore --clean --if-exists`) → comparar conteos de filas (`users`, `campaigns`) entre origen y restaurada → `dropdb`. Con ~1.2 MB de datos el ciclo completo tomó unos segundos; el tiempo en producción escala con el volumen real de datos y debe medirse contra una copia de ese tamaño antes de fijar una ventana de mantenimiento.

Guarde backups fuera del servidor, cifrados, con control de acceso y pruebas periódicas. Retención sugerida: diarios 14 días, semanales 8 semanas y mensuales 12 meses, ajustada a política local. Monitoree espacio de PostgreSQL/informes/evidencia, expiración de TLS, 5xx y latencia. No imprima secretos al diagnosticar.
