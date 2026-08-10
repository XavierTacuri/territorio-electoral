"""browser auth sessions and security audit

Revision ID: b10a10c2026
Revises: 88caa938c6b8
Create Date: 2026-08-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b10a10c2026"
down_revision: Union[str, None] = "88caa938c6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_session_id", sa.Uuid(), nullable=True),
        sa.Column("revocation_reason", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["replaced_by_session_id"], ["auth_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_family_id", "auth_sessions", ["family_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_index("ix_auth_sessions_revoked_at", "auth_sessions", ["revoked_at"])
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_audit_events_event_date", "security_audit_events", ["event_date"])
    op.create_index("ix_security_audit_events_user_id", "security_audit_events", ["user_id"])
    op.create_index("ix_security_audit_events_campaign_id", "security_audit_events", ["campaign_id"])
    op.create_index("ix_security_audit_events_event_type", "security_audit_events", ["event_type"])
    op.create_index("ix_security_audit_events_outcome", "security_audit_events", ["outcome"])
    op.create_index("ix_security_audit_events_resource", "security_audit_events", ["resource_type", "resource_id"])


def downgrade() -> None:
    op.drop_index("ix_security_audit_events_resource", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_outcome", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_event_type", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_campaign_id", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_user_id", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_event_date", table_name="security_audit_events")
    op.drop_table("security_audit_events")
    op.drop_index("ix_auth_sessions_revoked_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_family_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_column("users", "token_version")
