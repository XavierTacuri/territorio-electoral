from uuid import UUID
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from app.models.role import Role
from app.models.user import User


class UserRepository:
    def __init__(self, db: Session): self.db = db
    def _loaded(self): return select(User).options(selectinload(User.roles))
    def get_by_id(self, user_id: UUID) -> User | None: return self.db.scalar(self._loaded().where(User.id == user_id))
    def get_by_email(self, email: str) -> User | None: return self.db.scalar(self._loaded().where(User.email == email.strip().lower()))
    def get_by_username(self, username: str) -> User | None: return self.db.scalar(self._loaded().where(User.username == username.strip().lower()))
    def get_by_identifier(self, value: str) -> User | None:
        normalized = value.strip().lower()
        return self.db.scalar(self._loaded().where(or_(User.username == normalized, User.email == normalized)))
    def create(self, **values: object) -> User:
        user = User(**values); self.db.add(user); return user
    def list(self, page: int, page_size: int, search: str | None = None, is_active: bool | None = None, role_code: str | None = None) -> tuple[list[User], int]:
        filters = []
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(or_(func.lower(User.first_name).like(term), func.lower(User.last_name).like(term), User.email.like(term), User.username.like(term)))
        if is_active is not None: filters.append(User.is_active.is_(is_active))
        if role_code: filters.append(User.roles.any(Role.code == role_code.strip().upper()))
        total = self.db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
        statement = self._loaded().where(*filters).order_by(User.username, User.id).offset((page - 1) * page_size).limit(page_size)
        return list(self.db.scalars(statement).all()), total
    def count_active_admins(self) -> int:
        return self.db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True), or_(User.is_superuser.is_(True), User.roles.any(Role.code == "ADMIN")))) or 0
