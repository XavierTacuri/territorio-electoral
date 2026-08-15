"""generic campaign feature entitlements and AI usage

Revision ID: 20260815_0001
Revises: 20260814_0002
"""
from alembic import op
import sqlalchemy as sa
revision="20260815_0001";down_revision="20260814_0002";branch_labels=None;depends_on=None
def upgrade():
    op.create_table("campaign_feature_entitlements",
        sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("campaign_id",sa.Uuid(),sa.ForeignKey("campaigns.id",ondelete="CASCADE"),nullable=False),
        sa.Column("feature_code",sa.String(80),nullable=False),sa.Column("enabled",sa.Boolean(),server_default="true",nullable=False),sa.Column("entitlement_type",sa.String(30),nullable=False),
        sa.Column("starts_at",sa.DateTime(timezone=True)),sa.Column("expires_at",sa.DateTime(timezone=True)),sa.Column("monthly_request_limit",sa.Integer()),sa.Column("monthly_token_limit",sa.Integer()),
        sa.Column("created_by_user_id",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),sa.Column("updated_by_user_id",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint("campaign_id","feature_code",name="uq_campaign_feature_entitlements_campaign_feature"),sa.CheckConstraint("entitlement_type IN ('LICENSE','TRIAL','ADMIN_OVERRIDE')",name=op.f("ck_campaign_feature_entitlements_entitlement_type")),sa.CheckConstraint("starts_at IS NULL OR expires_at IS NULL OR starts_at < expires_at",name=op.f("ck_campaign_feature_entitlements_validity_range")))
    op.create_index("ix_campaign_feature_entitlements_campaign","campaign_feature_entitlements",["campaign_id"]);op.create_index("ix_campaign_feature_entitlements_feature","campaign_feature_entitlements",["feature_code"])
    op.create_table("ai_usage_events",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("campaign_id",sa.Uuid(),sa.ForeignKey("campaigns.id",ondelete="RESTRICT"),nullable=False),sa.Column("user_id",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),sa.Column("provider",sa.String(80),nullable=False),sa.Column("model",sa.String(120),nullable=False),sa.Column("input_tokens",sa.Integer()),sa.Column("output_tokens",sa.Integer()),sa.Column("request_count",sa.Integer(),server_default="1",nullable=False),sa.Column("timestamp",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_ai_usage_campaign_timestamp","ai_usage_events",["campaign_id","timestamp"])
def downgrade():
    op.drop_table("ai_usage_events");op.drop_table("campaign_feature_entitlements")
