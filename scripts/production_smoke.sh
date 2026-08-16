#!/usr/bin/env sh
set -eu
base=${1:?Uso: production_smoke.sh URL_BASE}
curl --fail --silent --show-error "$base/health" >/dev/null
curl --fail --silent --show-error "$base/api/v1/health" >/dev/null
curl --fail --silent --show-error "$base/api/v1/ready" >/dev/null
echo "Smoke de produccion completado"
