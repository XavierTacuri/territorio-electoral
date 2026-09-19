"""Election Day Fase 1B: invitaciones de personal operativo (Delegados de
recinto / Validadores de actas). Deliberadamente NO crea ningún vínculo con
CampaignUser/OrganizationMembership/TerritorialAssignment/UserRole — el
acceso de este personal vive exclusivamente en ElectionDayAssignment.

Revision ID: 20260919_0001
Revises: 20260918_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260919_0001"
down_revision = "20260918_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "election_day_staff_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("staff_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_user_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("staff_type IN ('POLLING_PLACE_DELEGATE','ACT_VALIDATOR')", name=op.f("ck_election_day_staff_invitations_staff_type")),
        sa.CheckConstraint("status IN ('PENDING','ACCEPTED','REVOKED','EXPIRED')", name=op.f("ck_election_day_staff_invitations_status")),
        sa.CheckConstraint("(status = 'ACCEPTED') = (accepted_user_id IS NOT NULL AND accepted_at IS NOT NULL)", name=op.f("ck_election_day_staff_invitations_accepted_fields_consistent")),
        sa.CheckConstraint("(status = 'REVOKED') = (revoked_at IS NOT NULL AND revoked_by_user_id IS NOT NULL)", name=op.f("ck_election_day_staff_invitations_revoked_fields_consistent")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_election_day_staff_invitations_organization_id_organizations"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], name=op.f("fk_election_day_staff_invitations_campaign_id_campaigns"), ondelete="RESTRICT"),
        # Nombre acortado (sin sufijo de tabla referida): el nombre completo
        # excede el límite de 63 caracteres de PostgreSQL. Debe coincidir
        # exactamente con el `name=` explícito del modelo.
        sa.ForeignKeyConstraint(["operation_id"], ["election_day_operations.id"], name="fk_election_day_staff_invitations_operation_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], name=op.f("fk_election_day_staff_invitations_invited_by_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_user_id"], ["users.id"], name=op.f("fk_election_day_staff_invitations_accepted_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], name=op.f("fk_election_day_staff_invitations_revoked_by_user_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_election_day_staff_invitations")),
    )
    op.create_index("ix_election_day_staff_invitations_organization_id", "election_day_staff_invitations", ["organization_id"], unique=False)
    op.create_index("ix_election_day_staff_invitations_campaign_id", "election_day_staff_invitations", ["campaign_id"], unique=False)
    op.create_index("ix_election_day_staff_invitations_operation_id", "election_day_staff_invitations", ["operation_id"], unique=False)
    op.create_index("ix_election_day_staff_invitations_email", "election_day_staff_invitations", ["email"], unique=False)
    op.create_index("ix_election_day_staff_invitations_status", "election_day_staff_invitations", ["status"], unique=False)
    op.create_index("ix_election_day_staff_invitations_token_hash", "election_day_staff_invitations", ["token_hash"], unique=True)

    op.create_table(
        "election_day_staff_invitation_polling_places",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invitation_id", sa.Uuid(), nullable=False),
        sa.Column("polling_place_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        # Nombres acortados (sin sufijo de tabla referida / columna
        # abreviada): el nombre completo excede el límite de 63 caracteres de
        # PostgreSQL. Deben coincidir exactamente con los `name=` explícitos
        # del modelo.
        sa.ForeignKeyConstraint(["invitation_id"], ["election_day_staff_invitations.id"], name="fk_election_day_staff_invitation_polling_places_invitation_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["polling_place_id"], ["polling_places.id"], name="fk_election_day_staff_invitation_polling_places_place_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_election_day_staff_invitation_polling_places")),
        sa.UniqueConstraint("invitation_id", "polling_place_id", name="uq_election_day_staff_invitation_polling_places_pair"),
    )
    op.create_index("ix_election_day_staff_invitation_polling_places_invitation_id", "election_day_staff_invitation_polling_places", ["invitation_id"], unique=False)
    op.create_index("ix_election_day_staff_invitation_polling_places_place_id", "election_day_staff_invitation_polling_places", ["polling_place_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_election_day_staff_invitation_polling_places_place_id", table_name="election_day_staff_invitation_polling_places")
    op.drop_index("ix_election_day_staff_invitation_polling_places_invitation_id", table_name="election_day_staff_invitation_polling_places")
    op.drop_table("election_day_staff_invitation_polling_places")

    op.drop_index("ix_election_day_staff_invitations_token_hash", table_name="election_day_staff_invitations")
    op.drop_index("ix_election_day_staff_invitations_status", table_name="election_day_staff_invitations")
    op.drop_index("ix_election_day_staff_invitations_email", table_name="election_day_staff_invitations")
    op.drop_index("ix_election_day_staff_invitations_operation_id", table_name="election_day_staff_invitations")
    op.drop_index("ix_election_day_staff_invitations_campaign_id", table_name="election_day_staff_invitations")
    op.drop_index("ix_election_day_staff_invitations_organization_id", table_name="election_day_staff_invitations")
    op.drop_table("election_day_staff_invitations")
