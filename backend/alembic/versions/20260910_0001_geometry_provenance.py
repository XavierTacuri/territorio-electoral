"""Track real geometry provenance on cantons/parishes.

Adds geometry_source/geometry_quality so the map API can report the actual
origin of stored geometry instead of assuming every polygon is an official
import. Existing non-null geometries in this system were only ever written by
the synthetic seed scripts (seed_gualaceo.py, seed_e2e.py), so they are
backfilled as SYNTHETIC_PLACEHOLDER rather than left ambiguous; rows without
geometry stay UNKNOWN since the field is moot until geometry is imported.

Revision ID: 20260910_0001
Revises: 20260909_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260910_0001"
down_revision = "20260909_0001"
branch_labels = None
depends_on = None


TABLES = (("cantons", "canton"), ("parishes", "parish"))


def upgrade():
    for table, singular in TABLES:
        op.add_column(table, sa.Column("geometry_source", sa.String(30), nullable=False, server_default="UNKNOWN"))
        op.add_column(table, sa.Column("geometry_quality", sa.String(20), nullable=False, server_default="UNKNOWN"))
        op.execute(f"UPDATE {table} SET geometry_source='SYNTHETIC_PLACEHOLDER', geometry_quality='PLACEHOLDER' WHERE geometry IS NOT NULL")
        # Names must match Base's ck naming convention (ck_<table>_<name>) or
        # `alembic check` reports permanent drift against the ORM models.
        op.create_check_constraint(f"ck_{table}_{singular}_geometry_source", table, "geometry_source IN ('OFFICIAL_IMPORT','SYNTHETIC_PLACEHOLDER','UNKNOWN')")
        op.create_check_constraint(f"ck_{table}_{singular}_geometry_quality", table, "geometry_quality IN ('VALID','PLACEHOLDER','UNKNOWN')")


def downgrade():
    for table, singular in TABLES:
        op.drop_constraint(f"ck_{table}_{singular}_geometry_quality", table, type_="check")
        op.drop_constraint(f"ck_{table}_{singular}_geometry_source", table, type_="check")
        op.drop_column(table, "geometry_quality")
        op.drop_column(table, "geometry_source")
