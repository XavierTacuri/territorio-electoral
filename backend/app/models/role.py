from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from app.db.base import Base
from app.models.user_role import UserRole
if TYPE_CHECKING:
    from app.models.user import User


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (Index("ix_roles_code", "code", unique=True), Index("ix_roles_name", "name", unique=True))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    users: Mapped[list["User"]] = relationship(secondary=UserRole.__table__, back_populates="roles", lazy="selectin")

    @validates("code")
    def normalize_code(self, _key: str, value: str) -> str:
        return value.strip().upper()

    @validates("name")
    def normalize_name(self, _key: str, value: str) -> str:
        return value.strip()
