#!/usr/bin/env sh
set -eu
[ "$#" -ge 2 ] || { echo "Uso: backup_reports.sh ORIGEN DESTINO [--dry-run]"; exit 2; }
source_dir=$1
target_dir=$2
[ -d "$source_dir" ] || { echo "Origen inexistente"; exit 2; }
file="$target_dir/reports_$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
if [ "$#" -ge 3 ] && [ "$3" = "--dry-run" ]; then echo "Se crearía $file"; exit 0; fi
mkdir -p "$target_dir"
umask 077
tar -C "$source_dir" -czf "$file" .
tar -tzf "$file" >/dev/null
echo "Backup verificado: $file"
