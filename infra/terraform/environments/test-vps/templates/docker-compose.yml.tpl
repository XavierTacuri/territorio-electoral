services:
  postgres:
    image: postgis/postgis:16-3.4
    env_file:
      - /opt/territorio-electoral/.env.secrets
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  api:
    image: ${backend_image}
    env_file:
      - /opt/territorio-electoral/.env.secrets
      - /opt/territorio-electoral/.env.runtime
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: "5432"
      # El Dockerfile del backend arranca Uvicorn en $${PORT:-10000} si PORT
      # no esta definido -- nginx.conf (test-vps y prod) siempre espera
      # api:8000. Mismo patron que docker-compose.yml/docker-compose.prod.yml
      # del repo: forzar PORT=8000 explicitamente.
      PORT: "8000"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  frontend:
    image: ${frontend_image}
    ports:
      - "80:8080"
    depends_on:
      - api
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  postgres-data:
