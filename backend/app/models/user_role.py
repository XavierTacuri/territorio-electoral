from uuid import UUID
from sqlalchemy import ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True)
