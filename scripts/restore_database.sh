#!/usr/bin/env sh
set -eu
[ "$#" -ge 1 ] || { echo "Uso: restore_database.sh ARCHIVO [--confirm]"; exit 2; }
file=$1
[ -f "$file" ] || { echo "Archivo inexistente"; exit 2; }
pg_restore --list "$file" >/dev/null
if [ "$#" -lt 2 ] || [ "$2" != "--confirm" ]; then echo "Restauración validada. Repita con --confirm para ejecutar."; exit 0; fi
: "$DATABASE_URL"
pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" "$file"
echo "Restauración completada"
