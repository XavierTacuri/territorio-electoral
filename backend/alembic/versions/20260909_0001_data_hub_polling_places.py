"""Data Hub: add CNE_POLLING_PLACES/CNE_ELECTORAL_BOARDS dataset types.

Revision ID: 20260909_0001
Revises: 20260908_0002
"""
from alembic import op

revision = "20260909_0001"
down_revision = "20260908_0002"
branch_labels = None
depends_on = None

OLD_TYPES = "'CNE_ELECTORAL_RESULTS','CNE_CANDIDATES','CNE_POLITICAL_ORGANIZATIONS','CNE_TURNOUT','CNE_ELECTORAL_ROLL_SNAPSHOT','INEC_DEMOGRAPHIC_INDICATORS','INEC_POPULATION_PROJECTIONS','INEC_GEOGRAPHIC_CLASSIFIER','OTHER_AGGREGATED_OFFICIAL'"
NEW_TYPES = OLD_TYPES + ",'CNE_POLLING_PLACES','CNE_ELECTORAL_BOARDS'"


def upgrade():
    op.execute("ALTER TABLE data_sources DROP CONSTRAINT ck_data_sources_dataset_type")
    op.execute(f"ALTER TABLE data_sources ADD CONSTRAINT ck_data_sources_dataset_type CHECK (dataset_type IN ({NEW_TYPES}))")


def downgrade():
    op.execute("ALTER TABLE data_sources DROP CONSTRAINT ck_data_sources_dataset_type")
    op.execute(f"ALTER TABLE data_sources ADD CONSTRAINT ck_data_sources_dataset_type CHECK (dataset_type IN ({OLD_TYPES}))")
