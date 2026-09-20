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

# NOTE (Fase 4A, §31): this entrypoint runs `alembic upgrade head` on every
# container start — correct for today's single-replica topologies (Render,
# docker-compose.prod.yml), where exactly one instance boots at a time.
# On ECS/Fargate with >=2 `api` tasks (Fase 4B target,
# docs/aws/PRODUCTION_ARCHITECTURE.md), every replica would run this
# concurrently. Do NOT split the migration out here without an explicit,
# tested ECS release-task strategy — that separation is Fase 4B's job, not a
# change to make unreviewed against this Dockerfile alone.
CMD ["/bin/sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
