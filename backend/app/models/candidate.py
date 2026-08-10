from datetime import date, datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (CheckConstraint("birth_date IS NULL OR birth_date <= CURRENT_DATE", name="birth_not_future"), Index("ix_candidates_campaign_id", "campaign_id", unique=True), Index("ix_candidates_user_id", "user_id", unique=True))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    birth_date: Mapped[date | None] = mapped_column(Date)
    political_organization: Mapped[str | None] = mapped_column(String(180))
    list_number: Mapped[int | None] = mapped_column(Integer)
    biography: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
