"""Uploaded evidence files alongside the existing external-link evidence.

Revision ID: 20260903_0001
Revises: 20260901_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_0001"
down_revision = "20260901_0001"
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column("activity_evidence", "url", existing_type=sa.String(1000), nullable=True)
    op.add_column("activity_evidence", sa.Column("storage_key", sa.String(255), nullable=True))
    op.add_column("activity_evidence", sa.Column("mime_type", sa.String(120), nullable=True))
    op.add_column("activity_evidence", sa.Column("size_bytes", sa.Integer(), nullable=True))
    op.add_column("activity_evidence", sa.Column("sha256", sa.String(64), nullable=True))
    op.add_column("activity_evidence", sa.Column("original_filename", sa.String(255), nullable=True))
    op.add_column("activity_evidence", sa.Column("client_generated_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        "url_or_storage_key", "activity_evidence", "url IS NOT NULL OR storage_key IS NOT NULL"
    )
    op.create_index(
        "uq_activity_evidence_storage_key", "activity_evidence", ["storage_key"], unique=True,
        postgresql_where=sa.text("storage_key IS NOT NULL"),
    )
    op.create_index(
        "uq_activity_evidence_client_id",
        "activity_evidence",
        ["activity_id", "uploaded_by_user_id", "client_generated_id"],
        unique=True,
        postgresql_where=sa.text("client_generated_id IS NOT NULL"),
    )

def downgrade():
    op.drop_index("uq_activity_evidence_client_id", table_name="activity_evidence")
    op.drop_index("uq_activity_evidence_storage_key", table_name="activity_evidence")
    op.drop_constraint(op.f("ck_activity_evidence_url_or_storage_key"), "activity_evidence", type_="check")
    op.drop_column("activity_evidence", "client_generated_id")
    op.drop_column("activity_evidence", "original_filename")
    op.drop_column("activity_evidence", "sha256")
    op.drop_column("activity_evidence", "size_bytes")
    op.drop_column("activity_evidence", "mime_type")
    op.drop_column("activity_evidence", "storage_key")
    op.alter_column("activity_evidence", "url", existing_type=sa.String(1000), nullable=False)
