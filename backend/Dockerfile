FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/generated-reports /app/generated-evidence \
    && chown -R app:app /app/generated-reports /app/generated-evidence

USER app

EXPOSE 8000

# NOTE (Fase 4A §31, CONFIRMED Fase 4B): this entrypoint runs
# `alembic upgrade head` on every container start — correct for today's
# single-replica topologies (Render, docker-compose.prod.yml), where exactly
# one instance boots at a time. This is NOT a hypothetical risk: Fase 4B's
# real two-process test topology (docker-compose.multi-instance.yml) hit it
# on first boot — both replicas ran this concurrently against the same
# database and raced to create `alembic_version` (UniqueViolation). That
# compose file's fix (only one replica migrates; the other waits on
# `service_healthy`) is a test-only workaround, not a pattern to copy into
# ECS/Fargate (Fase 4C target, docs/aws/PRODUCTION_ARCHITECTURE.md): there,
# migrations must run as a dedicated one-off release task, exactly once,
# before the service scales to >1 task. Do NOT split the migration out here
# without that explicit, tested ECS release-task strategy.
# WEB_CONCURRENCY (Fase 4B) defaults to 1: uvicorn's own default, and the
# right choice for ECS/Fargate (Fase 4C) — scale by adding tasks, not
# workers per task, so each task's health/readiness reflects one real
# process. Only docker-compose.prod.yml's Render topology overrides this
# today (its own `command:` sets 2, preserving the existing behavior there);
# this default never silently starts multiple workers where nothing asked
# for it.
CMD ["/bin/sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers ${WEB_CONCURRENCY:-1}"]
