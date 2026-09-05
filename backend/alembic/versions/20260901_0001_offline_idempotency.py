"""Client-generated idempotency keys for offline-created activities and needs.

Revision ID: 20260901_0001
Revises: 20260830_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260901_0001"
down_revision = "20260830_0001"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("territorial_activities", sa.Column("client_generated_id", sa.Uuid(), nullable=True))
    op.create_index(
        "uq_territorial_activities_client_id",
        "territorial_activities",
        ["campaign_id", "created_by_user_id", "client_generated_id"],
        unique=True,
        postgresql_where=sa.text("client_generated_id IS NOT NULL"),
    )
    op.add_column("citizen_needs", sa.Column("client_generated_id", sa.Uuid(), nullable=True))
    op.create_index(
        "uq_citizen_needs_client_id",
        "citizen_needs",
        ["campaign_id", "created_by_user_id", "client_generated_id"],
        unique=True,
        postgresql_where=sa.text("client_generated_id IS NOT NULL"),
    )

def downgrade():
    op.drop_index("uq_citizen_needs_client_id", table_name="citizen_needs")
    op.drop_column("citizen_needs", "client_generated_id")
    op.drop_index("uq_territorial_activities_client_id", table_name="territorial_activities")
    op.drop_column("territorial_activities", "client_generated_id")
