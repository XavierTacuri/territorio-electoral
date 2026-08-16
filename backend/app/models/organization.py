from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','SUSPENDED','ARCHIVED')", name="status"),
        Index("ix_organizations_slug", "slug", unique=True),
        Index("ix_organizations_status", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE")
    legal_name: Mapped[str | None] = mapped_column(String(255))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="EC", server_default="EC")
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Guayaquil", server_default="America/Guayaquil")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_memberships_organization_user"),
        CheckConstraint("organization_role IN ('OWNER','ADMIN','MEMBER')", name="role"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE','INVITED')", name="status"),
        Index("ix_organization_memberships_organization_status", "organization_id", "status"),
        Index("ix_organization_memberships_user_status", "user_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    organization_role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class OrganizationSubscription(Base):
    __tablename__ = "organization_subscriptions"
    __table_args__ = (
        CheckConstraint("status IN ('TRIAL','ACTIVE','PAST_DUE','SUSPENDED','EXPIRED','CANCELLED')", name="status"),
        CheckConstraint("plan_code IN ('STANDARD','PRO')", name="plan_code"),
        CheckConstraint("max_campaigns IS NULL OR max_campaigns > 0", name="max_campaigns_positive"),
        CheckConstraint("max_users IS NULL OR max_users > 0", name="max_users_positive"),
        CheckConstraint("starts_at IS NULL OR expires_at IS NULL OR starts_at < expires_at", name="validity_range"),
        Index("ix_organization_subscriptions_organization_status", "organization_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    plan_code: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_campaigns: Mapped[int | None] = mapped_column(Integer)
    max_users: Mapped[int | None] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column("metadata", JSON_VALUE, nullable=False, default=dict, server_default="{}")
    external_customer_id: Mapped[str | None] = mapped_column(String(255))
    external_subscription_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
