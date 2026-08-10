from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4
from sqlalchemy import Boolean, DateTime, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from app.db.base import Base
from app.models.user_role import UserRole
if TYPE_CHECKING:
    from app.models.role import Role


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True), Index("ix_users_username", "username", unique=True))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    roles: Mapped[list["Role"]] = relationship(secondary=UserRole.__table__, back_populates="users", lazy="selectin")

    @validates("email", "username")
    def normalize_identifier(self, _key: str, value: str) -> str:
        return value.strip().lower()
