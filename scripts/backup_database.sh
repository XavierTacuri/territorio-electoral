#!/usr/bin/env sh
set -eu
[ "$#" -ge 1 ] || { echo "Uso: backup_database.sh DIRECTORIO [--dry-run]"; exit 2; }
target=$1
stamp=$(date -u +%Y%m%dT%H%M%SZ)
file="$target/territorio_electoral_$stamp.dump"
if [ "$#" -ge 2 ] && [ "$2" = "--dry-run" ]; then echo "Se crearía un backup custom en $file"; exit 0; fi
: "$DATABASE_URL"
mkdir -p "$target"
umask 077
pg_dump --format=custom --file="$file" "$DATABASE_URL"
pg_restore --list "$file" >/dev/null
echo "Backup verificado: $file"
