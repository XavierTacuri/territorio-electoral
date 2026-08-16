"""SaaS organizations, memberships and subscriptions V2.8.

Revision ID: 20260816_0001
Revises: 20260815_0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260816_0001"
down_revision = "20260815_0002"
branch_labels = None
depends_on = None

INITIAL_ORGANIZATION_ID = "00000000-0000-0000-0000-000000002801"


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("slug", sa.String(180), nullable=False),
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
        sa.Column("legal_name", sa.String(255)),
        sa.Column("contact_email", sa.String(320)),
        sa.Column("contact_phone", sa.String(50)),
        sa.Column("country", sa.String(2), server_default="EC", nullable=False),
        sa.Column("timezone", sa.String(80), server_default="America/Guayaquil", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','SUSPENDED','ARCHIVED')", name=op.f("ck_organizations_status")),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
    op.create_index("ix_organizations_status", "organizations", ["status"])
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("organization_role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("organization_role IN ('OWNER','ADMIN','MEMBER')", name=op.f("ck_organization_memberships_role")),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE','INVITED')", name=op.f("ck_organization_memberships_status")),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_memberships_organization_user"),
    )
    op.create_index("ix_organization_memberships_organization_status", "organization_memberships", ["organization_id", "status"])
    op.create_index("ix_organization_memberships_user_status", "organization_memberships", ["user_id", "status"])
    op.create_table(
        "organization_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("plan_code", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True)),
        sa.Column("max_campaigns", sa.Integer()),
        sa.Column("max_users", sa.Integer()),
        sa.Column("metadata", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), server_default="{}", nullable=False),
        sa.Column("external_customer_id", sa.String(255)),
        sa.Column("external_subscription_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('TRIAL','ACTIVE','PAST_DUE','SUSPENDED','EXPIRED','CANCELLED')", name=op.f("ck_organization_subscriptions_status")),
        sa.CheckConstraint("plan_code IN ('STANDARD','PRO')", name=op.f("ck_organization_subscriptions_plan_code")),
        sa.CheckConstraint("max_campaigns IS NULL OR max_campaigns > 0", name=op.f("ck_organization_subscriptions_max_campaigns_positive")),
        sa.CheckConstraint("max_users IS NULL OR max_users > 0", name=op.f("ck_organization_subscriptions_max_users_positive")),
        sa.CheckConstraint("starts_at IS NULL OR expires_at IS NULL OR starts_at < expires_at", name=op.f("ck_organization_subscriptions_validity_range")),
    )
    op.create_index("ix_organization_subscriptions_organization_status", "organization_subscriptions", ["organization_id", "status"])
    op.add_column("campaigns", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f("fk_campaigns_organization_id_organizations"), "campaigns", "organizations", ["organization_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_campaigns_organization_id", "campaigns", ["organization_id"])

    op.execute(sa.text(
        "INSERT INTO organizations (id,name,slug,status,country,timezone) "
        "VALUES (CAST(:id AS uuid),'Territorio Electoral - Organizacion principal',"
        "'organizacion-principal','ACTIVE','EC','America/Guayaquil')"
    ).bindparams(id=INITIAL_ORGANIZATION_ID))
    op.execute(sa.text("UPDATE campaigns SET organization_id=CAST(:id AS uuid) WHERE organization_id IS NULL").bindparams(id=INITIAL_ORGANIZATION_ID))
    op.alter_column("campaigns", "organization_id", nullable=False)
    op.execute(sa.text(
        "INSERT INTO organization_memberships (id,organization_id,user_id,organization_role,status) "
        "SELECT gen_random_uuid(),CAST(:id AS uuid),cu.user_id,'MEMBER','ACTIVE' "
        "FROM campaign_users cu GROUP BY cu.user_id "
        "ON CONFLICT (organization_id,user_id) DO NOTHING"
    ).bindparams(id=INITIAL_ORGANIZATION_ID))
    op.execute(sa.text(
        "INSERT INTO organization_subscriptions (id,organization_id,plan_code,status,metadata) "
        "VALUES (gen_random_uuid(),CAST(:id AS uuid),'STANDARD','ACTIVE','{}')"
    ).bindparams(id=INITIAL_ORGANIZATION_ID))


def downgrade():
    op.drop_index("ix_campaigns_organization_id", table_name="campaigns")
    op.drop_constraint(op.f("fk_campaigns_organization_id_organizations"), "campaigns", type_="foreignkey")
    op.drop_column("campaigns", "organization_id")
    op.drop_table("organization_subscriptions")
    op.drop_table("organization_memberships")
    op.drop_table("organizations")
