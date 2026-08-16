#!/usr/bin/env sh
set -eu
[ "$#" -ge 1 ] || { echo "Uso: restore_database.sh ARCHIVO [--confirm DESTINO_NO_PRODUCTIVO]"; exit 2; }
file=$1
[ -f "$file" ] || { echo "Archivo inexistente"; exit 2; }
pg_restore --list "$file" >/dev/null
if [ "$#" -lt 3 ] || [ "$2" != "--confirm" ]; then
  echo "Restauracion validada. Indique --confirm y un destino explicito no productivo."
  exit 0
fi
destination=$3
[ -n "$destination" ] || { echo "El destino es obligatorio"; exit 2; }
[ "${APP_ENV:-}" != "production" ] || { echo "Restore bloqueado cuando APP_ENV=production"; exit 3; }
case "$destination" in *prod*|*production*) echo "El destino parece productivo; operacion bloqueada"; exit 3;; esac
pg_restore --clean --if-exists --no-owner --dbname="$destination" "$file"
echo "Restauracion completada"
