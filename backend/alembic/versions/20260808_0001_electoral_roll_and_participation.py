"""electoral roll snapshots and explainable participation projections

Revision ID: 20260808_0001
Revises: b10a10c2026
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260808_0001"
down_revision = "b10a10c2026"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("dataset_type", "data_sources", type_="check")
    op.create_check_constraint("dataset_type", "data_sources", "dataset_type IN ('CNE_ELECTORAL_RESULTS','CNE_CANDIDATES','CNE_POLITICAL_ORGANIZATIONS','CNE_TURNOUT','CNE_ELECTORAL_ROLL_SNAPSHOT','INEC_DEMOGRAPHIC_INDICATORS','INEC_POPULATION_PROJECTIONS','INEC_GEOGRAPHIC_CLASSIFIER','OTHER_AGGREGATED_OFFICIAL')")
    op.create_table(
        "electoral_roll_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("electoral_process_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("electoral_processes.id", ondelete="RESTRICT")),
        sa.Column("snapshot_date", sa.Date(), nullable=False), sa.Column("name", sa.String(250), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text()), sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('DRAFT','IMPORTED','VALIDATED','PUBLISHED','ARCHIVED')", name="status"),
    )
    op.create_index("ix_roll_snapshots_source_id", "electoral_roll_snapshots", ["source_id"])
    op.create_index("ix_roll_snapshots_date", "electoral_roll_snapshots", ["snapshot_date"])
    op.create_table(
        "electoral_roll_snapshot_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("electoral_roll_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("geography_level", sa.String(20), nullable=False), sa.Column("province_id", sa.Integer(), sa.ForeignKey("provinces.id")), sa.Column("canton_id", sa.Integer(), sa.ForeignKey("cantons.id")), sa.Column("parish_id", sa.Integer(), sa.ForeignKey("parishes.id")),
        sa.Column("province_dpa", sa.String(2)), sa.Column("canton_dpa", sa.String(4)), sa.Column("parish_dpa", sa.String(6)),
        sa.Column("registered_voters", sa.Integer(), nullable=False), sa.Column("male_voters", sa.Integer()), sa.Column("female_voters", sa.Integer()), sa.Column("electoral_zones", sa.Integer()), sa.Column("juntas", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("geography_level IN ('PROVINCE','CANTON','PARISH')", name="level"), sa.CheckConstraint("registered_voters >= 0 AND (male_voters IS NULL OR male_voters >= 0) AND (female_voters IS NULL OR female_voters >= 0) AND (electoral_zones IS NULL OR electoral_zones >= 0) AND (juntas IS NULL OR juntas >= 0)", name="nonnegative"), sa.CheckConstraint("male_voters IS NULL OR female_voters IS NULL OR male_voters + female_voters = registered_voters", name="sexes_sum"), sa.UniqueConstraint("snapshot_id", "geography_level", "province_id", "canton_id", "parish_id", name="uq_roll_snapshot_geo"),
    )
    op.create_table(
        "participation_projection_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="RESTRICT")), sa.Column("electoral_process_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("electoral_processes.id", ondelete="RESTRICT"), nullable=False), sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("electoral_roll_snapshots.id", ondelete="RESTRICT"), nullable=False), sa.Column("model_code", sa.String(100), nullable=False), sa.Column("model_version", sa.String(30), nullable=False), sa.Column("historical_process_ids", postgresql.JSONB(), nullable=False), sa.Column("parameters", postgresql.JSONB(), nullable=False), sa.Column("run_date", sa.Date(), nullable=False), sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_projection_runs_campaign_id", "participation_projection_runs", ["campaign_id"])
    op.create_index("ix_projection_runs_snapshot_id", "participation_projection_runs", ["snapshot_id"])
    op.create_table(
        "participation_projection_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("participation_projection_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("parish_id", sa.Integer(), sa.ForeignKey("parishes.id", ondelete="RESTRICT"), nullable=False), sa.Column("registered_voters", sa.Integer(), nullable=False), sa.Column("turnout_rate_low", sa.Numeric(12, 8), nullable=False), sa.Column("turnout_rate_central", sa.Numeric(12, 8), nullable=False), sa.Column("turnout_rate_high", sa.Numeric(12, 8), nullable=False), sa.Column("expected_voters_low", sa.Integer(), nullable=False), sa.Column("expected_voters_central", sa.Integer(), nullable=False), sa.Column("expected_voters_high", sa.Integer(), nullable=False), sa.Column("data_quality_status", sa.String(30), nullable=False), sa.Column("explanation", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("registered_voters >= 0 AND expected_voters_low >= 0 AND expected_voters_central >= 0 AND expected_voters_high >= 0", name="nonnegative"), sa.CheckConstraint("expected_voters_low <= registered_voters AND expected_voters_central <= registered_voters AND expected_voters_high <= registered_voters", name="bounded"), sa.UniqueConstraint("run_id", "parish_id", name="uq_projection_run_parish"),
    )


def downgrade():
    op.drop_table("participation_projection_results"); op.drop_index("ix_projection_runs_snapshot_id", table_name="participation_projection_runs"); op.drop_index("ix_projection_runs_campaign_id", table_name="participation_projection_runs"); op.drop_table("participation_projection_runs"); op.drop_table("electoral_roll_snapshot_entries"); op.drop_index("ix_roll_snapshots_date", table_name="electoral_roll_snapshots"); op.drop_index("ix_roll_snapshots_source_id", table_name="electoral_roll_snapshots"); op.drop_table("electoral_roll_snapshots")
    op.drop_constraint("dataset_type", "data_sources", type_="check")
    op.create_check_constraint("dataset_type", "data_sources", "dataset_type IN ('CNE_ELECTORAL_RESULTS','CNE_CANDIDATES','CNE_POLITICAL_ORGANIZATIONS','CNE_TURNOUT','INEC_DEMOGRAPHIC_INDICATORS','INEC_POPULATION_PROJECTIONS','INEC_GEOGRAPHIC_CLASSIFIER','OTHER_AGGREGATED_OFFICIAL')")
