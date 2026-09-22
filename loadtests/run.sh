#!/usr/bin/env bash
# Fase 4C.6 — ejecuta un escenario k6 contra el stack aislado
# docker-compose.e2e.yml (o multi-instance si K6_BASE_URL_B esta definido),
# capturando en paralelo "docker stats" de los contenedores relevantes y el
# resumen JSON de k6. Nunca apunta a AWS/produccion — solo a contenedores
# locales por nombre.
#
# Uso:
#   K6_SCENARIO=smoke K6_MIX=mixed ./loadtests/run.sh
#
# Variables relevantes (ver docs/performance/LOAD_STRESS_TESTING.md):
#   K6_SCENARIO=smoke|baseline|load|stress|spike|soak (default smoke)
#   K6_MIX=read|mixed|write|auth (default mixed)
#   K6_BASE_URL (default http://api:8000, red territorio-e2e_default)
#   K6_BASE_URL_B (opcional — segunda instancia, comparacion single vs multi)
#   K6_NETWORK (default territorio-e2e_default)
#   K6_STATS_CONTAINERS (default "territorio-e2e-api-1 territorio-e2e-db-1")
#   K6_USER_PASSWORD (obligatorio)
set -euo pipefail

SCENARIO="${K6_SCENARIO:-smoke}"
MIX="${K6_MIX:-mixed}"
NETWORK="${K6_NETWORK:-territorio-e2e_default}"
BASE_URL="${K6_BASE_URL:-http://api:8000}"
STATS_CONTAINERS="${K6_STATS_CONTAINERS:-territorio-e2e-api-1 territorio-e2e-db-1}"

if [ -z "${K6_USER_PASSWORD:-}" ]; then
  echo "K6_USER_PASSWORD es obligatorio (mismo valor que E2E_USER_PASSWORD del stack)." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$ROOT_DIR/results"
mkdir -p "$RESULTS_DIR"

RUN_ID="${SCENARIO}_${MIX}_$(date -u +%Y%m%dT%H%M%SZ)"
STATS_FILE="$RESULTS_DIR/${RUN_ID}_docker_stats.csv"
SUMMARY_FILE="$RESULTS_DIR/${RUN_ID}_summary.json"

echo "container,timestamp,cpu_perc,mem_usage,mem_perc,net_io,block_io,pids" > "$STATS_FILE"

# Poller de docker stats en background — una linea por contenedor cada 2s,
# hasta que se le mate al terminar k6. No agrega un stack de observabilidad:
# es "docker stats --no-stream" en bucle, la herramienta que ya trae Docker.
(
  while true; do
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    for c in $STATS_CONTAINERS; do
      docker stats --no-stream --format "{{.Name}},$ts,{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.NetIO}},{{.BlockIO}},{{.PIDs}}" "$c" 2>/dev/null >> "$STATS_FILE" || true
    done
    sleep 2
  done
) &
STATS_PID=$!
trap 'kill "$STATS_PID" 2>/dev/null || true' EXIT

echo "=== k6 $SCENARIO/$MIX -> $BASE_URL${K6_BASE_URL_B:+ + $K6_BASE_URL_B} ==="
MSYS_NO_PATHCONV=1 docker run --rm --network "$NETWORK" \
  -v "$ROOT_DIR:/loadtests" \
  -e K6_BASE_URL="$BASE_URL" \
  -e K6_BASE_URL_B="${K6_BASE_URL_B:-}" \
  -e K6_USER_PASSWORD="$K6_USER_PASSWORD" \
  -e K6_SCENARIO="$SCENARIO" \
  -e K6_MIX="$MIX" \
  -e K6_FIXTURE_FILE="${K6_FIXTURE_FILE:-}" \
  -e K6_VUS="${K6_VUS:-}" \
  -e K6_DURATION="${K6_DURATION:-}" \
  -e K6_RAMP="${K6_RAMP:-}" \
  -e K6_HOLD="${K6_HOLD:-}" \
  -e K6_MIX_WRITE_RATIO="${K6_MIX_WRITE_RATIO:-}" \
  -e K6_SLEEP="${K6_SLEEP:-}" \
  -e K6_STRESS_STEP1="${K6_STRESS_STEP1:-}" -e K6_STRESS_STEP2="${K6_STRESS_STEP2:-}" \
  -e K6_STRESS_STEP3="${K6_STRESS_STEP3:-}" -e K6_STRESS_STEP4="${K6_STRESS_STEP4:-}" -e K6_STRESS_STEP5="${K6_STRESS_STEP5:-}" \
  -e K6_SPIKE_BASELINE="${K6_SPIKE_BASELINE:-}" -e K6_SPIKE_PEAK="${K6_SPIKE_PEAK:-}" \
  grafana/k6:0.54.0 run --summary-export="/loadtests/results/$(basename "$SUMMARY_FILE")" /loadtests/k6/main.js

kill "$STATS_PID" 2>/dev/null || true
trap - EXIT
echo "=== resultados: $SUMMARY_FILE / $STATS_FILE ==="
