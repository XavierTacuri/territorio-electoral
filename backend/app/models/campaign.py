from datetime import date, datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (CheckConstraint("office_type IN ('MAYOR','URBAN_COUNCILOR','RURAL_COUNCILOR','PARISH_BOARD')", name="office_type"), CheckConstraint("status IN ('DRAFT','ACTIVE','COMPLETED','ARCHIVED')", name="status"), CheckConstraint("start_date IS NULL OR end_date IS NULL OR start_date <= end_date", name="date_range"), CheckConstraint("start_date IS NULL OR election_date >= start_date", name="election_after_start"), Index("ix_campaigns_slug", "slug", unique=True), Index("ix_campaigns_canton_id", "canton_id"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    canton_id: Mapped[int] = mapped_column(ForeignKey("cantons.id", ondelete="RESTRICT"), nullable=False)
    office_type: Mapped[str] = mapped_column(String(30), nullable=False)
    election_name: Mapped[str] = mapped_column(String(180), nullable=False)
    election_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
