"""Official electoral milestones for the calendar read-model.

Revision ID: 20260905_0001
Revises: 20260904_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260905_0001"
down_revision = "20260904_0001"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "electoral_milestones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("electoral_process_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("milestone_type", sa.String(length=30), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("import_job_id", sa.Uuid(), nullable=True),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=True),
        sa.Column("is_official", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "milestone_type IN ('CONVOCATORIA','CANDIDATE_REGISTRATION','CAMPAIGN_PERIOD','DEBATE','ELECTORAL_SILENCE','ELECTION_DAY','VOTE_COUNT','OTHER')",
            name=op.f("ck_electoral_milestones_milestone_type"),
        ),
        sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name=op.f("ck_electoral_milestones_status")),
        sa.ForeignKeyConstraint(["electoral_process_id"], ["electoral_processes.id"], name=op.f("fk_electoral_milestones_electoral_process_id_electoral_processes"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], name=op.f("fk_electoral_milestones_source_id_data_sources"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_job_id"], ["data_import_jobs.id"], name=op.f("fk_electoral_milestones_import_job_id_data_import_jobs"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], name=op.f("fk_electoral_milestones_dataset_version_id_dataset_versions"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_electoral_milestones_created_by_user_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_electoral_milestones")),
    )
    op.create_index("ix_electoral_milestones_process_id", "electoral_milestones", ["electoral_process_id"])
    op.create_index("ix_electoral_milestones_starts_at", "electoral_milestones", ["starts_at"])
    op.create_index("ix_electoral_milestones_status", "electoral_milestones", ["status"])
    op.create_index(
        "uq_electoral_milestones_identity",
        "electoral_milestones",
        ["electoral_process_id", "milestone_type", "starts_at", "title"],
        unique=True,
    )

def downgrade():
    op.drop_index("uq_electoral_milestones_identity", table_name="electoral_milestones")
    op.drop_index("ix_electoral_milestones_status", table_name="electoral_milestones")
    op.drop_index("ix_electoral_milestones_starts_at", table_name="electoral_milestones")
    op.drop_index("ix_electoral_milestones_process_id", table_name="electoral_milestones")
    op.drop_table("electoral_milestones")
