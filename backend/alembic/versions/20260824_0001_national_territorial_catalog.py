"""Load the INEC 2026 national territorial master catalog.

Revision ID: 20260824_0001
Revises: 20260821_0001
"""

import csv
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "20260824_0001"
down_revision = "20260821_0001"
branch_labels = None
depends_on = None


provinces = sa.table(
    "provinces",
    sa.column("id", sa.Integer), sa.column("code", sa.String),
    sa.column("name", sa.String), sa.column("is_active", sa.Boolean),
)
cantons = sa.table(
    "cantons",
    sa.column("id", sa.Integer), sa.column("province_id", sa.Integer),
    sa.column("code", sa.String), sa.column("dpa_code", sa.String),
    sa.column("name", sa.String), sa.column("is_active", sa.Boolean),
)
parishes = sa.table(
    "parishes",
    sa.column("id", sa.Integer), sa.column("canton_id", sa.Integer),
    sa.column("code", sa.String), sa.column("dpa_code", sa.String),
    sa.column("name", sa.String), sa.column("parish_type", sa.String),
    sa.column("is_active", sa.Boolean),
)


def _catalog_rows():
    path = Path(__file__).parents[2] / "app" / "data" / "inec_dpa_2026.csv"
    with path.open(encoding="utf-8", newline="") as catalog:
        return list(csv.DictReader(catalog))


def upgrade() -> None:
    op.drop_constraint("uq_parishes_canton_name", "parishes", type_="unique")
    connection = op.get_bind()
    rows = _catalog_rows()
    province_ids = {}
    for row in (item for item in rows if item["level"] == "PROVINCE"):
        province_id = connection.scalar(sa.select(provinces.c.id).where(provinces.c.code == row["dpa_code"]))
        if province_id is None:
            connection.execute(provinces.insert().values(code=row["dpa_code"], name=row["name"], is_active=True))
            province_id = connection.scalar(sa.select(provinces.c.id).where(provinces.c.code == row["dpa_code"]))
        else:
            connection.execute(provinces.update().where(provinces.c.id == province_id).values(name=row["name"], is_active=True))
        province_ids[row["dpa_code"]] = province_id

    canton_ids = {}
    for row in (item for item in rows if item["level"] == "CANTON"):
        canton_id = connection.scalar(sa.select(cantons.c.id).where(cantons.c.dpa_code == row["dpa_code"]))
        values = dict(province_id=province_ids[row["parent_dpa_code"]], code=row["dpa_code"][2:], name=row["name"], is_active=True)
        if canton_id is None:
            connection.execute(cantons.insert().values(dpa_code=row["dpa_code"], **values))
            canton_id = connection.scalar(sa.select(cantons.c.id).where(cantons.c.dpa_code == row["dpa_code"]))
        else:
            connection.execute(cantons.update().where(cantons.c.id == canton_id).values(**values))
        canton_ids[row["dpa_code"]] = canton_id

    for row in (item for item in rows if item["level"] == "PARISH"):
        parish_id = connection.scalar(sa.select(parishes.c.id).where(parishes.c.dpa_code == row["dpa_code"]))
        values = dict(canton_id=canton_ids[row["parent_dpa_code"]], code=row["dpa_code"][4:], name=row["name"], parish_type=row["parish_type"], is_active=True)
        if parish_id is None:
            connection.execute(parishes.insert().values(dpa_code=row["dpa_code"], **values))
        else:
            connection.execute(parishes.update().where(parishes.c.id == parish_id).values(**values))


def downgrade() -> None:
    # Master rows can be referenced by campaigns and datasets. Never delete them automatically.
    pass
