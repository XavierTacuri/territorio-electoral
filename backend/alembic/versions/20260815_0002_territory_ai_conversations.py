"""territory ai conversations

Revision ID: 20260815_0002
Revises: 20260815_0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="20260815_0002";down_revision="20260815_0001";branch_labels=None;depends_on=None
def upgrade():
    op.create_table("territory_ai_conversations",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("campaign_id",sa.Uuid(),sa.ForeignKey("campaigns.id",ondelete="RESTRICT"),nullable=False),sa.Column("user_id",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),sa.Column("title",sa.String(180),nullable=False),sa.Column("last_intent",sa.String(50)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_territory_ai_conversations_campaign_user","territory_ai_conversations",["campaign_id","user_id"])
    op.create_table("territory_ai_messages",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("conversation_id",sa.Uuid(),sa.ForeignKey("territory_ai_conversations.id",ondelete="CASCADE"),nullable=False),sa.Column("role",sa.String(20),nullable=False),sa.Column("content",sa.Text(),nullable=False),sa.Column("citations",sa.JSON().with_variant(postgresql.JSONB(),"postgresql"),server_default="[]",nullable=False),sa.Column("intent",sa.String(50)),sa.Column("territory_id",sa.Integer(),sa.ForeignKey("parishes.id",ondelete="SET NULL")),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.CheckConstraint("role IN ('USER','ASSISTANT')",name=op.f("ck_territory_ai_messages_role")))
    op.create_index("ix_territory_ai_messages_conversation","territory_ai_messages",["conversation_id","created_at"])
def downgrade():op.drop_table("territory_ai_messages");op.drop_table("territory_ai_conversations")
