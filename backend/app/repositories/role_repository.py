from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.role import Role


class RoleRepository:
    def __init__(self, db: Session): self.db = db
    def get_by_id(self, role_id: int) -> Role | None: return self.db.get(Role, role_id)
    def get_by_code(self, code: str) -> Role | None: return self.db.scalar(select(Role).where(Role.code == code.strip().upper()))
    def get_by_codes(self, codes: list[str]) -> list[Role]:
        normalized = list(dict.fromkeys(code.strip().upper() for code in codes))
        return list(self.db.scalars(select(Role).where(Role.code.in_(normalized))).all())
    def list(self, active_only: bool = True) -> list[Role]:
        statement = select(Role).order_by(Role.code)
        if active_only: statement = statement.where(Role.is_active.is_(True))
        return list(self.db.scalars(statement).all())
    def create(self, code: str, name: str, description: str | None = None) -> Role:
        role = Role(code=code, name=name, description=description)
        self.db.add(role)
        return role
