#!/bin/bash
# cloud-init de la EC2 de test-vps. Se ejecuta UNA SOLA VEZ, en el primer
# arranque de la instancia (comportamiento estandar de EC2 user_data) --
# por eso aqui solo va la instalacion de paquetes y la escritura de los
# archivos de /opt/territorio-electoral. El arranque/reinicio real de la
# aplicacion (que si debe repetirse en cada boot, incluyendo despues de un
# STOP/START) lo hace territorio-electoral.service llamando a start.sh.
#
# Deliberadamente SIN "set -x" (no volcar nada sensible al log de
# cloud-init, revisable sin autenticacion SSM por cualquiera con permiso de
# consola/metadata en algunas configuraciones).
set -euo pipefail

APP_DIR=/opt/territorio-electoral
mkdir -p "$APP_DIR"

dnf install -y docker
systemctl enable --now docker

# Docker Compose (plugin CLI) en version FIJADA -- nunca "latest", para que
# el arranque sea reproducible (item 9 de la fase).
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/${compose_version}/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

base64 -d > "$APP_DIR/docker-compose.yml" <<'COMPOSE_B64'
${docker_compose_b64}
COMPOSE_B64

base64 -d > "$APP_DIR/start.sh" <<'START_B64'
${start_script_b64}
START_B64
chmod 0700 "$APP_DIR/start.sh"
chown root:root "$APP_DIR/start.sh"

base64 -d > /etc/systemd/system/territorio-electoral.service <<'UNIT_B64'
${systemd_unit_b64}
UNIT_B64

systemctl daemon-reload
systemctl enable --now territorio-electoral.service
