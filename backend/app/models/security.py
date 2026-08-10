from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_family_id", "family_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
        Index("ix_auth_sessions_revoked_at", "revoked_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("auth_sessions.id", ondelete="SET NULL"))
    revocation_reason: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class SecurityAuditEvent(Base):
    __tablename__ = "security_audit_events"
    __table_args__ = (
        Index("ix_security_audit_events_event_date", "event_date"),
        Index("ix_security_audit_events_user_id", "user_id"),
        Index("ix_security_audit_events_campaign_id", "campaign_id"),
        Index("ix_security_audit_events_event_type", "event_type"),
        Index("ix_security_audit_events_outcome", "outcome"),
        Index("ix_security_audit_events_resource", "resource_type", "resource_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    campaign_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
