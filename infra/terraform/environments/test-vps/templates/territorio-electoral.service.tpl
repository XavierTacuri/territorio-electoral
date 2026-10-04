[Unit]
Description=Territorio Electoral (test-vps): recalcula la IP publica y levanta Docker Compose
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/territorio-electoral/start.sh
TimeoutStartSec=600
# Respaldo ademas del retry/backoff interno de start.sh: si el script agota
# sus propios reintentos y aun asi falla, systemd lo vuelve a intentar en
# vez de dejar el stack caido para siempre.
Restart=on-failure
RestartSec=30
StartLimitIntervalSec=900
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
