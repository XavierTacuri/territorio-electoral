"""Deactivate parish rows absent from the current INEC 2026 catalog.

Revision ID: 20260824_0002
Revises: 20260824_0001
"""

import csv
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "20260824_0002"
down_revision = "20260824_0001"
branch_labels = None
depends_on = None


cantons = sa.table(
    "cantons",
    sa.column("id", sa.Integer),
    sa.column("dpa_code", sa.String),
)
parishes = sa.table(
    "parishes",
    sa.column("canton_id", sa.Integer),
    sa.column("dpa_code", sa.String),
    sa.column("name", sa.String),
    sa.column("parish_type", sa.String),
    sa.column("is_active", sa.Boolean),
)


def _catalog_rows():
    path = Path(__file__).parents[2] / "app" / "data" / "inec_dpa_2026.csv"
    with path.open(encoding="utf-8", newline="") as catalog:
        return list(csv.DictReader(catalog))


def upgrade() -> None:
    rows = _catalog_rows()
    current_parish_dpas = {
        row["dpa_code"] for row in rows if row["level"] == "PARISH"
    }
    official_canton_dpas = {
        row["dpa_code"] for row in rows if row["level"] == "CANTON"
    }
    official_canton_ids = sa.select(cantons.c.id).where(
        cantons.c.dpa_code.in_(official_canton_dpas)
    )
    for row in (item for item in rows if item["level"] == "PARISH"):
        op.get_bind().execute(
            parishes.update()
            .where(parishes.c.dpa_code == row["dpa_code"])
            .values(
                name=row["name"],
                parish_type=row["parish_type"],
                is_active=True,
            )
        )
    op.get_bind().execute(
        parishes.update()
        .where(
            parishes.c.canton_id.in_(official_canton_ids),
            parishes.c.dpa_code.not_in(current_parish_dpas),
        )
        .values(is_active=False)
    )


def downgrade() -> None:
    # Previous active state is unknowable; never reactivate historical rows automatically.
    pass
