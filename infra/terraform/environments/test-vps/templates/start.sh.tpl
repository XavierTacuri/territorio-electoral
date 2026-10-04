#!/bin/bash
# Generado por Terraform (environments/test-vps/ec2.tf) a partir de este
# template. Se ejecuta en cada arranque via systemd (territorio-electoral.service)
# -- incluyendo despues de un STOP/START de la instancia, cuando la IP
# publica puede haber cambiado. Idempotente: puede ejecutarse cualquier
# numero de veces sin efectos destructivos.
#
# Deliberadamente SIN "set -x": nunca se debe volcar el contenido de
# .env.secrets ni de ninguna variable derivada de el a los logs de
# cloud-init/systemd (journalctl).
set -euo pipefail

APP_DIR=/opt/territorio-electoral
SECRETS_FILE="$APP_DIR/.env.secrets"
RUNTIME_FILE="$APP_DIR/.env.runtime"
REGION="${aws_region}"
ECR_REGISTRY="${ecr_registry_host}"

cd "$APP_DIR"

# --- Reintentos con backoff: network-online.target no garantiza que IMDS ni
# el resto de la red (DNS, ECR, Docker Hub) respondan en el primer intento
# justo al arrancar -- sin esto, un unico fallo transitorio mataria el
# script entero (set -e) y, al ser un servicio systemd oneshot, el stack
# nunca llegaria a levantarse.
retry() {
  local attempts=10 delay=3 i=0 out
  while true; do
    i=$((i + 1))
    if out=$("$@"); then
      printf '%s' "$out"
      return 0
    fi
    if [ "$i" -ge "$attempts" ]; then
      echo "Fallaron los $attempts intentos de: $*" >&2
      return 1
    fi
    sleep "$delay"
    delay=$((delay * 2 > 30 ? 30 : delay * 2))
  done
}

fetch_imds_token() {
  curl -sS -f -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60"
}

fetch_public_ip() {
  curl -sS -f -H "X-aws-ec2-metadata-token: $TOKEN" \
    "http://169.254.169.254/latest/meta-data/public-ipv4"
}

TOKEN=$(retry fetch_imds_token)
PUBLIC_IP=$(retry fetch_public_ip)

if [ -z "$PUBLIC_IP" ]; then
  echo "No fue posible obtener la IP publica via IMDSv2." >&2
  exit 1
fi

# --- Secretos TEST: generados UNA SOLA VEZ, nunca regenerados si ya existen ----
if [ ! -f "$SECRETS_FILE" ]; then
  umask 077
  {
    echo "APP_ENV=test"
    echo "APP_DEBUG=false"
    echo "ENABLE_API_DOCS=false"
    echo "POSTGRES_DB=territorio_electoral"
    echo "POSTGRES_USER=territorio_user"
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 32)"
    echo "POSTGRES_HOST=postgres"
    echo "POSTGRES_PORT=5432"
    echo "SECRET_KEY=$(openssl rand -hex 32)"
    echo "BROWSER_REFRESH_TOKEN_HMAC_SECRET=$(openssl rand -hex 32)"
    echo "SURVEY_SUBMISSION_HMAC_SECRET=$(openssl rand -hex 32)"
    echo "BROWSER_COOKIE_SECURE=false"
    echo "BROWSER_COOKIE_SAMESITE=lax"
    echo "INITIAL_ADMIN_EMAIL=admin@test-vps.local"
    echo "INITIAL_ADMIN_USERNAME=admin"
    echo "INITIAL_ADMIN_PASSWORD=$(openssl rand -base64 24)"
    echo "INITIAL_ADMIN_FIRST_NAME=Administrador"
    echo "INITIAL_ADMIN_LAST_NAME=Test-VPS"
  } > "$SECRETS_FILE"
  chown root:root "$SECRETS_FILE"
  chmod 0600 "$SECRETS_FILE"
  echo "Secretos TEST generados en $SECRETS_FILE (no se imprimen)."
else
  echo "Secretos TEST ya existian — no se regeneran."
fi

# --- Config de runtime dependiente de la IP publica actual: SI se reescribe ----
# en cada arranque (a diferencia de .env.secrets arriba).
umask 077
{
  echo "FRONTEND_ORIGINS=http://$PUBLIC_IP"
  echo "BROWSER_ALLOWED_ORIGINS=http://$PUBLIC_IP"
  echo "TRUSTED_HOSTS=$PUBLIC_IP"
} > "$RUNTIME_FILE"
chown root:root "$RUNTIME_FILE"
chmod 0600 "$RUNTIME_FILE"

# --- ECR login via el rol de instancia (sin AWS keys estaticas) -----------
ecr_login() {
  aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY"
}
retry ecr_login > /dev/null

retry docker compose pull > /dev/null
docker compose up -d

# --- Espera a que la API responda a traves de nginx antes de inicializar ----
# Se usa $PUBLIC_IP (no 127.0.0.1) como host de la URL: curl envia ese mismo
# valor como header Host, y TrustedHostMiddleware del backend solo acepta
# TRUSTED_HOSTS=$PUBLIC_IP (ver .env.runtime arriba) -- con 127.0.0.1 esta
# llamada recibiria siempre 400 Bad Request y el loop agotaria sus 60
# intentos sin detectar nunca un backend realmente listo.
for _ in $(seq 1 60); do
  if curl -sf "http://$PUBLIC_IP/api/v1/ready" > /dev/null; then
    break
  fi
  sleep 5
done

# alembic upgrade head ya corre automaticamente en el entrypoint del
# contenedor backend (ver backend/Dockerfile) en cada arranque. Solo falta
# el administrador inicial -- create_admin ya es idempotente (verifica si
# el usuario existe antes de crearlo), asi que es seguro invocarlo en cada
# arranque de este script.
docker compose exec -T api python -m app.scripts.create_admin || true

echo "test-vps listo en http://$PUBLIC_IP"
