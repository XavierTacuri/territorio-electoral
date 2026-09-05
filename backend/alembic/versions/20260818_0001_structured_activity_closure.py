"""Store structured completion and cancellation details for activities."""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0001"
down_revision = "20260816_0002"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("territorial_activities", sa.Column("completion_summary", sa.Text(), nullable=True))
    op.add_column("territorial_activities", sa.Column("outcome_notes", sa.Text(), nullable=True))
    op.add_column("territorial_activities", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("territorial_activities", sa.Column("completed_by_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_activity_completed_by", "territorial_activities", "users", ["completed_by_user_id"], ["id"], ondelete="SET NULL")
    op.add_column("territorial_activities", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.add_column("territorial_activities", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("territorial_activities", sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_activity_cancelled_by", "territorial_activities", "users", ["cancelled_by_user_id"], ["id"], ondelete="SET NULL")

def downgrade():
    op.drop_constraint("fk_activity_cancelled_by", "territorial_activities", type_="foreignkey")
    op.drop_column("territorial_activities", "cancelled_by_user_id")
    op.drop_column("territorial_activities", "cancelled_at")
    op.drop_column("territorial_activities", "cancellation_reason")
    op.drop_constraint("fk_activity_completed_by", "territorial_activities", type_="foreignkey")
    op.drop_column("territorial_activities", "completed_by_user_id")
    op.drop_column("territorial_activities", "completed_at")
    op.drop_column("territorial_activities", "outcome_notes")
    op.drop_column("territorial_activities", "completion_summary")
