#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL es obligatorio}"
alembic upgrade head
alembic current
alembic check
