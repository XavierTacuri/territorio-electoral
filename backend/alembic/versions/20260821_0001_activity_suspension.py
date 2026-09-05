"""Add the distinct suspended activity state and its audit fields."""
from alembic import op
import sqlalchemy as sa

revision = "20260821_0001"
down_revision = "20260818_0001"
branch_labels = None
depends_on = None

def upgrade():
    op.drop_constraint(op.f("ck_territorial_activities_status"), "territorial_activities", type_="check")
    op.create_check_constraint("status", "territorial_activities", "status IN ('PLANNED','IN_PROGRESS','COMPLETED','SUSPENDED','CANCELLED')")
    op.add_column("territorial_activities", sa.Column("suspension_reason", sa.Text(), nullable=True))
    op.add_column("territorial_activities", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("territorial_activities", sa.Column("suspended_by_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_activity_suspended_by", "territorial_activities", "users", ["suspended_by_user_id"], ["id"], ondelete="SET NULL")

def downgrade():
    op.execute("UPDATE territorial_activities SET status='CANCELLED' WHERE status='SUSPENDED'")
    op.drop_constraint("fk_activity_suspended_by", "territorial_activities", type_="foreignkey")
    op.drop_column("territorial_activities", "suspended_by_user_id")
    op.drop_column("territorial_activities", "suspended_at")
    op.drop_column("territorial_activities", "suspension_reason")
    op.drop_constraint(op.f("ck_territorial_activities_status"), "territorial_activities", type_="check")
    op.create_check_constraint("status", "territorial_activities", "status IN ('PLANNED','IN_PROGRESS','COMPLETED','CANCELLED')")
