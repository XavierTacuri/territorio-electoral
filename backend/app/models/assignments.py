from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class CampaignUser(Base):
    __tablename__ = "campaign_users"
    __table_args__ = (UniqueConstraint("campaign_id", "user_id", name="uq_campaign_users_campaign_user"), Index("ix_campaign_users_campaign_id", "campaign_id"), Index("ix_campaign_users_user_id", "user_id"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    assigned_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class TerritorialAssignment(Base):
    __tablename__ = "territorial_assignments"
    __table_args__ = (UniqueConstraint("campaign_id", "user_id", "parish_id", "community_id", "sector_id", name="uq_territorial_assignment_scope"), CheckConstraint("sector_id IS NULL OR community_id IS NOT NULL", name="sector_requires_community"), Index("ix_territorial_assignments_campaign_id", "campaign_id"), Index("ix_territorial_assignments_user_id", "user_id"), Index("ix_territorial_assignments_parish_id", "parish_id"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    parish_id: Mapped[int] = mapped_column(ForeignKey("parishes.id", ondelete="RESTRICT"), nullable=False)
    community_id: Mapped[UUID | None] = mapped_column(ForeignKey("communities.id", ondelete="RESTRICT"))
    sector_id: Mapped[UUID | None] = mapped_column(ForeignKey("sectors.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    assigned_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
