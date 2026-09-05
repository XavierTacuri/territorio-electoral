"""Dataset version ledger for the official-data Centro de datos admin layer.

Revision ID: 20260904_0001
Revises: 20260903_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260904_0001"
down_revision = "20260903_0001"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_type", sa.String(length=50), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("version_label", sa.String(length=150), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("import_job_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="VALIDATED"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT','VALIDATED','ACTIVE','SUPERSEDED','REJECTED','ARCHIVED')",
            name=op.f("ck_dataset_versions_status"),
        ),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], name=op.f("fk_dataset_versions_data_source_id_data_sources"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_job_id"], ["data_import_jobs.id"], name=op.f("fk_dataset_versions_import_job_id_data_import_jobs"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], name=op.f("fk_dataset_versions_activated_by_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["dataset_versions.id"], name=op.f("fk_dataset_versions_superseded_by_id_dataset_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_versions")),
    )
    op.create_index("ix_dataset_versions_source_id", "dataset_versions", ["data_source_id"])
    op.create_index("ix_dataset_versions_dataset_type", "dataset_versions", ["dataset_type"])
    op.create_index("ix_dataset_versions_import_job_id", "dataset_versions", ["import_job_id"], unique=True)
    op.create_index(
        "ix_dataset_versions_active_scope",
        "dataset_versions",
        ["data_source_id", "dataset_type"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

def downgrade():
    op.drop_index("ix_dataset_versions_active_scope", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_import_job_id", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_dataset_type", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_source_id", table_name="dataset_versions")
    op.drop_table("dataset_versions")
