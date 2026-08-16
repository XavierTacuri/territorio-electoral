#!/usr/bin/env sh
set -eu
: "${SOURCE_DATABASE_URL:?SOURCE_DATABASE_URL es obligatorio}"
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL es obligatorio}"
[ "${APP_ENV:-test}" != "production" ] || { echo "Drill bloqueado en produccion"; exit 3; }
case "$RESTORE_DATABASE_URL" in *prod*|*production*) echo "Destino inseguro"; exit 3;; esac
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT
dump="$workdir/drill.dump"
pg_dump --format=custom --file="$dump" "$SOURCE_DATABASE_URL"
pg_restore --list "$dump" >/dev/null
pg_restore --clean --if-exists --no-owner --dbname="$RESTORE_DATABASE_URL" "$dump"
psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT 1 FROM alembic_version LIMIT 1" >/dev/null
psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT 1 FROM organizations LIMIT 1" >/dev/null
psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT 1 FROM campaigns LIMIT 1" >/dev/null
psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT 1 FROM cantons LIMIT 1" >/dev/null
echo "Restore drill completado"
